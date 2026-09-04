"""Resumable immutable model staging, validation, activation, and rollback."""

from __future__ import annotations

import json
import os
import sys
import threading
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol
from uuid import uuid4

from videocaptioner.config import MODEL_PATH

from .models import (
    DEFAULT_VIENEU_MODEL_REPO,
    VieNeuModelState,
    sanitize_error,
    utc_now_iso,
    validate_relative_reference,
    validate_revision,
)
from .runtime_manager import (
    VieNeuRuntimeLaunchConfig,
    VieNeuRuntimeManager,
)


class VieNeuModelUpdateError(RuntimeError):
    pass


class VieNeuDownloadCancelled(VieNeuModelUpdateError):
    pass


@dataclass(frozen=True)
class VieNeuModelPaths:
    root: Path
    state_file: Path
    hf_cache: Path
    candidates: Path
    rejected: Path

    @classmethod
    def under(cls, root: str | Path | None = None) -> "VieNeuModelPaths":
        model_root = Path(root) if root else MODEL_PATH / "vieneu"
        return cls(
            root=model_root,
            state_file=model_root / "state.json",
            hf_cache=model_root / "hf",
            candidates=model_root / "candidates",
            rejected=model_root / "rejected",
        )

    def ensure(self) -> None:
        for path in (self.root, self.hf_cache, self.candidates, self.rejected):
            path.mkdir(parents=True, exist_ok=True)


class VieNeuStateStore:
    def __init__(self, paths: VieNeuModelPaths | None = None):
        self.paths = paths or VieNeuModelPaths.under()
        self.paths.ensure()

    def load(self) -> VieNeuModelState:
        if not self.paths.state_file.is_file():
            return VieNeuModelState()
        try:
            payload = json.loads(self.paths.state_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise VieNeuModelUpdateError(f"VieNeu model state is corrupt: {sanitize_error(exc)}") from exc
        return VieNeuModelState.from_dict(payload)

    def save(self, state: VieNeuModelState) -> None:
        state.validate()
        self.paths.ensure()
        temp = self.paths.state_file.parent / (
            f".{self.paths.state_file.name}.{os.getpid()}.{uuid4().hex}.tmp"
        )
        try:
            with temp.open("w", encoding="utf-8", newline="\n") as handle:
                json.dump(state.to_dict(), handle, ensure_ascii=False, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp, self.paths.state_file)
        finally:
            temp.unlink(missing_ok=True)

    def relative_snapshot(self, snapshot: str | Path) -> str:
        resolved = Path(snapshot).resolve()
        try:
            relative = resolved.relative_to(self.paths.root.resolve()).as_posix()
        except ValueError as exc:
            raise VieNeuModelUpdateError(
                "Managed VieNeu snapshots must stay under AppData/models/vieneu"
            ) from exc
        return validate_relative_reference(relative)

    def resolve_snapshot(self, reference: str) -> Path:
        reference = validate_relative_reference(reference)
        return (self.paths.root / reference).resolve() if reference else Path()


class VieNeuHubClient(Protocol):
    def remote_revision(self, repository_id: str) -> str: ...

    def snapshot_download(
        self,
        repository_id: str,
        revision: str,
        cache_dir: Path,
        *,
        progress_callback: Callable[[int, int, str], None] | None = None,
        cancel_event: threading.Event | None = None,
    ) -> Path: ...


class HuggingFaceVieNeuClient:
    """Lazy import keeps Hugging Face/network code out of GUI module import paths."""

    def remote_revision(self, repository_id: str) -> str:
        from huggingface_hub import HfApi

        info = HfApi().model_info(repository_id, timeout=10)
        revision = str(info.sha or "")
        return validate_revision(revision, allow_empty=False)

    def snapshot_download(
        self,
        repository_id: str,
        revision: str,
        cache_dir: Path,
        *,
        progress_callback: Callable[[int, int, str], None] | None = None,
        cancel_event: threading.Event | None = None,
    ) -> Path:
        from huggingface_hub import constants as hf_constants
        from huggingface_hub import snapshot_download
        from tqdm.auto import tqdm

        if sys.platform == "win32":
            # huggingface_hub probes symlink support lazily per cache dir; with
            # several download threads a second thread can pass the probe before
            # it finishes and hit WinError 1314 on machines without the symlink
            # privilege. Windows caches are always materialised as plain files.
            os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS", "1")
            hf_constants.HF_HUB_DISABLE_SYMLINKS = True

        class ProgressTqdm(tqdm):
            def update(self, value=1):
                result = super().update(value)
                if cancel_event and cancel_event.is_set():
                    raise VieNeuDownloadCancelled(
                        "VieNeu download cancelled; partial files remain resumable"
                    )
                if progress_callback:
                    progress_callback(int(self.n), int(self.total or 0), str(self.desc or ""))
                return result

        path = snapshot_download(
            repo_id=repository_id,
            revision=validate_revision(revision, allow_empty=False),
            cache_dir=str(cache_dir),
            local_files_only=False,
            tqdm_class=ProgressTqdm,
        )
        return Path(path).resolve()


@dataclass(frozen=True)
class VieNeuUpdateCheck:
    status: str
    active_revision: str
    remote_revision: str = ""
    message: str = ""


class VieNeuCandidateValidator:
    def __init__(self, manager: VieNeuRuntimeManager):
        self.manager = manager

    @staticmethod
    def _validate_wav(data: bytes, expected_sample_rate: int) -> None:
        import io

        try:
            with wave.open(io.BytesIO(data), "rb") as wav:
                sample_rate = wav.getframerate()
                frames = wav.getnframes()
                channels = wav.getnchannels()
                sample_width = wav.getsampwidth()
        except (wave.Error, EOFError, OSError) as exc:
            raise VieNeuModelUpdateError("Candidate returned undecodable WAV audio") from exc
        if sample_rate != expected_sample_rate:
            raise VieNeuModelUpdateError(
                f"Candidate WAV sample rate {sample_rate} != expected {expected_sample_rate}"
            )
        duration = frames / sample_rate if sample_rate > 0 else 0.0
        if channels < 1 or sample_width not in {1, 2, 3, 4} or not 0.05 <= duration <= 15.0:
            raise VieNeuModelUpdateError("Candidate WAV shape/duration is unreasonable")

    def validate(
        self,
        config: VieNeuRuntimeLaunchConfig,
        *,
        cancel_event: threading.Event | None = None,
    ):
        identity = self.manager.ensure_ready(config, cancel_event=cancel_event)
        voices_payload = self.manager.get_json("voices", timeout=15)
        voices = voices_payload.get("voices") or voices_payload.get("data") or []
        if not isinstance(voices, list) or not voices:
            raise VieNeuModelUpdateError("Candidate returned an empty voice list")
        first = voices[0]
        voice = first.get("id") if isinstance(first, dict) else str(first)
        audio, content_type = self.manager.post_bytes(
            "audio/speech",
            {
                "model": identity.model_revision,
                "input": "Xin chào.",
                "voice": voice,
                "response_format": "wav",
                "speed": 1.0,
            },
            timeout=180,
        )
        if "wav" not in content_type.casefold() and "wave" not in content_type.casefold():
            raise VieNeuModelUpdateError(
                f"Candidate returned unexpected audio content type: {content_type}"
            )
        self._validate_wav(audio, identity.sample_rate)
        return identity


class VieNeuModelUpdater:
    def __init__(
        self,
        *,
        store: VieNeuStateStore | None = None,
        hub: VieNeuHubClient | None = None,
    ):
        self.store = store or VieNeuStateStore()
        self.hub = hub or HuggingFaceVieNeuClient()
        self._lock = threading.RLock()

    def status(self) -> VieNeuModelState:
        return self.store.load()

    def provision_dependencies(
        self,
        *,
        tokenizer_repository: str,
        tokenizer_revision: str,
        codec_repository: str,
        codec_revision: str,
        cancel_event: threading.Event | None = None,
        progress_callback: Callable[[int, int, str], None] | None = None,
    ) -> VieNeuModelState:
        """Provision runtime-pinned tokenizer/codec snapshots without following main."""
        tokenizer_revision = validate_revision(tokenizer_revision, allow_empty=False)
        codec_revision = validate_revision(codec_revision, allow_empty=False)
        with self._lock:
            state = self.store.load()
            downloaded: dict[tuple[str, str], Path] = {}
            for repository, revision in {
                (tokenizer_repository, tokenizer_revision),
                (codec_repository, codec_revision),
            }:
                if cancel_event and cancel_event.is_set():
                    raise VieNeuDownloadCancelled(
                        "VieNeu dependency download cancelled; partial files remain resumable"
                    )
                downloaded[(repository, revision)] = self.hub.snapshot_download(
                    repository,
                    revision,
                    self.store.paths.hf_cache,
                    progress_callback=progress_callback,
                    cancel_event=cancel_event,
                )
            state.tokenizer_repository = tokenizer_repository
            state.tokenizer_revision = tokenizer_revision
            state.tokenizer_snapshot = self.store.relative_snapshot(
                downloaded[(tokenizer_repository, tokenizer_revision)]
            )
            state.codec_repository = codec_repository
            state.codec_revision = codec_revision
            state.codec_snapshot = self.store.relative_snapshot(
                downloaded[(codec_repository, codec_revision)]
            )
            state.last_download_at = utc_now_iso()
            state.last_error = ""
            self.store.save(state)
            return state

    def check_for_update(self, *, manual_retry_rejected: bool = False) -> VieNeuUpdateCheck:
        with self._lock:
            state = self.store.load()
            try:
                remote = self.hub.remote_revision(state.repository_id)
                state.last_check_at = utc_now_iso()
                state.last_error = ""
                if remote == state.active_revision:
                    result = VieNeuUpdateCheck("current", state.active_revision, remote)
                elif remote in state.rejected_revisions and not manual_retry_rejected:
                    result = VieNeuUpdateCheck(
                        "rejected",
                        state.active_revision,
                        remote,
                        "Latest revision was previously rejected; manual retry is available",
                    )
                else:
                    result = VieNeuUpdateCheck("available", state.active_revision, remote)
            except Exception as exc:
                state.last_check_at = utc_now_iso()
                state.last_error = sanitize_error(exc)
                result = VieNeuUpdateCheck(
                    "offline",
                    state.active_revision,
                    "",
                    "Remote check unavailable; active model remains usable",
                )
            self.store.save(state)
            return result

    def stage_revision(
        self,
        revision: str,
        *,
        cancel_event: threading.Event | None = None,
        manual_retry_rejected: bool = False,
        progress_callback: Callable[[int, int, str], None] | None = None,
    ) -> Path:
        revision = validate_revision(revision, allow_empty=False)
        with self._lock:
            state = self.store.load()
            if revision in state.rejected_revisions and not manual_retry_rejected:
                raise VieNeuModelUpdateError(
                    "Revision was rejected previously; use manual retry to stage it again"
                )
            if cancel_event and cancel_event.is_set():
                raise VieNeuDownloadCancelled("VieNeu model download cancelled before start")
            state.candidate_revision = revision
            state.candidate_snapshot = ""
            state.last_error = ""
            self.store.save(state)
            try:
                snapshot = self.hub.snapshot_download(
                    state.repository_id,
                    revision,
                    self.store.paths.hf_cache,
                    progress_callback=progress_callback,
                    cancel_event=cancel_event,
                )
                if cancel_event and cancel_event.is_set():
                    raise VieNeuDownloadCancelled(
                        "VieNeu model download cancelled; partial files remain resumable"
                    )
                relative = self.store.relative_snapshot(snapshot)
                state = self.store.load()
                state.candidate_revision = revision
                state.candidate_snapshot = relative
                state.last_download_at = utc_now_iso()
                state.last_error = ""
                self.store.save(state)
                return snapshot
            except VieNeuDownloadCancelled:
                raise
            except Exception as exc:
                state = self.store.load()
                state.last_error = sanitize_error(exc)
                self.store.save(state)
                raise VieNeuModelUpdateError(
                    f"VieNeu candidate download failed: {sanitize_error(exc)}"
                ) from exc

    def validate_and_activate(
        self,
        manager: VieNeuRuntimeManager,
        config_factory: Callable[[Path, str], VieNeuRuntimeLaunchConfig],
        *,
        cancel_event: threading.Event | None = None,
    ):
        with self._lock:
            state = self.store.load()
            if not state.candidate_revision or not state.candidate_snapshot:
                raise VieNeuModelUpdateError("No complete VieNeu candidate is staged")
            if manager.active_jobs:
                return "deferred"
            candidate_revision = state.candidate_revision
            candidate_snapshot = self.store.resolve_snapshot(state.candidate_snapshot)
            validator = VieNeuCandidateValidator(manager)
            try:
                identity = validator.validate(
                    config_factory(candidate_snapshot, candidate_revision),
                    cancel_event=cancel_event,
                )
                state = self.store.load()
                state.previous_revision = state.active_revision
                state.previous_snapshot = state.active_snapshot
                state.active_revision = candidate_revision
                state.active_snapshot = state.candidate_snapshot
                state.candidate_revision = ""
                state.candidate_snapshot = ""
                state.active_backend = identity.backend
                state.runtime_version = identity.runtime_version
                state.last_validation_at = utc_now_iso()
                state.last_activation_at = utc_now_iso()
                state.last_error = ""
                state.rejected_revisions.pop(candidate_revision, None)
                self.store.save(state)
                return identity
            except Exception as exc:
                manager.shutdown(force=True)
                state = self.store.load()
                state.reject(candidate_revision, exc)
                state.last_validation_at = utc_now_iso()
                self.store.save(state)
                if state.active_revision and state.active_snapshot:
                    try:
                        manager.ensure_ready(
                            config_factory(
                                self.store.resolve_snapshot(state.active_snapshot),
                                state.active_revision,
                            )
                        )
                    except Exception as rollback_exc:
                        state = self.store.load()
                        state.last_error = sanitize_error(
                            f"Candidate rejected; previous restart failed: {rollback_exc}"
                        )
                        self.store.save(state)
                raise VieNeuModelUpdateError(
                    f"VieNeu candidate {candidate_revision} rejected: {sanitize_error(exc)}"
                ) from exc

    def rollback(self) -> VieNeuModelState:
        with self._lock:
            state = self.store.load()
            if not state.previous_revision or not state.previous_snapshot:
                raise VieNeuModelUpdateError("No previous known-good VieNeu revision is available")
            state.active_revision, state.previous_revision = (
                state.previous_revision,
                state.active_revision,
            )
            state.active_snapshot, state.previous_snapshot = (
                state.previous_snapshot,
                state.active_snapshot,
            )
            state.last_activation_at = utc_now_iso()
            state.last_error = ""
            self.store.save(state)
            return state

    def stage_latest(
        self,
        *,
        cancel_event: threading.Event | None = None,
        manual_retry_rejected: bool = False,
        progress_callback: Callable[[int, int, str], None] | None = None,
    ) -> VieNeuUpdateCheck:
        check = self.check_for_update(manual_retry_rejected=manual_retry_rejected)
        if check.status != "available":
            return check
        self.stage_revision(
            check.remote_revision,
            cancel_event=cancel_event,
            manual_retry_rejected=manual_retry_rejected,
            progress_callback=progress_callback,
        )
        return VieNeuUpdateCheck(
            "staged",
            check.active_revision,
            check.remote_revision,
            "Candidate downloaded and awaiting validation/activation",
        )


def initial_state(repository_id: str = DEFAULT_VIENEU_MODEL_REPO) -> VieNeuModelState:
    state = VieNeuModelState(repository_id=repository_id)
    state.validate()
    return state

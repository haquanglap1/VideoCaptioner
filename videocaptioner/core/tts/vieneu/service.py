"""Application-level managed VieNeu service shared by GUI dubbing entry points."""

from __future__ import annotations

import atexit
import json
import os
from contextlib import contextmanager
from pathlib import Path
from threading import Event
from typing import TYPE_CHECKING, Iterator

from .client_identity import VieNeuClientIdentity
from .model_updater import VieNeuModelUpdater, VieNeuStateStore
from .models import VieNeuModelState
from .runtime_manager import (
    VieNeuRuntimeError,
    VieNeuRuntimeLaunchConfig,
    VieNeuRuntimeManager,
)

VIENEU_RUNTIME_INSTALL_MESSAGE = (
    "VieNeu Local runtime is not installed in this base build. "
    "Use the VideoCaptioner VieNeu One-App package, which includes the managed runtime "
    "required to download and validate models."
)

if TYPE_CHECKING:
    from videocaptioner.core.dubbing.config import DubbingConfig


class VieNeuManagedService:
    def __init__(
        self,
        *,
        manager: VieNeuRuntimeManager | None = None,
        store: VieNeuStateStore | None = None,
        updater: VieNeuModelUpdater | None = None,
        explicit_runtime: str | Path | None = None,
        explicit_bridge: str | Path | None = None,
    ):
        self.manager = manager or VieNeuRuntimeManager()
        self.store = store or VieNeuStateStore()
        self.updater = updater or VieNeuModelUpdater(store=self.store)
        self.explicit_runtime = Path(explicit_runtime) if explicit_runtime else None
        self.explicit_bridge = Path(explicit_bridge) if explicit_bridge else None
        self._cancel_event = Event()

    def cancel_pending(self) -> None:
        self._cancel_event.set()

    def reset_cancel(self) -> None:
        self._cancel_event.clear()

    def model_state(self) -> VieNeuModelState:
        return self.store.load()

    @staticmethod
    def runtime_manifest() -> dict:
        from videocaptioner.config import ROOT_PATH

        candidates = (
            Path(ROOT_PATH) / "runtime" / "vieneu" / "runtime-manifest.json",
            Path(__file__).resolve().parents[4]
            / "runtime"
            / "vieneu"
            / "runtime-manifest.json",
        )
        manifest = next((path for path in candidates if path.is_file()), None)
        if manifest is None:
            raise VieNeuRuntimeError(VIENEU_RUNTIME_INSTALL_MESSAGE)
        try:
            return dict(json.loads(manifest.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError) as exc:
            raise VieNeuRuntimeError("VieNeu runtime manifest is invalid") from exc

    def update_prerequisite_error(self) -> str:
        """Return one actionable error when this distribution cannot manage VieNeu models."""
        try:
            self.runtime_manifest()
            runtime = self.explicit_runtime or os.environ.get(
                "VIDEOCAPTIONER_VIENEU_RUNTIME", ""
            )
            bridge = self.explicit_bridge or os.environ.get(
                "VIDEOCAPTIONER_VIENEU_BRIDGE", ""
            )
            self.manager.locator.locate(runtime or None, bridge or None)
        except Exception:
            return VIENEU_RUNTIME_INSTALL_MESSAGE
        return ""

    def prepare_update_prerequisites(
        self,
        *,
        progress_callback=None,
    ) -> VieNeuModelState:
        manifest = self.runtime_manifest()
        state = self.store.load()
        state.repository_id = str(manifest["model_repository"])
        state.model_subfolder = str(manifest.get("model_subfolder", "update"))
        state.runtime_version = str(manifest.get("runtime_version", ""))
        self.store.save(state)
        return self.updater.provision_dependencies(
            tokenizer_repository=str(manifest["tokenizer_repository"]),
            tokenizer_revision=str(manifest["tokenizer_revision"]),
            codec_repository=str(manifest["codec_repository"]),
            codec_revision=str(manifest["codec_revision"]),
            cancel_event=self._cancel_event,
            progress_callback=progress_callback,
        )

    def launch_config(
        self,
        state: VieNeuModelState | None = None,
        *,
        snapshot: Path | None = None,
        revision: str = "",
    ) -> VieNeuRuntimeLaunchConfig:
        state = state or self.store.load()
        active_revision = revision or state.active_revision
        model_snapshot = snapshot or self.store.resolve_snapshot(state.active_snapshot)
        if not active_revision or not model_snapshot.is_dir():
            raise VieNeuRuntimeError(
                "VieNeu Local has no active model. Download and validate a model first."
            )
        tokenizer_snapshot = self.store.resolve_snapshot(state.tokenizer_snapshot)
        codec_snapshot = self.store.resolve_snapshot(state.codec_snapshot)
        if not state.tokenizer_revision or not tokenizer_snapshot.is_dir():
            raise VieNeuRuntimeError("VieNeu tokenizer snapshot is not provisioned")
        if not state.codec_revision or not codec_snapshot.is_dir():
            raise VieNeuRuntimeError("VieNeu codec snapshot is not provisioned")
        runtime = self.explicit_runtime or os.environ.get(
            "VIDEOCAPTIONER_VIENEU_RUNTIME", ""
        )
        bridge = self.explicit_bridge or os.environ.get(
            "VIDEOCAPTIONER_VIENEU_BRIDGE", ""
        )
        return VieNeuRuntimeLaunchConfig(
            model_snapshot=model_snapshot,
            model_revision=active_revision,
            model_repository=state.repository_id,
            backend=state.active_backend or "pytorch",
            model_subfolder=state.model_subfolder,
            tokenizer_snapshot=tokenizer_snapshot,
            tokenizer_revision=state.tokenizer_revision,
            codec_snapshot=codec_snapshot,
            codec_revision=state.codec_revision,
            explicit_runtime=Path(runtime) if runtime else None,
            explicit_bridge=Path(bridge) if bridge else None,
            startup_timeout=300.0,
            request_timeout=10.0,
            retry_count=1,
            max_batch=16,
            max_wait=0.03,
        )

    def ensure_ready(self) -> VieNeuClientIdentity:
        self.reset_cancel()
        return self.manager.ensure_ready(
            self.launch_config(), cancel_event=self._cancel_event
        )

    @contextmanager
    def acquire_for_dubbing(
        self, config: "DubbingConfig"
    ) -> Iterator[VieNeuClientIdentity]:
        if config.tts_config is None:
            raise VieNeuRuntimeError("TTS config is required for VieNeu Local")
        self.reset_cancel()
        original = (
            config.tts_config.api_key,
            config.tts_config.base_url,
            config.tts_config.model,
            config.tts_config.sample_rate,
        )
        with self.manager.acquire(
            self.launch_config(), cancel_event=self._cancel_event
        ) as identity:
            config.tts_config.api_key = identity.session_token
            config.tts_config.base_url = identity.endpoint
            config.tts_config.model = f"vieneu:{identity.model_revision}"
            config.tts_config.sample_rate = identity.sample_rate
            config.tts_config.response_format = "wav"
            config.managed_tts_identity = identity.cache_identity()
            try:
                yield identity
            finally:
                (
                    config.tts_config.api_key,
                    config.tts_config.base_url,
                    config.tts_config.model,
                    config.tts_config.sample_rate,
                ) = original

    def voices(self) -> list[dict]:
        self.ensure_ready()
        payload = self.manager.get_json("voices", timeout=20)
        voices = payload.get("voices") or payload.get("data") or []
        return [dict(item) for item in voices if isinstance(item, dict)]

    def shutdown(self) -> None:
        self.cancel_pending()
        self.manager.shutdown(force=True)


_service: VieNeuManagedService | None = None


def get_vieneu_service() -> VieNeuManagedService:
    global _service
    if _service is None:
        _service = VieNeuManagedService()
        atexit.register(_service.shutdown)
    return _service


def set_vieneu_service_for_tests(service: VieNeuManagedService | None) -> None:
    global _service
    if _service is not None and _service is not service:
        _service.shutdown()
    _service = service

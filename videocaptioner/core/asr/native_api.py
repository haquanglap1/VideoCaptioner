"""Job-owned native HTTP lifecycle, bounded polling and cancellable in-flight I/O."""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import re
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable
from uuid import UUID, uuid4

import httpx

from videocaptioner.core.utils.cache import get_asr_cache, is_cache_enabled
from videocaptioner.core.utils.logger import setup_logger
from videocaptioner.core.utils.subprocess_helper import _NO_WINDOW, child_environment

from .api_profiles import ASRAPIError
from .api_transcription import audio_attachment
from .asr_data import ASRData
from .native_profiles import NATIVE_PROFILES, NativeASRConfig
from .native_result import native_cues, parse_native

logger = setup_logger("native_asr")
Check = Callable[[], None]
REMOTE_NOTICE = "Local waiting stopped; remote processing/storage may continue and incur charges. Review the provider console."


class NativeAPIError(ASRAPIError):
    def __init__(self, stage: str, reason: str, *, uncertain: bool = False, timed_out: bool = False):
        self.stage = stage
        self.uncertain = uncertain
        self.timed_out = timed_out
        super().__init__(f"Native ASR {stage}: {reason}" + (f" {REMOTE_NOTICE}" if uncertain else ""))


@dataclass
class NativeJobState:
    stage: str = "preflight"
    status: str = "pending"
    remote: str = "not_submitted"
    warnings: list[str] = field(default_factory=list)


def audio_fingerprint(path: Path, config: NativeASRConfig, language: str, check: Check) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(1024 * 1024):
            check()
            digest.update(block)
    settings = json.dumps({"provider": config.provider, "endpoint": config.api_base,
                           "model": config.model, "language": language, "diarize": config.diarize,
                           "events": True, "speaker_policy": "request-scoped-v1",
                           "timing": "native-full-file-v1"}, sort_keys=True)
    digest.update(settings.encode())
    return "NativeASR:v1-" + digest.hexdigest()


def audio_duration(path: Path, check: Check) -> int:
    """Probe without decoding multi-hour files into RAM or exposing media paths in errors."""
    try:
        process = subprocess.Popen(
            ["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries",
             "stream=duration:format=duration", "-of", "json", str(path)],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
            env=child_environment(), creationflags=_NO_WINDOW,
        )
    except OSError:
        raise NativeAPIError("preflight", "FFprobe unavailable.") from None
    try:
        deadline = time.monotonic() + 30
        while True:
            check()
            if time.monotonic() >= deadline:
                raise NativeAPIError("preflight", "Audio probe timed out.", timed_out=True)
            try:
                output, _ = process.communicate(timeout=0.1)
                break
            except subprocess.TimeoutExpired:
                continue
        try:
            data = json.loads(output)
            if process.returncode or not data.get("streams"):
                raise ValueError
            duration = data["streams"][0].get("duration", data.get("format", {}).get("duration"))
            seconds = float(duration)
            if not math.isfinite(seconds) or seconds <= 0:
                raise ValueError
            return round(seconds * 1000)
        except (ValueError, TypeError, KeyError):
            raise NativeAPIError("preflight", "Cannot determine audio duration.") from None
    finally:
        if process.poll() is None:
            process.kill()
        process.communicate()


def run_cancellable(operation, check: Check):
    async def run():
        task = asyncio.create_task(operation)
        try:
            while not task.done():
                check()
                await asyncio.wait({task}, timeout=0.1)
            return await task
        finally:
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)
    return asyncio.run(run())


class NativeASR:
    def __init__(self, audio_path: str, config: NativeASRConfig, language: str = "",
                 word_timing: bool = True, *, use_cache: bool = True,
                 transport: httpx.AsyncBaseTransport | None = None, deadline_seconds: float = 3600):
        self.config = config.validated()
        self.path = Path(audio_path)
        self.language = "" if language in ("", "auto") else language
        if self.language not in ("", "zh", "cmn", "zho"):
            raise NativeAPIError("preflight", "S3 supports Chinese or automatic language detection.")
        if self.language:
            self.language = "zh"
        self.word_timing = word_timing
        self.use_cache = use_cache
        self.transport = transport
        self.deadline_seconds = deadline_seconds
        self.state = NativeJobState()
        self._file_id: str | None = None
        self._job_id: str | None = None
        self._submit_attempted = False
        self._upload_attempted = False
        self._scribe_id: str | None = None

    def run(self, callback: Callable[[int, str], None] | None = None) -> ASRData:
        self.state = NativeJobState()
        self._file_id = self._job_id = self._scribe_id = None
        self._submit_attempted = self._upload_attempted = False
        def check():
            if callback:
                try:
                    callback(95 if self.state.stage == "result" else 10,
                             f"Native ASR: {self.state.stage}")
                except BaseException:
                    self.state.status = "cancelled"
                    raise
        self._check = check
        try:
            check()
            profile = NATIVE_PROFILES[self.config.provider]
            if not self.path.is_file() or not 0 < self.path.stat().st_size <= profile.max_upload_bytes:
                raise NativeAPIError("preflight", "Audio is empty or exceeds the application upload limit.")
            self.duration_ms = audio_duration(self.path, check)
            if not 100 <= self.duration_ms <= profile.max_duration_ms:
                raise NativeAPIError("preflight", "Audio exceeds the supported duration; no automatic chunking.")
            with self.path.open("rb") as handle:
                name, _, mime = audio_attachment(handle.read(32), 32)
            self.attachment = (name, mime)
            key = audio_fingerprint(self.path, self.config, self.language, check)
            cache = get_asr_cache()
            enabled = self.use_cache and is_cache_enabled()
            cached: Any = cache.get(key) if enabled else None
            if cached is not None and (not isinstance(cached, dict) or not isinstance(cached.get("scope"), str)
                                       or not isinstance(cached.get("response"), dict)):
                raise NativeAPIError("cache", "Invalid native cache; review required.")
            check()
            if cached is None:
                response: Any = run_cancellable(self._run_http(), check)
                scope = uuid4().hex
            else:
                response, scope = cached["response"], cached["scope"]
            check()
            result = parse_native(response, self.config.provider, self.duration_ms, scope, self.config.diarize)
            if enabled and cached is None:
                # Cache only fields required by the parser, never remote IDs/raw error bodies.
                field_name = "tokens" if self.config.provider == "soniox" else "words"
                fields = {"text", "type", "start", "end", "start_ms", "end_ms", "speaker",
                          "speaker_id", "translation_status"}
                minimal = {"text": response["text"], field_name: [
                    {k: v for k, v in item.items() if k in fields} for item in response[field_name]]}
                cache.set(key, {"response": minimal, "scope": scope}, expire=86400 * 2)
            self.state.status = "succeeded"
            if callback:
                observed = len({seg.speaker for seg in result if seg.speaker is not None})
                callback(100, f"Native ASR: {len(result)} timed speech spans; {observed} anonymous speaker labels observed. "
                         + " ".join(self.state.warnings))
            return result if self.word_timing else native_cues(result)
        except NativeAPIError as exc:
            self.state.status = "timeout" if exc.timed_out else "failed"
            raise
        except OSError:
            if self.state.status == "cancelled":
                raise
            self.state.status = "failed"
            raise NativeAPIError(self.state.stage, "Cannot read the audio or cache files.") from None
        except BaseException:
            if self.state.status != "cancelled":
                self.state.status = "failed"
            raise

    async def _request(self, client: httpx.AsyncClient, method: str, route: str, stage: str,
                       **kwargs) -> dict[str, Any]:
        self.state.stage = stage
        attempts = 3 if method == "GET" else 1
        for attempt in range(attempts):
            self._check()
            remaining = self._deadline - time.monotonic()
            if remaining <= 0:
                raise NativeAPIError(stage, "Job timed out.", uncertain=self._submit_attempted, timed_out=True)
            if method == "POST":
                if stage == "upload":
                    self._upload_attempted = True
                elif stage in ("submit", "recognition"):
                    self._submit_attempted = True
                    self.state.remote = "uncertain"
            try:
                response = await asyncio.wait_for(client.request(method, route, **kwargs), timeout=remaining)
            except (httpx.HTTPError, asyncio.TimeoutError) as exc:
                if attempt + 1 == attempts:
                    timed_out = isinstance(exc, (httpx.TimeoutException, asyncio.TimeoutError))
                    reason = "Request timed out." if timed_out else "Connection failed."
                    raise NativeAPIError(stage, reason + " Request was not resubmitted.",
                                         uncertain=method == "POST" or self._submit_attempted,
                                         timed_out=timed_out) from None
                await asyncio.sleep(min(2 ** attempt, max(0, self._deadline - time.monotonic())))
                continue
            if response.status_code >= 400 or response.is_redirect:
                if method == "GET" and (response.status_code == 429 or response.status_code >= 500) and attempt + 1 < attempts:
                    try:
                        delay = float(response.headers.get("Retry-After", 2 ** attempt))
                        if not math.isfinite(delay):
                            raise ValueError
                    except ValueError:
                        delay = 2 ** attempt
                    await asyncio.sleep(min(max(0, delay), 10, max(0, self._deadline - time.monotonic())))
                    continue
                if method == "POST" and 400 <= response.status_code < 500:
                    if stage in ("submit", "recognition"):
                        self._submit_attempted = False
                        self.state.remote = "rejected"
                    elif stage == "upload":
                        self._upload_attempted = False
                raise NativeAPIError(stage, f"HTTP {response.status_code}; no automatic new job.",
                                     uncertain=method == "POST" and response.status_code >= 500)
            try:
                value = response.json()
                if not isinstance(value, dict):
                    raise ValueError
                return value
            except ValueError:
                raise NativeAPIError(stage, "Malformed response; review required.", uncertain=method == "POST") from None
        raise AssertionError("Unreachable retry state")

    @staticmethod
    def _owned_id(value: dict, stage: str) -> str:
        try:
            return str(UUID(value["id"]))
        except (KeyError, ValueError, TypeError, AttributeError):
            raise NativeAPIError(stage, "Missing resource ID; acceptance is uncertain.", uncertain=True) from None

    async def _cleanup(self, client: httpx.AsyncClient) -> None:
        async def delete(route: str) -> bool:
            try:
                response = await asyncio.wait_for(client.delete(route), timeout=3)
                return response.status_code in (200, 204, 404)
            except (httpx.HTTPError, asyncio.TimeoutError):
                return False
        job_removed = False
        if self._job_id:
            job_removed = await delete(f"transcriptions/{self._job_id}")
            if job_removed:
                self.state.remote = "deleted"
        # Never remove input under a still-running or ambiguously submitted transcription.
        if self._file_id and (not self._submit_attempted or job_removed or self.state.remote in ("completed", "error")):
            if not await delete(f"files/{self._file_id}"):
                self.state.warnings.append("Uploaded file cleanup failed; review the provider console.")
        if self._submit_attempted and not job_removed and self.state.remote not in ("completed", "error"):
            self.state.warnings.append(REMOTE_NOTICE)
        if self._job_id and not job_removed and self.state.remote in ("completed", "error"):
            self.state.warnings.append("Transcript cleanup failed; review the provider console.")
        if self._upload_attempted and self._file_id is None:
            self.state.warnings.append("Upload acceptance/cleanup is uncertain; review the provider console.")
        for warning in self.state.warnings:
            logger.warning(warning)

    async def _run_http(self) -> dict:
        cfg = self.config
        headers = {"Authorization": f"Bearer {cfg.api_key}"} if cfg.provider == "soniox" else {"xi-api-key": cfg.api_key}
        self._deadline = time.monotonic() + self.deadline_seconds
        async with httpx.AsyncClient(base_url=cfg.api_base + "/", headers=headers, transport=self.transport,
                                     timeout=httpx.Timeout(120, connect=10), follow_redirects=False,
                                     trust_env=False) as client:
            try:
                with self.path.open("rb") as handle:
                    files = {"file": (self.attachment[0], handle, self.attachment[1])}
                    if cfg.provider == "scribe":
                        data = {"model_id": cfg.model, "diarize": str(cfg.diarize).lower(),
                                "tag_audio_events": "true", "timestamps_granularity": "word",
                                "webhook": "false", "use_multi_channel": "false",
                                "no_verbatim": "false", "use_speaker_library": "false",
                                "detect_speaker_roles": "false"}
                        if self.language:
                            data["language_code"] = self.language
                        result = await self._request(client, "POST", "speech-to-text", "recognition",
                                                     data=data, files=files, timeout=self.deadline_seconds)
                        self.state.remote = "completed"
                        transcript_id = result.get("transcription_id")
                        if isinstance(transcript_id, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,256}", transcript_id):
                            self._scribe_id = transcript_id
                        else:
                            self.state.warnings.append("No usable transcript ID returned; remote storage cleanup is unavailable.")
                        return result
                    uploaded = await self._request(client, "POST", "files", "upload", files=files)
                    self._file_id = self._owned_id(uploaded, "upload")
                payload = {"model": cfg.model, "file_id": self._file_id,
                           "enable_speaker_diarization": cfg.diarize}
                if self.language:
                    payload["language_hints"] = [self.language]
                created = await self._request(client, "POST", "transcriptions", "submit", json=payload)
                self._job_id = self._owned_id(created, "submit")
                delay = 0.5
                while True:
                    status = await self._request(client, "GET", f"transcriptions/{self._job_id}", "poll")
                    remote = status.get("status")
                    if remote not in ("queued", "processing", "completed", "error"):
                        raise NativeAPIError("poll", "Unknown remote state; review required.", uncertain=True)
                    self.state.remote = remote
                    if remote == "error":
                        raise NativeAPIError("poll", "Provider job failed; review provider console.")
                    if remote == "completed":
                        return await self._request(client, "GET", f"transcriptions/{self._job_id}/transcript", "result")
                    await asyncio.sleep(min(delay, max(0, self._deadline - time.monotonic())))
                    delay = min(delay * 1.5, 5)
            finally:
                if cfg.provider == "soniox":
                    await self._cleanup(client)
                else:
                    if self._scribe_id:
                        try:
                            response = await asyncio.wait_for(client.delete(
                                f"speech-to-text/transcripts/{self._scribe_id}"), 3)
                            if response.status_code not in (200, 204, 404):
                                raise ValueError
                            self.state.remote = "deleted"
                        except (httpx.HTTPError, asyncio.TimeoutError, ValueError):
                            self.state.warnings.append("Transcript cleanup failed; review the provider console.")
                    elif self._submit_attempted and self.state.remote != "completed":
                        self.state.warnings.append(REMOTE_NOTICE)
                    for warning in self.state.warnings:
                        logger.warning(warning)


def probe_service(config: NativeASRConfig, check: Check, *, transport=None) -> None:
    """Auth/read-scope probe only. Discard account/catalog payload without logging it."""
    config = config.validated()
    async def probe():
        headers = ({"Authorization": f"Bearer {config.api_key}"} if config.provider == "soniox"
                   else {"xi-api-key": config.api_key})
        route = "models" if config.provider == "soniox" else "user"
        async with httpx.AsyncClient(headers=headers, transport=transport, timeout=10,
                                     follow_redirects=False, trust_env=False) as client:
            try:
                response = await asyncio.wait_for(client.get(config.api_base + "/" + route), 15)
            except (httpx.HTTPError, asyncio.TimeoutError):
                raise NativeAPIError("service probe", "Connection failed or timed out.") from None
            if response.status_code != 200:
                raise NativeAPIError("service probe", f"HTTP {response.status_code}; check key/read permissions.")
    run_cancellable(probe(), check)

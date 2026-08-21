"""Own, authenticate, monitor, and stop the isolated VieNeu sidecar."""

from __future__ import annotations

import os
import secrets
import socket
import subprocess
import threading
import time
from collections import deque
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterator
from uuid import uuid4

import psutil
import requests

from videocaptioner.core.utils.logger import setup_logger

from .client_identity import VieNeuClientIdentity
from .models import (
    DEFAULT_MODEL_SUBFOLDER,
    DEFAULT_VIENEU_MODEL_REPO,
    VieNeuHealth,
    VieNeuRuntimeState,
    sanitize_error,
    validate_revision,
)
from .runtime_locator import VieNeuRuntimeLayout, VieNeuRuntimeLocator

logger = setup_logger("tts.vieneu.runtime")
_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
_TOKEN_ENV = "VIDEOCAPTIONER_VIENEU_SESSION_TOKEN"


class VieNeuRuntimeError(RuntimeError):
    pass


class VieNeuPortOwnershipError(VieNeuRuntimeError):
    pass


class VieNeuRuntimeIdentityError(VieNeuRuntimeError):
    pass


class VieNeuRuntimeCancelled(VieNeuRuntimeError):
    pass


@dataclass(frozen=True)
class VieNeuRuntimeLaunchConfig:
    model_snapshot: Path
    model_revision: str
    model_repository: str = DEFAULT_VIENEU_MODEL_REPO
    backend: str = "pytorch"
    model_subfolder: str = DEFAULT_MODEL_SUBFOLDER
    tokenizer_snapshot: Path | None = None
    tokenizer_revision: str = ""
    codec_snapshot: Path | None = None
    codec_revision: str = ""
    explicit_runtime: Path | None = None
    explicit_bridge: Path | None = None
    startup_timeout: float = 180.0
    health_interval: float = 0.2
    request_timeout: float = 5.0
    retry_count: int = 1
    port: int | None = None
    max_batch: int = 16
    max_wait: float = 0.03
    extra_args: tuple[str, ...] = ()
    extra_env: dict[str, str] = field(default_factory=dict)

    def validate(self) -> None:
        validate_revision(self.model_revision, allow_empty=False)
        if not self.model_snapshot.is_dir():
            raise FileNotFoundError(f"VieNeu model snapshot not found: {self.model_snapshot}")
        if self.tokenizer_snapshot is not None and not self.tokenizer_snapshot.is_dir():
            raise FileNotFoundError(
                f"VieNeu tokenizer snapshot not found: {self.tokenizer_snapshot}"
            )
        if self.codec_snapshot is not None and not self.codec_snapshot.is_dir():
            raise FileNotFoundError(f"VieNeu codec snapshot not found: {self.codec_snapshot}")
        if self.startup_timeout <= 0 or self.request_timeout <= 0:
            raise ValueError("VieNeu runtime timeouts must be positive")


class VieNeuRuntimeManager:
    """One-process owner. It never adopts or kills an unrelated listener."""

    def __init__(
        self,
        *,
        locator: VieNeuRuntimeLocator | None = None,
        popen_factory: Callable[..., subprocess.Popen] = subprocess.Popen,
        session: requests.Session | None = None,
    ):
        self.locator = locator or VieNeuRuntimeLocator()
        self._popen_factory = popen_factory
        self._session = session or requests.Session()
        self._lock = threading.RLock()
        self._process: subprocess.Popen | None = None
        self._layout: VieNeuRuntimeLayout | None = None
        self._identity: VieNeuClientIdentity | None = None
        self._launch_config: VieNeuRuntimeLaunchConfig | None = None
        self._session_token = ""
        self._session_id = ""
        self._port = 0
        self._state = VieNeuRuntimeState.STOPPED
        self._active_jobs = 0
        self._state_callbacks: list[Callable[[VieNeuRuntimeState, str], None]] = []
        self._log_tail: deque[str] = deque(maxlen=80)
        self._drain_threads: list[threading.Thread] = []

    @property
    def state(self) -> VieNeuRuntimeState:
        with self._lock:
            return self._state

    @property
    def identity(self) -> VieNeuClientIdentity | None:
        with self._lock:
            return self._identity

    @property
    def process_id(self) -> int | None:
        with self._lock:
            return self._process.pid if self._process and self._process.poll() is None else None

    @property
    def active_jobs(self) -> int:
        with self._lock:
            return self._active_jobs

    def add_state_callback(
        self, callback: Callable[[VieNeuRuntimeState, str], None]
    ) -> None:
        self._state_callbacks.append(callback)

    def remove_state_callback(
        self, callback: Callable[[VieNeuRuntimeState, str], None]
    ) -> None:
        try:
            self._state_callbacks.remove(callback)
        except ValueError:
            pass

    def _set_state(self, state: VieNeuRuntimeState, message: str = "") -> None:
        with self._lock:
            self._state = state
        safe_message = sanitize_error(message) if message else ""
        for callback in tuple(self._state_callbacks):
            try:
                callback(state, safe_message)
            except Exception:
                logger.debug("VieNeu state callback failed", exc_info=True)

    @staticmethod
    def _allocate_port() -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            return int(sock.getsockname()[1])

    @staticmethod
    def _port_is_free(port: int) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind(("127.0.0.1", int(port)))
            except OSError:
                return False
        return True

    def _select_port(self, requested: int | None) -> int:
        port = int(requested) if requested else self._allocate_port()
        if not self._port_is_free(port):
            raise VieNeuPortOwnershipError(
                f"Loopback port {port} is occupied by an unrelated process; it was not terminated"
            )
        return port

    def _command(
        self,
        layout: VieNeuRuntimeLayout,
        config: VieNeuRuntimeLaunchConfig,
        port: int,
    ) -> list[str]:
        command = [
            str(layout.python_executable),
            "-u",
            str(layout.bridge_script),
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--session-id",
            self._session_id,
            "--token-env",
            _TOKEN_ENV,
            "--model-snapshot",
            str(config.model_snapshot),
            "--model-repository",
            config.model_repository,
            "--model-revision",
            config.model_revision,
            "--model-subfolder",
            config.model_subfolder,
            "--backend",
            config.backend,
            "--max-batch",
            str(max(1, config.max_batch)),
            "--max-wait",
            str(max(0.0, config.max_wait)),
        ]
        if config.tokenizer_snapshot:
            command.extend(["--tokenizer-snapshot", str(config.tokenizer_snapshot)])
        if config.tokenizer_revision:
            command.extend(["--tokenizer-revision", config.tokenizer_revision])
        if config.codec_snapshot:
            command.extend(["--codec-snapshot", str(config.codec_snapshot)])
        if config.codec_revision:
            command.extend(["--codec-revision", config.codec_revision])
        command.extend(config.extra_args)
        return command

    def _environment(self, config: VieNeuRuntimeLaunchConfig) -> dict[str, str]:
        environment = os.environ.copy()
        environment.update(config.extra_env)
        environment[_TOKEN_ENV] = self._session_token
        environment["PYTHONUNBUFFERED"] = "1"
        # Runtime receives immutable local snapshots and must not follow mutable main.
        environment["HF_HUB_OFFLINE"] = "1"
        environment["TRANSFORMERS_OFFLINE"] = "1"
        if config.model_snapshot.parent.name == "snapshots":
            managed_hf_cache = config.model_snapshot.parents[2]
        else:
            managed_hf_cache = config.model_snapshot.parent / "hf-runtime"
        modules_cache = managed_hf_cache / "modules"
        transformers_cache = managed_hf_cache / "transformers"
        modules_cache.mkdir(parents=True, exist_ok=True)
        transformers_cache.mkdir(parents=True, exist_ok=True)
        environment["HF_HOME"] = str(managed_hf_cache.parent)
        environment["HF_HUB_CACHE"] = str(managed_hf_cache)
        environment["HF_MODULES_CACHE"] = str(modules_cache)
        environment["TRANSFORMERS_CACHE"] = str(transformers_cache)
        environment["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
        return environment

    def _drain_stream(self, stream, label: str) -> None:
        if stream is None:
            return
        try:
            for line in iter(stream.readline, ""):
                safe = sanitize_error(line.replace(self._session_token, "***"))
                if not safe:
                    continue
                self._log_tail.append(f"{label}: {safe}")
                logger.info("VieNeu sidecar %s: %s", label, safe)
        finally:
            try:
                stream.close()
            except Exception:
                pass

    def _start_drainers(self, process: subprocess.Popen) -> None:
        self._drain_threads = []
        for stream, label in ((process.stdout, "stdout"), (process.stderr, "stderr")):
            thread = threading.Thread(
                target=self._drain_stream,
                args=(stream, label),
                name=f"vieneu-{label}-{process.pid}",
                daemon=True,
            )
            thread.start()
            self._drain_threads.append(thread)

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._session_token}"}

    def _health_url(self) -> str:
        return f"http://127.0.0.1:{self._port}/health"

    def _wait_for_health(
        self,
        config: VieNeuRuntimeLaunchConfig,
        cancel_event: threading.Event | None,
    ) -> VieNeuHealth:
        deadline = time.monotonic() + config.startup_timeout
        last_error = "VieNeu runtime did not respond"
        while time.monotonic() < deadline:
            if cancel_event and cancel_event.is_set():
                raise VieNeuRuntimeCancelled("VieNeu startup was cancelled")
            process = self._process
            if process is None or process.poll() is not None:
                tail = self._log_tail[-1] if self._log_tail else "no sidecar error output"
                raise VieNeuRuntimeError(
                    f"VieNeu sidecar exited during startup: {sanitize_error(tail)}"
                )
            try:
                response = self._session.get(
                    self._health_url(),
                    headers=self._headers(),
                    timeout=min(config.request_timeout, 2.0),
                )
                if response.status_code == 200:
                    try:
                        return VieNeuHealth.from_payload(
                            response.json(),
                            expected_session_id=self._session_id,
                            expected_revision=config.model_revision,
                        )
                    except ValueError as exc:
                        raise VieNeuRuntimeIdentityError(str(exc)) from exc
                last_error = f"health returned HTTP {response.status_code}"
            except VieNeuRuntimeIdentityError:
                raise
            except requests.RequestException as exc:
                last_error = str(exc)
            time.sleep(max(0.02, config.health_interval))
        raise VieNeuRuntimeError(
            f"VieNeu startup timed out after {config.startup_timeout:.1f}s: {sanitize_error(last_error)}"
        )

    def _same_runtime(self, config: VieNeuRuntimeLaunchConfig) -> bool:
        return bool(
            self._identity
            and self._process
            and self._process.poll() is None
            and self._identity.model_revision == config.model_revision
            and self._identity.backend == config.backend
        )

    def ensure_ready(
        self,
        config: VieNeuRuntimeLaunchConfig,
        *,
        cancel_event: threading.Event | None = None,
    ) -> VieNeuClientIdentity:
        config.validate()
        with self._lock:
            if self._same_runtime(config):
                assert self._identity is not None
                return self._identity
            if self._active_jobs:
                raise VieNeuRuntimeError(
                    "Cannot switch VieNeu model/runtime while a dubbing job is active"
                )
            if self._process:
                self.shutdown(force=True)

            layout = self.locator.locate(config.explicit_runtime, config.explicit_bridge)
            self._layout = layout
            self._launch_config = config

            last_error: Exception | None = None
            for attempt in range(max(0, int(config.retry_count)) + 1):
                try:
                    self._session_token = secrets.token_urlsafe(32)
                    self._session_id = uuid4().hex
                    self._port = self._select_port(config.port)
                    self._set_state(VieNeuRuntimeState.STARTING, "Starting VieNeu Local")
                    self._log_tail.clear()
                    self._process = self._popen_factory(
                        self._command(layout, config, self._port),
                        cwd=str(layout.runtime_root),
                        env=self._environment(config),
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        bufsize=1,
                        creationflags=_CREATE_NO_WINDOW,
                    )
                    self._start_drainers(self._process)
                    health = self._wait_for_health(config, cancel_event)
                    endpoint = f"http://127.0.0.1:{self._port}/v1/"
                    self._identity = VieNeuClientIdentity.from_health(
                        endpoint, self._session_token, health
                    )
                    self._set_state(VieNeuRuntimeState.READY, "VieNeu Local ready")
                    return self._identity
                except (VieNeuRuntimeIdentityError, VieNeuPortOwnershipError):
                    self.shutdown(force=True)
                    raise
                except VieNeuRuntimeCancelled:
                    self.shutdown(force=True)
                    raise
                except Exception as exc:
                    last_error = exc
                    self.shutdown(force=True)
                    if attempt >= max(0, int(config.retry_count)):
                        break
            message = sanitize_error(last_error or "VieNeu startup failed")
            self._set_state(VieNeuRuntimeState.FAILED, message)
            raise VieNeuRuntimeError(message) from last_error

    @contextmanager
    def acquire(
        self,
        config: VieNeuRuntimeLaunchConfig,
        *,
        cancel_event: threading.Event | None = None,
    ) -> Iterator[VieNeuClientIdentity]:
        identity = self.ensure_ready(config, cancel_event=cancel_event)
        with self._lock:
            self._active_jobs += 1
            self._set_state(VieNeuRuntimeState.BUSY, "VieNeu Local busy")
        try:
            yield identity
        finally:
            with self._lock:
                self._active_jobs = max(0, self._active_jobs - 1)
                if self._active_jobs == 0 and self._process and self._process.poll() is None:
                    self._set_state(VieNeuRuntimeState.READY, "VieNeu Local ready")

    def get_json(self, path: str, *, timeout: float = 10.0) -> dict:
        if not self._identity:
            raise VieNeuRuntimeError("VieNeu Local is not ready")
        url = self._identity.endpoint.rstrip("/") + "/" + path.lstrip("/")
        response = self._session.get(url, headers=self._headers(), timeout=timeout)
        response.raise_for_status()
        return dict(response.json())

    def post_bytes(
        self, path: str, payload: dict, *, timeout: float = 120.0
    ) -> tuple[bytes, str]:
        if not self._identity:
            raise VieNeuRuntimeError("VieNeu Local is not ready")
        url = self._identity.endpoint.rstrip("/") + "/" + path.lstrip("/")
        response = self._session.post(
            url,
            headers=self._headers(),
            json=payload,
            timeout=timeout,
        )
        response.raise_for_status()
        return response.content, response.headers.get("content-type", "")

    @staticmethod
    def _owned_processes(root_pid: int) -> list[psutil.Process]:
        try:
            root = psutil.Process(root_pid)
        except psutil.Error:
            return []
        return [root, *root.children(recursive=True)]

    def shutdown(self, *, force: bool = False, timeout: float = 8.0) -> bool:
        with self._lock:
            if self._active_jobs and not force:
                return False
            process = self._process
            if not process:
                self._identity = None
                self._set_state(VieNeuRuntimeState.STOPPED, "")
                return True
            self._set_state(VieNeuRuntimeState.STOPPING, "Stopping VieNeu Local")
            root_pid = process.pid
            # Snapshot descendants before graceful shutdown. Once the parent exits,
            # orphaned children can no longer be discovered through its PID.
            owned = self._owned_processes(root_pid)
            if process.poll() is None and self._port and self._session_token:
                try:
                    self._session.post(
                        f"http://127.0.0.1:{self._port}/shutdown",
                        headers=self._headers(),
                        timeout=min(2.0, timeout),
                    )
                except requests.RequestException:
                    pass
            try:
                process.wait(timeout=max(0.1, timeout / 2))
            except subprocess.TimeoutExpired:
                pass

            known_pids = {owned_process.pid for owned_process in owned}
            for owned_process in self._owned_processes(root_pid):
                if owned_process.pid not in known_pids:
                    owned.append(owned_process)
                    known_pids.add(owned_process.pid)
            for owned_process in reversed(owned):
                try:
                    if owned_process.is_running():
                        owned_process.terminate()
                except psutil.Error:
                    continue
            _, alive = psutil.wait_procs(owned, timeout=max(0.1, timeout / 3)) if owned else ([], [])
            for owned_process in alive:
                try:
                    owned_process.kill()
                except psutil.Error:
                    continue
            if process.poll() is None:
                try:
                    process.kill()
                    process.wait(timeout=2)
                except Exception:
                    pass
            self._process = None
            self._identity = None
            self._session_token = ""
            self._session_id = ""
            self._port = 0
            self._set_state(VieNeuRuntimeState.STOPPED, "")
            return True

    def owned_processes_alive(self) -> list[int]:
        pid = self.process_id
        if pid is None:
            return []
        return [process.pid for process in self._owned_processes(pid) if process.is_running()]

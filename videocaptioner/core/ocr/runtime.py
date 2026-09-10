"""One explicitly located, offline CPU worker per OCR job, supervised outside the Qt thread."""

from __future__ import annotations

import hashlib
import json
import math
import os
import queue
import subprocess
import tempfile
import threading
import time
from contextvars import copy_context
from dataclasses import dataclass, field
from pathlib import Path

from videocaptioner.core.utils.subprocess_helper import _NO_WINDOW, child_environment

from .consensus import validate_read
from .decoder import stop_owned_process
from .models import Check, EngineRead, OcrError, ReadLine, RoiFrame

PROTOCOL = "ocr-stream-v1"
MAX_RESPONSE_BYTES = 1024 * 1024


class OcrRuntimeMissing(OcrError):
    pass


@dataclass
class RuntimeMetrics:
    requests: int = 0
    completed: int = 0
    request_wall_s: float = 0
    inference_s: float = 0
    process_wall_s: float = 0
    stderr_bytes: int = 0
    last_worker: dict = field(default_factory=dict)
    worker_error: dict = field(default_factory=dict)
    # Attempt counters from the worker before ONNX calls, retained even on cancellation.
    started_inference_calls: dict[str, int] = field(default_factory=lambda: {"det": 0, "rec": 0, "cls": 0})


class CpuOcrRuntime:
    """Source OCR-2 uses explicit bridge/root; app discovery and bundling are OCR-4.

    Use one instance on one owning job thread. close() is idempotent and cannot restart
    a cancelled worker; a fresh instance is needed for a new job.
    """

    def __init__(self, root: Path, bridge: Path, jobs_root: Path, profile_sha256: str, *,
                 timeout: float = 30, startup_timeout: float = 60, max_requests: int = 1000,
                 check: Check = lambda: None):
        if (any(not math.isfinite(t) or t <= 0 for t in (timeout, startup_timeout))
                or type(max_requests) is not int or not 1 <= max_requests <= 100000
                or len(profile_sha256) != 64 or any(c not in "0123456789abcdef" for c in profile_sha256)):
            raise OcrError("Invalid CPU OCR runtime policy")
        self.root, self.bridge, self.jobs_root = root.resolve(), bridge.resolve(), jobs_root.resolve()
        self.profile_sha256 = profile_sha256
        self.timeout, self.startup_timeout, self.check = timeout, startup_timeout, check
        self.max_requests = max_requests
        self.process: subprocess.Popen | None = None
        self.readers: list[threading.Thread] = []
        self.messages: queue.Queue[bytes] = queue.Queue(maxsize=16)
        self.errors: queue.Queue[str] = queue.Queue(maxsize=1)
        self.stopped = threading.Event()
        self.output_done = threading.Event()
        self.temporary: tempfile.TemporaryDirectory | None = None
        self.directory: Path | None = None
        self.metrics = RuntimeMetrics()
        self.started = 0.0
        self.state = "new"
        self.bridge_sha256 = ""

    def _fail(self, message: str) -> None:
        try:
            self.errors.put_nowait(message)
        except queue.Full:
            pass

    def _stdout(self) -> None:
        assert self.process is not None and self.process.stdout is not None
        try:
            while not self.stopped.is_set():
                line = self.process.stdout.readline(MAX_RESPONSE_BYTES + 1)
                if not line:
                    break
                if len(line) > MAX_RESPONSE_BYTES or not line.endswith(b"\n"):
                    self._fail("Oversized or truncated OCR response")
                    return
                while not self.stopped.is_set():
                    try:
                        self.messages.put(line, timeout=0.05)
                        break
                    except queue.Full:
                        continue
        except OSError:
            self._fail("OCR response pipe failed")
        finally:
            self.output_done.set()

    def _stderr(self) -> None:
        assert self.process is not None and self.process.stderr is not None
        try:
            while not self.stopped.is_set():
                block = os.read(self.process.stderr.fileno(), 4096)
                if not block:
                    return
                # Count and discard; exceptions/logs from a dependency may contain private text.
                self.metrics.stderr_bytes += len(block)
        except OSError:
            self._fail("OCR stderr pipe failed")

    def _receive(self, deadline: float, check: Check) -> dict:
        while True:
            self.check()
            check()
            if time.monotonic() >= deadline:
                raise OcrError("CPU OCR worker timed out")
            if not self.errors.empty():
                raise OcrError(self.errors.get_nowait())
            try:
                raw = self.messages.get(timeout=0.05)
            except queue.Empty:
                if not self.errors.empty():
                    raise OcrError(self.errors.get_nowait())
                if self.output_done.is_set():
                    raise OcrError("CPU OCR worker exited without a response")
                continue
            try:
                payload = json.loads(raw)
                if isinstance(payload, dict) and payload.get("status") == "error":
                    error_type = payload.get("error_type")
                    if isinstance(error_type, str) and error_type.isidentifier():
                        self.metrics.worker_error = {"type": error_type, "trace": payload.get("trace", [])}
                    raise ValueError
                if not isinstance(payload, dict):
                    raise ValueError
                return payload
            except (ValueError, TypeError):
                raise OcrError("CPU OCR worker protocol or inference error") from None

    def _worker_metrics(self, payload: dict) -> None:
        metrics = payload.get("metrics")
        if (not isinstance(metrics, dict) or metrics.get("network_attempts") != 0
                or not isinstance(metrics.get("inference_calls"), dict)
                or metrics["inference_calls"].get("cls") != 0):
            raise OcrError("CPU OCR worker metrics/policy mismatch")
        self.metrics.last_worker = metrics

    def start(self) -> CpuOcrRuntime:
        self.check()
        if self.state != "new":
            raise OcrError("CPU OCR worker is not a fresh session")
        python = self.root / "env/python.exe"
        if not python.is_file():
            python = self.root / ("env/Scripts/python.exe" if os.name == "nt" else "env/bin/python")
        if not python.is_file() or not self.bridge.is_file() or not (self.root / "profile.json").is_file():
            raise OcrRuntimeMissing("CPU OCR runtime is missing; select an already installed runtime")
        if hashlib.sha256((self.root / "profile.json").read_bytes()).hexdigest() != self.profile_sha256:
            raise OcrError("CPU OCR profile hash mismatch")
        self.bridge_sha256 = hashlib.sha256(self.bridge.read_bytes()).hexdigest()
        try:
            self.jobs_root.mkdir(parents=True, exist_ok=True)
            self.temporary = tempfile.TemporaryDirectory(prefix="cpu-", dir=self.jobs_root)
            self.directory = Path(self.temporary.name)
            self.started = time.monotonic()
            self.state = "starting"
            self.process = subprocess.Popen(
                [str(python), "-I", str(self.bridge), "--root", str(self.root), "--job-dir", str(self.directory),
                 "--profile-sha256", self.profile_sha256], stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=child_environment(),
                creationflags=_NO_WINDOW, start_new_session=os.name != "nt",
            )
            for name, method in (("ocr-cpu-output", self._stdout), ("ocr-cpu-stderr", self._stderr)):
                reader = threading.Thread(target=copy_context().run, args=(method,), name=name)
                reader.start()
                self.readers.append(reader)
            health = self._receive(time.monotonic() + self.startup_timeout, lambda: None)
            if (health.get("status") != "ready" or health.get("protocol") != PROTOCOL
                    or health.get("profile_sha256") != self.profile_sha256
                    or health.get("bridge_sha256") != self.bridge_sha256
                    or health.get("provider") != "CPUExecutionProvider"):
                raise OcrError("CPU OCR worker identity mismatch")
            self._worker_metrics(health)
            self.state = "ready"
            return self
        except BaseException:
            self.close()
            raise

    def __call__(self, frame: RoiFrame, check: Check = lambda: None) -> EngineRead:
        if self.state != "ready" or self.directory is None or self.process is None or self.process.stdin is None:
            raise OcrError("CPU OCR worker is not ready")
        self.check()
        check()
        if self.metrics.requests >= self.max_requests:
            self.close()
            raise OcrError("CPU OCR request budget exhausted; review tracking before continuing")
        if len(frame.rgb) > 32 * 1024 * 1024:
            raise OcrError("CPU OCR ROI is too large")
        started = time.monotonic()
        self.metrics.requests += 1
        request_id = self.metrics.requests
        sha256 = hashlib.sha256(frame.rgb).hexdigest()
        try:
            with (self.directory / "frame.rgb").open("wb") as stream:
                for offset in range(0, len(frame.rgb), 1024 * 1024):
                    self.check()
                    check()
                    stream.write(frame.rgb[offset:offset + 1024 * 1024])
            request = {"op": "recognize", "request_id": request_id, "crop_sha256": sha256,
                       "width": frame.width, "height": frame.height}
            # One small request after the preceding response; never stream pixels into a blocked pipe.
            self.process.stdin.write(json.dumps(request).encode() + b"\n")
            self.process.stdin.flush()
            self.state = "waiting"
            deadline = time.monotonic() + self.timeout
            while True:
                response = self._receive(deadline, check)
                if response.get("request_id") != request_id:
                    raise OcrError("CPU OCR response/request mismatch")
                if response.get("status") == "inference":
                    calls = response.get("inference_calls")
                    if (not isinstance(calls, dict) or set(calls) != {"det", "rec", "cls"}
                            or any(type(v) is not int or v < 0 for v in calls.values()) or calls["cls"] != 0):
                        raise OcrError("CPU OCR inference policy mismatch")
                    self.metrics.started_inference_calls = calls
                    self.state = "inference"
                    continue
                if response.get("status") != "result" or response.get("crop_sha256") != sha256:
                    raise OcrError("CPU OCR result/crop mismatch")
                self._worker_metrics(response)
                try:
                    payload = response["result"]
                    result = EngineRead(tuple(ReadLine(line["text"], line["score"],
                                                       tuple(tuple(point) for point in line["box"]))
                                              for line in payload["lines"]), payload["revision"])
                    validate_read(result)
                    inference_s = float(payload["inference_s"])
                    if (result.revision != self.profile_sha256 or not math.isfinite(inference_s) or inference_s < 0
                            or any(not 0 <= x <= frame.width or not 0 <= y <= frame.height
                                   for line in result.lines for x, y in line.box)):
                        raise ValueError
                except (KeyError, TypeError, ValueError, OverflowError):
                    raise OcrError("Invalid CPU OCR result") from None
                self.metrics.inference_s += inference_s
                self.metrics.completed += 1
                self.state = "ready"
                return result
        except BaseException:
            self.close()
            raise
        finally:
            self.metrics.request_wall_s += time.monotonic() - started

    def close(self) -> None:
        if self.state == "closed":
            return
        self.stopped.set()
        try:
            if self.process is not None:
                stop_owned_process(self.process)
        finally:
            for reader in self.readers:
                reader.join(timeout=3)
            if any(reader.is_alive() for reader in self.readers):
                raise OcrError("CPU OCR reader did not stop")
            if self.process is not None:
                for stream in (self.process.stdin, self.process.stdout, self.process.stderr):
                    if stream:
                        stream.close()
            if self.temporary is not None:
                self.temporary.cleanup()
            if self.started:
                self.metrics.process_wall_s = time.monotonic() - self.started
            self.state = "closed"

    def __enter__(self) -> CpuOcrRuntime:
        return self.start()

    def __exit__(self, *_args) -> None:
        self.close()

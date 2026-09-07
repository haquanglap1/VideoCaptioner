"""One hidden, offline aligner process per job; no model imports in the host."""

from __future__ import annotations

import io
import json
import os
import queue
import subprocess
import tempfile
import threading
import time
import wave
from contextvars import copy_context
from dataclasses import dataclass
from pathlib import Path

from videocaptioner.config import ROOT_PATH
from videocaptioner.core.utils.subprocess_helper import _NO_WINDOW, child_environment

from .audio import Check, stop_process
from .contract import MAX_AUDIO_MS, MODEL_REVISION, POLICY, AlignmentError, chinese_language


@dataclass(frozen=True)
class RuntimeLayout:
    root: Path
    python: Path
    bridge: Path
    model: Path


def locate_runtime(root: Path | None = None) -> RuntimeLayout:
    root = root or Path(os.environ.get("VIDEOCAPTIONER_ALIGNMENT_RUNTIME", "") or
                        Path(ROOT_PATH) / "runtime" / "alignment")
    if (root / ".failed").exists():
        raise AlignmentError("runtime installation failed; rebuild in a new directory")
    if (root / ".installing").exists():
        raise AlignmentError("runtime downloading")
    python = root / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    bridge = root / "bridge.py"
    model = root / "model"
    if not all(p.is_file() for p in (python, bridge, root / "runtime-manifest.json")):
        raise AlignmentError("runtime missing; run scripts/build_alignment_runtime.py")
    try:
        manifest = json.loads((root / "runtime-manifest.json").read_text(encoding="utf-8"))
        if (manifest["model_revision"] != MODEL_REVISION or manifest["policy"] != POLICY or
                manifest["protocol"] != "alignment-v1" or not (model / "config.json").is_file()):
            raise ValueError
    except (ValueError, KeyError, OSError, TypeError):
        raise AlignmentError("runtime manifest or model invalid") from None
    return RuntimeLayout(root, python, bridge, model)


class AlignmentRuntime:
    def __init__(self, layout: RuntimeLayout | None = None, timeout: float = 180):
        self.layout = layout or locate_runtime()
        self.timeout = timeout
        self.process: subprocess.Popen | None = None
        self.reader: threading.Thread | None = None
        self.messages: queue.Queue = queue.Queue()
        self.state = "stopped"
        self.metrics: dict = {}

    def _receive(self, check: Check) -> dict:
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            check()
            try:
                line = self.messages.get(timeout=0.1)
            except queue.Empty:
                if self.process is None or self.process.poll() is not None:
                    raise AlignmentError("runtime exited")
                continue
            try:
                payload = json.loads(line)
                if not isinstance(payload, dict) or payload.get("status") != "ready":
                    raise ValueError
                return payload
            except (ValueError, TypeError):
                raise AlignmentError("runtime inference or protocol error") from None
        raise AlignmentError("runtime timeout")

    def start(self, language: str, check: Check = lambda: None) -> None:
        chinese_language(language)
        check()
        if self.process is not None:
            raise AlignmentError("runtime already started")
        self.state = "starting"
        try:
            self.process = subprocess.Popen(
                [str(self.layout.python), "-I", str(self.layout.bridge), str(self.layout.model)],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                text=True, encoding="utf-8", bufsize=1, creationflags=_NO_WINDOW,
                env=child_environment({"HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1",
                                       "HF_HUB_DISABLE_TELEMETRY": "1", "TOKENIZERS_PARALLELISM": "false"}),
            )
            stream = self.process.stdout
            assert stream is not None

            def read():
                for line in stream:
                    self.messages.put(line)

            self.reader = threading.Thread(target=copy_context().run, args=(read,), daemon=True)
            self.reader.start()
            health = self._receive(check)
            if (health.get("revision") != MODEL_REVISION or health.get("policy") != POLICY or
                    health.get("language") != "Chinese"):
                raise AlignmentError("runtime health mismatch")
            self.state = "ready"
        except (OSError, ValueError) as exc:
            self.close()
            self.state = "error"
            if isinstance(exc, AlignmentError):
                raise
            raise AlignmentError("runtime startup failed") from None
        except BaseException:
            self.close()
            self.state = "error"
            raise

    def align(self, audio: bytes, text: str, check: Check = lambda: None) -> list[dict]:
        if self.state != "ready" or self.process is None or self.process.stdin is None:
            raise AlignmentError("runtime not ready")
        try:
            check()
            try:
                with wave.open(io.BytesIO(audio), "rb") as stream:
                    if (stream.getframerate() != 16000 or stream.getnchannels() != 1 or
                            stream.getsampwidth() != 2 or not 0 < stream.getnframes() <= MAX_AUDIO_MS * 16):
                        raise AlignmentError("alignment input must be mono PCM16 16kHz and at most five minutes")
            except (wave.Error, EOFError):
                raise AlignmentError("invalid alignment WAV") from None
            with tempfile.TemporaryDirectory(prefix="vc-align-request-") as directory:
                root = Path(directory)
                (root / "audio.wav").write_bytes(audio)
                (root / "request.json").write_text(json.dumps({"text": text}), encoding="utf-8")
                self.process.stdin.write(json.dumps({"directory": str(root)}) + "\n")
                self.process.stdin.flush()
                self.metrics = self._receive(check)
                output = root / "result.json"
                if output.stat().st_size > 4_000_000:
                    raise AlignmentError("oversized runtime response")
                result = json.loads(output.read_text(encoding="utf-8"))
                if not isinstance(result, list):
                    raise AlignmentError("malformed runtime spans")
                return result
        except (OSError, ValueError) as exc:
            self.close()
            self.state = "error"
            if isinstance(exc, AlignmentError):
                raise
            raise AlignmentError("runtime response unavailable or invalid") from None
        except BaseException:
            self.close()
            self.state = "error"
            raise

    def close(self) -> None:
        if self.process is not None:
            stop_process(self.process)
            if self.reader is not None:
                self.reader.join(timeout=3)
            for stream in (self.process.stdin, self.process.stdout):
                if stream is not None:
                    stream.close()
            self.process = None
        self.state = "stopped"

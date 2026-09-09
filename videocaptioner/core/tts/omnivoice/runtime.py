"""One pinned OmniVoice worker per dubbing job; cooperative cancellation and GPU ownership."""

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import time
import wave
from contextlib import contextmanager
from threading import Lock
from uuid import uuid4

from videocaptioner.core.asr.alignment.audio import stop_process
from videocaptioner.core.utils.gpu_lease import GPULease
from videocaptioner.core.utils.subprocess_helper import _NO_WINDOW, StreamReader, child_environment

from .config import CODE_REVISION, MODEL_REVISION, POLICY, resources, runtime_root
from .prepare import digest, verify


class OmniVoiceRuntime:
    def __init__(self):
        self.process = None
        self.reader = None
        self.scratch = None
        self.log = None
        self.job_lock = Lock()
        self.request_lock = Lock()
        self.lease = GPULease()
        self.check = lambda: None
        self.timeout = 300
        self.options = None

    def _receive(self):
        deadline = time.monotonic() + self.timeout
        while True:
            self.check()
            if time.monotonic() >= deadline:
                raise RuntimeError("OmniVoice request timed out")
            if self.reader is None or self.process is None:
                raise RuntimeError("OmniVoice is not running")
            item = self.reader.get_output(timeout=0.1)
            if item and item[1].startswith("VC_OMNI "):
                result = json.loads(item[1][8:])
                if result.get("status") == "error":
                    raise RuntimeError(f"OmniVoice synthesis failed ({result.get('error_type', 'worker error')})")
                return result
            if self.process.poll() is not None:
                raise RuntimeError("OmniVoice worker stopped; check runtime compatibility and GPU memory")

    def request(self, payload):
        if self.process is None or self.process.stdin is None:
            raise RuntimeError("OmniVoice runtime is not acquired for this job")
        try:
            self.check()
            self.process.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
            self.process.stdin.flush()
            return self._receive()
        except BaseException:
            # After timeout/cancellation a late reply must never become the next
            # utterance's result. End this worker before another request can run.
            self.close()
            raise

    @contextmanager
    def acquire(self, config, callback=None):
        if not self.job_lock.acquire(blocking=False):
            raise RuntimeError("OmniVoice is busy with another dubbing job")
        original_identity = config.managed_tts_identity
        original_language = (config.target_language, config.strip_cjk)
        settings = config.tts_config
        original_tts = (settings.model, settings.sample_rate, settings.response_format) if settings else None
        try:
            if settings is None:
                raise ValueError("OmniVoice requires TTS configuration")
            options = config.omnivoice
            config.target_language = options.language
            if options.language.lower().startswith(("zh", "ja", "ko", "yue", "cmn", "chinese", "japanese", "korean")):
                config.strip_cjk = False
            self.options, self.timeout = options, options.timeout
            self.check = lambda: callback(10, "OmniVoice: preparing / synthesizing") if callback else None
            root = runtime_root(options.runtime)
            verify(root, self.check)
            self.scratch = tempfile.TemporaryDirectory(prefix="vc-omnivoice-")
            from pathlib import Path
            scratch = Path(self.scratch.name)
            reference = ""
            reference_hash = ""
            if options.reference_audio:
                path = Path(options.reference_audio)
                if not path.is_file() or path.stat().st_size > 50 * 1024 * 1024:
                    raise ValueError("Choose a reference audio file smaller than 50 MiB")
                snapshot = scratch / ("reference" + path.suffix)
                shutil.copyfile(path, snapshot)
                reference = str(snapshot)
                reference_hash = digest(snapshot, self.check)
            self.lease.acquire()
            self.log = (scratch / "worker.log").open("wb")
            env = child_environment({"HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1",
                                     "HF_HUB_DISABLE_IMPLICIT_TOKEN": "1", "PYTHONIOENCODING": "utf-8"})
            python = root / "env" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
            self.process = subprocess.Popen([str(python), "-u", str(resources() / "worker.py"),
                "--model", str(root / "model"), "--scratch", str(scratch)],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.log, text=True, encoding="utf-8",
                env=env, creationflags=_NO_WINDOW)
            self.reader = StreamReader(self.process)
            self.reader.start_reading()
            ready = self._receive()
            if ready.get("status") != "ready" or ready.get("sample_rate") != 24000:
                raise RuntimeError("Unexpected OmniVoice worker format")
            self.request({"operation": "configure", "reference_audio": reference, "reference_text": options.reference_text})
            settings.model, settings.sample_rate, settings.response_format = f"omnivoice:{MODEL_REVISION}", 24000, "wav"
            config.managed_tts_identity = {"provider": "omnivoice-local", "policy": POLICY,
                "code_revision": CODE_REVISION, "model_revision": MODEL_REVISION, "steps": options.steps,
                "bridge_sha256": digest(resources() / "worker.py"),
                "seed": options.seed, "language": options.language, "reference_sha256": reference_hash,
                "reference_text_sha256": hashlib.sha256(options.reference_text.encode()).hexdigest()}
            yield self
        finally:
            self.close()
            config.managed_tts_identity = original_identity
            config.target_language, config.strip_cjk = original_language
            if settings and original_tts:
                settings.model, settings.sample_rate, settings.response_format = original_tts
            self.job_lock.release()

    def synthesize(self, text, output, *, voice="auto", speed=1.0):
        from pathlib import Path
        with self.request_lock:
            if self.scratch is None or self.options is None:
                raise RuntimeError("OmniVoice is not acquired")
            temporary = Path(self.scratch.name) / (uuid4().hex + ".wav")
            try:
                result = self.request({"operation": "synthesize", "text": text, "output": str(temporary),
                    "language": self.options.language, "voice": voice or "auto", "speed": speed,
                    "steps": self.options.steps, "seed": self.options.seed})
                if result.get("status") != "complete":
                    raise RuntimeError("Incomplete OmniVoice response")
                with wave.open(str(temporary)) as wav:
                    if wav.getframerate() != 24000 or wav.getnchannels() != 1 or wav.getnframes() <= 0:
                        raise RuntimeError("Invalid OmniVoice WAV output")
                    duration = wav.getnframes() / wav.getframerate()
                self.check()
                shutil.copyfile(temporary, output)
                return duration
            finally:
                temporary.unlink(missing_ok=True)

    def close(self):
        if self.process:
            stop_process(self.process)
            if self.reader:
                for thread in self.reader.threads:
                    thread.join(timeout=1)
            for pipe in (self.process.stdin, self.process.stdout):
                if pipe:
                    pipe.close()
            self.process = None
        self.reader = None
        if self.log:
            self.log.close()
            self.log = None
        if self.scratch:
            self.scratch.cleanup()
            self.scratch = None
        self.lease.close()
        self.options = None
        self.check = lambda: None


_service = OmniVoiceRuntime()


def get_omnivoice_service():
    return _service

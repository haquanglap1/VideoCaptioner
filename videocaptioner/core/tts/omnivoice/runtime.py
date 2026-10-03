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
from videocaptioner.core.utils.gpu_lease import GPULease, current_gpu_job
from videocaptioner.core.utils.subprocess_helper import _NO_WINDOW, StreamReader, child_environment

from .config import CODE_REVISION, MODEL_REVISION, POLICY, resources, runtime_root
from .effects import POLICY as EFFECTS_POLICY
from .effects import apply_effects
from .prepare import digest, verify
from .prompt_cache import PromptCache
from .voices import ALIASES, resolve_voice


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
        self.voice = ""
        self.metrics = {}

    def _receive(self, *, request_id=None, on_event=None):
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
                if request_id is not None and result.get("request_id") != request_id:
                    raise RuntimeError("OmniVoice response ID mismatch")
                if on_event and result.get("status") in ("item", "fallback", "metrics"):
                    on_event(result)
                    continue
                if result.get("status") == "error":
                    raise RuntimeError(f"OmniVoice synthesis failed ({result.get('error_type', 'worker error')})")
                return result
            if self.process.poll() is not None:
                raise RuntimeError("OmniVoice worker stopped; check runtime compatibility and GPU memory")

    def request(self, payload, on_event=None):
        if self.process is None or self.process.stdin is None:
            raise RuntimeError("OmniVoice runtime is not acquired for this job")
        try:
            self.check()
            self.process.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
            self.process.stdin.flush()
            return self._receive(request_id=payload.get("request_id"), on_event=on_event)
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
            self.voice = settings.voice or "auto"
            if self.voice == "reference" and not options.reference_audio:
                raise ValueError("Chọn audio giọng mẫu và nhập đúng lời mẫu trước khi lồng tiếng.")
            self.check = lambda: callback(10, "OmniVoice: preparing / synthesizing") if callback else None
            root = runtime_root(options.runtime)
            self.metrics = {}
            started = time.monotonic()
            verify(root, self.check)
            self.metrics["verify_seconds"] = time.monotonic() - started
            self.scratch = tempfile.TemporaryDirectory(prefix="vc-omnivoice-")
            from pathlib import Path
            scratch = Path(self.scratch.name)
            reference = ""
            reference_hash = ""
            reference_audio, reference_text = options.reference_audio, options.reference_text
            profile = None if reference_audio else resolve_voice(self.voice)
            if profile:
                reference_audio, reference_text = str(profile.audio_path), profile.transcript
            if reference_audio:
                path = Path(reference_audio)
                if not path.is_file() or path.stat().st_size > 50 * 1024 * 1024:
                    raise ValueError("Choose a reference audio file smaller than 50 MiB")
                snapshot = scratch / ("reference" + path.suffix)
                shutil.copyfile(path, snapshot)
                reference = str(snapshot)
                reference_hash = digest(snapshot, self.check)
                if profile and reference_hash != profile.sha256:
                    raise ValueError("OmniVoice reference changed while starting the job")
            self.lease.acquire()
            self.log = (scratch / "worker.log").open("wb")
            env = child_environment({"HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1",
                                     "HF_HUB_DISABLE_IMPLICIT_TOKEN": "1", "PYTHONIOENCODING": "utf-8"})
            python = root / "env" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
            if os.name == "nt" and (root / "env/python.exe").is_file():
                python = root / "env/python.exe"
            self.process = subprocess.Popen([str(python), "-u", str(resources() / "worker.py"),
                "--model", str(root / "model"), "--scratch", str(scratch)],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.log, text=True, encoding="utf-8",
                env=env, creationflags=_NO_WINDOW)
            self.reader = StreamReader(self.process)
            self.reader.start_reading()
            started = time.monotonic()
            ready = self._receive()
            self.metrics["worker_start_seconds"] = time.monotonic() - started
            if ready.get("status") != "ready" or ready.get("sample_rate") != 24000:
                raise RuntimeError("Unexpected OmniVoice worker format")
            self.metrics.update(ready.get("metrics", {}))
            prompt_identity = {"schema": "omnivoice-prompt-v1", "code_revision": CODE_REVISION,
                "model_revision": MODEL_REVISION, "recipe_sha256": digest(resources() / "recipe.json")
                if (resources() / "recipe.json").exists() else "",
                "worker_sha256": digest(resources() / "worker.py"), "dtype": "float16",
                "preprocess_prompt": True, "reference_sha256": reference_hash,
                "reference_text_sha256": hashlib.sha256(reference_text.encode()).hexdigest()}
            prompt_cache = PromptCache(prompt_identity)
            prompt_file = scratch / "prompt.json"
            if reference:
                prompt_cache.restore(prompt_file)
            configured = self.request({"operation": "configure", "reference_audio": reference,
                "reference_text": reference_text, "prompt_file": str(prompt_file)})
            if configured.get("status") != "configured":
                raise RuntimeError("OmniVoice reference configuration failed")
            self.metrics.update(configured.get("metrics", {}))
            if reference and prompt_file.exists():
                self.metrics["prompt_cache_saved"] = prompt_cache.store(prompt_file)
            settings.model, settings.sample_rate, settings.response_format = f"omnivoice:{MODEL_REVISION}", 24000, "wav"
            config.managed_tts_identity = {"provider": "omnivoice-local", "policy": POLICY,
                "code_revision": CODE_REVISION, "model_revision": MODEL_REVISION, "steps": options.effective_steps,
                "dtype": "float16", "preprocess_prompt": True,
                "recipe_sha256": prompt_identity["recipe_sha256"],
                "batch_size": options.batch_size, "batch_max_chars": options.batch_max_chars,
                "rng_policy": "ordered-batch-v1-first-valid-wav", "fallback_policy": "bisect-v1",
                "bridge_sha256": digest(resources() / "worker.py"),
                "seed": options.seed, "language": options.language, "reference_sha256": reference_hash,
                "reference_text_sha256": hashlib.sha256(reference_text.encode()).hexdigest()}
            if options.pitch_semitones or options.punctuation_pause_ms:
                config.managed_tts_identity.update(effects_policy=EFFECTS_POLICY,
                    pitch_semitones=options.pitch_semitones, punctuation_pause_ms=options.punctuation_pause_ms)
            if profile:
                config.managed_tts_identity["voice_profile_id"] = profile.voice_id
            yield self
        finally:
            self.close()
            config.managed_tts_identity = original_identity
            config.target_language, config.strip_cjk = original_language
            if settings and original_tts:
                settings.model, settings.sample_rate, settings.response_format = original_tts
            self.job_lock.release()

    def synthesize_batch(self, items, on_result, *, voice="auto", speed=1.0):
        """Own the pipe until all IDs finish; publish valid items before a later cancellation."""
        from pathlib import Path
        with self.request_lock:
            if self.scratch is None or self.options is None:
                raise RuntimeError("OmniVoice is not acquired")
            if ALIASES.get(voice, voice) != ALIASES.get(self.voice, self.voice):
                raise ValueError("OmniVoice uses one selected voice per job")
            if not items or len(items) > self.options.batch_size:
                raise ValueError("OmniVoice batch exceeds configured size")
            if len(items) > 1 and max(len(text) for _, text, _ in items) * len(items) > self.options.batch_max_chars:
                raise ValueError("OmniVoice batch exceeds character budget")
            pending = {item_id: (text, destination) for item_id, text, destination in items}
            if len(pending) != len(items):
                raise ValueError("Duplicate OmniVoice item ID")
            paths = {item_id: Path(self.scratch.name) / (uuid4().hex + ".wav") for item_id in pending}
            warnings = {item_id: [] for item_id in pending}
            request_id = uuid4().hex

            def receive(event):
                if event["status"] == "metrics":
                    self.metrics.setdefault("inference", []).append(event["metrics"])
                    return
                if event["status"] == "fallback":
                    reason = event.get("reason", "worker error")
                    for item_id in event.get("ids", []):
                        if item_id not in pending:
                            raise RuntimeError("OmniVoice fallback ID mismatch")
                        warnings[item_id].append(f"OmniVoice {reason}: batch {event['batch_size']} split for retry")
                    return
                item_id = event.get("id")
                if item_id not in pending:
                    raise RuntimeError("OmniVoice duplicate or unknown result ID")
                text, destination = pending.pop(item_id)
                error = event.get("error_type", "")
                duration = 0.0
                if not error:
                    try:
                        self._validate_wav(paths[item_id])
                        apply_effects(paths[item_id], destination, text, self.options, self.check)
                        duration = self._validate_wav(destination)
                    except (OSError, EOFError, wave.Error, RuntimeError):
                        error = "InvalidWAV"
                on_result(item_id, duration, error, warnings[item_id])

            try:
                result = self.request({"operation": "synthesize_batch", "request_id": request_id,
                    "items": [{"id": item_id, "text": text, "output": str(paths[item_id])}
                              for item_id, text, _destination in items],
                    "language": self.options.language, "voice": voice or "auto", "speed": speed,
                    "steps": self.options.effective_steps, "seed": self.options.seed}, on_event=receive)
                if result.get("status") != "complete" or pending or result.get("count") != len(items):
                    self.close()
                    raise RuntimeError("OmniVoice incomplete batch result count")
            finally:
                for path in paths.values():
                    path.unlink(missing_ok=True)

    @staticmethod
    def _validate_wav(path):
        with wave.open(str(path)) as wav:
            if (wav.getframerate() != 24000 or wav.getnchannels() != 1 or wav.getsampwidth() != 2
                or wav.getnframes() <= 0):
                raise RuntimeError("Invalid OmniVoice WAV output")
            wav.setpos(wav.getnframes() - 1)
            if len(wav.readframes(1)) != 2:
                raise RuntimeError("Truncated OmniVoice WAV output")
            return wav.getnframes() / wav.getframerate()

    def synthesize(self, text, output, *, voice="auto", speed=1.0):
        from pathlib import Path
        with self.request_lock:
            if self.scratch is None or self.options is None:
                raise RuntimeError("OmniVoice is not acquired")
            if ALIASES.get(voice, voice) != ALIASES.get(self.voice, self.voice):
                raise ValueError("OmniVoice uses one selected voice per job; start a separate job to change voice.")
            temporary = Path(self.scratch.name) / (uuid4().hex + ".wav")
            try:
                result = self.request({"operation": "synthesize", "text": text, "output": str(temporary),
                    "language": self.options.language, "voice": voice or "auto", "speed": speed,
                    "steps": self.options.effective_steps, "seed": self.options.seed})
                self.metrics.setdefault("inference", []).append(result.get("metrics", {}))
                if result.get("status") != "complete":
                    raise RuntimeError("Incomplete OmniVoice response")
                self._validate_wav(temporary)
                self.check()
                apply_effects(temporary, output, text, self.options, self.check)
                return self._validate_wav(output)
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
        self.voice = ""
        self.check = lambda: None


_service = OmniVoiceRuntime()


def get_omnivoice_service():
    job = current_gpu_job()
    if job is not None:
        return job.service("omnivoice", OmniVoiceRuntime)
    return _service

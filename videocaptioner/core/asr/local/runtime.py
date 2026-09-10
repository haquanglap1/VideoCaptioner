"""Pinned local runtimes, with bounded request ownership and no GPU imports in Qt."""

from __future__ import annotations

import hashlib
import json
import os
import queue
import subprocess
import tempfile
import threading
import time
from contextvars import copy_context
from dataclasses import dataclass
from pathlib import Path

from videocaptioner.config import ROOT_PATH, portable_models_path
from videocaptioner.core.utils.gpu_lease import GPULease
from videocaptioner.core.utils.subprocess_helper import _NO_WINDOW, child_environment

from ..alignment.audio import Check, stop_process
from .profiles import MODELS, PROTOCOL, LocalModel


class LocalRuntimeError(ValueError):
    """Safe error text, without provider output, credentials or media paths."""


class LocalRuntimeTimeout(LocalRuntimeError):
    """A bounded request can be retried with smaller recognition windows."""


class LocalRuntimeGenerationLimit(LocalRuntimeError):
    """No complete text was produced, but the model remains loaded for a retry."""


# The previous bundled bridge used the same protocol, recipe and checkpoint layout.
# Run current bundled code against that verified environment without rewriting it.
LEGACY_BRIDGE_SHA256 = "d8de7fce52e46ff19d3398ca78312a654170c47505dd38a8f51f74e6bb7e82ff"


def recipe_directory() -> Path:
    return Path(__file__).resolve().parents[3] / "resources" / "local_asr"


def file_hash(path: Path, *, check: Check = lambda: None) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            check()
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class LocalLayout:
    root: Path
    python: Path
    bridge: Path
    model_path: Path
    model: LocalModel


def default_root(runtime: str) -> Path:
    variable = "VIDEOCAPTIONER_QWEN_RUNTIME" if runtime == "qwen" else "VIDEOCAPTIONER_DIARIZATION_RUNTIME"
    packaged = portable_models_path(Path(ROOT_PATH))
    default = packaged / runtime if packaged else Path(ROOT_PATH) / "runtime" / f"local-{runtime}"
    return Path(os.environ.get(variable, "") or default)


def locate(model_id: str, root: str | Path = "", *, verify: bool = False, check: Check = lambda: None) -> LocalLayout:
    """Read installed state only; preparation is explicit in the job's core path."""
    try:
        return _locate_exact(model_id, root, verify=verify, check=check)
    except LocalRuntimeError as initial_error:
        failure = initial_error
        for candidate in (managed_root(model_id, root), _managed_root(model_id, root, LEGACY_BRIDGE_SHA256)):
            if candidate.exists():
                try:
                    return _locate_exact(model_id, candidate, verify=verify, check=check)
                except LocalRuntimeError as candidate_error:
                    failure = candidate_error
                    check()
        raise failure


def managed_root(model_id: str, root: str | Path = "") -> Path:
    return _managed_root(model_id, root, file_hash(recipe_directory() / "bridge.py"))


def _managed_root(model_id: str, root: str | Path, bridge_hash: str) -> Path:
    model = MODELS[model_id]
    base = Path(root) if root else default_root(model.runtime)
    recipe = recipe_directory()
    fingerprint = hashlib.sha256((file_hash(recipe / f"{model.runtime}.lock") +
                                  file_hash(recipe / f"{model.runtime}.json") +
                                  bridge_hash).encode()).hexdigest()[:12]
    return base.parent / f"{base.name}-managed" / f"{model_id}-{model.revision[:12]}-{fingerprint}"


def _locate_exact(model_id: str, root: str | Path = "", *, verify: bool = False,
                  check: Check = lambda: None, preparing: bool = False) -> LocalLayout:
    model = MODELS[model_id]
    root = Path(root) if root else default_root(model.runtime)
    if (root / ".failed").exists():
        raise LocalRuntimeError("Local runtime failed installation; choose a new destination.")
    if not preparing and (root / ".installing").exists():
        raise LocalRuntimeError("Local runtime incomplete: installation is in progress.")
    python = root / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if os.name == "nt" and (root / "python.exe").is_file():
        python = root / "python.exe"
    recipe = recipe_directory()
    try:
        manifest = json.loads((root / "runtime-manifest.json").read_text(encoding="utf-8"))
        expected = json.loads((recipe / f"{model.runtime}.json").read_text(encoding="utf-8"))
        if (manifest["protocol"] != PROTOCOL or manifest["recipe"] != expected or not python.is_file() or
                manifest["lock_sha256"] != file_hash(recipe / f"{model.runtime}.lock") or
                file_hash(root / "requirements.lock") != manifest["lock_sha256"] or
                file_hash(root / "bridge.py") not in (file_hash(recipe / "bridge.py"), LEGACY_BRIDGE_SHA256)):
            raise ValueError
        inventory = manifest["models"][model_id]
        if inventory["revision"] != model.revision or inventory["repository"] != model.repository or not inventory["files"]:
            raise ValueError
        required = ({"config.yaml", "embedding/pytorch_model.bin", "segmentation/pytorch_model.bin",
                     "plda/plda.npz", "plda/xvec_transform.npz"} if model_id == "community-1" else
                    {"config.json", "preprocessor_config.json", "tokenizer_config.json", "vocab.json", "merges.txt"})
        if not required.issubset(inventory["files"]) or (model_id != "community-1" and
                not any(name.endswith(".safetensors") for name in inventory["files"])):
            raise ValueError
        model_path = root / "models" / model_id
        for relative, info in inventory["files"].items():
            check()
            path = model_path / relative
            if (not path.resolve().is_relative_to(model_path.resolve()) or not path.is_file() or
                    path.stat().st_size != info["size"] or not isinstance(info["sha256"], str) or len(info["sha256"]) != 64):
                raise ValueError
            if verify and file_hash(path, check=check) != info["sha256"]:
                raise ValueError
        if model_id == "qwen-1.7b":
            index = json.loads((model_path / "model.safetensors.index.json").read_text(encoding="utf-8"))
            if not set(index["weight_map"].values()).issubset(inventory["files"]):
                raise ValueError
    except LocalRuntimeError:
        raise
    except (KeyError, ValueError, TypeError, OSError):
        raise LocalRuntimeError(f"{model_id}: runtime/model missing, incomplete or manifest mismatch. Use local-asr install explicitly.") from None
    return LocalLayout(root, python, recipe / "bridge.py", model_path, model)


def offline_environment() -> dict[str, str]:
    env = child_environment({"HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1",
                             "HF_HUB_DISABLE_TELEMETRY": "1", "HF_HUB_DISABLE_IMPLICIT_TOKEN": "1",
                             "PYANNOTE_METRICS_ENABLED": "0", "TOKENIZERS_PARALLELISM": "false"})
    for key in tuple(env):
        if key.upper() in ("HF_TOKEN", "HUGGING_FACE_HUB_TOKEN", "HUGGINGFACE_TOKEN", "PYANNOTE_API_KEY"):
            del env[key]
    return env


class LocalRuntime:
    def __init__(self, layout: LocalLayout, timeout: float = 180):
        if not 0 < timeout <= 3600:
            raise ValueError("Invalid local runtime deadline.")
        self.layout, self.timeout = layout, timeout
        self.process: subprocess.Popen | None = None
        self.reader: threading.Thread | None = None
        self.messages: queue.Queue = queue.Queue()
        self.state = "stopped"
        self.metrics: dict = {}
        self.lease = GPULease()

    def _receive(self, check: Check) -> dict:
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            check()
            try:
                value = json.loads(self.messages.get(timeout=0.1))
            except queue.Empty:
                if self.process is None or self.process.poll() is not None:
                    raise LocalRuntimeError("Local runtime exited before completing the stage.")
                continue
            except (ValueError, TypeError):
                raise LocalRuntimeError("Local runtime protocol error.") from None
            if isinstance(value, dict) and value.get("status") in ("ready", "incomplete"):
                if (value.get("protocol") != PROTOCOL or value.get("revision") != self.layout.model.revision or
                        value.get("model") != self.layout.model.id):
                    raise LocalRuntimeError("Local runtime health identity mismatch.")
                if value["status"] == "incomplete" and (self.state != "busy" or
                        not self.layout.model.id.startswith("qwen-") or value.get("reason") != "generation-limit"):
                    raise LocalRuntimeError("Local runtime protocol error.")
                return value
            reason = value.get("reason") if isinstance(value, dict) else ""
            if reason == "oom":
                raise LocalRuntimeError("GPU out of memory. Close idle GPU workloads or explicitly select the smaller model; no model was changed.")
            raise LocalRuntimeError("Local runtime inference or protocol error.")
        raise LocalRuntimeTimeout("Local runtime stage timed out; its process was stopped.")

    def start(self, check: Check = lambda: None):
        if self.process is not None:
            raise LocalRuntimeError("Local runtime already started.")
        self.messages = queue.Queue()
        self.state = "loading"
        try:
            check()
            self.lease.acquire()
            self.process = subprocess.Popen(
                [str(self.layout.python), "-I", str(self.layout.bridge), str(self.layout.root), self.layout.model.id],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                text=True, encoding="utf-8", bufsize=1, creationflags=_NO_WINDOW, env=offline_environment())
            stream = self.process.stdout
            assert stream is not None

            def read():
                for line in stream:
                    self.messages.put(line)

            self.reader = threading.Thread(target=copy_context().run, args=(read,), daemon=True)
            self.reader.start()
            self.metrics = self._receive(check)
            self.state = "ready"
        except BaseException:
            self.close()
            self.state = "error"
            raise

    def request(self, audio: bytes, text: str = "", check: Check = lambda: None):
        if self.state != "ready" or self.process is None or self.process.stdin is None:
            raise LocalRuntimeError("Local runtime is not ready.")
        try:
            self.state = "busy"
            check()
            with tempfile.TemporaryDirectory(prefix="vc-local-request-") as directory:
                root = Path(directory)
                (root / "audio.wav").write_bytes(audio)
                (root / "request.json").write_text(json.dumps({"text": text}), encoding="utf-8")
                self.process.stdin.write(json.dumps({"directory": str(root)}) + "\n")
                self.process.stdin.flush()
                self.metrics = self._receive(check)
                check()
                if self.metrics["status"] == "incomplete":
                    raise LocalRuntimeGenerationLimit("Recognition generation did not finish within its audio-sized budget; no partial text was accepted.")
                output = root / "result.json"
                if output.stat().st_size > 32_000_000:
                    raise LocalRuntimeError("Local result exceeds the response limit.")
                result = json.loads(output.read_text(encoding="utf-8"))
                self.state = "ready"
                return result
        except LocalRuntimeGenerationLimit:
            self.state = "ready"
            raise
        except BaseException:
            self.close()
            self.state = "error"
            raise

    def close(self):
        try:
            if self.process is not None:
                stop_process(self.process)
                if self.reader is not None:
                    self.reader.join(timeout=3)
                for stream in (self.process.stdin, self.process.stdout):
                    if stream is not None:
                        stream.close()
                self.process = None
        finally:
            self.lease.close()
            self.state = "stopped"

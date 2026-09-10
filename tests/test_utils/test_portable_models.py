"""Portable model lookup and copying do not depend on the developer checkout."""

import json

import pytest

from scripts.package_test_models import copy_payload, make_standalone_python
from videocaptioner.config import portable_models_path
from videocaptioner.core.asr import faster_whisper
from videocaptioner.core.asr.local import runtime
from videocaptioner.core.tts.omnivoice import config as omni_config
from videocaptioner.core.tts.vieneu.runtime_locator import VieNeuRuntimeLocator


def test_default_model_roots_follow_relocated_app(tmp_path, monkeypatch):
    app = tmp_path / "relocated-app"
    models = app / "models"
    assert portable_models_path(app) is None
    models.mkdir(parents=True)
    (models / "portable-models.json").write_text(json.dumps({"schema": "portable-models-v1"}))
    monkeypatch.setattr(runtime, "ROOT_PATH", app)
    monkeypatch.setattr(omni_config, "ROOT_PATH", app)
    for name in ("QWEN", "DIARIZATION", "OMNIVOICE"):
        monkeypatch.delenv(f"VIDEOCAPTIONER_{name}_RUNTIME", raising=False)
    assert portable_models_path(app) == models
    assert runtime.default_root("qwen") == models / "qwen"
    assert runtime.default_root("diarization") == models / "diarization"
    assert omni_config.runtime_root() == models / "omnivoice"
    explicit = tmp_path / "user-runtime"
    assert omni_config.runtime_root(str(explicit)) == explicit
    monkeypatch.setenv("VIDEOCAPTIONER_QWEN_RUNTIME", str(explicit))
    assert runtime.default_root("qwen") == explicit
    vieneu = models / "vieneu-runtime"
    (vieneu / "bridge").mkdir(parents=True)
    (vieneu / "python.exe").write_bytes(b"runtime")
    (vieneu / "bridge/vieneu_bridge.py").write_text("")
    assert VieNeuRuntimeLocator(app_root=app).locate().runtime_root == vieneu


def test_installed_faster_whisper_is_found_without_startup_path(tmp_path, monkeypatch):
    monkeypatch.setattr(faster_whisper, "FASTER_WHISPER_PATH", tmp_path)
    monkeypatch.setattr(faster_whisper.shutil, "which", lambda _: None)
    program = tmp_path / "faster-whisper-xxl.exe"
    program.write_bytes(b"x" * faster_whisper.MIN_PROGRAM_SIZE)
    assert faster_whisper.resolve_program(program.name, "cuda") == str(program)
    with pytest.raises(EnvironmentError):
        faster_whisper.resolve_program(str(tmp_path / "missing/explicit.exe"), "cuda")


def test_runtime_copy_materializes_python_and_preserves_existing_packages(tmp_path):
    environment, base, target = (tmp_path / name for name in ("env", "base", "target"))
    (environment / "Lib/site-packages").mkdir(parents=True)
    (environment / "Lib/site-packages/example.py").write_text("VALUE = 1")
    (environment / "pyvenv.cfg").write_text("home = old-machine")
    (environment / "install.log").write_text("not part of the application")
    (base / "Lib/site-packages").mkdir(parents=True)
    (base / "Lib/os.py").write_text("standard library")
    (base / "Lib/site-packages/private.py").write_text("must not copy base packages")
    (base / "python.exe").write_bytes(b"interpreter")
    copy_payload(environment, target)
    make_standalone_python(target, base)
    assert (target / "python.exe").read_bytes() == b"interpreter"
    assert (target / "Lib/os.py").is_file()
    assert (target / "Lib/site-packages/example.py").is_file()
    assert not (target / "Lib/site-packages/private.py").exists()
    assert not (target / "pyvenv.cfg").exists()
    assert not (target / "install.log").exists()
    assert (environment / "pyvenv.cfg").is_file()


def test_copy_refuses_to_overwrite_unrelated_payload(tmp_path):
    source, target = tmp_path / "source", tmp_path / "target"
    source.mkdir()
    target.mkdir()
    (source / "model.bin").write_bytes(b"new")
    (target / "model.bin").write_bytes(b"existing")
    with pytest.raises(ValueError, match="Conflicting"):
        copy_payload(source, target)
    assert (target / "model.bin").read_bytes() == b"existing"

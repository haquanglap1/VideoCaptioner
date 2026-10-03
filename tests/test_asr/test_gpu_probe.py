"""GPU-name probing must not open a console for every ASR job/cache lookup."""

import os
import subprocess
from types import SimpleNamespace

import pytest

from videocaptioner.core.asr import faster_whisper as fw


@pytest.mark.parametrize("name,expected", [("NVIDIA GeForce RTX 5090\n", True), ("NVIDIA RTX 4090\n", False)])
def test_gpu_probe_preserves_detection_and_hides_process(monkeypatch, name, expected):
    calls = []
    monkeypatch.setattr(fw.shutil, "which", lambda _: "nvidia-smi")
    monkeypatch.setenv("OPENAI_API_KEY", "fixture-private")
    def run(args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(returncode=0, stdout=name)
    monkeypatch.setattr(fw.subprocess, "run", run)
    assert fw.is_rtx_50_series() is expected
    args, options = calls[0]
    assert "--query-gpu=name" in args and options["timeout"] == 5
    assert "OPENAI_API_KEY" not in options["env"]
    if os.name == "nt":
        assert options["creationflags"] & subprocess.CREATE_NO_WINDOW


def test_failed_gpu_probe_is_nonfatal(monkeypatch):
    monkeypatch.setattr(fw.shutil, "which", lambda _: "nvidia-smi")
    def fail(*args, **kwargs):
        raise subprocess.TimeoutExpired("nvidia-smi", 5)
    monkeypatch.setattr(fw.subprocess, "run", fail)
    assert not fw.is_rtx_50_series()

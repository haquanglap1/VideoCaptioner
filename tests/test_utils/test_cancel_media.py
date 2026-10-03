"""Quiet native children must stop even before they print progress."""

import sys
import time

import pytest

from videocaptioner.core.asr.faster_whisper import FasterWhisperASR
from videocaptioner.core.utils.subprocess_helper import (
    _NO_WINDOW,
    child_environment,
    run_cancellable,
)


def test_quiet_faster_whisper_is_cancelled_and_reaped(tmp_path, monkeypatch):
    audio = tmp_path / "input.wav"
    audio.write_bytes(b"synthetic")
    asr = object.__new__(FasterWhisperASR)
    asr.audio_input = str(audio)
    monkeypatch.setattr(asr, "_build_command", lambda _: [sys.executable, "-c", "import time; time.sleep(30)"])
    started = time.monotonic()
    def callback(*_):
        if time.monotonic() - started > .3:
            raise RuntimeError("synthetic cancel")
    with pytest.raises(RuntimeError, match="synthetic cancel"):
        asr._run(callback)
    assert time.monotonic() - started < 5
    assert asr.process.poll() is not None


def test_quiet_media_run_cancels_before_completion(tmp_path):
    completion = tmp_path / "must-not-exist"
    started = time.monotonic()
    def check():
        if time.monotonic() - started > .3:
            raise RuntimeError("synthetic cancel")
    with pytest.raises(RuntimeError, match="synthetic cancel"):
        run_cancellable([sys.executable, "-c",
                         "import time,pathlib,sys; time.sleep(30); pathlib.Path(sys.argv[1]).touch()", str(completion)],
                        check_cancelled=check, capture_output=True, env=child_environment(), creationflags=_NO_WINDOW)
    assert time.monotonic() - started < 5 and not completion.exists()

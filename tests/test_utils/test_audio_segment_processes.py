"""Media wrappers preserve decoding while hiding helpers and excluding credentials."""

import io
import os
import shutil
import subprocess
import sys
import wave

import pytest

from videocaptioner.core.utils import audio_segment as audio
from videocaptioner.core.utils.subprocess_helper import SECRET_ENV_PREFIXES


def test_pydub_probe_decode_and_encode_use_hidden_scrubbed_processes(monkeypatch, tmp_path):
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        pytest.skip("FFmpeg/ffprobe required")
    raw = io.BytesIO()
    with wave.open(raw, "wb") as stream:
        stream.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
        stream.writeframes(b"\x01\x00" * 8000)
    original = subprocess.Popen
    calls = []
    def capture(*args, **kwargs):
        calls.append(kwargs.copy())
        return original(*args, **kwargs)
    monkeypatch.setattr(audio.subprocess, "Popen", capture)
    monkeypatch.setenv("OPENAI_API_KEY", "fixture-private")
    segment = audio.AudioSegment.from_file(io.BytesIO(raw.getvalue()))
    destination = tmp_path / "audio.mp3"
    segment.export(destination, format="mp3").close()
    assert len(segment) == 500 and destination.stat().st_size > 0
    assert len(calls) >= 3
    assert all(not any(key.upper().startswith(SECRET_ENV_PREFIXES) for key in call["env"]) for call in calls)
    if os.name == "nt":
        assert all(call["creationflags"] & subprocess.CREATE_NO_WINDOW for call in calls)


def test_pydub_wrapper_does_not_replace_global_popen():
    import pydub.audio_segment
    import pydub.utils

    assert pydub.audio_segment.subprocess is not subprocess
    assert pydub.utils.Popen is audio._popen
    assert subprocess.Popen is not audio._popen


@pytest.mark.skipif(os.name != "nt", reason="Windows console ownership")
def test_child_has_no_console_and_explicit_environment_is_scrubbed():
    process = audio._popen(
        [sys.executable, "-c", "import ctypes,os; print(ctypes.windll.kernel32.GetConsoleWindow()); print(os.getenv('OPENAI_API_KEY','absent'))"],
        env={**os.environ, "OPENAI_API_KEY": "fixture-private"},
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
    )
    stdout, stderr = process.communicate(timeout=20)
    assert process.returncode == 0, stderr
    assert stdout.splitlines() == ["0", "absent"]

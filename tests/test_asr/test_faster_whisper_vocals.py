"""Vocal separation must survive executable resolution and own its cache key."""

import io
import wave

import pytest

from videocaptioner.core.asr import faster_whisper as fw


@pytest.mark.parametrize(("name", "supported"), [
    ("faster-whisper-xxl.exe", True),
    ("Faster-Whisper-XXL.EXE", True),
    ("faster-whisper-xxl-r245.exe", True),
    ("faster-whisper.exe", False),
    ("faster_whisper.exe", False),
])
def test_resolved_program_preserves_vocal_filter_and_cache_identity(tmp_path, monkeypatch, name, supported):
    binary = str(tmp_path / "installed tools" / name)
    monkeypatch.setattr(fw, "resolve_program", lambda _configured, _device: binary)
    monkeypatch.setattr(fw, "is_rtx_50_series", lambda: False)
    monkeypatch.setattr("videocaptioner.core.asr.base.get_asr_cache", lambda: {})
    audio = io.BytesIO()
    with wave.open(audio, "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(16000)
        output.writeframes(b"\0\0" * 1600)
    engine = fw.FasterWhisperASR(audio.getvalue(), "selected-program", "large-v3", "models", ff_mdx_kim2=False)
    plain = engine._build_command("source.wav")
    plain_key = engine._get_key()
    engine.ff_mdx_kim2 = True
    filtered = engine._build_command("source.wav")
    assert filtered[0] == binary
    assert "--ff_mdx_kim2" not in plain
    assert ("--ff_mdx_kim2" in filtered) is supported
    assert (engine._get_key() != plain_key) is supported
    assert [arg for arg in filtered if arg != "--ff_mdx_kim2"] == plain

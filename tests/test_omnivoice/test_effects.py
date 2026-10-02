"""Real FFmpeg pitch at tempo1 and lossless added silence, independent of GPU synthesis."""

import math
import shutil
import struct
import subprocess
import wave

import pytest

from videocaptioner.core.tts.omnivoice.config import OmniVoiceOptions
from videocaptioner.core.tts.omnivoice.effects import apply_effects, terminal_pause_ms
from videocaptioner.core.utils.subprocess_helper import child_environment


def tone(path):
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(24000)
        output.writeframes(b"".join(struct.pack("<h", int(8000 * math.sin(2 * math.pi * 440 * i / 24000)))
            for i in range(48000)))


@pytest.mark.parametrize("text,milliseconds", [("Câu hỏi?", 240), ("Câu xong.”", 240),
    ("Phần đầu,", 120), ("Không dấu", 0), ("Giữ, nguyên dấu bên trong", 0)])
def test_terminal_pause_only(text, milliseconds):
    assert terminal_pause_ms(text, 120) == milliseconds


def test_default_is_byte_preserving_and_pause_keeps_every_frame(tmp_path):
    source, neutral, paused = (tmp_path / name for name in ("source.wav", "neutral.wav", "pause.wav"))
    tone(source)
    apply_effects(source, neutral, "Đủ lời.", OmniVoiceOptions())
    assert source.read_bytes() == neutral.read_bytes()
    apply_effects(source, paused, "Đủ lời.", OmniVoiceOptions(punctuation_pause_ms=120))
    with wave.open(str(source)) as a, wave.open(str(paused)) as b:
        assert b.getnframes() == a.getnframes() + 5760
        assert b.readframes(a.getnframes()) == a.readframes(a.getnframes())
        assert b.readframes(5760) == b"\0\0" * 5760


def test_pitch_changes_frequency_without_changing_tempo(tmp_path):
    if not shutil.which("ffmpeg"):
        pytest.skip("FFmpeg not available")
    filters = subprocess.run(["ffmpeg", "-hide_banner", "-filters"], env=child_environment(),
        capture_output=True, text=True).stdout
    if "rubberband" not in filters:
        pytest.skip("FFmpeg lacks rubberband")
    source, pitched = tmp_path / "source.wav", tmp_path / "pitch.wav"
    tone(source)
    apply_effects(source, pitched, "Đủ lời.", OmniVoiceOptions(pitch_semitones=2))
    with wave.open(str(pitched)) as audio:
        assert abs(audio.getnframes() - 48000) <= 24
        samples = struct.unpack("<" + "h" * audio.getnframes(), audio.readframes(audio.getnframes()))
    middle = samples[6000:42000]
    crossings = sum(a <= 0 < b for a, b in zip(middle, middle[1:]))
    frequency = crossings / (len(middle) / 24000)
    assert abs(frequency - 440 * 2 ** (2 / 12)) < 2


def test_effect_limits_and_cancellation(tmp_path):
    with pytest.raises(ValueError):
        OmniVoiceOptions(pitch_semitones=float("nan"))
    with pytest.raises(ValueError):
        OmniVoiceOptions(punctuation_pause_ms=501)
    source = tmp_path / "source.wav"
    tone(source)
    def cancel():
        raise ValueError("cancelled")
    with pytest.raises(ValueError, match="cancelled"):
        apply_effects(source, tmp_path / "unused.wav", "words", OmniVoiceOptions(pitch_semitones=2), cancel)
    assert not (tmp_path / "unused.wav").exists()

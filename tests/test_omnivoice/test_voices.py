"""Speaker identity, portable references and private-library storage contracts."""

import importlib.util
import io
import json
import math
import struct
import sys
import wave
from types import SimpleNamespace

import pytest

from videocaptioner.core.tts.omnivoice import voices
from videocaptioner.core.tts.omnivoice.config import resources


def make_wav(path, *, seconds=4, rate=16000, channels=2, silent=False):
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(channels)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(b"".join(struct.pack("<h", 0 if silent else int(3000 * math.sin(index / 17))) * channels
            for index in range(int(seconds * rate))))


def test_four_builtin_references_have_distinct_verified_identity():
    profiles = voices.list_voices()
    assert tuple(p.voice_id for p in profiles) == voices.BUILTIN_IDS
    assert len({p.sha256 for p in profiles}) == 4
    for profile in profiles:
        profile.verify()
        with wave.open(str(profile.audio_path)) as audio:
            assert (audio.getframerate(), audio.getnchannels(), audio.getsampwidth()) == (24000, 1, 2)
            assert 3 <= audio.getnframes() / audio.getframerate() <= 10
    assert voices.resolve_voice("female") == profiles[0]
    assert voices.resolve_voice("male") == profiles[2]
    assert voices.resolve_voice("auto") is None


def test_import_normalizes_copy_and_survives_source_removal(tmp_path):
    original = tmp_path / "original.wav"
    make_wav(original)
    before = original.read_bytes()
    profile = voices.save_voice("Giọng của tôi", str(original), "Đây là lời mẫu.", "vi")
    assert original.read_bytes() == before
    original.unlink()
    profile.verify()
    assert voices.resolve_voice(profile.voice_id) == profile
    with wave.open(str(profile.audio_path)) as audio:
        assert (audio.getnchannels(), audio.getframerate(), audio.getnframes()) == (1, 24000, 96000)
    metadata = (profile.audio_path.parent / "profile.json").read_text(encoding="utf-8")
    assert str(tmp_path) not in metadata
    assert "Đây là lời mẫu" not in repr(profile)


@pytest.mark.parametrize("seconds,silent", [(1, False), (11, False), (4, True)])
def test_bad_reference_never_becomes_a_saved_voice(tmp_path, seconds, silent):
    audio = tmp_path / "bad.wav"
    make_wav(audio, seconds=seconds, silent=silent)
    with pytest.raises(ValueError):
        voices.save_voice("Invalid", str(audio), "Text", "vi")
    assert not list(voices.library_root().glob("saved-*"))


def test_cancel_import_keeps_source_and_publishes_nothing(tmp_path):
    audio = tmp_path / "cancel.wav"
    make_wav(audio)
    checks = 0

    def check():
        nonlocal checks
        checks += 1
        if checks >= 2:
            raise ValueError("cancelled")

    with pytest.raises(ValueError, match="cancelled"):
        voices.save_voice("Cancelled", str(audio), "Text", "vi", check=check)
    assert audio.exists()
    assert not list(voices.library_root().glob("saved-*"))


def test_changed_wav_and_unknown_id_fail_closed(tmp_path):
    audio = tmp_path / "ref.wav"
    make_wav(audio)
    profile = voices.save_voice("Named", str(audio), "Words", "vi")
    profile.audio_path.write_bytes(b"corrupted")
    with pytest.raises(ValueError, match="thay đổi"):
        voices.resolve_voice(profile.voice_id)
    with pytest.raises(ValueError, match="Không tìm thấy"):
        voices.resolve_voice("../../outside")
    assert len(voices.list_voices()) == 5


def test_worker_reuses_prompt_for_different_sentences_and_clears_it(monkeypatch, tmp_path):
    calls = []
    clone = object()
    reference = tmp_path / "reference.wav"
    reference.touch()

    class Model:
        sampling_rate = 24000

        @staticmethod
        def create_voice_clone_prompt(**kwargs):
            calls.append(("clone", kwargs))
            return clone

        @staticmethod
        def generate(**kwargs):
            calls.append(("generate", kwargs))
            return [[0.1] * 240]

    monkeypatch.setitem(sys.modules, "numpy", SimpleNamespace(isfinite=lambda _: SimpleNamespace(all=lambda: True)))
    monkeypatch.setitem(sys.modules, "soundfile", SimpleNamespace(write=lambda *a, **k: None))
    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(float16="float16", manual_seed=lambda _: None))
    monkeypatch.setitem(sys.modules, "omnivoice", SimpleNamespace(OmniVoice=SimpleNamespace(from_pretrained=lambda *a, **k: Model())))
    payloads = [{"operation": "configure", "reference_audio": str(reference), "reference_text": "Example."}]
    for index, text in enumerate(("Câu đầu tiên.", "Nội dung khác hẳn.")):
        payloads.append(dict(operation="synthesize", voice="vi-female-1", text=text, seed=0, language="vi",
            speed=1.0, steps=32, output=str(tmp_path / f"{index}.wav")))
    payloads += [{"operation": "configure"}, dict(payloads[-1], voice="auto")]
    monkeypatch.setattr(sys, "stdin", io.StringIO("\n".join(json.dumps(p) for p in payloads)))
    monkeypatch.setattr(sys, "argv", ["worker", "--model", "unused", "--scratch", str(tmp_path)])
    spec = importlib.util.spec_from_file_location("test_omni_worker", resources() / "worker.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module.logging, "disable", lambda _: None)
    module.main()
    generated = [item for operation, item in calls if operation == "generate"]
    assert len(generated) == 3
    assert generated[0]["voice_clone_prompt"] is generated[1]["voice_clone_prompt"] is clone
    assert generated[2]["voice_clone_prompt"] is None
    assert len([item for op, item in calls if op == "clone"]) == 1
    assert [g["text"] for g in generated[:2]] == ["Câu đầu tiên.", "Nội dung khác hẳn."]

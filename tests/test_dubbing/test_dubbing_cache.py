import json
import wave
from pathlib import Path

from videocaptioner.core.dubbing.cache import PersistentTTSCache, build_tts_cache_key


def write_wav(path: Path, duration: float = 0.2, sample_rate: int = 8000):
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(b"\0\0" * int(duration * sample_rate))


def key(**overrides):
    values = {
        "text": "hello",
        "provider": "openai",
        "api_base": "https://api.example.com/v1",
        "model": "tts-1",
        "voice": "alloy",
        "speed": 1.0,
        "sample_rate": 8000,
    }
    values.update(overrides)
    return build_tts_cache_key(**values)


def test_key_is_deterministic_and_credentials_are_excluded():
    assert key() == key(text="hello\n")
    assert key(api_base="https://user:secret@api.example.com/v1") == key()


def test_voice_model_speed_change_key():
    original = key()
    assert key(voice="nova") != original
    assert key(model="tts-2") != original
    assert key(speed=1.1) != original


def test_cache_hit_miss_and_metadata_has_no_transcript(tmp_path):
    source = tmp_path / "source.wav"
    write_wav(source)
    cache = PersistentTTSCache(tmp_path / "cache")
    cache_key = key()
    assert cache.get(cache_key) is None
    entry = cache.put(
        cache_key,
        source,
        provider="openai",
        model="tts-1",
        voice="alloy",
        sample_rate=8000,
    )
    assert entry is not None
    hit = cache.get(cache_key)
    assert hit is not None and hit.duration > 0
    metadata = json.loads(Path(hit.metadata_path).read_text(encoding="utf-8"))
    assert "hello" not in json.dumps(metadata)


def test_corrupt_or_missing_wav_is_a_miss(tmp_path):
    cache = PersistentTTSCache(tmp_path)
    cache_key = key()
    (tmp_path / f"{cache_key}.wav").write_bytes(b"not-a-wav")
    (tmp_path / f"{cache_key}.json").write_text(
        json.dumps({"key": cache_key}), encoding="utf-8"
    )
    assert cache.get(cache_key) is None
    (tmp_path / f"{cache_key}.wav").unlink()
    assert cache.get(cache_key) is None


def test_disabled_cache_bypasses_reads_and_writes(tmp_path):
    source = tmp_path / "source.wav"
    write_wav(source)
    cache = PersistentTTSCache(tmp_path / "cache", enabled=False)
    assert cache.put(key(), source, provider="p", model="m", voice="v", sample_rate=8000) is None
    assert cache.get(key()) is None
    assert not cache.root.exists()

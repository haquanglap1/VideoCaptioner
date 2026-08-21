import wave
from pathlib import Path

from videocaptioner.core.dubbing.cache import PersistentTTSCache, build_tts_cache_key
from videocaptioner.core.dubbing.config import AudioMixMode, DubbingConfig
from videocaptioner.core.dubbing.engine import DubbingEngine
from videocaptioner.core.dubbing.models import DubbingTextSource, DubbingTimingMode
from videocaptioner.core.editor.models import EditorCue, EditorProject
from videocaptioner.core.editor.voice import regenerate_selected_voice
from videocaptioner.core.tts import TTSConfig


def write_wav(path: Path, duration: float, sample_rate: int = 8000):
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(b"\0\0" * int(duration * sample_rate))


class FakeTTS:
    def __init__(self, calls):
        self.calls = calls

    def synthesize(self, data, output_dir, callback=None, max_workers=1):
        for index, segment in enumerate(data.segments):
            self.calls.append(segment.text)
            path = Path(output_dir) / f"voice-{index}.wav"
            write_wav(path, 0.4)
            segment.audio_path = str(path)
        if callback:
            callback(100, "fake")
        return data


def config():
    return DubbingConfig(
        enabled=True,
        tts_config=TTSConfig(
            model="fake",
            api_key="runtime-only",
            base_url="https://fake.invalid/v1",
            voice="alloy",
            speed=1.0,
            sample_rate=8000,
            response_format="wav",
        ),
        text_source=DubbingTextSource.AUTO,
        timing_mode=DubbingTimingMode.NATURAL,
        strip_cjk=False,
        mix_mode=AudioMixMode.MUTE_ORIGINAL,
        rewrite_enabled=False,
        target_language="vi",
    )


def test_selected_regeneration_refreshes_one_key_and_preserves_other_cache_entry(tmp_path):
    project = EditorProject.empty(str(tmp_path / "input.mp4"), 4000)
    project.cues = [
        EditorCue("cue-a", 0, 800, "A", "A", "voice A"),
        EditorCue("cue-b", 2000, 2800, "B", "B", "voice B"),
    ]
    cache_root = tmp_path / "cache"
    cache = PersistentTTSCache(cache_root)
    cfg = config()
    other_key = build_tts_cache_key(
        text="voice B",
        provider=cfg.tts_provider.name.lower(),
        api_base=cfg.tts_config.base_url,
        model=cfg.tts_config.model,
        voice=cfg.tts_config.voice,
        speed=cfg.tts_config.speed,
        sample_rate=cfg.tts_config.sample_rate,
    )
    other_wav = tmp_path / "other.wav"
    write_wav(other_wav, 0.4)
    cache.put(
        other_key,
        other_wav,
        provider=cfg.tts_provider.name.lower(),
        model=cfg.tts_config.model,
        voice=cfg.tts_config.voice,
        sample_rate=cfg.tts_config.sample_rate,
    )
    before_other = cache.get(other_key)
    calls = []
    engine = DubbingEngine(
        tts_provider_factory=lambda _config: FakeTTS(calls),
        cache_root=cache_root,
    )

    groups = regenerate_selected_voice(
        project,
        {"cue-a"},
        cfg,
        tmp_path / "generated",
        engine=engine,
    )

    assert calls == ["voice A"]
    assert len(groups) == 1
    assert groups[0].cue_ids == ["cue-a"]
    assert project.cue_by_id("cue-a").audio_path
    assert project.cue_by_id("cue-b").audio_path == ""
    after_other = cache.get(other_key)
    assert before_other is not None and after_other is not None
    assert Path(after_other.audio_path).read_bytes() == Path(before_other.audio_path).read_bytes()


def test_cache_invalidate_removes_only_named_entry(tmp_path):
    cache = PersistentTTSCache(tmp_path / "cache")
    wav = tmp_path / "input.wav"
    write_wav(wav, 0.2)
    for key in ("a", "b"):
        cache.put(key, wav, provider="fake", model="m", voice="v", sample_rate=8000)
    assert cache.invalidate("a") is True
    assert cache.get("a") is None
    assert cache.get("b") is not None

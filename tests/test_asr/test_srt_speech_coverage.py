"""Raw ASR SRT owns every spoken line, including code-switching and repeats."""

import pytest
from pydub import AudioSegment

from videocaptioner.core.asr import asr_data, base
from videocaptioner.core.asr.asr_data import ASRData
from videocaptioner.core.asr.faster_whisper import FasterWhisperASR
from videocaptioner.core.asr.local import sentence_fallback as fallback
from videocaptioner.core.asr.whisper_cpp import WhisperCppASR
from videocaptioner.core.entities import SubtitleLayoutEnum, TranscribeConfig


class MemoryCache(dict):
    def get(self, key, default=None):
        return super().get(key, default)

    def set(self, key, value, **kwargs):
        self[key] = value


@pytest.fixture(params=[
    ("Please open the window.", "然后我们继续讨论。"),
    ("Go now, go now.", "Then wait here, wait here."),
])
def wrapped_speech(request, monkeypatch):
    first, second = request.param
    # Pin a possible detector decision, including a false language split.
    monkeypatch.setattr(asr_data, "detect", lambda text: "en" if text == first else "zh-cn")
    raw = (f"1\n00:00:00,125 --> 00:00:01,875\n{first}\n{second}\n\n"
           f"2\n00:00:02,125 --> 00:00:03,875\n{first}\n{second}\n")
    return raw, f"{first}\n{second}"


def assert_full_speech(data, expected):
    assert [(s.text, s.translated_text, s.start_time, s.end_time) for s in data] == [
        (expected, "", 125, 1875), (expected, "", 2125, 3875)]
    assert data.to_srt(SubtitleLayoutEnum.ONLY_ORIGINAL).count(expected) == 2
    assert data.to_txt(layout=SubtitleLayoutEnum.ONLY_ORIGINAL) == f"{expected}\n{expected}"
    restored = ASRData.from_json(data.to_json())
    assert restored.to_json() == data.to_json()


@pytest.mark.parametrize("engine_type", [FasterWhisperASR, WhisperCppASR])
@pytest.mark.parametrize("cached", [False, True])
def test_raw_srt_keeps_wrapped_speech_in_primary_text(wrapped_speech, monkeypatch, engine_type, cached):
    raw, expected = wrapped_speech
    cache, requests = MemoryCache(), []
    engine = engine_type.__new__(engine_type)
    engine.use_cache = cached
    engine._cache = cache
    key = f"{engine_type.__name__}:synthetic"
    monkeypatch.setattr(engine, "_get_key", lambda: "synthetic")
    monkeypatch.setattr(base, "is_cache_enabled", lambda: True)

    def request(*args, **kwargs):
        requests.append(True)
        return raw

    monkeypatch.setattr(engine, "_run", request)
    if cached:
        cache[key] = raw
    data = engine.run()
    assert_full_speech(data, expected)
    assert requests == ([] if cached else [True])
    assert cache == {key: raw}


def test_raw_fallback_keeps_all_lines_on_fresh_and_cached_response(wrapped_speech, monkeypatch, tmp_path):
    raw, expected = wrapped_speech
    root = tmp_path / "models"
    model = root / "faster-whisper-large-v3"
    model.mkdir(parents=True)
    for name in ("model.bin", "config.json", "tokenizer.json"):
        (model / name).write_bytes(b"synthetic presence fixture, never loaded")

    class Engine:
        def __init__(self, *args, **kwargs):
            pass

        def _build_command(self, audio):
            return ["fake-whisper"]

    cache, requests = MemoryCache(), []
    monkeypatch.setattr(fallback, "FasterWhisperASR", Engine)
    monkeypatch.setattr(fallback, "is_cache_enabled", lambda: True)
    monkeypatch.setattr(fallback, "get_asr_cache", lambda: cache)
    owner = fallback.WhisperSentenceFallback(TranscribeConfig(faster_whisper_model_dir=str(root)))
    owner.revision = "synthetic"

    def request(*args):
        requests.append(True)
        return raw

    monkeypatch.setattr(owner, "_request", request)
    audio = AudioSegment.silent(duration=4000, frame_rate=16000)
    first, stage = owner(audio, lambda: None)
    second, same = owner(audio, lambda: None)
    assert_full_speech(first, expected)
    assert_full_speech(second, expected)
    assert stage == same and stage.provider == "faster-whisper"
    assert requests == [True]
    assert list(cache.values()) == [raw]


def test_user_srt_import_retains_bilingual_detection(wrapped_speech, tmp_path):
    raw, expected = wrapped_speech
    first, second = expected.splitlines()
    path = tmp_path / "bilingual.srt"
    path.write_text(raw, encoding="utf-8")
    for data in (ASRData.from_srt(raw), ASRData.from_subtitle_file(str(path))):
        assert [(s.text, s.translated_text) for s in data] == [(first, second), (first, second)]


@pytest.mark.parametrize("text", ["", "One line.", "First line.\r\n第二行。", "First.\nSecond.\nThird."])
def test_raw_srt_mode_never_calls_language_detector(monkeypatch, text):
    def unexpected_detection(*args):
        pytest.fail("Raw ASR text must not be classified into original/translation pairs")

    monkeypatch.setattr(asr_data, "detect", unexpected_detection)
    raw = f"1\n00:00:00,125 --> 00:00:01,875\n{text}\n" if text else ""
    data = ASRData.from_srt(raw, detect_bilingual=False)
    assert [(s.text, s.translated_text, s.start_time, s.end_time) for s in data] == (
        [(text.replace("\r\n", "\n"), "", 125, 1875)] if text else [])

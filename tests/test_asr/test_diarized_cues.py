"""Readable local speaker cues must retain measured evidence and real turn boundaries."""

from dataclasses import replace

import pytest
from pydub import AudioSegment

from videocaptioner.core.asr.asr_data import ASRData, ASRDataSeg
from videocaptioner.core.asr.audio_identity import identify_audio
from videocaptioner.core.asr.local import pipeline
from videocaptioner.core.asr.local.diarization import (
    assemble_diarized_cues,
    associate,
    validate_spans,
)
from videocaptioner.core.asr.metadata import ASRMetadata, StageProvenance
from videocaptioner.core.asr.native_result import native_cues
from videocaptioner.core.entities import TranscribeConfig
from videocaptioner.core.translate.conversation import ConversationContext, Scene

STAGE = StageProvenance("faster-whisper", "test-model", "test-revision", "test-policy")


def words():
    return ASRData([ASRDataSeg(text, start, end, metadata=ASRMetadata(
        "faster-whisper", "source", token_ids=(f"token-{i}",), recognition=STAGE), cue_id=f"cue-{i}")
        for i, (text, start, end) in enumerate((("你", 0, 200), ("好", 200, 600), ("吗？", 600, 1000)))],
        pending_diarization=True)


def spans(*items):
    return validate_spans([dict(start_ms=start, end_ms=end, speaker=speaker)
                           for start, end, speaker in items], 2000)


def test_unknown_prefix_is_assessed_on_complete_cue_without_changing_words():
    source = words()
    original = source.to_document()
    measured = spans((150, 1000, "A"))
    old = native_cues(associate(source, measured, 2000, "job", STAGE))
    assert len(old) > 1 and old.segments[0].metadata.diarization.status == "unknown"
    result = assemble_diarized_cues(source, measured, 2000, "job", STAGE)
    assert len(result) == 1
    cue = result.segments[0]
    assert (cue.text, cue.start_time, cue.end_time, cue.cue_id) == ("你好吗？", 0, 1000, "cue-0")
    assert cue.metadata.token_ids == ("token-0", "token-1", "token-2")
    assert cue.metadata.timing == "native" and cue.metadata.recognition == STAGE
    assert cue.metadata.diarization.status == "assigned"
    assert cue.metadata.diarization.coverage_ppm == 850_000
    assert source.to_document() == original
    assert result.pending_diarization
    assert ASRData.from_json(result.to_document()).to_document() == result.to_document()


@pytest.mark.parametrize("measured,status", [(spans(), "unknown"), (spans((500, 1000, "A")), "unknown")])
def test_grouping_does_not_relax_coverage_requirement(measured, status):
    result = assemble_diarized_cues(words(), measured, 2000, "job", STAGE)
    assert len(result) == 1
    assert result.segments[0].metadata.diarization.status == status
    assert result.segments[0].speaker is None


def test_real_speaker_change_remains_separate():
    result = assemble_diarized_cues(words(), spans((0, 600, "A"), (600, 1000, "B")), 2000, "job", STAGE)
    assert [s.text for s in result] == ["你好", "吗？"]
    assert [s.metadata.speaker for s in result] == ["A", "B"]


def test_speaker_in_interword_gap_blocks_join():
    source = words()
    source.segments[1].start_time = 400
    result = assemble_diarized_cues(source, spans((0, 200, "A"), (250, 350, "B"), (400, 1000, "A")),
                                     2000, "job", STAGE)
    assert [s.text for s in result] == ["你", "好吗？"]


def test_overlapping_speaker_word_is_retained_for_review():
    result = assemble_diarized_cues(words(), spans((0, 1000, "A"), (250, 350, "B")), 2000, "job", STAGE)
    assert [s.text for s in result] == ["你", "好", "吗？"]
    assert result.segments[1].metadata.diarization.status == "overlap"
    assert result.segments[1].speaker is None


def test_mixed_measured_timing_kinds_are_not_merged():
    source = words()
    source.segments[1].metadata = replace(source.segments[1].metadata, timing="imported")
    result = assemble_diarized_cues(source, spans((0, 1000, "A")), 2000, "job", STAGE)
    assert [s.cue_id for s in result] == [s.cue_id for s in source]
    assert result.segments[1].metadata.timing == "imported"


@pytest.mark.parametrize("change", [dict(speaker_override="manual"), dict(scope="different"),
                                   dict(recognition=replace(STAGE, revision="other"))])
def test_different_provenance_or_override_is_not_merged(change):
    source = words()
    source.segments[1].metadata = replace(source.segments[1].metadata, **change)
    result = assemble_diarized_cues(source, spans((0, 1000, "A")), 2000, "job", STAGE)
    assert [s.cue_id for s in result] == [s.cue_id for s in source]
    assert result.segments[1].metadata.speaker_override == change.get("speaker_override")


@pytest.mark.parametrize("reviewed", ["context", "translation"])
def test_existing_context_and_translation_keep_cue_boundaries(reviewed):
    source = words()
    if reviewed == "context":
        source.conversation_context = ConversationContext(scenes=(Scene("scene", "test", ("cue-1",)),))
    else:
        source.segments[1].translated_text = "translated"
    result = assemble_diarized_cues(source, spans((0, 1000, "A")), 2000, "job", STAGE)
    assert [s.cue_id for s in result] == [s.cue_id for s in source]
    assert result.conversation_context == source.conversation_context
    assert result.segments[1].translated_text == source.segments[1].translated_text


@pytest.mark.parametrize("word_mode,expected_count", [(True, 3), (False, 1)])
def test_pipeline_applies_assembly_only_in_sentence_mode(monkeypatch, word_mode, expected_count):
    audio = AudioSegment.silent(duration=1000, frame_rate=16000)
    source = words()
    source.audio_identity = identify_audio(audio)
    monkeypatch.setattr(pipeline, "decode_audio", lambda *a: audio)
    monkeypatch.setattr(pipeline, "diarization_preflight", lambda *a, **k: "layout")
    monkeypatch.setattr(pipeline, "is_cache_enabled", lambda: False)
    calls = []

    class Runtime:
        def __init__(self, *a): pass
        def start(self, check): calls.append("start")
        def request(self, binary, check): return [dict(start_ms=150, end_ms=1000, speaker="A")]
        def close(self): calls.append("close")

    monkeypatch.setattr(pipeline, "LocalRuntime", Runtime)
    result = pipeline.add_local_speakers("unused", source, TranscribeConfig(need_word_time_stamp=word_mode),
                                          aligned=False)
    assert len(result) == expected_count
    assert result.audio_identity == source.audio_identity
    assert not result.pending_diarization and source.pending_diarization
    assert calls == ["start", "close"]
    if word_mode:
        assert [(s.text, s.start_time, s.end_time, s.cue_id) for s in result] == [
            (s.text, s.start_time, s.end_time, s.cue_id) for s in source]
        assert result.segments[0].metadata.diarization.status == "unknown"


def test_cached_sentence_result_recomputes_word_confidence(monkeypatch):
    from types import SimpleNamespace
    audio = AudioSegment.silent(duration=1000, frame_rate=16000)
    source = words()
    source.audio_identity = identify_audio(audio)
    monkeypatch.setattr(pipeline, "decode_audio", lambda *a: audio)
    monkeypatch.setattr(pipeline, "diarization_preflight", lambda *a, **k: "layout")
    cached = {}
    cache = SimpleNamespace(get=cached.get, set=lambda key, value, **kw: cached.__setitem__(key, value))
    monkeypatch.setattr(pipeline, "is_cache_enabled", lambda: True)
    monkeypatch.setattr(pipeline, "get_asr_cache", lambda: cache)
    calls = []

    class Runtime:
        def __init__(self, *a): pass
        def start(self, check): calls.append("start")
        def request(self, binary, check):
            calls.append("request")
            return [dict(start_ms=150, end_ms=1000, speaker="A")]
        def close(self): calls.append("close")

    monkeypatch.setattr(pipeline, "LocalRuntime", Runtime)
    sentence = pipeline.add_local_speakers("unused", source, TranscribeConfig(need_word_time_stamp=False), aligned=False)
    assert sentence.segments[0].metadata.diarization.status == "assigned" and cached
    measured_words = pipeline.add_local_speakers("unused", source, TranscribeConfig(need_word_time_stamp=True), aligned=False)
    assert len(measured_words) == 3
    assert measured_words.segments[0].metadata.diarization.status == "unknown"
    assert measured_words.segments[0].metadata.diarization.coverage_ppm == 250_000
    assert calls == ["start", "request", "close", "close"]


def test_model_window_padding_preserves_raw_spans_and_source_cue_times():
    from videocaptioner.core.asr.local.diarization import validate_model_spans
    raw = [dict(start_ms=100, end_ms=9999, speaker="A")]
    measured = validate_model_spans(raw, 9950)
    assert measured[0].end_ms == 9999 and raw[0]["end_ms"] == 9999
    source = ASRData([ASRDataSeg("测试字幕", 100, 9900)])
    result = associate(source, measured, 9950, "job", STAGE)
    assert result.segments[0].metadata.diarization.coverage_ppm == 1_000_000
    assert result.segments[0].metadata.speaker == "A"
    assert (result.segments[0].start_time, result.segments[0].end_time) == (100, 9900)


def test_padding_only_speaker_does_not_label_source_speech():
    from videocaptioner.core.asr.local.diarization import validate_model_spans
    measured = validate_model_spans([dict(start_ms=9960, end_ms=9999, speaker="padding")], 9950)
    source = ASRData([ASRDataSeg("测试字幕", 100, 9900)])
    cue = associate(source, measured, 9950, "job", STAGE).segments[0]
    assert cue.speaker is None and cue.metadata.diarization.status == "unknown"
    assert cue.metadata.diarization.coverage_ppm == 0


@pytest.mark.parametrize("duration,start,end", [(10000, 100, 10001), (9950, 100, 10001), (9950, -1, 9999)])
def test_model_window_bound_does_not_accept_arbitrary_bad_timing(duration, start, end):
    from videocaptioner.core.asr.local.diarization import validate_model_spans
    with pytest.raises(ValueError):
        validate_model_spans([dict(start_ms=start, end_ms=end, speaker="A")], duration)


def test_short_input_uses_full_model_window_and_preserves_fractional_sample_tail():
    from videocaptioner.core.asr.local.diarization import validate_model_spans
    raw = [dict(start_ms=100, end_ms=9999, speaker="A")]
    assert validate_model_spans(raw, 950)[0].end_ms == 9999
    raw = [dict(start_ms=100, end_ms=10999, speaker="A")]
    assert validate_model_spans(raw, 10000, samples=160001)[0].end_ms == 10999
    with pytest.raises(ValueError):
        validate_model_spans(raw, 10000, samples=160000)


def test_model_padding_cannot_make_late_source_cues_valid():
    from videocaptioner.core.asr.local.diarization import validate_model_spans
    measured = validate_model_spans([dict(start_ms=100, end_ms=10999, speaker="A")], 10000, samples=160001)
    with pytest.raises(ValueError, match="measured cue timing"):
        associate(ASRData([ASRDataSeg("错误时间", 100, 10001)]), measured, 10000, "job", STAGE)


def test_pipeline_accepts_model_padding_without_changing_cue_timing(monkeypatch):
    audio = AudioSegment.silent(duration=1250, frame_rate=16000)
    source = ASRData([ASRDataSeg("测试字幕", 100, 1100)], audio_identity=identify_audio(audio), pending_diarization=True)
    monkeypatch.setattr(pipeline, "decode_audio", lambda *a: audio)
    monkeypatch.setattr(pipeline, "diarization_preflight", lambda *a, **k: "layout")
    monkeypatch.setattr(pipeline, "is_cache_enabled", lambda: False)
    raw = [dict(start_ms=100, end_ms=1268, speaker="A")]

    class Runtime:
        def __init__(self, *a): pass
        def start(self, check): pass
        def request(self, binary, check): return raw
        def close(self): pass

    monkeypatch.setattr(pipeline, "LocalRuntime", Runtime)
    result = pipeline.add_local_speakers("unused", source, TranscribeConfig(), aligned=False)
    assert result.segments[0].end_time == 1100 and raw[0]["end_ms"] == 1268
    assert result.segments[0].metadata.speaker == "A" and not result.pending_diarization
    assert result.audio_identity == source.audio_identity

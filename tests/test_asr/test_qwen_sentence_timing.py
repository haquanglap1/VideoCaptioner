"""Sentence timing exports only validated boundary anchors, preserving raw words."""

from copy import deepcopy

import pytest

from videocaptioner.core.asr.alignment.contract import AlignmentError, validate_alignment
from videocaptioner.core.asr.local.sentence_timing import sentence_cues


def items():
    return [dict(text=text, start_ms=start, end_ms=end) for text, start, end in
            [("你", 100, 250), ("好", 200, 200), ("世", 350, 300), ("界", 400, 550)]]


def test_internal_word_defects_do_not_change_sentence_boundaries_or_text():
    raw = items()
    before = deepcopy(raw)
    text = "你好，世界！"
    with pytest.raises(AlignmentError):
        validate_alignment(text, raw, 1000)
    cue, = sentence_cues(text, raw, 1000)
    assert (cue.span.text, cue.span.start_ms, cue.span.end_ms) == (text, 100, 550)
    assert (cue.first_token, cue.stop_token) == (0, 4)
    assert [(s.start_ms, s.end_ms) for s in cue.anchors] == [(100, 250), (400, 550)]
    assert raw == before


@pytest.mark.parametrize("index,key,value", [(0, "end_ms", 100), (3, "start_ms", 550),
    (0, "start_ms", -1), (3, "end_ms", 1001), (1, "start_ms", 99), (2, "end_ms", 551),
    (1, "end_ms", None), (1, "end_ms", float("nan")), (1, "end_ms", True),
    (1, "end_ms", 200.5)])
def test_invalid_anchors_and_internal_outliers_are_not_hidden(index, key, value):
    raw = items()
    raw[index][key] = value
    with pytest.raises(AlignmentError):
        sentence_cues("你好世界。", raw, 1000)


@pytest.mark.parametrize("text", ["你好世", "你好世界界", "您好世界", "你好世界！多"])
def test_exact_coverage_is_required(text):
    with pytest.raises(AlignmentError):
        sentence_cues(text, items(), 1000)


def test_sentence_groups_do_not_merge_to_hide_invalid_boundary():
    raw = items()
    with pytest.raises(AlignmentError, match="boundary"):
        sentence_cues("你好！世界。", raw, 1000)


def test_cross_sentence_overlap_is_rejected_without_sorting():
    raw = items()
    raw[1].update(start_ms=200, end_ms=380)
    raw[2].update(start_ms=350, end_ms=400)
    with pytest.raises(AlignmentError, match="overlapping sentence"):
        sentence_cues("你好！世界。", raw, 1000)


def test_script_numbers_punctuation_and_offsets_are_preserved():
    raw = [dict(text=t, start_ms=i * 100, end_ms=i * 100 + 90)
           for i, t in enumerate(["張", "三", "有", "１２", "元", "Yes"])]
    result = sentence_cues(" 張三有１２元。\nYes! ", raw, 1000)
    assert [c.span.text for c in result] == [" 張三有１２元。\n", "Yes! "]
    assert [(c.first_token, c.stop_token) for c in result] == [(0, 5), (5, 6)]
    assert [(c.span.start_ms, c.span.end_ms) for c in result] == [(0, 490), (500, 590)]


def test_long_interval_and_punctuation_only_do_not_become_cues():
    raw = items()
    raw[-1]["end_ms"] = 20000
    with pytest.raises(AlignmentError, match="cue limit"):
        sentence_cues("你好世界", raw, 30000)
    with pytest.raises(AlignmentError):
        sentence_cues("。", [], 1000)
    assert sentence_cues("", [], 1000) == ()


@pytest.mark.parametrize("silent_anchors", [False, True])
def test_sentence_pipeline_and_review_keep_raw_and_require_acoustic_anchors(monkeypatch, tmp_path, silent_anchors):
    from dataclasses import replace

    from pydub import AudioSegment
    from pydub.generators import Sine

    from videocaptioner.core.asr.local import pipeline
    from videocaptioner.core.asr.local.sentence_timing import SENTENCE_POLICY
    from videocaptioner.core.asr.review import NativeReview, NativeReviewRequired
    from videocaptioner.core.entities import TranscribeConfig

    audio = AudioSegment.silent(1000, frame_rate=16000) if silent_anchors else Sine(400, sample_rate=16000).to_audio_segment(1000)
    monkeypatch.setattr(pipeline, "decode_audio", lambda *a: audio)
    monkeypatch.setattr(pipeline, "locate", lambda model, *a, **kw: model)

    class Runtime:
        def __init__(self, model, timeout):
            self.model, self.state = model, "stopped"
        def start(self, check):
            self.state = "ready"
        def request(self, binary, text="", check=lambda: None):
            return items() if self.model == "aligner" else {"text": "你好，世界！"}
        def close(self):
            self.state = "stopped"

    monkeypatch.setattr(pipeline, "LocalRuntime", Runtime)
    config = TranscribeConfig(transcribe_language="zh", need_word_time_stamp=False)
    engine = pipeline.QwenLocalASR("fixture.wav", config)
    if silent_anchors:
        with pytest.raises(NativeReviewRequired) as error:
            engine.run()
        review = NativeReview.from_dict(error.value.review.to_dict())
        assert review.alignment_policy == SENTENCE_POLICY and not review.word_timing
        assert review.tokens[2].start == 350 and review.tokens[2].end == 300
        with pytest.raises(ValueError):
            review.resume()
    else:
        data = engine.run()
        assert len(data) == 1
        cue = data.segments[0]
        assert cue.text == "你好，世界！" and cue.start_time == 100 and cue.end_time == 550
        assert cue.metadata.alignment.policy == SENTENCE_POLICY and len(cue.metadata.token_ids) == 4
        data.save(str(tmp_path / "sentence.srt"))
        data.save(str(tmp_path / "sentence.json"))
        from videocaptioner.core.asr.asr_data import ASRData
        assert ASRData.from_subtitle_file(str(tmp_path / "sentence.srt")).segments[0].text == cue.text
        reopened = ASRData.from_subtitle_file(str(tmp_path / "sentence.json"))
        assert reopened.segments[0].metadata == cue.metadata
        # A strict word request is still a different contract.
        with pytest.raises(NativeReviewRequired):
            pipeline.QwenLocalASR("fixture.wav", replace(config, need_word_time_stamp=True)).run()


def test_sentence_review_resume_has_stable_ids_and_full_text():
    from dataclasses import replace

    from videocaptioner.core.asr.local.review import LocalReview
    from videocaptioner.core.asr.local.sentence_timing import SENTENCE_POLICY
    from videocaptioner.core.asr.metadata import StageProvenance
    from videocaptioner.core.asr.review import NativeReview

    review = LocalReview.capture_chunks(stage=StageProvenance("qwen-local", "model", "pin", "text"), scope="test",
        durations=[(0, 1000), (1000, 1000)], texts=["你好世界。", "你好世界。"], raw=[items(), items()], word_timing=False)
    review = replace(review, alignment_policy=SENTENCE_POLICY)
    loaded = NativeReview.from_dict(review.to_dict())
    data = loaded.resume()
    assert [(s.start_time, s.end_time) for s in data] == [(100, 550), (1100, 1550)]
    assert [s.cue_id for s in data] == [s.cue_id for s in loaded.resume()]
    assert "".join(s.text for s in data) == review.text
    assert loaded.tokens[1].start == loaded.tokens[1].end == 200

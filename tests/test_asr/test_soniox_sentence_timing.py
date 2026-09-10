"""Sentence timing can retain a nearby zero-width token without inventing word times."""

from copy import deepcopy
from dataclasses import replace

import pytest

from videocaptioner.core.asr.api_profiles import ASRAPIError
from videocaptioner.core.asr.native_result import parse_native
from videocaptioner.core.asr.review import NativeReview


def response():
    return {"text": "这里有人。", "tokens": [
        {"text": "这", "start_ms": 100, "end_ms": 200, "speaker": "1"},
        {"text": "里", "start_ms": 200, "end_ms": 200, "speaker": "1"},
        {"text": "有", "start_ms": 320, "end_ms": 420, "speaker": "1"},
        {"text": "人。", "start_ms": 450, "end_ms": 650, "speaker": "1"},
    ]}


def test_sentence_keeps_all_text_ids_speaker_and_reported_boundaries():
    value = response()
    before = deepcopy(value)
    data = parse_native(value, "soniox", 1000, "scope", True, word_timing=False)
    assert len(data) == 1
    cue = data.segments[0]
    assert (cue.text, cue.start_time, cue.end_time) == (value["text"], 100, 650)
    assert cue.metadata.token_ids == tuple(f"token-{i:06d}" for i in range(1, 5))
    assert cue.metadata.speaker == "1" and cue.metadata.timing == "native"
    assert value == before


def test_word_output_still_rejects_zero_duration():
    with pytest.raises(ASRAPIError, match="Zero-duration"):
        parse_native(response(), "soniox", 1000, "scope", True)


@pytest.mark.parametrize("change", ["speaker", "unknown", "gap", "sentence", "all_zero"])
def test_zero_token_requires_a_nearby_same_sentence_speech_anchor(change):
    value = response()
    tokens = value["tokens"]
    if change == "speaker":
        tokens[1]["speaker"] = "2"
    elif change == "unknown":
        tokens[1].pop("speaker")
    elif change == "gap":
        tokens[1].update(start_ms=1100, end_ms=1100)
        tokens[2].update(start_ms=2200, end_ms=2300)
        tokens[3].update(start_ms=2350, end_ms=2400)
    elif change == "sentence":
        tokens[0]["text"] += "。"
        tokens[1]["text"] += "。"
    elif change == "all_zero":
        for token in tokens:
            token.update(start_ms=200, end_ms=200)
    value["text"] = "".join(t["text"] for t in tokens)
    with pytest.raises(ASRAPIError, match="duration"):
        parse_native(value, "soniox", 3000, "scope", True, word_timing=False)


@pytest.mark.parametrize("edge", ["leading", "trailing"])
def test_sentence_edges_keep_the_reported_point_timestamp(edge):
    value = response()
    value["tokens"] = value["tokens"][1:] if edge == "leading" else value["tokens"][:2]
    value["text"] = "".join(t["text"] for t in value["tokens"])
    result = parse_native(value, "soniox", 1000, "scope", True, word_timing=False)
    assert len(result) == 1 and result.segments[0].text == value["text"]
    assert (result.segments[0].start_time, result.segments[0].end_time) == (
        value["tokens"][0]["start_ms"], value["tokens"][-1]["end_ms"])


@pytest.mark.parametrize("start,end", [(None, 200), (-1, 200), (300, 200), (200, 1200), (float("nan"), 200)])
def test_sentence_mode_does_not_relax_other_timing_errors(start, end):
    value = response()
    value["tokens"][1].update(start_ms=start, end_ms=end)
    with pytest.raises(ASRAPIError, match="timestamp"):
        parse_native(value, "soniox", 1000, "scope", True, word_timing=False)


def test_saved_sentence_review_resumes_locally_without_overrides(tmp_path):
    review = NativeReview.capture(response(), "soniox", "stt-async-v5", "scope", 1000, True, False)
    path = review.save(tmp_path / "review.json")
    before = path.read_bytes()
    loaded = NativeReview.load(path)
    assert not loaded.issues()
    result = loaded.resume()
    assert len(result) == 1 and not loaded.overrides
    assert loaded.tokens[1].start == loaded.tokens[1].end == 200
    assert path.read_bytes() == before
    assert replace(loaded, word_timing=True).issues()


def test_sentence_mode_still_requires_complete_coverage():
    value = response()
    value["text"] += "多"
    with pytest.raises(ASRAPIError, match="coverage"):
        parse_native(value, "soniox", 1000, "scope", True, word_timing=False)

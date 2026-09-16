"""Reject unusable native intervals without hiding the offending cue."""

import pytest

from videocaptioner.core.asr.api_profiles import MissingTimingError
from videocaptioner.core.asr.faster_whisper import FasterWhisperASR


@pytest.mark.parametrize("word_mode", [False, True])
@pytest.mark.parametrize("start,end,text", [
    ("00:00:01,000", "00:00:01,000", "测试"),
    ("00:00:01,100", "00:00:01,000", "测试"),
    ("00:00:01,000", "00:00:01,000", "[music]"),
])
def test_nonpositive_native_cue_rejects_entire_result(word_mode, start, end, text):
    engine = FasterWhisperASR.__new__(FasterWhisperASR)
    engine.need_word_time_stamp = word_mode
    raw = ("1\n00:00:00,100 --> 00:00:00,400\n第一句\n\n"
           f"2\n{start} --> {end}\n{text}\n\n"
           "3\n00:00:01,600 --> 00:00:01,900\n第三句\n")
    with pytest.raises(MissingTimingError, match="non-positive"):
        engine._make_segments(raw)


@pytest.mark.parametrize("word_mode", [False, True])
def test_positive_native_cues_keep_text_and_exact_boundaries(word_mode):
    engine = FasterWhisperASR.__new__(FasterWhisperASR)
    engine.need_word_time_stamp = word_mode
    raw = ("1\n00:00:00,100 --> 00:00:00,400\n第一句\n\n"
           "2\n00:00:00,600 --> 00:00:00,900\n第二句\n")
    result = engine._make_segments(raw)
    assert [(s.text, s.start_time, s.end_time) for s in result] == [
        ("第一句", 100, 400), ("第二句", 600, 900)]

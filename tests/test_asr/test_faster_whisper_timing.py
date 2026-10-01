"""Reject unusable native intervals without hiding the offending cue."""

import pytest

from videocaptioner.core.asr.api_profiles import MissingTimingError
from videocaptioner.core.asr.faster_whisper import FasterWhisperASR, logger


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


@pytest.mark.parametrize("fragments", [["now?"], ["now?", "now?"]])
def test_sentence_boundary_fragments_keep_all_text_without_extending_time(fragments, caplog, monkeypatch):
    monkeypatch.setattr(logger, "propagate", True)
    engine = FasterWhisperASR.__new__(FasterWhisperASR)
    engine.need_word_time_stamp = False
    raw = "1\n00:00:01,125 --> 00:00:02,900\nGo now\nThen wait\n\n"
    for index, text in enumerate(fragments, 2):
        raw += f"{index}\n00:00:02,900 --> 00:00:02,900\n{text}\n\n"
    raw += f"{len(fragments)+2}\n00:00:02,900 --> 00:00:04,060\nNext sentence\n"

    result = engine._make_segments(raw)

    assert [(s.text, s.start_time, s.end_time) for s in result] == [
        ("\n".join(["Go now", "Then wait", *fragments]), 1125, 2900),
        ("Next sentence", 2900, 4060),
    ]
    assert all(s.translated_text == "" for s in result)
    assert "sentence boundary" in caplog.text


@pytest.mark.parametrize("word_mode,previous,fragment,start,end", [
    (True, "First sentence", "suffix", "00:00:02,900", "00:00:02,900"),
    (False, "First sentence", "suffix", "00:00:02,901", "00:00:02,901"),
    (False, "First sentence", "suffix", "00:00:02,800", "00:00:02,900"),
    (False, "First sentence", "suffix", "00:00:02,900", "00:00:02,800"),
    (False, "[music]", "suffix", "00:00:02,900", "00:00:02,900"),
    (False, "First sentence", "[music]", "00:00:02,900", "00:00:02,900"),
    (False, "First sentence", "打赏支持明镜", "00:00:02,900", "00:00:02,900"),
])
def test_boundary_recovery_does_not_hide_invalid_or_filtered_cues(word_mode, previous, fragment, start, end):
    engine = FasterWhisperASR.__new__(FasterWhisperASR)
    engine.need_word_time_stamp = word_mode
    raw = (f"1\n00:00:01,125 --> 00:00:02,900\n{previous}\n\n"
           f"2\n{start} --> {end}\n{fragment}\n")
    if start < end:
        # Existing positive intervals, even overlaps, are kept exactly.
        assert engine._make_segments(raw)[-1].start_time == 2800
    else:
        with pytest.raises(MissingTimingError, match="non-positive"):
            engine._make_segments(raw)


def test_unanchored_first_point_still_requires_review():
    engine = FasterWhisperASR.__new__(FasterWhisperASR)
    engine.need_word_time_stamp = False
    with pytest.raises(MissingTimingError, match="non-positive"):
        engine._make_segments("1\n00:00:00,000 --> 00:00:00,000\nFirst\n")


def test_boundary_join_cannot_cross_a_filtered_cue():
    engine = FasterWhisperASR.__new__(FasterWhisperASR)
    engine.need_word_time_stamp = False
    raw = ("1\n00:00:00,100 --> 00:00:02,900\nFirst\n\n"
           "2\n00:00:02,000 --> 00:00:02,900\n[music]\n\n"
           "3\n00:00:02,900 --> 00:00:02,900\nsuffix\n")
    with pytest.raises(MissingTimingError, match="non-positive"):
        engine._make_segments(raw)

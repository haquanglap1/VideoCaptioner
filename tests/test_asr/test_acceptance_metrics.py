"""Known-reference checks for the offline S6 reader and scores."""

import itertools
import random

import pytest

from scripts.asr_acceptance import (
    ReferenceSegment,
    SpeakerSpan,
    character_error,
    diarization_error,
    maximum_assignment,
    parse_textgrid,
    select_windows,
)


def textgrid(mark='你好。', start="0.25", end="1.75"):
    return f'''File type = "ooTextFile"
Object class = "TextGrid"
xmin = 0
xmax = 2
tiers? <exists>
size = 1
item []:
    item [1]:
        class = "IntervalTier"
        name = "synthetic-speaker"
        xmin = 0
        xmax = 2
        intervals: size = 1
        intervals [1]:
            xmin = {start}
            xmax = {end}
            text = "{mark}"
'''


def test_reference_text_and_milliseconds_are_retained():
    duration, segments = parse_textgrid(textgrid('甲说：""你好""。\n乙回答。'))
    assert duration == 2000
    assert segments == [ReferenceSegment("synthetic-speaker", 250, 1750, '甲说："你好"。\n乙回答。')]


def test_quoted_text_cannot_create_fake_textgrid_fields():
    mark = '甲\nintervals [2]: xmin = 9\n乙'
    _, segments = parse_textgrid(textgrid(mark))
    assert len(segments) == 1
    assert segments[0].text == mark


@pytest.mark.parametrize("start,end", [("1", "0.5"), ("-1", "1"), ("1", "3"), ("1", "1"), ("nan", "1")])
def test_invalid_nonempty_reference_interval_is_rejected(start, end):
    with pytest.raises(ValueError):
        parse_textgrid(textgrid(start=start, end=end))


def test_silence_annotation_does_not_become_speech():
    assert parse_textgrid(textgrid('(SIL)'))[1] == []
    assert character_error('(SIL)', '多出来的字')["cer"] is None
    assert character_error('(SIL)', '多出来的字')["empty_reference_insertions"] == 5


def test_character_score_preserves_script_and_case():
    assert character_error("你好，世界！", "你好世界")["cer"] == 0
    result = character_error("甲乙丙", "甲丁丙戊")
    assert result["errors"] == 2 and result["cer"] == pytest.approx(2 / 3)
    assert character_error("體A1", "体a1")["errors"] == 2


def test_assignment_agrees_with_exhaustive_small_matrices():
    generator = random.Random(17)
    for size in range(1, 6):
        matrix = [[generator.randrange(20) for _ in range(size)] for _ in range(size)]
        obtained = sum(matrix[i][j] for i, j in maximum_assignment(matrix))
        expected = max(sum(matrix[i][j] for i, j in enumerate(order)) for order in itertools.permutations(range(size)))
        assert obtained == expected


def test_rectangular_and_empty_assignment():
    matrix = [[3, 10, 4], [8, 1, 0]]
    assert sum(matrix[i][j] for i, j in maximum_assignment(matrix)) == 18
    assert maximum_assignment([]) == []
    assert maximum_assignment([[]]) == []


def test_speaker_names_are_mapped_not_compared_literally():
    reference = [SpeakerSpan("a", 0, 1000), SpeakerSpan("b", 1000, 2000)]
    hypothesis = [SpeakerSpan("y", 0, 1000), SpeakerSpan("x", 1000, 2000)]
    assert diarization_error(reference, hypothesis, 2000, collar_ms=0)["der"] == 0


def test_overlap_missing_speaker_is_counted():
    reference = [SpeakerSpan("a", 0, 1000), SpeakerSpan("b", 0, 1000)]
    hypothesis = [SpeakerSpan("x", 0, 1000)]
    result = diarization_error(reference, hypothesis, 1000, collar_ms=0)
    assert result["der"] == 0.5
    assert result["missed_speaker_ms"] == 1000
    assert result["reference_speaker_ms"] == 2000


def test_repeated_same_speaker_spans_use_union():
    reference = [SpeakerSpan("a", 0, 1000)]
    hypothesis = [SpeakerSpan("x", 0, 800), SpeakerSpan("x", 200, 1000)]
    assert diarization_error(reference, hypothesis, 1000, collar_ms=0)["der"] == 0


def test_false_alarm_is_not_hidden_by_empty_reference():
    result = diarization_error([], [SpeakerSpan("x", 0, 1000)], 1000, collar_ms=0)
    assert result["der"] is None
    assert result["false_alarm_speaker_ms"] == 1000


def test_reference_collar_excludes_boundary_jitter():
    reference = [SpeakerSpan("a", 200, 1800)]
    hypothesis = [SpeakerSpan("x", 100, 1900)]
    assert diarization_error(reference, hypothesis, 2000, collar_ms=0)["der"] > 0
    assert diarization_error(reference, hypothesis, 2000, collar_ms=250)["der"] == 0


def test_collar_is_total_width_not_radius():
    reference = [SpeakerSpan("a", 200, 1800)]
    hypothesis = [SpeakerSpan("x", 0, 2000)]
    result = diarization_error(reference, hypothesis, 2000, collar_ms=250)
    assert result["false_alarm_speaker_ms"] == 150
    assert result["reference_speaker_ms"] == 1350


def test_windows_are_disjoint_and_do_not_cut_reference():
    segments = [ReferenceSegment("a", i * 5000 + 500, i * 5000 + 4000, "测试句子内容" * 3) for i in range(100)]
    windows = select_windows(segments, 500_000, count=3)
    assert len(windows) == 3
    assert all(105_000 <= end - start <= 150_000 for start, end in windows)
    assert all(windows[i][1] <= windows[i + 1][0] for i in range(len(windows) - 1))
    assert all(not (s.start_ms < edge < s.end_ms) for s in segments for window in windows for edge in window)


def test_utterance_timing_measures_existing_word_edges_only():
    from scripts.asr_acceptance import TimedText, utterance_timing
    reference = [ReferenceSegment("a", 200, 1500, "你好，世界！")]
    words = [TimedText(100, 700, "你好"), TimedText(800, 1700, "世界")]
    result = utterance_timing(reference, words, 2000)
    assert result["matched_utterances"] == 1 and result["coverage"] == 1
    assert result["errors"] == [{"reference_index": 0, "start_error_ms": -100, "end_error_ms": 200}]
    assert result["median_absolute_ms"] == 150 and result["p95_absolute_ms"] == 200


def test_timing_does_not_interpolate_inside_a_predicted_word():
    from scripts.asr_acceptance import TimedText, utterance_timing
    reference = [ReferenceSegment("a", 200, 1500, "你好世界")]
    result = utterance_timing(reference, [TimedText(0, 2000, "啊你好世界")], 2000)
    assert result["matched_utterances"] == 0
    assert result["unmatched_reasons"] == {"inside_hypothesis_word": 1}
    assert result["median_absolute_ms"] is None


def test_timing_reports_coverage_instead_of_repairing_mismatched_text():
    from scripts.asr_acceptance import TimedText, utterance_timing
    reference = [ReferenceSegment("a", 0, 1000, "你好世界"), ReferenceSegment("a", 1000, 2000, "新的内容")]
    result = utterance_timing(reference, [TimedText(0, 1000, "你好世界"), TimedText(1000, 2000, "错的内容")], 2000)
    assert result["coverage"] == .5
    assert result["unmatched_reasons"] == {"no_exact_match": 1}


@pytest.mark.parametrize("duplicate_reference", [True, False])
def test_ambiguous_repeated_text_does_not_get_a_timing_score(duplicate_reference):
    from scripts.asr_acceptance import TimedText, utterance_timing
    reference = [ReferenceSegment("a", 0, 1000, "同样的话")]
    hypothesis = [TimedText(0, 1000, "同样的话")]
    if duplicate_reference:
        reference.append(ReferenceSegment("b", 1000, 2000, "同样的话"))
    else:
        hypothesis.append(TimedText(1000, 2000, "同样的话"))
    result = utterance_timing(reference, hypothesis, 2000)
    assert result["matched_utterances"] == 0 and result["median_absolute_ms"] is None


def test_invalid_native_timing_cannot_enter_timing_statistics():
    from scripts.asr_acceptance import TimedText, utterance_timing
    with pytest.raises(ValueError, match="Invalid measured"):
        utterance_timing([], [TimedText(0, 0, "你好世界")], 1000)


def test_phrase_inside_another_reference_is_ambiguous_for_timing():
    from scripts.asr_acceptance import TimedText, utterance_timing
    reference = [ReferenceSegment("a", 0, 1000, "你好世界"), ReferenceSegment("a", 1000, 2000, "测试你好世界")]
    words = [TimedText(1000, 1200, "测试"), TimedText(1200, 2000, "你好世界")]
    result = utterance_timing(reference, words, 2000)
    assert result["unmatched_reasons"] == {"ambiguous_text_match": 1}
    assert result["matched_utterances"] == 1
    assert result["errors"] == [{"reference_index": 1, "start_error_ms": 0, "end_error_ms": 0}]

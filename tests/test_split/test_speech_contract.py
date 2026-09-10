"""Segmentation must preserve speech and consume every timed source token."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from videocaptioner.core.asr.asr_data import ASRData, ASRDataSeg
from videocaptioner.core.split.split import SubtitleSplitter
from videocaptioner.core.split.split_by_llm import _validate_split_result, split_by_llm


def reply(text):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text))])


@pytest.mark.parametrize("changed", [
    "Do open valve 12 after checking every indicator on the main control panel carefully.",
    "Do not open valve 13 after checking every indicator on the main control panel carefully.",
    "Do not open valve 12 after checking every indicator on the main control panel carefully!",
    "Do not open valve 12 after checking every indicator on the main control panel carefully. Extra.",
])
def test_small_edits_cannot_pass_a_similarity_threshold(changed):
    source = "Do not open valve 12 after checking every indicator on the main control panel carefully."
    valid, _ = _validate_split_result(source, [changed], 200, 100)
    assert not valid


@pytest.mark.parametrize(("source", "parts"), [
    ("The machine cannot restart until all safety checks have finished successfully.",
     ["The machine can", "not restart until all safety checks have finished successfully."]),
    ("Use version 3.14 for the control system after the final inspection.",
     ["Use version 3.", "14 for the control system after the final inspection."]),
    ("Please don't disconnect the cable before the system has completely shut down.",
     ["Please don'", "t disconnect the cable before the system has completely shut down."]),
    ("请使用OpenAI工具完成这个任务然后保存结果", ["请使用Open", "AI工具完成这个任务然后保存结果"]),
    ("Cafe\u0301 vẫn còn nóng nên hãy chờ một chút.", ["Cafe", "\u0301 vẫn còn nóng nên hãy chờ một chút."]),
])
def test_boundaries_do_not_cut_words_numbers_or_mixed_script_tokens(source, parts):
    valid, _ = _validate_split_result(source, parts, 200, 100)
    assert not valid


def test_invalid_last_reply_is_never_used():
    source = "Please do not delete the original recording after the subtitle export finishes."
    request = Mock(return_value=reply("Please delete the original recording.<br>The export finishes."))
    assert split_by_llm(source, request=request, max_word_count_english=20) == [source]
    assert request.call_count == 2


@pytest.mark.parametrize("content", [None, "", "<br>", "Hello.<br><br>World.", "```\nHello.<br>World.\n```"])
def test_malformed_reply_keeps_complete_original(content):
    source = "Hello. World."
    request = Mock(return_value=reply(content))
    assert split_by_llm(source, request=request) == [source]


def test_correction_returns_complete_source_with_case_and_punctuation():
    source = "Nếu trời mưa, chúng ta sẽ ở nhà. Bạn đồng ý không?"
    request = Mock(side_effect=[reply("Chúng ta ở nhà."), reply("Nếu trời mưa, chúng ta sẽ ở nhà.<br>Bạn đồng ý không?")])
    assert split_by_llm(source, request=request, max_word_count_english=15) == [
        "Nếu trời mưa, chúng ta sẽ ở nhà.", "Bạn đồng ý không?"
    ]


def test_single_fitting_sentence_does_not_need_a_break():
    source = "Nếu trời mưa, chúng ta sẽ ở nhà."
    request = Mock(return_value=reply(source))
    assert split_by_llm(source, request=request, max_word_count_english=15) == [source]
    assert request.call_count == 1


def test_timing_alignment_rejects_a_missing_prefix_instead_of_skipping_words():
    segments = [ASRDataSeg(word + " ", i * 300, (i + 1) * 300)
                for i, word in enumerate(["Please", "do", "not", "stop", "now."])]
    splitter = SubtitleSplitter(1, "offline-test")
    try:
        with pytest.raises(ValueError):
            splitter._merge_segments_based_on_sentences(segments, ["stop now."])
    finally:
        splitter.close()


def test_repeated_words_are_consumed_once_and_source_is_not_mutated():
    source = ASRData([ASRDataSeg(word, i * 300, (i + 1) * 300)
                      for i, word in enumerate(["No,", "no,", "please", "wait.", "Then", "go."])])
    before = source.to_document()
    request = Mock(return_value=reply("No, no, please wait.<br>Then go."))
    splitter = SubtitleSplitter(1, "offline-test", request=request)
    try:
        result = splitter.split_subtitle(source)
    finally:
        splitter.close()
    assert source.to_document() == before
    assert [s.text.strip() for s in result] == ["No, no, please wait.", "Then go."]
    assert [(s.start_time, s.end_time) for s in result] == [(0, 1200), (1200, 1800)]


def test_estimated_legacy_word_conversion_keeps_vietnamese_and_punctuation():
    text = "Nếu trời mưa, chúng ta sẽ ở nhà."
    source = ASRData([ASRDataSeg(text, 1000, 5500)])
    before = source.to_document()
    splitter = SubtitleSplitter(1, "offline-test", max_word_count_english=15,
                                request=Mock(return_value=reply(text)))
    try:
        result = splitter.split_subtitle(source)
    finally:
        splitter.close()
    assert source.to_document() == before
    assert [s.text.strip() for s in result] == [text]
    assert [(s.start_time, s.end_time) for s in result] == [(1000, 5500)]


def test_standalone_asr_punctuation_is_kept_in_the_spoken_sentence():
    source = ASRData([ASRDataSeg(text, i * 100, (i + 1) * 100)
                      for i, text in enumerate(["你", "好", "，", "世", "界", "。"])])
    splitter = SubtitleSplitter(1, "offline-test", request=Mock(return_value=reply("你好，世界。")))
    try:
        result = splitter.split_subtitle(source)
    finally:
        splitter.close()
    assert [s.text for s in result] == ["你好，世界。"]
    assert [(s.start_time, s.end_time) for s in result] == [(0, 600)]


def test_parallel_dispatch_prefers_sentence_end_to_a_small_internal_gap():
    segments = []
    time = 0
    for i in range(20):
        segments.append(ASRDataSeg("word." if i == 9 else "word", time, time + 100))
        time += 400 if i == 6 else 100
    splitter = SubtitleSplitter(2, "offline-test")
    try:
        chunks = splitter._split_asr_data(ASRData(segments), 2)
    finally:
        splitter.close()
    assert [len(chunk.segments) for chunk in chunks] == [10, 10]
    assert chunks[0].segments[-1].text == "word."
    assert [seg for chunk in chunks for seg in chunk] == segments

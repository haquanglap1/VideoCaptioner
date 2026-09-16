from copy import deepcopy

import pytest

from videocaptioner.core.asr.asr_data import ASRData, ASRDataSeg
from videocaptioner.core.asr.metadata import ASRMetadata
from videocaptioner.core.dubbing.engine import DubbingEngine
from videocaptioner.core.dubbing.models import (
    DubbingCue,
    DubbingTextSource,
    DubbingValidationError,
    resolve_dubbing_text,
)
from videocaptioner.core.dubbing.planner import (
    plan_dubbing_groups,
    predict_spoken_duration,
)


def cue(index, start, end, text, *, speaker=""):
    return DubbingCue(
        cue_id=index,
        start_time=start,
        end_time=end,
        source_text=f"source {index}",
        subtitle_text=text,
        tts_text=text,
        speaker=speaker,
        original_index=index,
    )


def test_text_source_auto_prefers_translation_and_modes_are_explicit():
    segment = ASRDataSeg("Original", 0, 1000, "Bản dịch")
    assert resolve_dubbing_text(segment, DubbingTextSource.AUTO) == "Bản dịch"
    assert resolve_dubbing_text(segment, DubbingTextSource.TRANSLATED) == "Bản dịch"
    assert resolve_dubbing_text(segment, DubbingTextSource.ORIGINAL) == "Original"


def test_translated_mode_requires_translation():
    with pytest.raises(DubbingValidationError, match="missing"):
        resolve_dubbing_text(ASRDataSeg("Original", 0, 1000), DubbingTextSource.TRANSLATED)


def test_engine_cues_keep_source_subtitle_and_tts_separate():
    segment = ASRDataSeg("Original", 0, 1000, "Target")
    cues = DubbingEngine()._create_dubbing_cues(
        [segment], strip_cjk=False, source_mode=DubbingTextSource.AUTO
    )
    assert cues[0].source_text == "Original"
    assert cues[0].subtitle_text == "Target"
    assert cues[0].tts_text == "Target"


@pytest.mark.parametrize(
    ("first", "second", "expected_groups"),
    [
        (ASRMetadata("soniox", "request-a", "1"), ASRMetadata("soniox", "request-a", "2"), 2),
        (ASRMetadata("soniox", "request-a", "1"), ASRMetadata("soniox", "request-a", "1"), 1),
        (ASRMetadata("soniox", "request-a", "1"), ASRMetadata("soniox", "request-b", "1"), 2),
        (ASRMetadata("soniox", "request-a", "1"), None, 2),
        (None, None, 1),
        (ASRMetadata("soniox", "request-a", "1", speaker_override="guest"),
         ASRMetadata("soniox", "request-a", "1", speaker_override="host"), 2),
        (ASRMetadata("soniox", "request-a", "1", speaker_override=""), None, 1),
    ],
)
def test_asr_speaker_boundaries_reach_dubbing_plan(first, second, expected_groups):
    from videocaptioner.core.dubbing.config import DubbingConfig
    from videocaptioner.core.dubbing.orchestrator import DubbingOrchestrator

    data = ASRData([
        ASRDataSeg("First phrase", 0, 1000, metadata=first),
        ASRDataSeg("Second phrase", 1100, 2000, metadata=second),
    ])
    before = deepcopy([segment.metadata for segment in data.segments])
    plan = DubbingOrchestrator(DubbingEngine())._build_dubbing_plan(
        data, "synthetic.json", 3.0, DubbingConfig(strip_cjk=False)
    )
    assert len(plan.groups) == expected_groups
    assert [segment.metadata for segment in data.segments] == before
    assert [g.tts_text for g in plan.groups] == (
        ["First phrase", "Second phrase"] if expected_groups == 2
        else ["First phrase Second phrase"]
    )


def test_bilingual_layout_can_be_selected_without_guessing():
    source_above = ASRData.from_srt("1\n00:00:00,000 --> 00:00:01,000\nHello world\nXin chào bạn\n")
    target_above = ASRData.from_srt("1\n00:00:00,000 --> 00:00:01,000\nXin chào bạn\nHello world\n")
    assert resolve_dubbing_text(source_above.segments[0], DubbingTextSource.TRANSLATED) == "Xin chào bạn"
    assert resolve_dubbing_text(target_above.segments[0], DubbingTextSource.ORIGINAL) == "Xin chào bạn"


def test_target_only_and_source_only_srt_routes_correctly():
    target = ASRData.from_srt("1\n00:00:00,000 --> 00:00:01,000\nXin chào\n")
    source = ASRData.from_srt("1\n00:00:00,000 --> 00:00:01,000\nHello\n")
    assert resolve_dubbing_text(target.segments[0], DubbingTextSource.AUTO) == "Xin chào"
    assert resolve_dubbing_text(source.segments[0], DubbingTextSource.AUTO) == "Hello"


def test_small_gap_merges_with_stable_ids_and_last_video_capacity():
    groups = plan_dubbing_groups(
        [cue(1, 0.0, 1.0, "A phrase,"), cue(2, 1.2, 2.0, "continues")],
        video_duration=3.0,
    )
    assert [group.group_id for group in groups] == ["g-0001"]
    assert groups[0].cue_ids == [1, 2]
    assert groups[0].available_end_time == 3.0
    assert groups[0].available_duration == 3.0


@pytest.mark.parametrize(
    ("items", "kwargs"),
    [
        ([cue(1, 0.0, 1.0, "one"), cue(2, 1.5, 2.0, "two")], {}),
        ([cue(1, 0.0, 1.0, "one", speaker="a"), cue(2, 1.1, 2.0, "two", speaker="b")], {}),
        ([cue(1, 0.0, 1.2, "one"), cue(2, 1.0, 2.0, "two")], {}),
        ([cue(1, 0.0, 1.0, "Done."), cue(2, 1.2, 2.0, "Next")], {}),
        ([cue(1, 0.0, 4.0, "one"), cue(2, 4.1, 9.0, "two")], {"max_group_duration": 8.0}),
    ],
)
def test_group_boundaries(items, kwargs):
    assert len(plan_dubbing_groups(items, video_duration=10.0, **kwargs)) == 2


def test_silence_guard_and_non_mutation():
    items = [cue(1, 0.0, 1.0, "Done."), cue(2, 2.0, 3.0, "Next")]
    before = deepcopy(items)
    groups = plan_dubbing_groups(items, video_duration=4.0, silence_guard_ms=80)
    assert groups[0].available_end_time == pytest.approx(1.92)
    assert items == before


def test_prediction_charges_numbers_acronyms_and_punctuation():
    plain = predict_spoken_duration("simple words")
    complex_text = predict_spoken_duration("Model X200 costs $1,299. 50% OK!")
    assert complex_text > plain


def test_merged_tts_removes_single_word_boundary_overlap_only_from_spoken_text():
    groups = plan_dubbing_groups(
        [cue(1, 0.0, 1.0, "Xin chào bạn"), cue(2, 1.1, 2.0, "bạn khỏe không")],
        video_duration=3.0,
    )
    assert groups[0].subtitle_text == "Xin chào bạn bạn khỏe không"
    assert groups[0].tts_text == "Xin chào bạn khỏe không"
    assert groups[0].warnings == ["Removed repeated TTS boundary overlap: bạn"]


def test_merged_tts_removes_longest_multiword_boundary_overlap():
    groups = plan_dubbing_groups(
        [
            cue(1, 0.0, 1.0, "Chúng ta đi tới Hà Nội"),
            cue(2, 1.1, 2.0, "Hà Nội hôm nay rất đẹp"),
        ],
        video_duration=3.0,
    )
    assert groups[0].tts_text == "Chúng ta đi tới Hà Nội hôm nay rất đẹp"
    assert groups[0].warnings == ["Removed repeated TTS boundary overlap: hà nội"]


def test_merged_tts_keeps_a_fully_repeated_cue():
    groups = plan_dubbing_groups(
        [cue(1, 0.0, 1.0, "Không"), cue(2, 1.1, 2.0, "Không")],
        video_duration=3.0,
    )
    assert groups[0].tts_text == "Không Không"
    assert groups[0].warnings == []

"""Bounded sequential playback from measured audio, preserving subtitle timing."""

from copy import deepcopy

import pytest

from videocaptioner.core.dubbing.config import DubbingConfig
from videocaptioner.core.dubbing.engine import DubbingEngine
from videocaptioner.core.dubbing.models import DubbingGroup, UnresolvedFitPolicy
from videocaptioner.core.dubbing.orchestrator import DubbingOrchestrator
from videocaptioner.core.dubbing.scheduling import sequential_slots
from videocaptioner.core.tts import TTSConfig


def groups():
    return [DubbingGroup(str(i), [i], start, start + capacity, start + capacity, capacity,
                         f"source-{i}", f"subtitle-{i}", f"speech-{i}", measured_duration=duration,
                         audio_path=f"audio-{i}.wav", fit_ratio=duration / capacity)
            for i, (start, capacity, duration) in enumerate([(0, 5.84, 2.2), (5.92, 2.72, 4.78),
                (8.72, 6.64, 8.64), (15.36, 3.12, 2.66), (18.56, 11.47, 9.02)])]


def test_one_shared_tempo_avoids_mid_passage_speed_jumps():
    data = groups()
    before = deepcopy(data)
    slots = sequential_slots(data, video_duration=30.03, max_speed=1.2, max_delay=2, gap=.08)
    assert data == before
    assert len({slot.speed for slot in slots}) == 1
    previous = -.08
    for group, slot in zip(data, slots):
        assert 1 <= slot.speed <= 1.2
        assert group.start_time <= slot.start <= group.start_time + 2
        assert slot.start >= previous + .08 - 1e-9
        previous = slot.start + group.measured_duration / slot.speed
    assert previous <= 30.03


def test_native_tempo_is_kept_when_shorter_speech_fits():
    data = groups()
    data[1].measured_duration = 3.0
    data[2].measured_duration = 6.5
    slots = sequential_slots(data, video_duration=30.03, max_speed=1.05, max_delay=2, gap=.08)
    assert all(slot.speed == 1.0 for slot in slots)


def fake_audio(monkeypatch, data):
    durations = {group.audio_path: group.measured_duration for group in data}
    def speed(source, destination, factor):
        # Include renderer duration error to verify the final schedule uses measured output.
        durations[destination] = durations[source] / factor + .005
        return True
    monkeypatch.setattr("videocaptioner.core.dubbing.orchestrator.adjust_audio_speed", speed)
    monkeypatch.setattr("videocaptioner.core.dubbing.orchestrator.measure_audio_duration", lambda path: durations[str(path)])


def test_rendered_schedule_preserves_original_cues_and_checks_actual_wav(monkeypatch, tmp_path):
    data = groups()
    original = [(g.start_time, g.subtitle_end_time, g.source_text, g.subtitle_text) for g in data]
    fake_audio(monkeypatch, data)
    config = DubbingConfig(tts_config=TTSConfig("", "", ""), natural_max_speed=1.2,
                           unresolved_policy=UnresolvedFitPolicy.SEQUENTIAL)
    output = DubbingOrchestrator(DubbingEngine())._apply_fit_policy(data, config, tmp_path, video_duration=30.03)
    assert not any(g.needs_review for g in data)
    assert original == [(g.start_time, g.subtitle_end_time, g.source_text, g.subtitle_text) for g in data]
    for a, b in zip(output, output[1:]):
        assert b["start_time"] >= a["end_time"] + .079
    assert all(g.start_delay <= 2 for g in data)
    assert all(g.fit_ratio == pytest.approx(g.measured_duration / g.available_duration) for g in data)
    assert output[-1]["end_time"] <= 30.03


def test_impossible_schedule_requires_review_instead_of_truncating(monkeypatch, tmp_path):
    data = groups()
    data[-1].measured_duration = 100
    fake_audio(monkeypatch, data)
    engine = DubbingEngine()
    monkeypatch.setattr(engine, "_truncate_audio", lambda *a: pytest.fail("no truncation"))
    config = DubbingConfig(tts_config=TTSConfig("", "", ""), natural_max_speed=1.2,
                           unresolved_policy=UnresolvedFitPolicy.SEQUENTIAL)
    DubbingOrchestrator(engine)._apply_fit_policy(data, config, tmp_path, video_duration=30.03)
    assert any(g.needs_review for g in data)
    assert all(g.applied_speed <= 1.2 for g in data)


def test_provider_speed_is_not_accelerated_past_the_overall_ceiling(monkeypatch, tmp_path):
    data = groups()[:2]
    fake_audio(monkeypatch, data)
    config = DubbingConfig(tts_config=TTSConfig("", "", "", speed=1.2), natural_max_speed=1.2,
                           unresolved_policy=UnresolvedFitPolicy.SEQUENTIAL)
    DubbingOrchestrator(DubbingEngine())._apply_fit_policy(data, config, tmp_path, video_duration=12)
    assert all(g.applied_speed == 1 for g in data)


@pytest.mark.parametrize("duration", [0, -1, float("nan"), float("inf")])
def test_invalid_duration_is_not_scheduled(duration):
    data = groups()
    data[0].measured_duration = duration
    with pytest.raises(ValueError):
        sequential_slots(data, video_duration=30, max_speed=1.2, max_delay=2, gap=.08)

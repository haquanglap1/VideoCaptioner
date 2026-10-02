"""Dialogue plans keep cue ownership, require wording review and bound drift."""

from copy import deepcopy

import pytest

from videocaptioner.core.dubbing.config import DubbingConfig
from videocaptioner.core.dubbing.dialogue import PLAN_SCHEMA, dialogue_groups, source_config
from videocaptioner.core.dubbing.engine import DubbingEngine
from videocaptioner.core.dubbing.models import DubbingReviewRequired, UnresolvedFitPolicy
from videocaptioner.core.dubbing.orchestrator import DubbingOrchestrator
from videocaptioner.core.dubbing.review import DubbingResumeError, DubbingReview
from videocaptioner.core.translate.dialogue import DialogueCue, DialogueDocument, SpeechBlock
from videocaptioner.core.tts import TTSConfig


def document():
    return DialogueDocument((
        DialogueCue("a", "Nếu ngày mai", "Nếu mai", 0, 1000),
        DialogueCue("b", "trời mưa.", "trời mưa.", 1000, 2000),
        DialogueCue("c", "Không, không đi.", "Không, không đi.", 2200, 3400),
    ), (SpeechBlock(("a", "b"), "Nếu mai trời mưa."),
        SpeechBlock(("c",), "Không, không đi.")), "vi")


@pytest.fixture
def inputs(tmp_path, monkeypatch):
    source = tmp_path / "test.dialogue.json"
    document().save(source)
    video = tmp_path / "video.mp4"
    video.write_bytes(b"synthetic-video")
    monkeypatch.setattr(DubbingOrchestrator, "_validate", staticmethod(lambda *args: None))
    monkeypatch.setattr(DubbingOrchestrator, "_video_duration", staticmethod(lambda *args: 10.0))
    config = DubbingConfig(tts_config=TTSConfig("synthetic", "", "https://synthetic.invalid", voice="fixed", speed=1.2))
    return source, video, config


def test_dialogue_preset_is_job_local_and_uses_two_second_limit(inputs):
    path, _, config = inputs
    before = deepcopy(config)
    effective = source_config(str(path), config)
    assert config == before and effective is not config
    assert effective.tts_config.speed == effective.natural_max_speed == 1.0
    assert effective.max_start_delay_ms == 2000
    assert effective.silence_guard_ms == 80
    assert effective.unresolved_policy == UnresolvedFitPolicy.SEQUENTIAL
    assert not effective.rewrite_enabled


def test_direct_dub_stops_before_provider_until_wording_is_approved(inputs, tmp_path):
    path, video, config = inputs
    engine = DubbingEngine(tts_provider_factory=lambda cfg: pytest.fail("Unapproved dialogue reached TTS"),
                           cache_root=tmp_path / "cache")
    with pytest.raises(DubbingReviewRequired, match="Duyệt lời thoại"):
        engine.dub(str(video), str(path), str(tmp_path / "out.mp4"), config)
    assert engine.last_review is not None
    assert engine.last_review.plan.schema_version == PLAN_SCHEMA
    assert engine.last_review.groups[0].cue_ids == ["a", "b"]
    assert all(group.needs_review for group in engine.last_review.groups)
    assert not (tmp_path / "out.mp4").exists()


def test_prepared_review_roundtrip_and_changed_boundary_rejected(inputs, tmp_path):
    path, video, config = inputs
    engine = DubbingEngine(cache_root=tmp_path / "cache")
    review = engine.prepare_review(str(video), str(path), config)
    restored = DubbingReview.from_report(review.to_dict())
    assert restored.to_dict() == review.to_dict()
    fresh = engine.prepare_review(str(video), str(path), config).plan
    restored.restore_into(fresh, source_config(str(path), config))
    assert [g.tts_text for g in fresh.groups] == [b.text for b in document().blocks]
    tampered = review.to_dict()
    tampered["groups"][0]["hard_end_time"] = 20
    with pytest.raises(DubbingResumeError, match="hard_end_time"):
        DubbingReview.from_report(tampered).restore_into(fresh, source_config(str(path), config))


def test_native_pace_can_overrun_cue_but_stays_within_two_seconds(inputs, tmp_path, monkeypatch):
    path, _, config = inputs
    groups = dialogue_groups(document(), 10)
    groups[0].measured_duration = 3.5
    groups[1].measured_duration = 1
    monkeypatch.setattr("videocaptioner.core.dubbing.orchestrator.adjust_audio_speed",
                        lambda *args: pytest.fail("Must not accelerate speech"))
    DubbingOrchestrator(DubbingEngine())._apply_sequential_policy(groups, source_config(str(path), config), tmp_path, 10)
    assert groups[1].playback_start_time == pytest.approx(3.58)
    assert groups[1].start_delay == pytest.approx(1.38)
    assert not any(g.needs_review for g in groups)
    groups[0].measured_duration = 4.5
    DubbingOrchestrator(DubbingEngine())._apply_sequential_policy(groups, source_config(str(path), config), tmp_path, 10)
    assert groups[1].start_delay == pytest.approx(2.38)
    assert groups[1].needs_review


def test_speech_crossing_explicit_turn_requires_review(inputs, tmp_path):
    path, _, config = inputs
    groups = dialogue_groups(document(), 10)
    groups[0].hard_end_time = 3
    groups[0].measured_duration = 3.5
    groups[1].measured_duration = 1
    DubbingOrchestrator(DubbingEngine())._apply_sequential_policy(groups, source_config(str(path), config), tmp_path, 10)
    assert groups[0].needs_review
    assert any("boundary" in text for text in groups[0].warnings)


def test_preview_audio_offset_seeks_into_wave_instead_of_replaying_its_prefix(tmp_path):
    import math
    import shutil
    import struct
    import wave

    from videocaptioner.core.dubbing.audio_mixer import build_voice_track
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        pytest.skip("FFmpeg required")
    path = tmp_path / "speech.wav"
    with wave.open(str(path), "wb") as wav:
        wav.setparams((1, 2, 24000, 0, "NONE", "not compressed"))
        wav.writeframes(b"\0\0" * 24000)
        wav.writeframes(b"".join(struct.pack("<h", round(4000 * math.sin(n / 10))) for n in range(24000)))
    output = tmp_path / "preview.wav"
    assert build_voice_track([{"audio_path": str(path), "start_time": 0, "end_time": 1, "audio_offset": 1}],
                             1, str(output), sample_rate=24000, normalize=False)
    with wave.open(str(output), "rb") as wav:
        wav.setpos(1200)
        samples = struct.unpack("<1200h", wav.readframes(1200))
    assert max(abs(value) for value in samples) > 1000

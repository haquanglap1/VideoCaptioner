"""Post-TTS tempo and video retiming preserve speech and resume identity."""

import hashlib
import json
import subprocess
import wave
from copy import deepcopy
from pathlib import Path

import pytest

from videocaptioner.core.dubbing.config import DubbingConfig
from videocaptioner.core.dubbing.dialogue import source_config
from videocaptioner.core.dubbing.engine import DubbingEngine
from videocaptioner.core.dubbing.orchestrator import DubbingOrchestrator
from videocaptioner.core.dubbing.review import DubbingReview, synthesis_cache_key
from videocaptioner.core.tts import TTSConfig


def test_balanced_rates_are_job_local_and_do_not_change_native_cache(tmp_path):
    source = tmp_path / "speech.srt"
    source.write_text("1\n00:00:00,000 --> 00:00:01,000\nFull speech.\n", encoding="utf-8")
    config = DubbingConfig(tts_config=TTSConfig("test", "", "", voice="fixed"),
                           voice_tempo=1.2, video_speed=.77)
    before = deepcopy(config)
    effective = source_config(str(source), config)
    assert config == before
    assert effective.tts_config.speed == effective.natural_max_speed == 1
    assert not effective.rewrite_enabled
    assert effective.unresolved_policy.value == "sequential"
    native = deepcopy(effective)
    native.voice_tempo = native.video_speed = 1
    assert synthesis_cache_key("Full speech.", effective) == synthesis_cache_key("Full speech.", native)


def test_review_accepts_only_playback_rate_changes_and_preserves_source_binding(tmp_path, monkeypatch):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"synthetic source")
    subtitle = tmp_path / "speech.srt"
    subtitle.write_text("1\n00:00:00,000 --> 00:00:01,000\nFull speech.\n", encoding="utf-8")
    monkeypatch.setattr(DubbingOrchestrator, "_validate", staticmethod(lambda *a: None))
    monkeypatch.setattr(DubbingOrchestrator, "_video_duration", staticmethod(lambda *a: 3.0))
    config = DubbingConfig(tts_config=TTSConfig("test", "", "", voice="fixed"),
                           voice_tempo=1.1, video_speed=.8)
    engine = DubbingEngine()
    review = engine.prepare_review(str(video), str(subtitle), config)
    original = review.to_dict()
    changed = deepcopy(config)
    changed.voice_tempo, changed.video_speed = 1.2, .77
    fresh = engine.prepare_review(str(video), str(subtitle), changed).plan
    review.restore_into(fresh, source_config(str(subtitle), changed))
    assert fresh.groups[0].start_time == review.groups[0].start_time
    assert review.to_dict() == original
    assert DubbingReview.from_report(review.to_dict()).plan.video_speed == .8
    changed.tts_config.voice = "other voice"
    fresh = engine.prepare_review(str(video), str(subtitle), changed).plan
    with pytest.raises(ValueError, match="settings mismatch"):
        review.restore_into(fresh, source_config(str(subtitle), changed))


@pytest.mark.parametrize("tempo,video", [(1.21, .77), (float("nan"), 1), (1.2, 0), (1.2, 1.1)])
def test_invalid_playback_rates_are_rejected_before_provider(tmp_path, tempo, video):
    source = tmp_path / "speech.srt"
    source.write_text("", encoding="utf-8")
    with pytest.raises(ValueError):
        source_config(str(source), DubbingConfig(voice_tempo=tempo, video_speed=video))


@pytest.mark.parametrize("has_audio,mode", [(False, "none"), (True, "soft"), (False, "hard")])
def test_real_render_retime_and_changed_rates_reuse_native_cache(tmp_path, has_audio, mode):
    import math
    import shutil
    import struct

    from videocaptioner.core.utils.subprocess_helper import child_environment

    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        pytest.skip("FFmpeg required")
    video = tmp_path / "input.mp4"
    command = ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=black:s=320x180:r=10:d=3"]
    if has_audio:
        command += ["-f", "lavfi", "-i", "sine=frequency=440:duration=3", "-c:a", "aac"]
    subprocess.run(command + ["-c:v", "libx264", "-pix_fmt", "yuv420p", str(video)],
                   env=child_environment(), capture_output=True, check=True)
    subtitle = tmp_path / "speech.srt"
    subtitle.write_text("1\n00:00:00,000 --> 00:00:01,000\nFirst sentence.\n\n"
                        "2\n00:00:01,200 --> 00:00:02,400\nSecond sentence.\n", encoding="utf-8")
    calls = []

    class Provider:
        def synthesize(self, data, output_dir, callback=None, max_workers=1):
            for i, segment in enumerate(data.segments):
                calls.append(segment.text)
                path = Path(output_dir) / f"{i}.wav"
                path.parent.mkdir(parents=True, exist_ok=True)
                with wave.open(str(path), "wb") as wav:
                    wav.setparams((1, 2, 24000, 0, "NONE", "not compressed"))
                    wav.writeframes(b"".join(struct.pack("<h", round(3000 * math.sin(n * .1))) for n in range(43200)))
                segment.audio_path = str(path)
            return data

    config = DubbingConfig(enabled=True, strip_cjk=False, rewrite_enabled=False,
                           voice_tempo=1.2, video_speed=.77, subtitle_mode=mode,
                           tts_config=TTSConfig("fixture", "", "", voice="fixed", sample_rate=24000))
    cache = tmp_path / "cache"
    engine = DubbingEngine(tts_provider_factory=lambda _: Provider(), cache_root=cache)
    output = tmp_path / "first.mp4"
    engine.dub(str(video), str(subtitle), str(output), config)
    assert len(calls) == 2
    report = engine.last_report
    assert report["summary"]["review_groups"] == 0
    assert report["voice_tempo"] == 1.2 and report["video_speed"] == .77
    assert report["groups"][1]["start_time"] == 1.2
    assert report["groups"][1]["playback_start_time"] >= 1.2 / .77
    assert all(g["applied_speed"] == 1.2 for g in report["groups"])
    native_hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in cache.glob("*.wav")}
    assert len(native_hashes) == 2
    for p in cache.glob("*.wav"):
        with wave.open(str(p)) as wav:
            assert wav.getnframes() / wav.getframerate() == 1.8
    from videocaptioner.core.asr.asr_data import ASRData
    captions = ASRData.from_subtitle_file(engine.last_subtitle_path)
    assert [s.text for s in captions] == ["First sentence.", "Second sentence."]
    assert captions.segments[1].start_time == round(report["groups"][1]["playback_start_time"] * 1000)
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-of", "json", str(output)],
                           env=child_environment(), capture_output=True, check=True)
    streams = json.loads(probe.stdout)["streams"]
    actual = next(s for s in streams if s["codec_type"] == "video")
    assert int(actual["nb_frames"]) == 30
    assert float(actual["duration"]) == pytest.approx(3 / .77, abs=.1)
    if mode == "soft":
        assert any(s["codec_type"] == "subtitle" for s in streams)
    saved = engine.last_review
    config.voice_tempo, config.video_speed = 1.1, .7
    engine.dub(str(video), str(subtitle), str(tmp_path / "second.mp4"), config, review=saved)
    assert len(calls) == 2
    assert engine.last_report["summary"]["cache_hits"] == 2
    assert {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in cache.glob("*.wav")} == native_hashes
    assert all(g["measured_duration"] == pytest.approx(1.8 / 1.1, abs=.08) for g in engine.last_report["groups"])


def test_media_cancel_reaps_only_owned_process(monkeypatch):
    import sys

    import psutil

    from videocaptioner.core.dubbing import playback
    real_popen = subprocess.Popen
    owned = []

    def launch(*args, **kwargs):
        process = real_popen(*args, **kwargs)
        owned.append(process)
        return process

    def cancel(*args):
        raise RuntimeError("user cancellation")

    monkeypatch.setattr(playback.subprocess, "Popen", launch)
    with pytest.raises(RuntimeError, match="user cancellation"):
        playback.run_media([sys.executable, "-c", "import time; time.sleep(30)"], cancel, "render")
    assert owned and all(p.poll() is not None and not psutil.pid_exists(p.pid) for p in owned)


def test_playback_default_caption_style_is_white_and_explicit_style_is_preserved(tmp_path, monkeypatch):
    from videocaptioner.core.dubbing import playback
    from videocaptioner.core.subtitle.style_manager import SubtitleStyle

    captions = tmp_path / "playback.srt"
    captions.write_text("1\n00:00:00,000 --> 00:00:01,000\nTiếng Việt đầy đủ.\n", encoding="utf-8")
    commands = []
    monkeypatch.setattr(playback, "run_media", lambda command, *a, **k: commands.append(command))
    monkeypatch.setattr("videocaptioner.core.utils.video_utils.check_cuda_available", lambda: False)
    monkeypatch.setattr("videocaptioner.core.utils.video_utils.auto_wrap_ass_file", lambda p: p)
    config = DubbingConfig(subtitle_mode="hard")
    playback.render_captions("source.mp4", tmp_path / "output.mp4", captions, config, lambda *a: None)
    ass = captions.with_suffix(".ass").read_text(encoding="utf-8")
    assert "Style: Default,Arial,40,&H00FFFFFF" in ass
    assert ",0,0,0,0,100,100,0," in ass
    custom = SubtitleStyle(name="User", font_name="Arial", font_size=32, primary_color="#FF0000").to_ass_string()
    config.subtitle_style = custom
    playback.render_captions("source.mp4", tmp_path / "other.mp4", captions, config, lambda *a: None)
    assert custom in captions.with_suffix(".ass").read_text(encoding="utf-8")
    for command in commands:
        effect = command[command.index("-vf") + 1]
        assert "BorderStyle=3" in effect and "OutlineColour=&H00000000" in effect
        assert "BackColour=&H00000000" in effect and "Shadow=0" in effect
        assert "Fontsize=" not in effect and "Alignment=" not in effect

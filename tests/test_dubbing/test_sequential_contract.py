"""Full-text 1x sequential jobs; fake TTS and short, real FFmpeg tail checks."""

import math
import struct
import subprocess
import wave
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from videocaptioner.core.asr.asr_data import ASRData, ASRDataSeg
from videocaptioner.core.dubbing.audio_mixer import mix_audio_tracks
from videocaptioner.core.dubbing.cache import PersistentTTSCache, measure_audio_duration
from videocaptioner.core.dubbing.config import AudioMixMode, DubbingConfig
from videocaptioner.core.dubbing.engine import DubbingEngine
from videocaptioner.core.dubbing.models import (
    DubbingProviderError,
    DubbingReviewRequired,
    UnresolvedFitPolicy,
)
from videocaptioner.core.dubbing.orchestrator import DubbingOrchestrator
from videocaptioner.core.dubbing.review import DubbingReview
from videocaptioner.core.tts import TTSConfig
from videocaptioner.core.utils.subprocess_helper import child_environment


def strict_config(**overrides):
    values = dict(
        tts_config=TTSConfig("fixture", "", "https://fixture.invalid/v1", voice="fixture",
                             speed=1.0, sample_rate=24000, response_format="wav"),
        natural_max_speed=1.0, max_start_delay_ms=1000, rewrite_enabled=False,
        unresolved_policy=UnresolvedFitPolicy.SEQUENTIAL, strip_cjk=False,
    )
    values.update(overrides)
    return DubbingConfig(**values)


def write_wav(path, duration, frequency=660):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(24000)
        audio.writeframes(b"".join(
            struct.pack("<h", round(6000 * math.sin(2 * math.pi * frequency * n / 24000)))
            for n in range(round(duration * 24000))
        ))


class Provider:
    def __init__(self, durations, calls):
        self.durations, self.calls = durations, calls

    def synthesize(self, data, output_dir, callback, max_workers):
        for i, segment in enumerate(data.segments):
            self.calls.append(segment.text)
            if segment.text not in self.durations:
                segment.error = "fixture provider failure"
                continue
            segment.audio_path = str(Path(output_dir) / f"{i}.wav")
            write_wav(segment.audio_path, self.durations[segment.text])


class NoRewrite:
    configured = True

    def rewrite(self, *args, **kwargs):
        pytest.fail("No automatic rewriting is permitted")


def make_engine(root, durations, calls):
    def provider(config):
        assert config.tts_config.speed == 1.0
        return Provider(durations, calls)
    return DubbingEngine(tts_provider_factory=provider,
                         rewrite_service_factory=lambda config: NoRewrite(), cache_root=root / "cache")


@pytest.fixture(autouse=True)
def forbid_speech_edits(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Sequential 1x must not apply atempo or truncate audio")
    monkeypatch.setattr("videocaptioner.core.dubbing.orchestrator.adjust_audio_speed", forbidden)
    monkeypatch.setattr(DubbingEngine, "_truncate_audio", forbidden)


@pytest.fixture
def offline_mix(monkeypatch):
    monkeypatch.setattr(DubbingOrchestrator, "_validate", staticmethod(lambda *args: None))
    monkeypatch.setattr(DubbingOrchestrator, "_video_duration", staticmethod(lambda *args: 5.0))
    captured = []
    def build(segments, duration, output, **kwargs):
        captured.extend(deepcopy(segments))
        assert duration == 5.0
        for segment in segments:
            assert measure_audio_duration(segment["audio_path"]) == pytest.approx(
                segment["end_time"] - segment["start_time"])
        return True
    def mix(video, voice, output, **kwargs):
        Path(output).write_bytes(b"fixture-output")
        return True
    monkeypatch.setattr("videocaptioner.core.dubbing.orchestrator.build_voice_track", build)
    monkeypatch.setattr("videocaptioner.core.dubbing.orchestrator.mix_audio_tracks", mix)
    return captured


def sources(root, texts=("First.", "Second.", "Last.")):
    video, subtitle = root / "input.mp4", root / "spoken.srt"
    video.write_bytes(b"fixture-video")
    subtitle.write_text("\n\n".join(
        f"{i+1}\n00:00:0{i},000 --> 00:00:0{i},500\n{text}"
        for i, text in enumerate(texts)
    ), encoding="utf-8")
    return video, subtitle


@pytest.mark.parametrize("parts", [
    ("Go now", "now please."), ("Đi Hà Nội", "Hà Nội hôm nay."),
    ("Không", "Không"), ("慢慢", "慢慢走。"),
])
def test_sequential_preserves_intentional_repetitions(parts):
    data = ASRData([ASRDataSeg(text, i * 450, i * 450 + 400) for i, text in enumerate(parts)])
    before = [(s.text, s.translated_text, s.start_time, s.end_time) for s in data.segments]
    plan = DubbingOrchestrator(DubbingEngine())._build_dubbing_plan(data, "spoken.srt", 3, strict_config())
    assert len(plan.groups) == 1
    group = plan.groups[0]
    assert group.tts_text == group.original_tts_text == group.subtitle_text == " ".join(parts)
    assert group.cue_ids == [1, 2]
    assert (group.start_time, group.subtitle_end_time) == (0, .85)
    assert not group.warnings
    assert [(s.text, s.translated_text, s.start_time, s.end_time) for s in data.segments] == before


@pytest.mark.parametrize("durations,starts", [
    ((.4, .4, .4), (0, 1, 2)), ((1.4, 1.2, .6), (0, 1.48, 2.76)),
    ((1.92, .5, .4), (0, 2, 2.58)),
])
def test_native_order_full_wavs_cache_and_resume(tmp_path, offline_mix, durations, starts):
    video, subtitle = sources(tmp_path)
    before = subtitle.read_bytes()
    mapping = dict(zip(("First.", "Second.", "Last."), durations))
    calls = []
    engine = make_engine(tmp_path, mapping, calls)
    cfg = strict_config()
    engine.dub(str(video), str(subtitle), str(tmp_path / "output.mp4"), cfg)
    assert calls == list(mapping)
    report = engine.last_report
    for i, group in enumerate(report["groups"]):
        assert group["tts_text"] == group["original_tts_text"] == list(mapping)[i]
        assert group["cue_ids"] == [i + 1]
        assert (group["start_time"], group["subtitle_end_time"]) == (i, i + .5)
        assert group["playback_start_time"] == pytest.approx(starts[i], abs=.001)
        assert group["measured_duration"] == durations[i]
        assert group["applied_speed"] == 1 and group["start_delay"] <= 1
        assert not group["needs_review"]
        hit = PersistentTTSCache(tmp_path / "cache").get(group["cache_key"])
        assert hit is not None and hit.duration == durations[i]
    for a, b in zip(offline_mix, offline_mix[1:]):
        assert b["start_time"] >= a["end_time"] + .08 - 1e-9
    assert report["summary"]["speed_adjusted_groups"] == report["summary"]["rewritten_groups"] == 0
    saved = tmp_path / "review.json"
    DubbingReview.from_report(report).save(saved)
    for review in (None, DubbingReview.load(saved)):
        resumed_calls = []
        resumed = make_engine(tmp_path, {}, resumed_calls)
        resumed.dub(str(video), str(subtitle), str(tmp_path / "cached.mp4"), cfg, review=review)
        assert resumed_calls == []
        assert resumed.last_report["summary"]["cache_hits"] == 3
        assert [g["playback_start_time"] for g in resumed.last_report["groups"]] == pytest.approx(starts, abs=.001)
    assert subtitle.read_bytes() == before


@pytest.mark.parametrize("duration,warning", [(2.0, "start delay"), (4.0, "video end")])
@pytest.mark.parametrize("cache_enabled", [True, False])
def test_overflow_retains_review_and_complete_audio(tmp_path, offline_mix, duration, warning, cache_enabled):
    video, subtitle = sources(tmp_path)
    calls = []
    engine = make_engine(tmp_path, {"First.": duration, "Second.": 1, "Last.": 1}, calls)
    cfg = strict_config(cache_enabled=cache_enabled)
    output = tmp_path / "output.mp4"
    with pytest.raises(DubbingReviewRequired) as error:
        engine.dub(str(video), str(subtitle), str(output), cfg)
    assert not output.exists() and not offline_mix
    assert engine.last_review is not None
    assert [g.tts_text for g in engine.last_review.groups] == ["First.", "Second.", "Last."]
    retained = sorted(measure_audio_duration(p) for p in (tmp_path / "cache").rglob("*.wav"))
    assert retained == sorted([duration, 1, 1])
    warnings = " ".join(w for g in engine.last_review.groups for w in g.warnings)
    assert warning in warnings
    assert "g-000" in str(error.value)
    assert "1000" in str(error.value) if warning == "start delay" else "5.000" in str(error.value)
    if cache_enabled:
        resumed_calls = []
        resumed = make_engine(tmp_path, {}, resumed_calls)
        with pytest.raises(DubbingReviewRequired):
            resumed.dub(str(video), str(subtitle), str(output), cfg, review=engine.last_review)
        assert resumed_calls == [] and resumed.last_report["summary"]["cache_hits"] == 3


@pytest.mark.parametrize("cache_enabled", [True, False])
def test_partial_provider_failure_is_incomplete_and_resumable(tmp_path, offline_mix, cache_enabled):
    video, subtitle = sources(tmp_path)
    calls = []
    engine = make_engine(tmp_path, {"First.": .5, "Last.": .5}, calls)
    cfg = strict_config(cache_enabled=cache_enabled)
    output = tmp_path / "output.mp4"
    with pytest.raises(DubbingProviderError, match="g-0002"):
        engine.dub(str(video), str(subtitle), str(output), cfg)
    assert not output.exists() and not offline_mix
    assert engine.last_report["summary"]["output_created"] is False
    assert len(list((tmp_path / "cache").rglob("*.wav"))) == 2
    calls = []
    resumed = make_engine(tmp_path, {"First.": .5, "Second.": .5, "Last.": .5}, calls)
    resumed.dub(str(video), str(subtitle), str(output), cfg, review=engine.last_review)
    assert calls == (["Second."] if cache_enabled else ["First.", "Second.", "Last."])
    assert resumed.last_report["summary"]["cache_hits"] == (2 if cache_enabled else 0)


def test_grouped_repetition_reaches_provider_and_saved_resume(tmp_path, offline_mix):
    video, subtitle = sources(tmp_path)
    subtitle.write_text(
        "1\n00:00:00,000 --> 00:00:00,400\nGo now\n\n"
        "2\n00:00:00,450 --> 00:00:00,850\nnow please.\n", encoding="utf-8")
    before = subtitle.read_bytes()
    calls = []
    engine = make_engine(tmp_path, {"Go now now please.": 1.5}, calls)
    cfg = strict_config()
    engine.dub(str(video), str(subtitle), str(tmp_path / "first.mp4"), cfg)
    assert calls == ["Go now now please."]
    report = tmp_path / "review.json"
    engine.last_review.save(report)
    calls = []
    resumed = make_engine(tmp_path, {}, calls)
    resumed.dub(str(video), str(subtitle), str(tmp_path / "second.mp4"), cfg, review=DubbingReview.load(report))
    assert calls == [] and resumed.last_report["summary"]["cache_hits"] == 1
    group = resumed.last_report["groups"][0]
    assert group["tts_text"] == group["original_tts_text"] == "Go now now please."
    assert group["cue_ids"] == [1, 2]
    assert subtitle.read_bytes() == before


def run_media(args):
    result = subprocess.run(args, env=child_environment(), capture_output=True)
    assert result.returncode == 0, result.stderr.decode("utf-8", errors="replace")
    return result.stdout


@pytest.mark.parametrize("mode", list(AudioMixMode))
@pytest.mark.parametrize("has_audio", [True, False])
def test_export_keeps_known_tail_and_video_length(tmp_path, mode, has_audio):
    video, voice, output = [tmp_path / name for name in ("video.mp4", "voice.wav", "output.mp4")]
    args = ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=black:s=160x90:r=10:d=3"]
    if has_audio:
        args += ["-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono:d=1", "-c:a", "aac"]
    run_media(args + ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-y", str(video)])
    write_wav(voice, 3)
    assert mix_audio_tracks(str(video), str(voice), str(output), mode, normalize_voice=False)
    duration = float(run_media(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
        "stream=duration", "-of", "default=nw=1:nk=1", str(output)]))
    assert duration == pytest.approx(3, abs=.001)
    pcm = run_media(["ffmpeg", "-v", "error", "-i", str(output), "-vn", "-ar", "24000", "-ac", "1",
                     "-f", "s16le", "-"])
    samples = struct.unpack("<" + "h" * (len(pcm) // 2), pcm)
    tail = samples[round(2.7 * 24000):round(2.98 * 24000)]
    assert len(tail) == round(.28 * 24000)
    assert (sum(value * value for value in tail) / len(tail)) ** .5 > 1000


@pytest.mark.parametrize("suffix", [".mp4", ".mkv"])
def test_full_engine_exports_delayed_tail_without_changing_subtitles(tmp_path, suffix):
    video, subtitle = sources(tmp_path)
    video = tmp_path / f"input{suffix}"
    run_media(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=black:s=160x90:r=10:d=3",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-y", str(video)])
    before = subtitle.read_bytes()
    calls = []
    engine = make_engine(tmp_path, {"First.": 1.4, "Second.": .9, "Last.": .54}, calls)
    output = tmp_path / "dubbed.mp4"
    engine.dub(str(video), str(subtitle), str(output), strict_config())
    groups = engine.last_report["groups"]
    assert groups[-1]["playback_end_time"] == pytest.approx(3, abs=.001)
    assert all(g["applied_speed"] == 1 for g in groups)
    pcm = run_media(["ffmpeg", "-v", "error", "-i", str(output), "-vn", "-ar", "24000", "-ac", "1",
                     "-f", "s16le", "-"])
    samples = struct.unpack("<" + "h" * (len(pcm) // 2), pcm)
    tail = samples[round(2.7 * 24000):round(2.98 * 24000)]
    assert len(tail) == round(.28 * 24000)
    assert (sum(v * v for v in tail) / len(tail)) ** .5 > 500
    assert calls == ["First.", "Second.", "Last."] and subtitle.read_bytes() == before


def test_longer_original_audio_cannot_hide_speech_beyond_video_end(tmp_path):
    video, subtitle = sources(tmp_path)
    run_media(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=black:s=160x90:r=10:d=3",
        "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono:d=5", "-c:a", "aac",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-y", str(video)])
    engine = make_engine(tmp_path, {"First.": .5, "Second.": .5, "Last.": 2}, [])
    output = tmp_path / "output.mp4"
    with pytest.raises(DubbingReviewRequired, match="video end 3.000s"):
        engine.dub(str(video), str(subtitle), str(output), strict_config())
    assert not output.exists()
    assert engine.last_review is not None
    assert engine.last_report["resume_metadata"]["video_duration"] == 3
    assert sorted(measure_audio_duration(p) for p in (tmp_path / "cache").glob("*.wav")) == [.5, .5, 2]


@pytest.mark.parametrize("response", [
    '{"streams": []}', '{"streams": [{"duration": "N/A"}]}',
    '{"streams": [{"duration": "nan"}]}', '{"streams": [{"duration": "0"}]}', 'invalid json',
])
def test_unknown_video_end_is_not_guessed_from_subtitle(monkeypatch, response):
    monkeypatch.setattr("videocaptioner.core.dubbing.orchestrator.subprocess.run",
                        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout=response))
    data = ASRData([ASRDataSeg("Full speech.", 0, 90000)])
    with pytest.raises(ValueError, match="video stream duration"):
        DubbingOrchestrator._video_duration("video.mp4", data, True)

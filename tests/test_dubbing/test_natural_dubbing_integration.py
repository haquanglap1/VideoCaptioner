import subprocess
import wave
from pathlib import Path

import pytest

from videocaptioner.core.dubbing.config import AudioMixMode, DubbingConfig
from videocaptioner.core.dubbing.engine import DubbingEngine
from videocaptioner.core.dubbing.models import (
    DubbingProviderError,
    DubbingReviewRequired,
    DubbingTextSource,
    DubbingTimingMode,
    UnresolvedFitPolicy,
)
from videocaptioner.core.tts import TTSConfig


def write_wav(path: Path, duration: float, sample_rate: int = 8000):
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(b"\0\0" * int(duration * sample_rate))


class FakeTTS:
    def __init__(self, durations, calls):
        self.durations = durations
        self.calls = calls

    def synthesize(self, data, output_dir, callback=None, max_workers=1):
        for index, segment in enumerate(data.segments):
            self.calls.append(segment.text)
            duration = self.durations.get(segment.text)
            if duration is None:
                continue
            path = Path(output_dir) / f"fake-{index}.wav"
            write_wav(path, duration)
            segment.audio_path = str(path)
        if callback:
            callback(100, "fake")
        return data


class FakeRewrite:
    configured = True

    def rewrite(self, request, *, rescue):
        return "Short target" if rescue else None


class FailingRewrite:
    configured = True

    def __init__(self):
        self.calls = 0

    def rewrite(self, request, *, rescue):
        if rescue:
            self.calls += 1
            raise ValueError("invalid candidate")
        return None


@pytest.fixture
def silent_video(tmp_path):
    path = tmp_path / "input.mp4"
    result = subprocess.run(
        [
            "ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=black:s=160x90:r=10:d=3",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-y", str(path),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    return path


def config(**overrides):
    values = {
        "enabled": True,
        "tts_config": TTSConfig(
            model="fake-v1",
            api_key="fake",
            base_url="https://fake.invalid/v1",
            voice="test",
            speed=1.0,
            sample_rate=8000,
            response_format="wav",
        ),
        "text_source": DubbingTextSource.TRANSLATED,
        "timing_mode": DubbingTimingMode.NATURAL,
        "strip_cjk": False,
        "mix_mode": AudioMixMode.MUTE_ORIGINAL,
        "rewrite_enabled": False,
        "target_language": "vi",
    }
    values.update(overrides)
    return DubbingConfig(**values)


def write_bilingual(path: Path, source: str, target: str, end="00:00:01,000"):
    path.write_text(
        f"1\n00:00:00,000 --> {end}\n{source}\n{target}\n", encoding="utf-8"
    )


def test_end_to_end_target_routing_report_and_cross_run_cache(silent_video, tmp_path):
    subtitle = tmp_path / "input.srt"
    write_bilingual(subtitle, "Original English sentence.", "Câu đích ngắn.")
    first_calls = []
    first = DubbingEngine(
        tts_provider_factory=lambda cfg: FakeTTS({"Câu đích ngắn.": 1.0}, first_calls),
        cache_root=tmp_path / "cache",
    )
    output1 = tmp_path / "dubbed-1.mp4"
    first.dub(str(silent_video), str(subtitle), str(output1), config())
    assert first_calls == ["Câu đích ngắn."]
    report1 = first.last_report
    assert first.last_report_path == ""
    assert list(tmp_path.glob("*-dubbing-report.json")) == []
    assert report1["schema_version"] == "dubbing-report-v1"
    assert report1["source_path"] == subtitle.name
    assert report1["groups"][0]["source_text"] == "Original English sentence."
    assert report1["groups"][0]["tts_text"] == "Câu đích ngắn."
    assert report1["summary"]["output_created"] is True
    assert report1["groups"][0]["measured_duration"] == pytest.approx(1.0, abs=0.02)
    assert not Path(report1["groups"][0]["audio_path"]).is_absolute()

    second_calls = []
    second = DubbingEngine(
        tts_provider_factory=lambda cfg: FakeTTS({}, second_calls),
        cache_root=tmp_path / "cache",
    )
    second.dub(str(silent_video), str(subtitle), str(tmp_path / "dubbed-2.mp4"), config())
    assert second_calls == []
    report2 = second.last_report
    assert report2["summary"]["cache_hits"] == 1


def test_measured_outlier_rewrites_only_outlier(silent_video, tmp_path):
    subtitle = tmp_path / "rewrite.srt"
    write_bilingual(subtitle, "Original", "Target phrase")
    calls = []
    engine = DubbingEngine(
        tts_provider_factory=lambda cfg: FakeTTS(
            {"Target phrase": 3.6, "Short target": 2.5}, calls
        ),
        rewrite_service_factory=lambda cfg: FakeRewrite(),
        cache_root=tmp_path / "cache",
    )
    cfg = config(rewrite_enabled=True, natural_max_speed=1.08)
    engine.dub(str(silent_video), str(subtitle), str(tmp_path / "rewrite.mp4"), cfg)
    report = engine.last_report
    assert calls == ["Target phrase", "Short target"]
    assert report["summary"]["rewritten_groups"] == 1
    assert report["groups"][0]["measured_duration"] == pytest.approx(2.5, abs=0.02)


def test_natural_review_never_truncates(silent_video, tmp_path, monkeypatch):
    subtitle = tmp_path / "review.srt"
    write_bilingual(subtitle, "Original", "Quá dài")
    engine = DubbingEngine(
        tts_provider_factory=lambda cfg: FakeTTS({"Quá dài": 5.0}, []),
        cache_root=tmp_path / "cache",
    )

    def forbidden(*args, **kwargs):
        raise AssertionError("Natural mode must never truncate")

    monkeypatch.setattr(engine, "_truncate_audio", forbidden)
    output = tmp_path / "review.mp4"
    with pytest.raises(DubbingReviewRequired) as exc_info:
        engine.dub(str(silent_video), str(subtitle), str(output), config())
    assert "g-0001" in str(exc_info.value)
    assert "audio" in str(exc_info.value)
    assert "khung khả dụng" in str(exc_info.value)
    report = engine.last_report
    assert not output.exists()
    assert report["summary"]["review_groups"] == 1
    assert "speed_adjust_1.080x" in report["groups"][0]["action_taken"]
    assert "review_required" in report["groups"][0]["action_taken"]
    assert report["summary"]["speed_adjusted_groups"] == 1


def test_natural_allow_overlap_keeps_full_speech(silent_video, tmp_path):
    subtitle = tmp_path / "overlap.srt"
    write_bilingual(subtitle, "Original", "Quá dài")
    engine = DubbingEngine(
        tts_provider_factory=lambda cfg: FakeTTS({"Quá dài": 5.0}, []),
        cache_root=tmp_path / "cache",
    )
    output = tmp_path / "overlap.mp4"
    cfg = config(unresolved_policy=UnresolvedFitPolicy.ALLOW_OVERLAP)
    engine.dub(str(silent_video), str(subtitle), str(output), cfg)
    report = engine.last_report
    assert output.exists()
    assert "allow_overlap" in report["groups"][0]["action_taken"]
    assert report["groups"][0]["measured_duration"] > report["groups"][0]["available_duration"]


def test_legacy_truncation_is_explicit(silent_video, tmp_path):
    subtitle = tmp_path / "legacy.srt"
    write_bilingual(subtitle, "Original", "Quá dài")
    engine = DubbingEngine(
        tts_provider_factory=lambda cfg: FakeTTS({"Quá dài": 5.0}, []),
        cache_root=tmp_path / "cache",
    )
    output = tmp_path / "legacy.mp4"
    engine.dub(
        str(silent_video),
        str(subtitle),
        str(output),
        config(timing_mode=DubbingTimingMode.LEGACY, max_speed=1.1),
    )
    report = engine.last_report
    assert output.exists()
    assert "legacy_truncate" in report["groups"][0]["action_taken"]


def test_provider_failure_keeps_in_memory_details_and_is_fatal(silent_video, tmp_path):
    subtitle = tmp_path / "failed.srt"
    write_bilingual(subtitle, "Original", "Missing audio")
    engine = DubbingEngine(
        tts_provider_factory=lambda cfg: FakeTTS({}, []),
        cache_root=tmp_path / "cache",
    )
    with pytest.raises(DubbingProviderError) as exc_info:
        engine.dub(str(silent_video), str(subtitle), str(tmp_path / "failed.mp4"), config())
    assert "TTS thất bại ở 1 nhóm" in str(exc_info.value)
    assert "g-0001" in str(exc_info.value)
    report = engine.last_report
    assert report["summary"]["failed_groups"] == 1
    assert report["summary"]["output_created"] is False
    assert engine.last_report_path == ""
    assert list(tmp_path.glob("*-dubbing-report.json")) == []


def test_explicit_report_path_is_still_supported(silent_video, tmp_path):
    subtitle = tmp_path / "explicit.srt"
    report_path = tmp_path / "requested-report.json"
    write_bilingual(subtitle, "Original", "Câu đích")
    engine = DubbingEngine(
        tts_provider_factory=lambda cfg: FakeTTS({"Câu đích": 0.8}, []),
        cache_root=tmp_path / "cache",
    )
    engine.dub(
        str(silent_video),
        str(subtitle),
        str(tmp_path / "explicit.mp4"),
        config(report_path=str(report_path)),
    )
    assert report_path.is_file()
    assert engine.last_report_path == str(report_path)


def test_duplicate_text_in_one_job_synthesizes_once(silent_video, tmp_path):
    subtitle = tmp_path / "duplicates.srt"
    subtitle.write_text(
        "1\n00:00:00,000 --> 00:00:00,700\nFirst source.\nLặp lại.\n\n"
        "2\n00:00:01,200 --> 00:00:01,900\nSecond source.\nLặp lại.\n",
        encoding="utf-8",
    )
    calls = []
    engine = DubbingEngine(
        tts_provider_factory=lambda cfg: FakeTTS({"Lặp lại.": 0.5}, calls),
        cache_root=tmp_path / "cache",
    )
    engine.dub(str(silent_video), str(subtitle), str(tmp_path / "duplicates.mp4"), config())
    assert calls == ["Lặp lại."]


def test_rewrite_attempt_limit_is_enforced(silent_video, tmp_path):
    subtitle = tmp_path / "retry.srt"
    write_bilingual(subtitle, "Original", "Quá dài")
    rewrite = FailingRewrite()
    engine = DubbingEngine(
        tts_provider_factory=lambda cfg: FakeTTS({"Quá dài": 5.0}, []),
        rewrite_service_factory=lambda cfg: rewrite,
        cache_root=tmp_path / "cache",
    )
    with pytest.raises(DubbingReviewRequired):
        engine.dub(
            str(silent_video),
            str(subtitle),
            str(tmp_path / "retry.mp4"),
            config(rewrite_enabled=True, max_rewrite_attempts=2),
        )
    assert rewrite.calls == 2

"""Resolution presets preserve aspect ratio, audio and the source file."""

import json
import shutil
import subprocess

import pytest

from videocaptioner.core.asr.asr_data import ASRData, ASRDataSeg
from videocaptioner.core.dubbing import playback
from videocaptioner.core.dubbing.config import DubbingConfig
from videocaptioner.core.entities import SubtitleLayoutEnum, SubtitleRenderModeEnum
from videocaptioner.core.utils import video_utils
from videocaptioner.core.utils.subprocess_helper import _NO_WINDOW, child_environment
from videocaptioner.core.utils.video_resolution import output_dimensions, resolution_filter


@pytest.mark.parametrize("source,limit,expected", [
    ((3840, 2160), 1080, (1920, 1080)), ((2160, 3840), 720, (720, 1280)),
    ((3840, 1600), 1080, (1920, 800)), ((1000, 1000), 720, (720, 720)),
    ((640, 360), 1080, (640, 360)), ((3840, 2160), 0, (3840, 2160)),
])
def test_dimensions(source, limit, expected):
    assert output_dimensions(*source, limit) == expected


@pytest.mark.parametrize("value", [-1, 480, 999, True, "1080"])
def test_invalid_preset_is_rejected(value):
    with pytest.raises(ValueError, match="resolution"):
        resolution_filter(value)


def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                          env=child_environment(), creationflags=_NO_WINDOW, timeout=40, check=True)


def inspect(path):
    return json.loads(run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,width,height,duration",
                           "-of", "json", str(path)]).stdout)["streams"]


@pytest.fixture
def clip(tmp_path, monkeypatch):
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        pytest.skip("FFmpeg required")
    monkeypatch.setattr(video_utils, "check_cuda_available", lambda: False)
    monkeypatch.setattr("videocaptioner.core.subtitle.ass_renderer._check_cuda_available", lambda: False)
    video = tmp_path / "input.mp4"
    run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=navy:s=1920x1080:r=5:d=1",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=1", "-c:v", "libx264", "-preset", "ultrafast",
         "-c:a", "aac", "-shortest", str(video)])
    data = ASRData([ASRDataSeg("Kiểm tra độ phân giải", 0, 1000)])
    subtitle = tmp_path / "input.srt"
    data.save(str(subtitle))
    return video, subtitle, data


@pytest.mark.parametrize("mode", ["soft", "hard", "ass", "rounded", "dubbing-soft", "dubbing-hard", "dubbing-none"])
def test_every_export_route_uses_selected_size(clip, tmp_path, mode):
    video, subtitle, data = clip
    original = video.read_bytes()
    output = tmp_path / (mode + ".mp4")
    if mode.startswith("dubbing-"):
        config = DubbingConfig(output_resolution=720, subtitle_mode=mode.removeprefix("dubbing-"))
        if config.subtitle_mode == "none":
            playback.resize_video(str(video), output, 720, lambda *_: None)
        else:
            playback.render_captions(str(video), output, subtitle, config, lambda *_: None)
    elif mode in ("ass", "rounded"):
        video_utils.add_subtitles_with_style(str(video), data, str(output),
            render_mode=SubtitleRenderModeEnum.ASS_STYLE if mode == "ass" else SubtitleRenderModeEnum.ROUNDED_BG,
            subtitle_layout=SubtitleLayoutEnum.ONLY_ORIGINAL, output_resolution=720)
    else:
        video_utils.add_subtitles(str(video), str(subtitle), str(output), soft_subtitle=mode == "soft", output_resolution=720)
    streams = inspect(output)
    picture = next(s for s in streams if s["codec_type"] == "video")
    assert (picture["width"], picture["height"]) == (1280, 720)
    assert float(picture["duration"]) == pytest.approx(1, abs=.21)
    assert any(s["codec_type"] == "audio" for s in streams)
    if "soft" in mode:
        assert any(s["codec_type"] == "subtitle" for s in streams)
    assert video.read_bytes() == original


@pytest.mark.parametrize("dimensions,limit,expected", [
    ("1080x1920", 720, (720, 1280)), ("640x360", 1080, (640, 360)), ("1000x1000", 720, (720, 720)),
])
def test_dynamic_filter_matches_geometry_on_real_frames(tmp_path, dimensions, limit, expected):
    if not shutil.which("ffmpeg"):
        pytest.skip("FFmpeg required")
    output = tmp_path / "scaled.mp4"
    run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", f"color=s={dimensions}:r=2:d=0.5",
         "-vf", resolution_filter(limit), "-c:v", "libx264", str(output)])
    stream = inspect(output)[0]
    assert (stream["width"], stream["height"]) == expected

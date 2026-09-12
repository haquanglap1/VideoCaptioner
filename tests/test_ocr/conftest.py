"""Synthetic, local-only fixtures; never read user media or OCR models."""

import shutil
import subprocess
from pathlib import Path

import pytest
from PIL import Image, ImageDraw, ImageFont

from videocaptioner.core.utils.subprocess_helper import _NO_WINDOW, child_environment


@pytest.fixture
def ffmpeg_tools():
    ffmpeg, ffprobe = shutil.which("ffmpeg"), shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        pytest.skip("Local FFmpeg/ffprobe required for generated video fixtures")
    return ffmpeg, ffprobe


@pytest.fixture
def text_image():
    font_path = Path(__file__).parents[2] / "resource/fonts/NotoSansSC-Regular.ttf"
    font = ImageFont.truetype(str(font_path), 28)

    def make(text="学生三人，2026年。", level=255, size=(640, 120)):
        image = Image.new("RGB", size, "black")
        ImageDraw.Draw(image).multiline_text((20, 12), text, font=font,
                                            fill=(level, level, 0), spacing=6)
        return image
    return make


@pytest.fixture
def make_video(tmp_path, ffmpeg_tools):
    ffmpeg, _ = ffmpeg_tools
    count = 0

    def make(images, *, vfr=False, offset=0, sar="1/1", rotation=0, frame_rate="10"):
        nonlocal count
        count += 1
        folder = tmp_path / str(count)
        folder.mkdir()
        for index, image in enumerate(images):
            image.save(folder / f"frame-{index:03d}.png")
        # Input grid is 100 ms. Alternating intervals become 100/200 ms in the VFR fixture.
        expression = "(N+floor(N/2))/(10*TB)" if vfr else "PTS"
        filters = f"setpts={expression}+{offset}/TB,setsar={sar}"
        video = folder / "fixture.mov"
        subprocess.run([ffmpeg, "-v", "error", "-nostdin", "-n", "-framerate", frame_rate, "-i",
                        str(folder / "frame-%03d.png"), "-vf", filters, "-fps_mode", "passthrough",
                        "-c:v", "png", "-threads", "1", "-pix_fmt", "rgb24", str(video)],
                       env=child_environment(), creationflags=_NO_WINDOW, check=True, timeout=30,
                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        if rotation:
            rotated = folder / "rotated.mov"
            subprocess.run([ffmpeg, "-v", "error", "-nostdin", "-n", "-display_rotation", str(rotation),
                            "-i", str(video), "-c", "copy", str(rotated)],
                           env=child_environment(), creationflags=_NO_WINDOW, check=True, timeout=30,
                           stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            video = rotated
        return video
    return make

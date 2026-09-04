"""Fixtures for core/utils tests.

``ffmpeg`` skips cleanly on machines without a working FFmpeg so the offline
parts of these suites still run everywhere; only the tests that exercise a
real binary depend on it.
"""

import shutil
import subprocess
from pathlib import Path

import pytest


def _runs(binary: str) -> bool:
    """True when ``binary -version`` actually executes.

    ``shutil.which`` alone is not enough: a foreign-platform file named
    ``ffmpeg`` on PATH is found but fails with WinError 216 on Windows.
    """
    try:
        return subprocess.run([binary, "-version"], capture_output=True, timeout=30).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


@pytest.fixture
def ffmpeg() -> str:
    """Path to a working ffmpeg (with a working ffprobe beside it), or skip."""
    path = shutil.which("ffmpeg")
    probe = shutil.which("ffprobe")
    if not path or not probe or not _runs(path) or not _runs(probe):
        pytest.skip("No working FFmpeg/ffprobe on PATH")
    return path


@pytest.fixture
def silent_video(ffmpeg, tmp_path) -> Path:
    """One-second 320x240 H.264 clip with a 440 Hz AAC tone."""
    target = tmp_path / "clip.mp4"
    command = [
        ffmpeg,
        "-y",
        "-loglevel",
        "error",
        "-f",
        "lavfi",
        "-i",
        "color=c=black:s=320x240:r=25:d=1",
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=440:sample_rate=48000:duration=1",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-shortest",
        str(target),
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.SubprocessError) as exc:
        pytest.skip(f"ffmpeg could not run: {exc}")
    if result.returncode != 0 or not target.exists():
        pytest.skip(f"ffmpeg could not create the test clip: {result.stderr.strip()[:200]}")
    return target

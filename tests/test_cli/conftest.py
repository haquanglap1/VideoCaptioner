"""Fixtures shared by CLI tests."""

import pytest


@pytest.fixture(autouse=True)
def ffmpeg_available(monkeypatch):
    """Pretend FFmpeg is on PATH.

    CLI commands gate on ``validate_ffmpeg()`` before any mocked work runs, so
    without this the dub/synthesize tests depend on the machine having FFmpeg
    installed instead of on the code under test.
    """
    monkeypatch.setattr("videocaptioner.cli.validators.validate_ffmpeg", lambda: True)

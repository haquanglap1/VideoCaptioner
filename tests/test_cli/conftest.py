"""Fixtures shared by CLI tests."""

import pytest

from videocaptioner.cli.config import ENV_MAP


@pytest.fixture(autouse=True)
def isolated_config_files(monkeypatch, tmp_path):
    """Keep ``build_config()`` away from this machine's real config sources.

    The user's ``config.toml``, the GUI's ``settings.json`` and any
    ``OPENAI_*``/``VIDEOCAPTIONER_*`` shell variables would otherwise leak API
    keys and provider choices into assertions about defaults. Tests that want
    a source set it explicitly (``config_path``, ``gui_settings_path`` or
    ``monkeypatch.setenv``).
    """
    monkeypatch.setattr("videocaptioner.cli.config.CONFIG_FILE", tmp_path / "config.toml")
    monkeypatch.setattr(
        "videocaptioner.cli.config.gui_settings_file",
        lambda: tmp_path / "settings.json",
    )
    for env_var in ENV_MAP:
        monkeypatch.delenv(env_var, raising=False)


@pytest.fixture(autouse=True)
def ffmpeg_available(monkeypatch):
    """Pretend FFmpeg is on PATH.

    CLI commands gate on ``validate_ffmpeg()`` before any mocked work runs, so
    without this the dub/synthesize tests depend on the machine having FFmpeg
    installed instead of on the code under test.
    """
    monkeypatch.setattr("videocaptioner.cli.validators.validate_ffmpeg", lambda: True)

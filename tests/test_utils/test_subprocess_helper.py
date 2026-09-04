"""Tests for the scrubbed environment handed to child processes."""

import os
import subprocess
import sys
import time

from videocaptioner.core.utils.subprocess_helper import (
    SECRET_ENV_PREFIXES,
    child_environment,
    run_process_with_stream_reader,
)

_PRINT_KEY = "import os; print(os.environ.get('OPENAI_API_KEY', 'absent'))"


def test_credential_variables_are_dropped_case_insensitively(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-leak")
    monkeypatch.setenv("openai_base_url", "https://leak.invalid/v1")
    monkeypatch.setenv("VIDEOCAPTIONER_LLM_API_KEY", "sk-leak-2")
    monkeypatch.setenv("VC_KEEP_ME", "1")

    env = child_environment()

    assert not [k for k in env if k.upper().startswith(SECRET_ENV_PREFIXES)]
    assert env["VC_KEEP_ME"] == "1"
    assert "sk-leak" not in env.values()


def test_path_is_preserved_and_overrides_apply_last(monkeypatch):
    bundled = os.path.join("C:\\", "bundled", "ffmpeg") if os.name == "nt" else "/opt/ffmpeg"
    monkeypatch.setenv("PATH", bundled + os.pathsep + os.environ.get("PATH", ""))
    monkeypatch.setenv("PYTHONUNBUFFERED", "0")

    env = child_environment({"PYTHONUNBUFFERED": "1", "HF_HUB_OFFLINE": "1"})

    assert env["PATH"] == os.environ["PATH"]
    assert env["PYTHONUNBUFFERED"] == "1"
    assert env["HF_HUB_OFFLINE"] == "1"


def test_returns_a_detached_copy():
    env = child_environment()
    env["VC_INJECTED"] = "x"
    assert "VC_INJECTED" not in os.environ


def test_real_child_process_does_not_see_the_key(monkeypatch):
    """The scrubbed dict must still be a valid environment for this OS."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-leak")

    result = subprocess.run(
        [sys.executable, "-c", _PRINT_KEY],
        env=child_environment(),
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "absent"


def test_stream_reader_helper_scrubs_by_default(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-leak")
    lines: list[str] = []

    process = run_process_with_stream_reader(
        [sys.executable, "-c", _PRINT_KEY], stdout_handler=lines.append
    )
    assert process.wait(timeout=60) == 0
    deadline = time.monotonic() + 10
    while not lines and time.monotonic() < deadline:
        time.sleep(0.05)

    assert [line.strip() for line in lines] == ["absent"]

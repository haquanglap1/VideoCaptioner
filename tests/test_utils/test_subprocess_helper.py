"""Tests for core/utils/subprocess_helper: scrubbed child environment and the
asynchronous stream reader, using real Python child processes."""

import os
import subprocess
import sys
import time

from videocaptioner.core.utils.subprocess_helper import (
    SECRET_ENV_PREFIXES,
    StreamReader,
    child_environment,
    run_process_with_stream_reader,
)

_PRINT_KEY = "import os; print(os.environ.get('OPENAI_API_KEY', 'absent'))"
_TWO_STREAMS = (
    "import sys; print('out-1'); print('out-2'); "
    "print('err-1', file=sys.stderr); sys.stdout.flush(); sys.stderr.flush()"
)


def _wait_for(predicate, timeout=10.0):
    deadline = time.monotonic() + timeout
    while not predicate() and time.monotonic() < deadline:
        time.sleep(0.02)
    return predicate()


# ---------------------------------------------------------------------------
# child_environment
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# StreamReader / run_process_with_stream_reader
# ---------------------------------------------------------------------------


def test_stream_reader_queues_both_streams_with_labels():
    process = subprocess.Popen(
        [sys.executable, "-c", _TWO_STREAMS],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    )
    reader = StreamReader(process)
    reader.start_reading()
    assert process.wait(timeout=60) == 0
    for thread in reader.threads:
        thread.join(timeout=10)

    assert not reader.is_empty()
    lines = sorted((name, line.strip()) for name, line in reader.get_remaining_output())
    assert lines == [("stderr", "err-1"), ("stdout", "out-1"), ("stdout", "out-2")]
    assert reader.is_empty()
    assert reader.get_output(timeout=0.01) is None


def test_helper_routes_lines_to_handlers_and_scrubs_env_by_default(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-leak")
    out: list[str] = []
    err: list[str] = []

    process = run_process_with_stream_reader(
        [sys.executable, "-c", _PRINT_KEY + "; import sys; print('e', file=sys.stderr)"],
        stdout_handler=out.append,
        stderr_handler=err.append,
    )

    assert process.wait(timeout=60) == 0
    assert _wait_for(lambda: out and err)
    assert [line.strip() for line in out] == ["absent"]
    assert [line.strip() for line in err] == ["e"]


def test_helper_lets_callers_override_env():
    seen: list[str] = []

    process = run_process_with_stream_reader(
        [sys.executable, "-c", "import os; print(os.environ['VC_CUSTOM'])"],
        stdout_handler=seen.append,
        env={**child_environment(), "VC_CUSTOM": "override-wins"},
    )

    assert process.wait(timeout=60) == 0
    assert _wait_for(lambda: bool(seen))
    assert seen[0].strip() == "override-wins"


def test_helper_without_handlers_still_returns_running_process():
    process = run_process_with_stream_reader([sys.executable, "-c", "print('quiet')"])
    assert process.wait(timeout=60) == 0

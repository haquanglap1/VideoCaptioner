"""Unicode output from the windowed EXE must also work with inherited streams."""

import importlib.util
import io
from pathlib import Path
from types import SimpleNamespace

import pytest

from videocaptioner.cli.main import main
from videocaptioner.cli.output import error


@pytest.fixture
def entry():
    path = Path(__file__).resolve().parents[2] / "scripts" / "pyinstaller_gui.py"
    spec = importlib.util.spec_from_file_location("packaged_entry_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_inherited_windows_streams_print_unicode_help_and_errors(entry, monkeypatch):
    stdout_bytes, stderr_bytes = io.BytesIO(), io.BytesIO()
    stdout = io.TextIOWrapper(stdout_bytes, encoding="cp1252", errors="strict")
    stderr = io.TextIOWrapper(stderr_bytes, encoding="cp1252", errors="strict")
    streams = SimpleNamespace(stdout=stdout, stderr=stderr)
    entry.sys = streams
    entry._prepare_cli_streams()
    assert streams.stdout is stdout and streams.stderr is stderr
    with monkeypatch.context() as context:
        context.setattr("sys.stdout", stdout)
        context.setattr("sys.stderr", stderr)
        with pytest.raises(SystemExit) as result:
            main(["--help"])
        assert result.value.code == 0
        error("Phụ đề tiếng Việt → thử lại")
    stdout.flush()
    stderr.flush()
    assert "→" in stdout_bytes.getvalue().decode("utf-8")
    assert "Phụ đề tiếng Việt → thử lại" in stderr_bytes.getvalue().decode("utf-8")


def test_unicode_text_capture_streams_are_preserved(entry):
    stdout, stderr = io.StringIO(), io.StringIO()
    entry.sys = SimpleNamespace(stdout=stdout, stderr=stderr)
    entry._prepare_cli_streams()
    entry.sys.stdout.write("Phụ đề → ✓")
    entry.sys.stderr.write("Lỗi ✗")
    assert entry.sys.stdout is stdout and stdout.getvalue() == "Phụ đề → ✓"
    assert entry.sys.stderr is stderr and stderr.getvalue() == "Lỗi ✗"


def test_windowed_gui_without_streams_keeps_unicode_safe_sinks(entry):
    entry.sys = SimpleNamespace(stdout=None, stderr=None)
    entry._ensure_standard_streams()
    try:
        for stream in (entry.sys.stdout, entry.sys.stderr):
            assert stream.encoding == "utf-8"
            stream.write("Phụ đề → ✓")
            stream.flush()
    finally:
        entry.sys.stdout.close()
        entry.sys.stderr.close()

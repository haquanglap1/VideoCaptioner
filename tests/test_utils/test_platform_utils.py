"""Tests for core/utils/platform_utils: PyInstaller layout detection and the
cross-platform open/reveal helpers (with a fake Popen)."""

import os
import subprocess
import sys

import pytest

from videocaptioner.core.entities import TranscribeModelEnum
from videocaptioner.core.utils import platform_utils
from videocaptioner.core.utils.platform_utils import (
    get_available_transcribe_models,
    get_subprocess_kwargs,
    is_linux,
    is_macos,
    is_model_available,
    is_onedir_frozen_build,
    is_windows,
    open_file,
    open_folder,
    reveal_in_explorer,
)

# ---------------------------------------------------------------------------
# PyInstaller layout detection
# ---------------------------------------------------------------------------


def _freeze(monkeypatch, executable, bundle_root):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(executable))
    monkeypatch.setattr(sys, "_MEIPASS", str(bundle_root), raising=False)


def test_source_run_is_not_onedir(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    assert not is_onedir_frozen_build()


def test_pyinstaller6_onedir_layout(monkeypatch, tmp_path):
    exe = tmp_path / "VideoCaptioner" / "VideoCaptioner.exe"
    _freeze(monkeypatch, exe, exe.parent / "_internal")
    assert is_onedir_frozen_build()


def test_legacy_onedir_layout_bundles_next_to_exe(monkeypatch, tmp_path):
    exe = tmp_path / "VideoCaptioner" / "VideoCaptioner.exe"
    _freeze(monkeypatch, exe, exe.parent)
    assert is_onedir_frozen_build()


def test_onefile_extracts_to_temp_and_is_not_onedir(monkeypatch, tmp_path):
    exe = tmp_path / "Downloads" / "VideoCaptioner.exe"
    _freeze(monkeypatch, exe, tmp_path / "Temp" / "_MEI123456")
    assert not is_onedir_frozen_build()


def test_frozen_without_bundle_root_is_not_onedir(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "VideoCaptioner.exe"))
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)
    assert not is_onedir_frozen_build()


# ---------------------------------------------------------------------------
# Platform predicates
# ---------------------------------------------------------------------------


@pytest.fixture
def system(monkeypatch):
    def set_system(name: str):
        monkeypatch.setattr(platform_utils.platform, "system", lambda: name)

    return set_system


@pytest.mark.parametrize(
    "name, expected",
    [
        ("Windows", (True, False, False)),
        ("Darwin", (False, True, False)),
        ("Linux", (False, False, True)),
        ("FreeBSD", (False, False, False)),
    ],
)
def test_platform_predicates(system, name, expected):
    system(name)
    assert (is_windows(), is_macos(), is_linux()) == expected


def test_subprocess_kwargs_hide_console_only_on_windows(system):
    system("Windows")
    # The flag only exists in the Windows build of the subprocess module, so a
    # CI runner on Linux pretending to be Windows still gets no creationflags.
    if hasattr(subprocess, "CREATE_NO_WINDOW"):
        assert get_subprocess_kwargs() == {"creationflags": subprocess.CREATE_NO_WINDOW}
    else:
        assert get_subprocess_kwargs() == {}
    system("Linux")
    assert get_subprocess_kwargs() == {}


def test_faster_whisper_is_hidden_on_macos(system):
    system("Darwin")
    assert TranscribeModelEnum.FASTER_WHISPER not in get_available_transcribe_models()
    assert is_model_available(TranscribeModelEnum.FASTER_WHISPER) is False
    assert is_model_available(TranscribeModelEnum.WHISPER_CPP) is True

    system("Windows")
    assert get_available_transcribe_models() == list(TranscribeModelEnum)
    assert is_model_available(TranscribeModelEnum.FASTER_WHISPER) is True


# ---------------------------------------------------------------------------
# open / reveal helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_popen(monkeypatch):
    calls: list[tuple[list, dict]] = []

    def popen(cmd, **kwargs):
        calls.append((list(cmd), kwargs))
        return object()

    monkeypatch.setattr(platform_utils.subprocess, "Popen", popen)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-leak")
    return calls


@pytest.fixture
def no_startfile(monkeypatch):
    monkeypatch.delattr(os, "startfile", raising=False)


def _assert_scrubbed(kwargs):
    assert "OPENAI_API_KEY" not in kwargs["env"]


@pytest.mark.parametrize(
    "helper, name, expected",
    [
        (open_folder, "Darwin", ["open", "X"]),
        (open_folder, "Linux", ["xdg-open", "X"]),
        (open_folder, "Windows", ["explorer", "X"]),
        (open_file, "Darwin", ["open", "X"]),
        (open_file, "Linux", ["xdg-open", "X"]),
        (open_file, "Windows", ["cmd", "/c", "start", "", "X"]),
        (reveal_in_explorer, "Darwin", ["open", "-R", "X"]),
    ],
)
def test_open_helpers_spawn_platform_launcher(
    system, fake_popen, no_startfile, helper, name, expected
):
    system(name)
    helper("X")
    cmd, kwargs = fake_popen[0]
    assert cmd == expected
    _assert_scrubbed(kwargs)


def test_windows_prefers_os_startfile(system, fake_popen, monkeypatch):
    system("Windows")
    opened = []
    monkeypatch.setattr(os, "startfile", opened.append, raising=False)

    open_folder("C:/folder")
    open_file("C:/file.txt")

    assert opened == ["C:/folder", "C:/file.txt"]
    assert fake_popen == []


def test_reveal_on_linux_opens_parent_directory(system, fake_popen):
    system("Linux")
    reveal_in_explorer("/tmp/dir/file.srt")
    cmd, kwargs = fake_popen[0]
    assert cmd == ["xdg-open", "/tmp/dir"]
    _assert_scrubbed(kwargs)


def test_reveal_on_windows_selects_normalised_path(system, fake_popen):
    system("Windows")
    reveal_in_explorer("C:/dir/file.srt")
    cmd, _ = fake_popen[0]
    assert cmd[:2] == ["explorer", "/select,"]
    assert cmd[2] == os.path.normpath("C:/dir/file.srt")


def test_launcher_failure_is_logged_not_raised(system, monkeypatch, no_startfile):
    system("Linux")

    def failing_popen(cmd, **kwargs):
        raise OSError("xdg-open missing")

    monkeypatch.setattr(platform_utils.subprocess, "Popen", failing_popen)
    reveal_in_explorer("/tmp/x")  # swallowed by the helper's except clause
    with pytest.raises(OSError):
        open_folder("/tmp/x")  # open_folder only guards the "other system" branch

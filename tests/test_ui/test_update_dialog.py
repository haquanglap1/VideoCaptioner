"""Regression tests for the in-app updater's apply step."""

import sys

import pytest
from PyQt5.QtWidgets import QWidget

from videocaptioner.ui.components import UpdateDialog as update_dialog_module
from videocaptioner.ui.components.UpdateDialog import UpdateDialog


@pytest.fixture
def dialog(qapp):
    parent = QWidget()
    parent.resize(800, 600)
    dlg = UpdateDialog(
        version="9.9.9",
        update_info="notes",
        download_url="https://example.invalid/VideoCaptioner.exe",
        parent=parent,
    )
    yield dlg
    dlg.deleteLater()
    parent.deleteLater()


@pytest.fixture
def frozen(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "VideoCaptioner.exe"))


@pytest.fixture
def process_spy(monkeypatch, dialog):
    launched = []
    quit_calls = []
    monkeypatch.setattr(
        update_dialog_module.subprocess,
        "Popen",
        lambda *args, **kwargs: launched.append((args, kwargs)),
    )
    monkeypatch.setattr(dialog, "_quit_application", lambda: quit_calls.append(True))
    return launched, quit_calls


def test_yes_button_starts_download_instead_of_closing(dialog, monkeypatch):
    started = []
    accepted = []
    monkeypatch.setattr(dialog, "_start_download", lambda: started.append(True))
    monkeypatch.setattr(dialog, "accept", lambda: accepted.append(True))

    dialog.yesButton.click()

    assert started == [True]
    assert accepted == []


def test_onedir_build_keeps_installer_and_does_not_swap_exe(
    dialog, monkeypatch, frozen, process_spy, tmp_path
):
    launched, quit_calls = process_spy
    monkeypatch.setattr(update_dialog_module, "is_onedir_frozen_build", lambda: True)
    revealed = []
    monkeypatch.setattr(update_dialog_module, "reveal_in_explorer", revealed.append)
    downloaded = tmp_path / "VideoCaptioner_update.exe"
    downloaded.write_bytes(b"x")

    dialog._on_download_complete(str(downloaded))

    assert launched == []
    assert quit_calls == []
    assert str(downloaded) in dialog.status_label.text()
    assert dialog.yesButton.isEnabled()
    assert dialog.yesButton.text() == "Mở thư mục tải về"

    dialog.yesButton.click()
    assert revealed == [str(downloaded)]


def test_onefile_build_launches_swap_script_without_shell(
    dialog, monkeypatch, frozen, process_spy, tmp_path
):
    launched, quit_calls = process_spy
    monkeypatch.setattr(update_dialog_module, "is_onedir_frozen_build", lambda: False)
    downloaded = tmp_path / "VideoCaptioner_update.exe"
    downloaded.write_bytes(b"x")

    dialog._on_download_complete(str(downloaded))

    assert len(launched) == 1
    args, kwargs = launched[0]
    assert "shell" not in kwargs
    assert all(isinstance(part, str) for part in args[0])
    assert quit_calls == [True]


def test_source_run_never_replaces_anything(dialog, monkeypatch, process_spy, tmp_path):
    launched, quit_calls = process_spy
    monkeypatch.delattr(sys, "frozen", raising=False)
    downloaded = tmp_path / "VideoCaptioner_update.exe"
    downloaded.write_bytes(b"x")

    dialog._on_download_complete(str(downloaded))

    assert launched == []
    assert quit_calls == []
    assert not dialog.yesButton.isEnabled()

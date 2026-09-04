"""Tests for PyInstaller layout detection used by the in-app updater."""

import sys

from videocaptioner.core.utils.platform_utils import is_onedir_frozen_build


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

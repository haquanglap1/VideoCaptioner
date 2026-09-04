"""Tests for core/utils/installer without network access.

``_download`` is always replaced; the archive handling, path resolution and
PATH bookkeeping are exercised with zips built in memory.
"""

import io
import os
import zipfile

import pytest

from videocaptioner.core.utils import installer


def _zip_bytes(entries: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
    return buffer.getvalue()


@pytest.fixture
def managed_dirs(monkeypatch, tmp_path):
    ffmpeg_dir = tmp_path / "bin" / "ffmpeg"
    deno_dir = tmp_path / "bin" / "deno"
    monkeypatch.setattr(installer, "_managed_ffmpeg_dir", lambda: ffmpeg_dir)
    monkeypatch.setattr(installer, "_managed_deno_dir", lambda: deno_dir)
    # ensure_* prepend the install dir to PATH; restore it so a fake
    # ffmpeg.exe never leaks into later tests' shutil.which() lookups.
    monkeypatch.setenv("PATH", os.environ.get("PATH", ""))
    return ffmpeg_dir, deno_dir


@pytest.fixture
def no_download(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("network download must not happen in this test")

    monkeypatch.setattr(installer, "_download", refuse)


@pytest.fixture
def windows(monkeypatch):
    monkeypatch.setattr(installer, "_is_windows", lambda: True)


@pytest.fixture
def not_windows(monkeypatch):
    monkeypatch.setattr(installer, "_is_windows", lambda: False)


@pytest.fixture
def nothing_on_path(monkeypatch):
    monkeypatch.setattr(installer.shutil, "which", lambda name: None)


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------


class TestBinaryLookup:
    def test_managed_install_wins_over_path(self, managed_dirs, windows, monkeypatch):
        ffmpeg_dir, _ = managed_dirs
        ffmpeg_dir.mkdir(parents=True)
        (ffmpeg_dir / "ffmpeg.exe").write_bytes(b"exe")
        monkeypatch.setattr(installer.shutil, "which", lambda name: "C:/other/ffmpeg.exe")

        assert installer.ffmpeg_path() == ffmpeg_dir / "ffmpeg.exe"

    def test_falls_back_to_path_lookup(self, managed_dirs, windows, monkeypatch, tmp_path):
        on_path = tmp_path / "elsewhere" / "ffmpeg.exe"
        monkeypatch.setattr(installer.shutil, "which", lambda name: str(on_path))

        assert installer.ffmpeg_path() == on_path

    def test_missing_everywhere_is_none(self, managed_dirs, windows, nothing_on_path):
        assert installer.ffmpeg_path() is None
        assert installer.deno_path() is None

    def test_posix_binary_name_has_no_suffix(self, managed_dirs, not_windows, nothing_on_path):
        _, deno_dir = managed_dirs
        deno_dir.mkdir(parents=True)
        (deno_dir / "deno").write_bytes(b"elf")

        assert installer.deno_path() == deno_dir / "deno"

    def test_can_auto_install_mirrors_platform(self, monkeypatch):
        monkeypatch.setattr(installer, "_is_windows", lambda: True)
        assert installer.can_auto_install() is True
        monkeypatch.setattr(installer, "_is_windows", lambda: False)
        assert installer.can_auto_install() is False


class TestPrependToPath:
    def test_prepends_once(self, monkeypatch, tmp_path):
        monkeypatch.setenv("PATH", "C:\\base" if os.name == "nt" else "/usr/bin")
        directory = tmp_path / "tools"

        installer._prepend_to_path(directory)
        installer._prepend_to_path(directory)

        entries = os.environ["PATH"].split(os.pathsep)
        assert entries[0] == str(directory)
        assert entries.count(str(directory)) == 1
        assert len(entries) == 2


# ---------------------------------------------------------------------------
# Archive handling
# ---------------------------------------------------------------------------


class TestValidateArchive:
    def test_too_small_is_rejected(self):
        with pytest.raises(RuntimeError, match="quá nhỏ"):
            installer._validate_archive(b"x" * 10, "FFmpeg", min_bytes=100)

    def test_non_zip_is_rejected(self):
        with pytest.raises(RuntimeError, match="zip"):
            installer._validate_archive(b"<html>error</html>" * 10, "Deno", min_bytes=10)

    def test_valid_zip_passes(self):
        data = _zip_bytes({"deno.exe": b"exe" * 100})
        installer._validate_archive(data, "Deno", min_bytes=10)


class TestExtract:
    def test_ffmpeg_zip_is_flattened_to_bin_files_only(self, tmp_path):
        data = _zip_bytes(
            {
                "ffmpeg-master-latest-win64-gpl/bin/ffmpeg.exe": b"ffmpeg",
                "ffmpeg-master-latest-win64-gpl/bin/ffprobe.exe": b"ffprobe",
                "ffmpeg-master-latest-win64-gpl/bin/ffplay.exe": b"ffplay",
                "ffmpeg-master-latest-win64-gpl/doc/ffmpeg.exe": b"decoy outside bin",
                "ffmpeg-master-latest-win64-gpl/LICENSE.txt": b"gpl",
            }
        )
        install_dir = tmp_path / "ffmpeg"
        install_dir.mkdir()

        installer._extract_ffmpeg_zip(data, install_dir)

        assert sorted(p.name for p in install_dir.iterdir()) == [
            "ffmpeg.exe",
            "ffplay.exe",
            "ffprobe.exe",
        ]
        assert (install_dir / "ffmpeg.exe").read_bytes() == b"ffmpeg"

    def test_deno_zip_root_binary_is_extracted(self, tmp_path):
        data = _zip_bytes({"deno.exe": b"deno", "README.md": b"docs"})
        install_dir = tmp_path / "deno"
        install_dir.mkdir()

        installer._extract_deno_zip(data, install_dir)

        assert [p.name for p in install_dir.iterdir()] == ["deno.exe"]


# ---------------------------------------------------------------------------
# ensure_* flows
# ---------------------------------------------------------------------------


class TestEnsureFlows:
    def test_existing_ffmpeg_is_reused_without_download(
        self, managed_dirs, windows, no_download, monkeypatch, tmp_path
    ):
        ffmpeg_dir, _ = managed_dirs
        ffmpeg_dir.mkdir(parents=True)
        binary = ffmpeg_dir / "ffmpeg.exe"
        binary.write_bytes(b"exe")
        monkeypatch.setenv("PATH", "C:\\base" if os.name == "nt" else "/usr/bin")

        assert installer.ensure_ffmpeg() == binary
        assert os.environ["PATH"].split(os.pathsep)[0] == str(ffmpeg_dir)

    def test_non_windows_without_ffmpeg_points_to_package_manager(
        self, managed_dirs, not_windows, nothing_on_path, no_download
    ):
        with pytest.raises(RuntimeError, match="brew"):
            installer.ensure_ffmpeg()
        with pytest.raises(RuntimeError, match="deno.land"):
            installer.ensure_deno()

    def test_windows_install_extracts_and_reports_progress(
        self, managed_dirs, windows, nothing_on_path, monkeypatch
    ):
        ffmpeg_dir, _ = managed_dirs
        archive = _zip_bytes({"ffmpeg-x/bin/ffmpeg.exe": b"ffmpeg", "ffmpeg-x/bin/ffprobe.exe": b"p"})
        monkeypatch.setattr(installer, "_download", lambda url, cb, label="FFmpeg": archive)
        # Size floor is covered by TestValidateArchive; the tiny test zip is fine here.
        monkeypatch.setattr(installer, "_validate_archive", lambda *a, **k: None)
        progress = []

        result = installer.ensure_ffmpeg(lambda pct, msg: progress.append(pct))

        assert result == ffmpeg_dir / "ffmpeg.exe"
        assert result.read_bytes() == b"ffmpeg"
        assert (ffmpeg_dir / "ffprobe.exe").exists()
        assert progress[0] == 5 and progress[-1] == 100

    def test_windows_install_fails_when_binary_missing_from_archive(
        self, managed_dirs, windows, nothing_on_path, monkeypatch
    ):
        archive = _zip_bytes({"ffmpeg-x/doc/readme.txt": b"no binaries here"})
        monkeypatch.setattr(installer, "_download", lambda url, cb, label="FFmpeg": archive)
        monkeypatch.setattr(installer, "_validate_archive", lambda *a, **k: None)

        with pytest.raises(RuntimeError, match="binary not found"):
            installer.ensure_ffmpeg()

    def test_deno_install_extracts_root_binary(
        self, managed_dirs, windows, nothing_on_path, monkeypatch
    ):
        _, deno_dir = managed_dirs
        archive = _zip_bytes({"deno.exe": b"deno"})
        monkeypatch.setattr(installer, "_download", lambda url, cb, label="FFmpeg": archive)
        monkeypatch.setattr(installer, "_validate_archive", lambda *a, **k: None)

        assert installer.ensure_deno() == deno_dir / "deno.exe"
        assert (deno_dir / "deno.exe").read_bytes() == b"deno"

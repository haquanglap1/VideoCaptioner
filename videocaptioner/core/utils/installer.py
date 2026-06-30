"""Auto-install helpers for runtime dependencies (ffmpeg today, more later).

The GUI calls ``ensure_ffmpeg(progress_cb)`` from a background thread; the CLI
exposes it via ``videocaptioner setup ffmpeg``. We download a static build into
the app's data directory so users don't need admin rights or a package manager.
"""

from __future__ import annotations

import io
import os
import platform
import shutil
import sys
import zipfile
from pathlib import Path
from typing import Callable, Optional

from videocaptioner.config import APPDATA_PATH, BIN_PATH


# Pinned to a stable BtbN GPL build. Relatively small (~80 MB) and self-contained.
# Updated only when older builds break due to TLS/auth changes; pin avoids surprises.
FFMPEG_WIN_URL = (
    "https://github.com/BtbN/FFmpeg-Builds/releases/download/"
    "latest/ffmpeg-master-latest-win64-gpl.zip"
)

ProgressCb = Callable[[int, str], None]  # (percent 0-100, status text)


def _is_windows() -> bool:
    return platform.system() == "Windows"


def ffmpeg_path() -> Optional[Path]:
    """Return the resolved ffmpeg executable path, or None if missing.

    Search order: managed install dir → PATH → None.
    """
    managed = _managed_ffmpeg_dir() / ("ffmpeg.exe" if _is_windows() else "ffmpeg")
    if managed.exists():
        return managed
    found = shutil.which("ffmpeg")
    return Path(found) if found else None


def _managed_ffmpeg_dir() -> Path:
    return APPDATA_PATH / "bin" / "ffmpeg"


def ensure_ffmpeg(progress_cb: Optional[ProgressCb] = None) -> Path:
    """Ensure ffmpeg is installed; download into APPDATA if missing.

    Returns the absolute path to the ffmpeg binary on success.
    Raises RuntimeError on download/extract failure or unsupported platform.
    """
    existing = ffmpeg_path()
    if existing:
        _prepend_to_path(existing.parent)
        return existing

    if not _is_windows():
        raise RuntimeError(
            "Auto-install hỗ trợ Windows. Trên macOS dùng `brew install ffmpeg`, "
            "trên Linux dùng package manager (apt/pacman/dnf)."
        )

    cb = progress_cb or (lambda *_: None)
    install_dir = _managed_ffmpeg_dir()
    install_dir.mkdir(parents=True, exist_ok=True)

    cb(5, "Đang tải FFmpeg...")
    archive_bytes = _download(FFMPEG_WIN_URL, cb)

    cb(85, "Đang giải nén...")
    _extract_ffmpeg_zip(archive_bytes, install_dir)

    bin_path = install_dir / "ffmpeg.exe"
    if not bin_path.exists():
        raise RuntimeError("FFmpeg installed but binary not found after extraction")
    _prepend_to_path(bin_path.parent)
    cb(100, "Hoàn tất")
    return bin_path


# Deno is the JS runtime yt-dlp uses to solve YouTube signature/n challenges.
# Without it almost all adaptive formats are skipped (downloads collapse to 360p
# or "Requested format is not available"). Pinned to the official latest release.
DENO_WIN_URL = (
    "https://github.com/denoland/deno/releases/latest/download/"
    "deno-x86_64-pc-windows-msvc.zip"
)


def _managed_deno_dir() -> Path:
    return APPDATA_PATH / "bin" / "deno"


def deno_path() -> Optional[Path]:
    """Return the resolved deno executable path, or None if missing.

    Search order: managed install dir → PATH → None.
    """
    managed = _managed_deno_dir() / ("deno.exe" if _is_windows() else "deno")
    if managed.exists():
        return managed
    found = shutil.which("deno")
    return Path(found) if found else None


def ensure_deno(progress_cb: Optional[ProgressCb] = None) -> Path:
    """Ensure deno is installed; download into APPDATA if missing.

    Returns the absolute path to the deno binary on success.
    Raises RuntimeError on download/extract failure or unsupported platform.
    """
    existing = deno_path()
    if existing:
        _prepend_to_path(existing.parent)
        return existing

    if not _is_windows():
        raise RuntimeError(
            "Auto-install Deno hỗ trợ Windows. Trên macOS/Linux cài Deno qua "
            "`curl -fsSL https://deno.land/install.sh | sh` hoặc package manager."
        )

    cb = progress_cb or (lambda *_: None)
    install_dir = _managed_deno_dir()
    install_dir.mkdir(parents=True, exist_ok=True)

    cb(5, "Đang tải Deno (runtime giải mã YouTube)...")
    archive_bytes = _download(DENO_WIN_URL, cb, label="Deno")

    cb(85, "Đang giải nén Deno...")
    _extract_deno_zip(archive_bytes, install_dir)

    bin_path = install_dir / "deno.exe"
    if not bin_path.exists():
        raise RuntimeError("Deno installed but binary not found after extraction")
    _prepend_to_path(bin_path.parent)
    cb(100, "Hoàn tất")
    return bin_path


def _extract_deno_zip(data: bytes, install_dir: Path) -> None:
    """Extract deno.exe to install_dir. The release zip has deno.exe at its root."""
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        for name in zf.namelist():
            if Path(name).name == "deno.exe":
                target = install_dir / "deno.exe"
                with zf.open(name) as src, target.open("wb") as dst:
                    shutil.copyfileobj(src, dst)
                return


def _download(url: str, cb: ProgressCb, label: str = "FFmpeg") -> bytes:
    import urllib.request

    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "VideoCaptioner-Installer/1.0",
            "Accept": "application/octet-stream",
        },
    )
    chunks: list[bytes] = []
    received = 0
    with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310 — pinned URL
        total = int(resp.headers.get("Content-Length") or 0)
        while True:
            chunk = resp.read(64 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
            received += len(chunk)
            if total > 0:
                # Map download progress to 5-80% of overall progress.
                pct = 5 + int(75 * received / total)
                mb = received / (1024 * 1024)
                cb(pct, f"Đang tải {label}... {mb:.1f} MB")
    return b"".join(chunks)


def _extract_ffmpeg_zip(data: bytes, install_dir: Path) -> None:
    """Extract ffmpeg.exe (and ffprobe.exe, ffplay.exe if present) to install_dir.

    BtbN archives have a ``<name>/bin/ffmpeg.exe`` layout; we flatten to
    ``install_dir/ffmpeg.exe`` so PATH only needs one entry.
    """
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        wanted = ("ffmpeg.exe", "ffprobe.exe", "ffplay.exe")
        for name in zf.namelist():
            base = Path(name).name
            if base in wanted and "/bin/" in name.replace("\\", "/"):
                target = install_dir / base
                with zf.open(name) as src, target.open("wb") as dst:
                    shutil.copyfileobj(src, dst)


def _prepend_to_path(directory: Path) -> None:
    """Make `directory` discoverable for `which`/`subprocess.run` in this process."""
    current = os.environ.get("PATH", "")
    if str(directory) in current.split(os.pathsep):
        return
    os.environ["PATH"] = str(directory) + os.pathsep + current


# ---- Initialization on import ---------------------------------------------

# If ffmpeg was installed in a previous session, make sure its dir is on PATH
# *before* the rest of the app runs `subprocess.run("ffmpeg", ...)`.
_existing = _managed_ffmpeg_dir()
if (_existing / "ffmpeg.exe").exists():
    _prepend_to_path(_existing)
elif (_existing / "ffmpeg").exists():
    _prepend_to_path(_existing)

# Same for a previously auto-installed Deno, so yt-dlp can find it on PATH.
_existing_deno = _managed_deno_dir()
if (_existing_deno / "deno.exe").exists() or (_existing_deno / "deno").exists():
    _prepend_to_path(_existing_deno)

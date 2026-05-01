"""Background thread that downloads ffmpeg and reports progress.

Used by ``main_window`` (or wherever) to auto-install ffmpeg on first run
without freezing the UI.
"""

from __future__ import annotations

from PyQt5.QtCore import QThread, pyqtSignal

from videocaptioner.core.utils.installer import ensure_ffmpeg


class FFmpegInstallThread(QThread):
    progress = pyqtSignal(int, str)  # percent, message
    finished_ok = pyqtSignal(str)  # absolute path to ffmpeg
    failed = pyqtSignal(str)  # error message

    def run(self) -> None:
        try:
            path = ensure_ffmpeg(progress_cb=lambda p, m: self.progress.emit(p, m))
            self.finished_ok.emit(str(path))
        except Exception as exc:  # noqa: BLE001 — surface any failure to UI
            self.failed.emit(str(exc))

"""Playlist workers keep network/media work off Qt's main thread."""

from contextvars import copy_context
from pathlib import Path

from PyQt5.QtCore import QThread, pyqtSignal

from videocaptioner.core.playlist import (
    DownloadCancelled,
    discover_playlist,
    download_playlist,
    friendly_error,
)


class PlaylistThread(QThread):
    result = pyqtSignal(object)
    progress = pyqtSignal(object, int)
    error = pyqtSignal(str)
    cancelled = pyqtSignal()

    def __init__(self, *, url="", scope="auto", info=None, selected=(), output="", cookies=None):
        super().__init__()
        self.url, self.scope = url, scope
        self.info, self.selected = info, tuple(selected)
        self.output = Path(output)
        self.cookies = Path(cookies) if cookies else None
        self.context = copy_context()

    def run(self):
        self.context.run(self._run)

    def _run(self):
        try:
            if self.info is None:
                result = discover_playlist(self.url, cookies=self.cookies, scope=self.scope,
                                           cancelled=self.isInterruptionRequested)
            else:
                result = download_playlist(self.info, self.selected, self.output, cookies=self.cookies,
                    cancelled=self.isInterruptionRequested, progress=self.progress.emit)
            self.result.emit(result)
        except DownloadCancelled:
            self.cancelled.emit()
        except Exception as exc:
            if self.isInterruptionRequested():
                self.cancelled.emit()
            else:
                self.error.emit(friendly_error(exc))

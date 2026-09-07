"""Verify a selected recording without loading a model or calling a provider."""

from contextvars import copy_context
from threading import Event

from PyQt5.QtCore import QThread, pyqtSignal

from videocaptioner.core.asr.audio_identity import AudioIdentity, verify_audio_file


class AudioIdentityThread(QThread):
    result = pyqtSignal(bool, str)

    def __init__(self, identity: AudioIdentity | None, path: str):
        super().__init__()
        self.identity, self.path = identity, path
        self.context = copy_context()
        self._cancelled = Event()

    def stop(self):
        self._cancelled.set()
        self.requestInterruption()

    def check(self):
        if self._cancelled.is_set() or self.isInterruptionRequested():
            raise ValueError("Audio verification cancelled.")

    def run(self):
        self.context.run(self._run)

    def _run(self):
        try:
            self.check()
            verified = verify_audio_file(self.identity, self.path, self.check)
            self.check()
            self.result.emit(verified, "")
        except (OSError, ValueError, RuntimeError) as exc:
            if not self._cancelled.is_set():
                self.result.emit(False, str(exc))

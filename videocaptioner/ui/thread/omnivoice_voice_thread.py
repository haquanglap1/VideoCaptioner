"""Import a private OmniVoice reference without blocking the Qt event loop."""

from PyQt5.QtCore import QThread, pyqtSignal

from videocaptioner.core.tts.omnivoice.voices import save_voice


class OmniVoiceImportThread(QThread):
    saved = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, name: str, audio: str, transcript: str, language: str):
        super().__init__()
        self.arguments = (name, audio, transcript, language)

    def run(self):
        def check():
            if self.isInterruptionRequested():
                raise RuntimeError("Đã hủy lưu giọng mẫu.")

        try:
            profile = save_voice(*self.arguments, check=check)
            check()
            self.saved.emit(profile.voice_id)
        except Exception as exc:
            if not self.isInterruptionRequested():
                self.failed.emit(str(exc))

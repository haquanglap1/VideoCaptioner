"""Explicit reference transcription and text/audio work outside the Qt main thread."""

from copy import deepcopy

from PyQt5.QtCore import QThread, pyqtSignal

from videocaptioner.core.tts.omnivoice.reference import transcribe_reference
from videocaptioner.core.tts.omnivoice.text_audio import export_text_audio


class OmniVoiceToolsThread(QThread):
    completed = pyqtSignal(object)
    failed = pyqtSignal(str)
    progress = pyqtSignal(str)

    def __init__(self, operation, *, audio="", asr_options=None, text="", output="", config=None):
        super().__init__()
        self.operation = operation
        self.audio, self.asr_options = audio, asr_options
        self.text, self.output, self.config = text, output, deepcopy(config)

    def check(self, _progress=0, message=""):
        if self.isInterruptionRequested():
            raise RuntimeError("Đã hủy tiện ích OmniVoice")
        self.progress.emit(message or ("Đang chép lời mẫu bằng ASR local..." if self.operation == "transcribe"
                                       else "Đang tạo audio từ văn bản..."))

    def run(self):
        try:
            self.check()
            if self.operation == "transcribe":
                if self.asr_options is None:
                    raise ValueError("Reference ASR configuration is required")
                result = transcribe_reference(self.audio, self.asr_options, self.check)
            elif self.operation == "text_audio":
                result = export_text_audio(self.text, self.output, self.config, self.check)
            else:
                raise ValueError("Unknown OmniVoice utility")
            self.check(100, "Hoàn tất")
            self.completed.emit(result)
        except Exception as exc:
            if not self.isInterruptionRequested():
                self.failed.emit(str(exc))

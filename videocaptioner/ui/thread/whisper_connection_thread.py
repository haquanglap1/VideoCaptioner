"""Background recognition probe shared by the two settings surfaces."""

from contextvars import copy_context

from PyQt5.QtCore import QThread, pyqtSignal

from videocaptioner.core.llm.check_whisper import check_whisper_connection


class WhisperConnectionThread(QThread):
    finished = pyqtSignal(bool, str)
    error = pyqtSignal(str)

    def __init__(self, base_url, api_key, model, provider="custom", request_profile="auto", parent=None):
        super().__init__(parent)
        self.base_url = base_url
        self.api_key = api_key
        self.model = model
        self.provider = provider
        self.request_profile = request_profile
        self.context = copy_context()

    def run(self):
        success, result = self.context.run(
            check_whisper_connection, self.base_url, self.api_key, self.model,
            provider=self.provider, request_profile=self.request_profile,
        )
        self.finished.emit(success, self.tr(result))

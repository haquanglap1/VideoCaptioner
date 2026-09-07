"""Explicit native service probe; no inference, speaker claim or startup network."""

from contextvars import copy_context

from PyQt5.QtCore import QThread, pyqtSignal

from videocaptioner.core.asr.native_profiles import NativeASRConfig


class NativeASRProbeThread(QThread):
    result = pyqtSignal(str)

    def __init__(self, config: NativeASRConfig, parent=None):
        super().__init__(parent)
        self.config = config
        self.context = copy_context()

    def run(self):
        self.context.run(self._probe)

    def _probe(self):
        from videocaptioner.core.asr.native_api import probe_service

        def check():
            if self.isInterruptionRequested():
                raise InterruptedError

        try:
            probe_service(self.config, check)
            self.result.emit(self.tr("Service probe passed. Recognition, timing and speakers are not tested."))
        except InterruptedError:
            self.result.emit(self.tr("Service probe cancelled."))
        except Exception:
            self.result.emit(self.tr("Service probe failed. Check endpoint, key and read permissions; ASR access is not tested."))

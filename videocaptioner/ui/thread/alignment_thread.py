"""Explicit local health probe with cancellation and context propagation."""

from contextvars import copy_context

from PyQt5.QtCore import QThread, pyqtSignal

from videocaptioner.core.asr.alignment.contract import AlignmentError
from videocaptioner.core.asr.alignment.runtime import AlignmentRuntime


class AlignmentThread(QThread):
    status = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.context = copy_context()

    def run(self):
        self.context.run(self._probe)

    def _probe(self):
        runtime = None
        try:
            runtime = AlignmentRuntime()
            self.status.emit(self.tr("Starting Chinese alignment runtime..."))

            def check():
                if self.isInterruptionRequested():
                    raise AlignmentError("cancelled")

            runtime.start("zh", check)
            self.status.emit(self.tr("Chinese alignment ready. Probe runtime released."))
        except AlignmentError as exc:
            self.status.emit(str(exc))
        except Exception:
            self.status.emit(self.tr("Chinese alignment runtime failed."))
        finally:
            if runtime is not None:
                runtime.close()

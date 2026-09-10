"""Supervised OCR jobs; heavy work stays outside the Qt event loop."""

from contextvars import copy_context
from pathlib import Path
from threading import Event
from typing import Callable

from PyQt5.QtCore import QThread, pyqtSignal

from videocaptioner.core.entities import OcrTask
from videocaptioner.core.ocr.document import OcrDocument
from videocaptioner.core.ocr.installation import inspect_installation
from videocaptioner.core.ocr.models import Check, OcrError
from videocaptioner.core.ocr.service import run_cpu_ocr


class OcrWorker(QThread):
    result_ready = pyqtSignal(object)
    failed = pyqtSignal(str)
    progress = pyqtSignal(int, str)

    def __init__(self, operation: Callable[[Check], object]):
        super().__init__()
        self.operation = operation
        self.context = copy_context()
        self.cancelled = Event()
        self.error_message = ""

    def stop(self):
        self.cancelled.set()
        self.requestInterruption()

    def check(self):
        if self.cancelled.is_set() or self.isInterruptionRequested():
            raise OcrError("Đã hủy tác vụ OCR.")

    def run(self):
        self.context.run(self._run)

    def _run(self):
        try:
            self.check()
            result = self.operation(self.check)
            self.check()
            self.result_ready.emit(result)
        except Exception as exc:
            if not self.cancelled.is_set():
                # OS errors can include private file names; domain errors are sanitized.
                self.error_message = str(exc) if isinstance(exc, OcrError) else "Không hoàn thành tác vụ OCR; kiểm tra nguồn và runtime."
                self.failed.emit(self.error_message)


class OcrThread(OcrWorker):
    def __init__(self, task: OcrTask):
        self.task = task
        self.partial_document: OcrDocument | None = None
        super().__init__(self.scan)

    def scan(self, check: Check) -> OcrDocument:
        self.progress.emit(0, "Kiểm tra runtime OCR đã cài…")
        installation = inspect_installation(Path(self.task.runtime_path) if self.task.runtime_path else None, check)
        config = installation.config(self.task.roi, self.task.selection)
        self.progress.emit(0, "Đang đọc phụ đề trong hình bằng CPU…")
        return run_cpu_ocr(Path(self.task.file_path), config, installation.root, installation.bridge,
                           max_requests=self.task.max_requests, check=check,
                           checkpoint=self.capture, progress=self.progress.emit,
                           expected_source_sha256=self.task.expected_source_sha256)

    def capture(self, document: OcrDocument) -> None:
        self.partial_document = document

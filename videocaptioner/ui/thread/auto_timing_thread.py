"""Owned Auto timing work, with context and cancellation across HTTP/media processing."""

from contextvars import copy_context
from copy import deepcopy

from PyQt5.QtCore import QThread, pyqtSignal

from videocaptioner.core.llm.context import set_task_context
from videocaptioner.ui.thread.dubbing_thread import DubbingCancelled, _engine_for_task


class AutoTimingThread(QThread):
    result = pyqtSignal(object)
    error = pyqtSignal(str)
    cancelled = pyqtSignal()
    progress = pyqtSignal(int, str)

    def __init__(self, task, *, use_llm: bool, allow_video_slowdown: bool, parent=None):
        super().__init__(parent)
        self.task = deepcopy(task)
        self.use_llm = use_llm
        self.allow_video_slowdown = allow_video_slowdown
        self.context = copy_context()

    def run(self):
        self.context.run(self._run)

    def _progress(self, value, message):
        if self.isInterruptionRequested():
            raise DubbingCancelled("Auto timing interrupted")
        self.progress.emit(value, message)

    def _run(self):
        try:
            self._progress(0, "Đang tự căn timing/tốc độ...")
            task = self.task
            if not task.dubbing_config or not task.dubbing_review or not task.video_path or not task.subtitle_path:
                raise ValueError("Chọn nguồn và duyệt lời trước khi tự căn timing.")
            set_task_context(task.task_id, "", "auto-timing")
            engine = _engine_for_task(task)
            result = engine.propose_timing(task.video_path, task.subtitle_path, task.dubbing_config,
                task.dubbing_review, self._progress, display_subtitle_path=task.display_subtitle_path,
                use_llm=self.use_llm, allow_video_slowdown=self.allow_video_slowdown,
                cancelled=self.isInterruptionRequested)
            self._progress(100, "Đã hoàn tất phân tích; xem trạng thái dự báo/đã đo.")
            self.result.emit(result)
        except Exception as exc:
            if self.isInterruptionRequested() or isinstance(exc, DubbingCancelled):
                self.cancelled.emit()
            else:
                self.error.emit(str(exc))

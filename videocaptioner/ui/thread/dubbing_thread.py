"""Dubbing thread — chạy DubbingEngine trên QThread."""

import datetime
from copy import deepcopy
from pathlib import Path
from typing import Literal

from PyQt5.QtCore import QThread, pyqtSignal

from videocaptioner.core.dubbing.engine import DubbingEngine
from videocaptioner.core.dubbing.review import DubbingReview
from videocaptioner.core.entities import DubbingTask
from videocaptioner.core.utils.logger import setup_logger

logger = setup_logger("dubbing_thread")


class DubbingCancelled(Exception):
    """Raised from the progress callback once the thread was asked to stop."""


def _engine_for_task(task: DubbingTask) -> DubbingEngine:
    """Validate the explicitly selected cache folder on the calling worker."""
    if not task.cache_root:
        return DubbingEngine()
    root = Path(task.cache_root)
    if not root.is_dir():
        raise ValueError("Thư mục WAV cache không tồn tại hoặc không phải thư mục: " + str(root))
    task.cache_root = str(root.resolve())
    return DubbingEngine(cache_root=task.cache_root)


class DubbingThread(QThread):
    """Thread lồng tiếng video."""

    finished = pyqtSignal(DubbingTask)
    progress = pyqtSignal(int, str)
    error = pyqtSignal(str)
    report_ready = pyqtSignal(object)
    plan_ready = pyqtSignal(object)
    cancelled = pyqtSignal()

    def __init__(self, task: DubbingTask, *, resume: bool = False):
        super().__init__()
        self.task = task
        self.resume = resume

    @property
    def lifecycle_finished(self):
        """Native thread completion, separate from the legacy task result signal."""
        return super().finished

    def run(self):
        engine = None
        try:
            self.task.started_at = datetime.datetime.now()
            self.task.completed_at = None
            self._check_cancelled()

            config = self.task.dubbing_config
            if not config:
                raise ValueError("DubbingConfig chưa được cấu hình")

            logger.info("\n%s", config.print_config())

            video_path = self.task.video_path
            subtitle_path = self.task.subtitle_path
            output_path = self.task.output_path

            if not video_path:
                raise ValueError(self.tr("Đường dẫn video đang trống"))
            if not subtitle_path:
                raise ValueError(self.tr("Đường dẫn phụ đề đang trống"))
            if not output_path:
                raise ValueError(self.tr("Đường dẫn đầu ra đang trống"))

            engine = _engine_for_task(self.task)
            resume_args = {}
            if self.resume:
                if self.task.dubbing_review is None:
                    raise ValueError("Không có kế hoạch lời đọc để tiếp tục")
                resume_args["review"] = self.task.dubbing_review
            if self.task.display_subtitle_path:
                resume_args["display_subtitle_path"] = self.task.display_subtitle_path
            engine.dub(
                video_path=video_path,
                subtitle_path=subtitle_path,
                output_path=output_path,
                config=config,
                callback=self._progress_callback,
                **resume_args,
            )
            self._capture_review(engine)
            self._check_cancelled()

            self.task.completed_at = datetime.datetime.now()
            self.progress.emit(100, self.tr("Lồng tiếng hoàn tất"))
            self.finished.emit(self.task)

        except DubbingCancelled:
            if engine is not None:
                self._capture_review(engine)
            logger.info("Dubbing stopped before completion (interruption requested)")
            self.progress.emit(100, self.tr("Lồng tiếng đã bị hủy"))
            self.cancelled.emit()
        except Exception as e:
            if engine is not None:
                self._capture_review(engine)
            if self.isInterruptionRequested():
                self.progress.emit(100, self.tr("Lồng tiếng đã bị hủy"))
                self.cancelled.emit()
                return
            logger.exception("Dubbing thất bại: %s", e)
            self.error.emit(str(e))
            self.progress.emit(100, self.tr("Lồng tiếng thất bại"))

    def _progress_callback(self, value: int, message: str):
        # Runs on the engine's thread and inside its TTS worker threads; raising
        # here is what unwinds a job, since the core API has no cancel token.
        self._check_cancelled()
        self.progress.emit(value, message)

    def _check_cancelled(self):
        if self.isInterruptionRequested():
            raise DubbingCancelled("dubbing interrupted")

    def _capture_review(self, engine):
        self.task.report_path = engine.last_report_path
        self.task.dubbing_report = engine.last_report
        if self.task.dubbing_report:
            self.report_ready.emit(self.task.dubbing_report)
        review = getattr(engine, "last_review", None)
        if review is not None:
            self.task.dubbing_review = review
            self.plan_ready.emit(review)


class DubbingReviewFileThread(QThread):
    """Explicit plan file I/O and legacy source binding outside the UI thread."""

    result = pyqtSignal(object)
    error = pyqtSignal(str)
    cancelled = pyqtSignal()
    progress = pyqtSignal(int, str)

    def __init__(self, operation: Literal["open", "save", "import"], path: str,
                 task: DubbingTask, parent=None):
        super().__init__(parent)
        self.operation = operation
        self.path = path
        self.task = deepcopy(task)

    def _progress_callback(self, value: int, message: str) -> None:
        if self.isInterruptionRequested():
            raise DubbingCancelled("dubbing review interrupted")
        self.progress.emit(value, message)

    def run(self) -> None:
        try:
            self._progress_callback(0, self.tr("Đang xử lý kế hoạch lời đọc..."))
            if self.operation == "save":
                review = self.task.dubbing_review
                if review is None:
                    raise ValueError("Không có kế hoạch lời đọc để lưu")
                review.save(self.path)
            else:
                if not self.task.dubbing_config or not self.task.video_path or not self.task.subtitle_path:
                    raise ValueError("Chọn video, phụ đề và bật cấu hình giọng trước khi mở kế hoạch")
                engine = _engine_for_task(self.task)
                review = DubbingReview.load(self.path)
                self._progress_callback(15, self.tr("Đã đọc kế hoạch lời đọc"))
                if self.operation == "import":
                    config = self.task.dubbing_config
                    if config is None or not self.task.video_path or not self.task.subtitle_path:
                        raise ValueError("Chọn video, phụ đề và cấu hình giọng trước khi nhập checkpoint")
                    review = engine.import_review(
                        review, video_path=self.task.video_path, subtitle_path=self.task.subtitle_path,
                        config=config, display_subtitle_path=self.task.display_subtitle_path,
                        callback=self._progress_callback,
                    )
                elif not review.can_resume:
                    raise ValueError("Checkpoint thiếu liên kết nguồn. Dùng nút Nhập checkpoint cũ để kiểm tra và liên kết rõ ràng.")
            self._progress_callback(100, self.tr("Đã xử lý kế hoạch lời đọc"))
            self.result.emit(review)
        except Exception as exc:
            if isinstance(exc, DubbingCancelled) or self.isInterruptionRequested():
                self.cancelled.emit()
            else:
                self.error.emit(str(exc))

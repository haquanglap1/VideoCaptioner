"""Dubbing thread — chạy DubbingEngine trên QThread."""

import datetime
from copy import deepcopy
from pathlib import Path
from time import monotonic
from typing import Literal

from PyQt5.QtCore import QThread, pyqtSignal

from videocaptioner.core.dubbing.completed import (
    CompletedVideo,
    load_legacy_video,
    load_video,
    save_video,
    video_identity,
)
from videocaptioner.core.dubbing.engine import DubbingEngine
from videocaptioner.core.dubbing.output import OutputClaim, video_destination
from videocaptioner.core.dubbing.review import DubbingReview
from videocaptioner.core.entities import DubbingTask
from videocaptioner.core.llm.context import task_context
from videocaptioner.core.llm.rate_limit import llm_admission_scope
from videocaptioner.core.utils.gpu_lease import gpu_job_scope
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

    def __init__(self, task: DubbingTask, *, resume: bool = False, automatic: bool = False):
        super().__init__()
        self.task = task
        self.resume = resume
        self.automatic = automatic
        self.llm_gate = None
        self.output_reservations = None
        self.gpu_session = None
        self.output_claim = None
        self.output_root = None

    @property
    def lifecycle_finished(self):
        """Native thread completion, separate from the legacy task result signal."""
        return super().finished

    def run(self):
        from videocaptioner.core.utils.subprocess_helper import cancellation_scope
        started = monotonic()
        try:
            with (cancellation_scope(self._check_cancelled), llm_admission_scope(self.llm_gate),
                  task_context(self.task.task_id, Path(self.task.video_path or "").name, "dubbing"),
                  gpu_job_scope(self.gpu_session, self._check_cancelled,
                                lambda: self.progress.emit(0, self.tr("Chờ GPU của tác vụ khác...")))):
                self._run()
        except Exception as exc:
            if not self.isInterruptionRequested():
                self.failure = exc
                self.error.emit(str(exc))
        finally:
            if self.output_claim:
                self.output_claim.close()
            logger.info("Dubbing job: task=%s completed=%s elapsed_seconds=%.3f", self.task.task_id,
                        self.task.completed_at is not None, monotonic() - started)

    def _run(self):
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

            destination = video_destination(output_path, "" if self.task.preview_only else self.task.output_directory,
                                            video_path)
            self.task.output_path = output_path = str(destination.output)
            receipt, self.output_root = destination.receipt, destination.root
            identity = ""
            if not self.task.preview_only and not self.resume and self.task.auto_timing_plan is None:
                identity = video_identity(video_path, subtitle_path, config, self.task.display_subtitle_path, self._check_cancelled)
                if config.reuse_completed:
                    cached = load_video(receipt, identity, self._check_cancelled, root=self.output_root)
                    if cached is None and self.output_root is None:
                        cached = load_legacy_video(video_path, subtitle_path, output_path, config, self._check_cancelled)
                    if cached:
                        self.task.output_path = cached.output
                        self.task.playback_subtitle_path = cached.captions or None
                        self.task.completed_at = datetime.datetime.now()
                        self._save_completed(receipt, identity, cached)
                        self.progress.emit(100, self.tr("Đã có video lồng tiếng; dùng lại, không xuất lại"))
                        self.finished.emit(self.task)
                        return

            if not self.task.preview_only:
                from .video_title import prepare_video_title
                prepare_video_title(self.task, self._check_cancelled, self.progress.emit, self.output_reservations)
                if self.output_root is not None:
                    self.output_claim = OutputClaim(self.task.output_path, self._check_cancelled)
                    self.task.output_path = str(self.output_claim.path)
                output_path = self.task.output_path
                assert output_path is not None

            engine = _engine_for_task(self.task)
            resume_args = {}
            if self.automatic:
                resume_args["review_before_tts"] = False
            if self.resume:
                if self.task.dubbing_review is None:
                    raise ValueError("Không có kế hoạch lời đọc để tiếp tục")
                resume_args["review"] = self.task.dubbing_review
            if self.task.display_subtitle_path:
                resume_args["display_subtitle_path"] = self.task.display_subtitle_path
            if self.task.auto_timing_plan is not None:
                resume_args["timing_plan"] = self.task.auto_timing_plan
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

            if identity:
                self._save_completed(receipt, identity, CompletedVideo(output_path, self.task.playback_subtitle_path or ""))
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
            self.failure = e
            if engine is not None:
                self._capture_review(engine)
            if self.isInterruptionRequested():
                self.progress.emit(100, self.tr("Lồng tiếng đã bị hủy"))
                self.cancelled.emit()
                return
            logger.exception("Dubbing thất bại: %s", e)
            self.error.emit(str(e))
            self.progress.emit(100, self.tr("Lồng tiếng thất bại"))

    def _save_completed(self, receipt, identity, result):
        try:
            save_video(receipt, identity, result, self._check_cancelled, root=self.output_root)
        except (OSError, ValueError):
            logger.warning("Could not save completed dubbing receipt")

    def _progress_callback(self, value: int, message: str):
        # Runs on the engine's thread and inside its TTS worker threads; raising
        # here is what unwinds a job, since the core API has no cancel token.
        self._check_cancelled()
        self.progress.emit(value, message)

    def _check_cancelled(self):
        if self.isInterruptionRequested():
            raise DubbingCancelled("dubbing interrupted")

    def _capture_review(self, engine):
        self.task.playback_subtitle_path = getattr(engine, "last_subtitle_path", "") or None
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

    def __init__(self, operation: Literal["open", "save", "import", "prepare"], path: str,
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
                if self.operation == "prepare":
                    review = engine.prepare_review(self.task.video_path, self.task.subtitle_path,
                        self.task.dubbing_config, callback=self._progress_callback,
                        display_subtitle_path=self.task.display_subtitle_path)
                    self._progress_callback(100, self.tr("Đã chuẩn bị lời đọc; chưa sinh audio"))
                    self.result.emit(review)
                    return
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

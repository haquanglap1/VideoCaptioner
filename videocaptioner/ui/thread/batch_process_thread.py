"""GUI-owned batch queue with retained workers and asynchronous cancellation."""

from collections import deque
from pathlib import Path
from typing import Optional

from PyQt5.QtCore import QObject, Qt, QThread, QTimer, pyqtSignal
from PyQt5.QtWidgets import QApplication

from videocaptioner.core.entities import (
    BatchTaskStatus,
    BatchTaskType,
    SubtitleLayoutEnum,
    SupportedSubtitleFormats,
)
from videocaptioner.core.llm.rate_limit import find_rate_limit
from videocaptioner.core.utils.logger import setup_logger
from videocaptioner.ui.common.config import cfg
from videocaptioner.ui.task_factory import TaskFactory
from videocaptioner.ui.thread.dubbing_thread import DubbingThread
from videocaptioner.ui.thread.subtitle_thread import SubtitleThread
from videocaptioner.ui.thread.transcript_thread import TranscriptThread
from videocaptioner.ui.thread.video_synthesis_thread import VideoSynthesisThread
from videocaptioner.ui.thread.worker_lifecycle import cancel_worker, retain_worker

logger = setup_logger("batch_process_thread")


class BatchTask:
    def __init__(self, file_path: str, task_type: BatchTaskType):
        self.file_path = file_path
        self.task_type = task_type
        self.status = BatchTaskStatus.WAITING
        self.progress = 0
        self.error_message = ""
        self.current_thread: Optional[QThread] = None


class BatchProcessThread(QObject):
    """Keep the public name; scheduling no longer needs a polling thread."""

    task_progress = pyqtSignal(str, int, str)
    task_error = pyqtSignal(str, str)
    task_completed = pyqtSignal(str)
    task_cancelled = pyqtSignal(str)
    busy_changed = pyqtSignal(bool)

    def __init__(self):
        super().__init__()
        self.task_queue = deque()
        self.current_tasks: dict[str, BatchTask] = {}
        self.factory = TaskFactory()
        self.threads: list[QThread] = []
        self._closing = False
        app = QApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self.shutdown)

    def isRunning(self):
        return bool(self.threads or self.task_queue)

    def add_task(self, task: BatchTask):
        old = self.current_tasks.get(task.file_path)
        if self._closing or (old and old.status in (
                BatchTaskStatus.WAITING, BatchTaskStatus.RUNNING, BatchTaskStatus.STOPPING)):
            return
        self.current_tasks[task.file_path] = task
        self.task_queue.append(task)
        self.busy_changed.emit(True)
        QTimer.singleShot(0, self._pump)

    def _pump(self):
        if self._closing or self.threads:
            return
        while self.task_queue:
            task = self.task_queue.popleft()
            if task.status != BatchTaskStatus.WAITING:
                continue
            task.status = BatchTaskStatus.RUNNING
            self.task_progress.emit(task.file_path, 0, str(task.status))
            try:
                if task.task_type == BatchTaskType.SUBTITLE:
                    self._subtitle(task, task.file_path)
                elif task.task_type == BatchTaskType.DUBBING:
                    if not cfg.dubbing_enabled.value:
                        raise ValueError("Lồng tiếng đang tắt — hãy bật ở tab Lồng tiếng trước")
                    subtitle = self._find_subtitle_for_video(task.file_path)
                    if not subtitle:
                        raise ValueError("Không tìm thấy phụ đề cùng tên trong thư mục")
                    self._dub(task, subtitle, subtitle)
                else:
                    self._transcribe(task)
            except Exception as exc:
                self._fail(task, str(exc))
            if self.threads:
                break
        self.busy_changed.emit(self.isRunning())

    def _fail(self, task, error):
        task.status = BatchTaskStatus.FAILED
        task.error_message = error
        self.task_error.emit(task.file_path, error)

    def _complete(self, task):
        task.status = BatchTaskStatus.COMPLETED
        task.progress = 100
        self.task_completed.emit(task.file_path)

    def _start(self, task, worker, start, end, success):
        if self._closing or task.status != BatchTaskStatus.RUNNING:
            return
        task.current_thread = worker
        self.threads.append(worker)
        outcome = {}

        def progress(value, message):
            if task.current_thread is worker and task.status == BatchTaskStatus.RUNNING:
                task.progress = start + int(value * (end - start) / 100)
                self.task_progress.emit(task.file_path, task.progress, message)

        def settle():
            # Result signals precede native completion and process cleanup.
            if not worker.wait(0):
                QTimer.singleShot(10, settle)
                return
            if worker in self.threads:
                self.threads.remove(worker)
            if self._closing or task.status == BatchTaskStatus.STOPPING:
                task.status = BatchTaskStatus.CANCELLED
                self.task_cancelled.emit(task.file_path)
            elif "error" in outcome:
                self._fail(task, outcome["error"])
                if find_rate_limit(getattr(worker, "failure", None)):
                    # A provider rejection is shared by the queue, not a broken video.
                    for queued in tuple(self.task_queue):
                        self.stop_task(queued.file_path)
            elif "result" in outcome:
                try:
                    success(*outcome["result"])
                except Exception as exc:
                    logger.exception("Batch stage handoff failed")
                    self._fail(task, str(exc))
            else:
                self._fail(task, "Tiến trình kết thúc mà không có kết quả.")
            self.busy_changed.emit(self.isRunning())
            QTimer.singleShot(0, self._pump)

        worker.progress.connect(progress, Qt.ConnectionType.QueuedConnection)
        worker.error.connect(lambda error: outcome.update(error=error), Qt.ConnectionType.QueuedConnection)
        worker.finished.connect(lambda *args: outcome.update(result=args), Qt.ConnectionType.QueuedConnection)
        QThread.finished.__get__(worker).connect(settle, Qt.ConnectionType.QueuedConnection)
        retain_worker(worker)
        worker.start()

    def _transcribe(self, task):
        next_stage = task.task_type != BatchTaskType.TRANSCRIBE
        trans = self.factory.create_transcribe_task(task.file_path, need_next_task=next_stage)

        def done(result):
            if not next_stage:
                self._complete(task)
            else:
                self._subtitle(task, result.output_path, result.asr_data)

        self._start(task, TranscriptThread(trans), 0, 100 if not next_stage else 25, done)

    def _subtitle(self, task, path, asr_data=None):
        full = task.task_type == BatchTaskType.FULL_PROCESS
        linked_video = task.task_type in (BatchTaskType.FULL_PROCESS, BatchTaskType.TRANS_SUB)
        subtitle = self.factory.create_subtitle_task(path, task.file_path if linked_video else None, need_next_task=linked_video)
        subtitle.asr_data = asr_data
        worker = SubtitleThread(subtitle)

        def done(video, display):
            if not full:
                self._complete(task)
            elif cfg.dubbing_enabled.value:
                self._dub(task, worker.task.dubbing_subtitle_path or display, display)
            else:
                self._synthesize(task, task.file_path, display, worker.task.subtitle_config.subtitle_layout)

        self._start(task, worker, 0 if task.task_type == BatchTaskType.SUBTITLE else 25, 50 if full else 100, done)

    def _dub(self, task, subtitle, display):
        dubbing = self.factory.create_dubbing_task(task.file_path, subtitle, display_subtitle_path=display)
        full = task.task_type == BatchTaskType.FULL_PROCESS
        if full and cfg.need_video.value and dubbing.dubbing_config:
            # Burn once, after retiming, using captions produced by dubbing.
            dubbing.dubbing_config.subtitle_mode = "none"
            dubbing.dubbing_config.output_resolution = 0
            dubbing.title_translation = None

        def done(result):
            if full:
                self._synthesize(task, result.output_path, result.playback_subtitle_path or display,
                                 SubtitleLayoutEnum.ONLY_TRANSLATE if result.playback_subtitle_path else cfg.subtitle_layout.value)
            else:
                self._complete(task)

        self._start(task, DubbingThread(dubbing, automatic=True), 50 if full else 0, 75 if full else 100, done)

    def _synthesize(self, task, video, subtitle, layout):
        synthesis = self.factory.create_synthesis_task(video, subtitle, input_subtitle_layout=layout,
                                                       title_source=task.file_path)
        self._start(task, VideoSynthesisThread(synthesis), 75, 100, lambda *_: self._complete(task))

    @staticmethod
    def _find_subtitle_for_video(video_path: str) -> Optional[str]:
        video = Path(video_path)
        for ext in ["srt"] + [fmt.value for fmt in SupportedSubtitleFormats if fmt.value != "srt"]:
            candidate = video.with_suffix(f".{ext}")
            if candidate.exists():
                return str(candidate)
        return None

    def stop_task(self, file_path: str):
        task = self.current_tasks.get(file_path)
        if task is None:
            return
        if task.status == BatchTaskStatus.WAITING:
            self.task_queue = deque(item for item in self.task_queue if item is not task)
            task.status = BatchTaskStatus.CANCELLED
            self.task_cancelled.emit(file_path)
        elif task.status == BatchTaskStatus.RUNNING:
            task.status = BatchTaskStatus.STOPPING
            self.task_progress.emit(file_path, task.progress, str(task.status))
            if task.current_thread:
                cancel_worker(task.current_thread)
        self.busy_changed.emit(self.isRunning())

    def stop_all(self):
        # No wait() on the GUI thread. Native completion acknowledges the stop.
        for path in tuple(self.current_tasks):
            self.stop_task(path)

    def shutdown(self):
        self._closing = True
        self.stop_all()

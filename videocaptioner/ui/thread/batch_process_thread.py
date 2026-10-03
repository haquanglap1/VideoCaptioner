"""GUI-owned batch queue with retained workers and asynchronous cancellation."""

from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional
from uuid import uuid4

from PyQt5.QtCore import QObject, Qt, QThread, QTimer, pyqtSignal
from PyQt5.QtWidgets import QApplication

from videocaptioner.core.batch import BatchAdmission, BatchLimits, BatchStage, asr_uses_gpu
from videocaptioner.core.dubbing.config import TTSProviderEnum
from videocaptioner.core.entities import (
    BatchTaskStatus,
    BatchTaskType,
    SubtitleLayoutEnum,
    SupportedSubtitleFormats,
    TranscribeModelEnum,
)
from videocaptioner.core.llm.rate_limit import RateLimitGate, find_rate_limit
from videocaptioner.core.translate.video_title import OutputReservations
from videocaptioner.core.utils.gpu_lease import BatchGPUSession
from videocaptioner.core.utils.logger import setup_logger
from videocaptioner.ui.batch_plan import BatchPlan
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
        self.task_id = uuid4().hex
        self.plan: BatchPlan | None = None
        self.started = False
        self.stage = BatchStage.ASR
        self.waiting_message = ""
        self.output_path = ""


@dataclass
class PendingStage:
    task: BatchTask
    stage: BatchStage
    gpu: bool
    launch: Callable
    exclusive: bool = False


class BatchProcessThread(QObject):
    """Keep the public name; scheduling no longer needs a polling thread."""

    task_progress = pyqtSignal(str, int, str)
    task_error = pyqtSignal(str, str)
    task_completed = pyqtSignal(str)
    task_cancelled = pyqtSignal(str)
    busy_changed = pyqtSignal(bool)

    def __init__(self, limits: BatchLimits | None = None):
        super().__init__()
        self.task_queue = deque()
        self.current_tasks: dict[str, BatchTask] = {}
        self.factory = TaskFactory()
        self.threads: list[QThread] = []
        self._closing = False
        self.limits = limits or BatchLimits(cfg.batch_videos.value, cfg.batch_asr.value,
            cfg.batch_subtitle.value, cfg.batch_dubbing.value, cfg.batch_synthesis.value, cfg.batch_gpu.value)
        self.admission = BatchAdmission(self.limits)
        self.gpu_session = BatchGPUSession(self.limits.gpu)
        self.pending: deque[PendingStage] = deque()
        self.llm_gate = RateLimitGate(cfg.thread_num.value)
        self.output_reservations = OutputReservations()
        app = QApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self.shutdown)

    def isRunning(self):
        return bool(self.threads or self.task_queue or self.pending)

    def configure(self, limits: BatchLimits):
        if self.isRunning():
            raise RuntimeError("Stop Batch before changing concurrency")
        self.limits = limits
        self.admission = BatchAdmission(limits)
        self.gpu_session = BatchGPUSession(limits.gpu)

    def add_task(self, task: BatchTask):
        old = self.current_tasks.get(task.file_path)
        if self._closing or (old and old.status in (
                BatchTaskStatus.WAITING, BatchTaskStatus.RUNNING, BatchTaskStatus.STOPPING)):
            return
        if not self.isRunning():
            self.llm_gate = RateLimitGate(cfg.thread_num.value)
            self.output_reservations = OutputReservations()
        output_base = str(Path(task.file_path).resolve().with_suffix("")).casefold()
        if any(str(Path(other.file_path).resolve().with_suffix("")).casefold() == output_base
               and other.file_path != task.file_path
               and other.status in (BatchTaskStatus.WAITING, BatchTaskStatus.RUNNING, BatchTaskStatus.STOPPING)
               for other in self.current_tasks.values()):
            self.current_tasks[task.file_path] = task
            self._fail(task, "Hai nguồn trong cùng thư mục dùng chung tên đầu ra. Hãy xử lý riêng hoặc đổi tên một nguồn.")
            return
        try:
            # All stages use settings captured now, including voice and output style.
            task.plan = BatchPlan.capture(task.file_path, task.task_type, self.factory,
                                          dub=cfg.dubbing_enabled.value, task_id=task.task_id)
        except Exception as exc:
            self.current_tasks[task.file_path] = task
            self._fail(task, str(exc))
            return
        self.current_tasks[task.file_path] = task
        self.task_queue.append(task)
        self.busy_changed.emit(True)
        QTimer.singleShot(0, self._pump)

    def _pump(self):
        if self._closing:
            return
        active = sum(t.started and t.status in (BatchTaskStatus.RUNNING, BatchTaskStatus.STOPPING)
                     for t in self.current_tasks.values())
        while self.task_queue and active < self.limits.videos:
            task = self.task_queue.popleft()
            if task.status != BatchTaskStatus.WAITING:
                continue
            task.status = BatchTaskStatus.RUNNING
            task.started = True
            active += 1
            self.task_progress.emit(task.file_path, 0, str(task.status))
            try:
                if task.task_type == BatchTaskType.SUBTITLE:
                    self._subtitle(task, task.file_path)
                elif task.task_type == BatchTaskType.DUBBING:
                    if not task.plan or not task.plan.dubbing or not task.plan.dubbing.dubbing_config:
                        raise ValueError("Lồng tiếng đang tắt — hãy bật ở tab Lồng tiếng trước")
                    subtitle = self._find_subtitle_for_video(task.file_path)
                    if not subtitle:
                        raise ValueError("Không tìm thấy phụ đề cùng tên trong thư mục")
                    self._dub(task, subtitle, subtitle)
                else:
                    self._transcribe(task)
            except Exception as exc:
                self._fail(task, str(exc))
                active -= 1
        for pending in tuple(self.pending):
            task = pending.task
            if task.status != BatchTaskStatus.RUNNING:
                self.pending.remove(pending)
                continue
            reason = self.admission.waiting_for(task.task_id, pending.stage, pending.gpu, pending.exclusive)
            if reason:
                message = "Chờ GPU" if reason == "gpu" else "Chờ lượt: " + self._stage_label(pending.stage)
                if task.waiting_message != message:
                    task.waiting_message = message
                    self.task_progress.emit(task.file_path, task.progress, message)
                continue
            self.admission.acquire(task.task_id, pending.stage, pending.gpu, pending.exclusive)
            self.pending.remove(pending)
            task.waiting_message = ""
            try:
                pending.launch()
            except Exception as exc:
                self.admission.release(task.task_id)
                self._fail(task, str(exc))
                QTimer.singleShot(0, self._pump)
        self.busy_changed.emit(self.isRunning())

    @staticmethod
    def _stage_label(stage):
        return {BatchStage.ASR: "Nhận dạng", BatchStage.SUBTITLE: "Xử lý phụ đề / dịch",
                BatchStage.DUBBING: "Lồng tiếng", BatchStage.SYNTHESIS: "Xuất video"}[stage]

    def _schedule(self, task, stage, launch, *, gpu=False, exclusive=False):
        task.stage = stage
        self.pending.append(PendingStage(task, stage, gpu, launch, exclusive))
        QTimer.singleShot(0, self._pump)

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
        worker.llm_gate = self.llm_gate
        worker.output_reservations = self.output_reservations
        worker.gpu_session = self.gpu_session if self.admission.active[task.task_id][1] else None
        self.threads.append(worker)
        self.task_progress.emit(task.file_path, start, self._stage_label(task.stage))
        outcome = {}

        def progress(value, message):
            if task.current_thread is worker and task.status == BatchTaskStatus.RUNNING:
                task.progress = start + int(value * (end - start) / 100)
                self.task_progress.emit(task.file_path, task.progress, self._stage_label(task.stage) + ": " + message)

        def settle():
            # Result signals precede native completion and process cleanup.
            if not worker.wait(0):
                QTimer.singleShot(10, settle)
                return
            if worker in self.threads:
                self.threads.remove(worker)
            task.current_thread = None
            self.admission.release(task.task_id)
            if self._closing or task.status == BatchTaskStatus.STOPPING:
                task.status = BatchTaskStatus.CANCELLED
                self.task_cancelled.emit(task.file_path)
            elif "error" in outcome:
                self._fail(task, outcome["error"])
                if find_rate_limit(getattr(worker, "failure", None)):
                    # A provider rejection is shared by the queue, not a broken video.
                    self.stop_all()
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
        assert task.plan and task.plan.transcribe
        trans = task.plan.transcribe

        def done(result):
            task.output_path = result.output_path or ""
            if not next_stage:
                self._complete(task)
            else:
                self._subtitle(task, result.output_path, result.asr_data)

        self._schedule(task, BatchStage.ASR,
                       lambda: self._start(task, TranscriptThread(trans), 0, 100 if not next_stage else 25, done),
                       gpu=asr_uses_gpu(trans.transcribe_config),
                       exclusive=trans.transcribe_config.transcribe_model != TranscribeModelEnum.FASTER_WHISPER)

    def _subtitle(self, task, path, asr_data=None):
        full = task.task_type == BatchTaskType.FULL_PROCESS
        assert task.plan and task.plan.subtitle
        subtitle = task.plan.subtitle
        subtitle.subtitle_path = path
        subtitle.asr_data = asr_data

        def launch():
            worker = SubtitleThread(subtitle)

            def done(video, display):
                task.output_path = display
                if not full:
                    self._complete(task)
                elif task.plan.dubbing:
                    self._dub(task, worker.task.dubbing_subtitle_path or display, display)
                else:
                    self._synthesize(task, task.file_path, display, worker.task.subtitle_config.subtitle_layout)

            self._start(task, worker, 0 if task.task_type == BatchTaskType.SUBTITLE else 25, 50 if full else 100, done)
        self._schedule(task, BatchStage.SUBTITLE, launch)

    def _dub(self, task, subtitle, display):
        assert task.plan and task.plan.dubbing
        dubbing = task.plan.dubbing
        dubbing.subtitle_path, dubbing.display_subtitle_path = subtitle, display
        full = task.task_type == BatchTaskType.FULL_PROCESS

        def done(result):
            task.output_path = result.output_path or ""
            if full:
                self._synthesize(task, result.output_path, result.playback_subtitle_path or display,
                                 SubtitleLayoutEnum.ONLY_TRANSLATE if result.playback_subtitle_path
                                 else task.plan.synthesis.synthesis_config.subtitle_layout)
            else:
                self._complete(task)

        gpu = dubbing.dubbing_config.tts_provider in (TTSProviderEnum.OMNIVOICE_LOCAL, TTSProviderEnum.VIENEU_LOCAL,
                                                     TTSProviderEnum.LOCAL_AI)
        self._schedule(task, BatchStage.DUBBING,
                       lambda: self._start(task, DubbingThread(dubbing, automatic=True),
                                           50 if full else 0, 75 if full else 100, done), gpu=gpu,
                       exclusive=dubbing.dubbing_config.tts_provider != TTSProviderEnum.OMNIVOICE_LOCAL)

    def _synthesize(self, task, video, subtitle, layout):
        assert task.plan and task.plan.synthesis
        synthesis = task.plan.synthesis
        synthesis.video_path, synthesis.subtitle_path = video, subtitle
        synthesis.input_subtitle_layout = layout
        synthesis.output_path = str(Path(video).with_name(Path(video).stem + "_captioned.mp4"))

        def done(result):
            task.output_path = result.output_path if synthesis.synthesis_config.need_video else video
            self._complete(task)

        self._schedule(task, BatchStage.SYNTHESIS,
                       lambda: self._start(task, VideoSynthesisThread(synthesis), 75, 100, done))

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
            if task.current_thread:
                task.status = BatchTaskStatus.STOPPING
                self.task_progress.emit(file_path, task.progress, str(task.status))
                cancel_worker(task.current_thread)
            else:
                self.pending = deque(item for item in self.pending if item.task is not task)
                task.status = BatchTaskStatus.CANCELLED
                self.task_cancelled.emit(file_path)
        self.busy_changed.emit(self.isRunning())
        QTimer.singleShot(0, self._pump)

    def stop_all(self):
        # No wait() on the GUI thread. Native completion acknowledges the stop.
        for path in tuple(self.current_tasks):
            self.stop_task(path)

    def shutdown(self):
        self._closing = True
        self.stop_all()

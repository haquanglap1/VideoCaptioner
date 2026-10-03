"""Batch cancellation joins native workers before handing off or restarting."""

import time
from types import SimpleNamespace

import pytest
from PyQt5.QtCore import QThread, QTimer, pyqtSignal

from videocaptioner.core.entities import BatchTaskStatus as Status
from videocaptioner.core.entities import BatchTaskType as Kind
from videocaptioner.core.entities import SubtitleLayoutEnum
from videocaptioner.ui.common.config import cfg
from videocaptioner.ui.thread import batch_process_thread as batch


def until(qapp, predicate):
    deadline = time.monotonic() + 4
    while not predicate() and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(.005)
    assert predicate()


@pytest.fixture
def queue(qapp, monkeypatch):
    coordinator = batch.BatchProcessThread()
    started, retired, workers = [], [], []
    state = {"hold": None}

    class Worker(QThread):
        finished = pyqtSignal(object)
        error = pyqtSignal(str)
        progress = pyqtSignal(int, str)

        def __init__(self, task, **options):
            super().__init__()
            assert len(started) == len(retired), "The previous worker has not finished cleanup"
            self.task, self.options = task, options
            workers.append(self)

        def run(self):
            stage = self.task.stage
            started.append(stage)
            if state.get("reject") == stage:
                from videocaptioner.core.llm.rate_limit import LLMRateLimitError
                self.failure = LLMRateLimitError("quota")
                self.error.emit(str(self.failure))
                retired.append(stage)
                return
            while state["hold"] == stage and not self.isInterruptionRequested():
                time.sleep(.01)
            if stage == "subtitle":
                self.finished.emit(self.task.video_path, "display.srt")
            else:
                self.finished.emit(self.task)
            # Force the late-result/native-finish race, including cancellation.
            time.sleep(.025)
            retired.append(stage)

    class SubtitleWorker(Worker):
        finished = pyqtSignal(str, str)

    monkeypatch.setattr(batch, "TranscriptThread", Worker)
    monkeypatch.setattr(batch, "SubtitleThread", SubtitleWorker)
    monkeypatch.setattr(batch, "DubbingThread", Worker)
    monkeypatch.setattr(batch, "VideoSynthesisThread", Worker)
    monkeypatch.setattr(cfg.dubbing_enabled, "value", True)
    monkeypatch.setattr(cfg.need_video, "value", True)
    captures = []

    class Factory:
        def create_transcribe_task(self, path, **kwargs):
            return SimpleNamespace(stage="asr", output_path="source.srt", asr_data="native")

        def create_subtitle_task(self, path, video, **kwargs):
            return SimpleNamespace(stage="subtitle", video_path=video, dubbing_subtitle_path="dialogue.json",
                                   need_next_task=kwargs["need_next_task"],
                                   subtitle_config=SimpleNamespace(subtitle_layout=SubtitleLayoutEnum.ONLY_TRANSLATE))

        def create_dubbing_task(self, video, subtitle, **kwargs):
            return SimpleNamespace(stage="tts", output_path="dubbed.mp4", playback_subtitle_path="playback.srt",
                                   dubbing_config=SimpleNamespace(subtitle_mode="hard"))

        def create_synthesis_task(self, video, subtitle, **kwargs):
            captures.append((video, subtitle, kwargs))
            return SimpleNamespace(stage="render")

    coordinator.factory = Factory()
    yield SimpleNamespace(coordinator=coordinator, started=started, retired=retired, state=state,
                          workers=workers, captures=captures)
    coordinator.shutdown()
    until(qapp, lambda: not coordinator.isRunning())
    for worker in workers:
        assert worker.wait(1000)


def test_two_full_jobs_advance_only_after_native_exit(queue, qapp):
    c = queue.coordinator
    completed = []
    c.task_completed.connect(completed.append)
    c.add_task(batch.BatchTask("one.mp4", Kind.FULL_PROCESS))
    c.add_task(batch.BatchTask("two.mp4", Kind.FULL_PROCESS))
    until(qapp, lambda: not c.isRunning())
    assert completed == ["one.mp4", "two.mp4"]
    assert queue.started == queue.retired == ["asr", "subtitle", "tts", "render"] * 2
    assert all(w.options.get("automatic") and w.task.dubbing_config.subtitle_mode == "none"
               for w in queue.workers if w.task.stage == "tts")
    assert all(row[1] == "playback.srt" and row[2]["input_subtitle_layout"] == SubtitleLayoutEnum.ONLY_TRANSLATE
               for row in queue.captures)


def test_rate_limit_stops_next_stage_and_remaining_videos(queue, qapp):
    queue.state["reject"] = "subtitle"
    first = batch.BatchTask("one.mp4", Kind.FULL_PROCESS)
    second = batch.BatchTask("two.mp4", Kind.FULL_PROCESS)
    queue.coordinator.add_task(first)
    queue.coordinator.add_task(second)
    until(qapp, lambda: not queue.coordinator.isRunning())
    assert queue.started == ["asr", "subtitle"]
    assert first.status == Status.FAILED and second.status == Status.CANCELLED
    assert "HTTP 429" in first.error_message


@pytest.mark.parametrize("stage", ["asr", "subtitle", "tts", "render"])
def test_stop_all_remains_responsive_and_ignores_late_success(queue, qapp, stage):
    c = queue.coordinator
    queue.state["hold"] = stage
    completed, cancelled, ticks = [], [], []
    c.task_completed.connect(completed.append)
    c.task_cancelled.connect(cancelled.append)
    first = batch.BatchTask("one.mp4", Kind.FULL_PROCESS)
    second = batch.BatchTask("two.mp4", Kind.FULL_PROCESS)
    c.add_task(first)
    c.add_task(second)
    until(qapp, lambda: stage in queue.started)
    timer = QTimer()
    timer.timeout.connect(lambda: ticks.append(True))
    timer.start(1)
    start = time.monotonic()
    c.stop_all()
    assert time.monotonic() - start < .1
    assert first.status == Status.STOPPING
    until(qapp, lambda: not c.isRunning())
    timer.stop()
    assert ticks and not completed and set(cancelled) == {"one.mp4", "two.mp4"}
    assert first.status == second.status == Status.CANCELLED
    assert queue.started[-1] == stage and queue.started.count("asr") == 1
    queue.state["hold"] = None
    c.add_task(batch.BatchTask("one.mp4", Kind.FULL_PROCESS))
    until(qapp, lambda: not c.isRunning())
    assert completed == ["one.mp4"]


def test_cancel_one_queued_job_does_not_clear_other_jobs(queue, qapp):
    c = queue.coordinator
    tasks = [batch.BatchTask(f"{i}.mp4", Kind.TRANSCRIBE) for i in range(3)]
    for task in tasks:
        c.add_task(task)
    c.stop_task("1.mp4")
    c.add_task(batch.BatchTask("0.mp4", Kind.TRANSCRIBE))
    until(qapp, lambda: not c.isRunning())
    assert [t.status for t in tasks] == [Status.COMPLETED, Status.CANCELLED, Status.COMPLETED]
    assert queue.started == ["asr", "asr"]


def test_dubbing_keeps_its_caption_mode_when_final_synthesis_is_disabled(queue, qapp, monkeypatch):
    monkeypatch.setattr(cfg.need_video, "value", False)
    queue.coordinator.add_task(batch.BatchTask("one.mp4", Kind.FULL_PROCESS))
    until(qapp, lambda: not queue.coordinator.isRunning())
    assert next(w for w in queue.workers if w.task.stage == "tts").task.dubbing_config.subtitle_mode == "hard"


def test_transcribe_and_subtitle_keeps_video_binding_and_stops_before_tts(queue, qapp):
    task = batch.BatchTask("one.mp4", Kind.TRANS_SUB)
    queue.coordinator.add_task(task)
    until(qapp, lambda: not queue.coordinator.isRunning())
    assert queue.started == ["asr", "subtitle"]
    subtitle = queue.workers[-1].task
    assert subtitle.video_path == "one.mp4" and subtitle.need_next_task
    assert subtitle.asr_data == "native" and task.status == Status.COMPLETED

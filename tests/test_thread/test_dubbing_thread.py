"""DubbingThread cooperative stop (used when the main window closes)."""

import threading
import time

from videocaptioner.core.dubbing.config import DubbingConfig
from videocaptioner.core.entities import DubbingTask
from videocaptioner.ui.thread import dubbing_thread as dubbing_thread_module
from videocaptioner.ui.thread.dubbing_thread import DubbingThread


def test_dubbing_task_preserves_legacy_positional_constructor():
    config = DubbingConfig()
    task = DubbingTask("legacy-task", None, None, None, "in.mp4", "in.srt", "display.srt",
                       "out.mp4", None, None, True, config)
    assert task.need_next_task is True and task.dubbing_config is config
    assert task.dubbing_review is None and task.cache_root is None


class SlowFakeEngine:
    """Reports progress until the callback raises, like a long TTS/mix job."""

    last_report_path = None
    last_report = None

    def __init__(self):
        self.started = threading.Event()
        self.unwound = threading.Event()

    def dub(self, *, video_path, subtitle_path, output_path, config, callback):
        self.started.set()
        try:
            for step in range(2000):
                callback(step % 100, "working")
                time.sleep(0.01)
        finally:
            self.unwound.set()
        raise AssertionError("dubbing was not interrupted")


def test_interrupted_thread_unwinds_job_without_error(qapp, monkeypatch):
    engine = SlowFakeEngine()
    monkeypatch.setattr(dubbing_thread_module, "DubbingEngine", lambda: engine)
    task = DubbingTask(
        video_path="in.mp4",
        subtitle_path="in.srt",
        output_path="out.mp4",
        dubbing_config=DubbingConfig(),
    )
    thread = DubbingThread(task)
    errors = []
    messages = []
    thread.error.connect(errors.append)
    thread.progress.connect(lambda _value, message: messages.append(message))

    thread.start()
    assert engine.started.wait(5)
    thread.requestInterruption()
    assert thread.wait(5000)
    assert engine.unwound.is_set()
    qapp.processEvents()
    assert errors == []
    assert messages[-1] == "Lồng tiếng đã bị hủy"


def test_cancel_after_engine_returns_suppresses_success_and_emits_native_finish(qapp, monkeypatch):
    started, release = threading.Event(), threading.Event()

    class ReturningEngine:
        last_report_path = ""
        last_report = {"summary": {"output_created": True}}

        def dub(self, **kwargs):
            started.set()
            assert release.wait(5)
            return kwargs["output_path"]

    monkeypatch.setattr(dubbing_thread_module, "DubbingEngine", ReturningEngine)
    task = DubbingTask(video_path="in.mp4", subtitle_path="in.srt", output_path="out.mp4",
                       dubbing_config=DubbingConfig())
    worker = DubbingThread(task)
    results, errors, cancelled, stopped = [], [], [], []
    worker.finished.connect(results.append)
    worker.error.connect(errors.append)
    worker.cancelled.connect(lambda: cancelled.append(True))
    worker.lifecycle_finished.connect(lambda: stopped.append(True))
    worker.start()
    try:
        assert started.wait(5)
        worker.requestInterruption()
        release.set()
        assert worker.wait(5000)
        qapp.processEvents()
        assert cancelled == [True] and stopped == [True]
        assert not results and not errors and task.completed_at is None
        assert task.dubbing_report == ReturningEngine.last_report
    finally:
        release.set()
        worker.requestInterruption()
        worker.wait()

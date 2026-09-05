"""DubbingThread cooperative stop (used when the main window closes)."""

import threading
import time

from videocaptioner.core.dubbing.config import DubbingConfig
from videocaptioner.core.entities import DubbingTask
from videocaptioner.ui.thread import dubbing_thread as dubbing_thread_module
from videocaptioner.ui.thread.dubbing_thread import DubbingThread


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

"""Version checks must finish their thread and survive closing the window."""

import atexit
import time
from threading import Event
from types import SimpleNamespace

import pytest
from PyQt5 import sip
from PyQt5.QtCore import QEventLoop, QTimer
from PyQt5.QtGui import QCloseEvent
from PyQt5.QtWidgets import QApplication, QWidget

from videocaptioner.ui.thread.version_checker_thread import VersionChecker
from videocaptioner.ui.thread.worker_lifecycle import supervisor
from videocaptioner.ui.view.main_window import MainWindow


def pump_until(predicate, timeout=1500):
    loop = QEventLoop()
    poll = QTimer()
    poll.timeout.connect(lambda: loop.quit() if predicate() else None)
    deadline = QTimer()
    deadline.setSingleShot(True)
    deadline.timeout.connect(loop.quit)
    poll.start(10)
    deadline.start(timeout)
    if not predicate():
        loop.exec_()
    poll.stop()
    deadline.stop()
    return predicate()


@pytest.fixture
def window(qapp, monkeypatch):
    monkeypatch.setattr(VersionChecker, "get_latest_version_info", lambda self: {})
    monkeypatch.setattr("videocaptioner.ui.thread.version_checker_thread.get_version_state_cache", lambda: {})
    monkeypatch.setattr(MainWindow, "stop", lambda self: None)
    monkeypatch.setattr(MainWindow, "_check_ffmpeg", lambda self: None)
    monkeypatch.setattr(QApplication, "quit", lambda: None)
    monkeypatch.setattr("videocaptioner.core.tts.vieneu.service.get_vieneu_service",
                        lambda: SimpleNamespace(cancel_pending=lambda: None, shutdown=lambda: None))

    class Window(MainWindow):
        def initWindow(self):
            self.splashScreen = SimpleNamespace(finish=lambda: None)

        def _create_lazy_interfaces(self):
            self.videoEditorInterface = QWidget(self)

        def initNavigation(self):
            pass

    view = Window()
    yield view
    thread = view.versionThread
    if thread is not None and not sip.isdeleted(thread):
        thread.requestInterruption()
        thread.quit()
        assert thread.wait(3000)
    supervisor().reap()
    atexit.unregister(view.stop)
    view.deleteLater()


@pytest.mark.parametrize("outcome", ["empty", "error", "success"])
def test_completed_is_emitted_on_every_exit(qapp, monkeypatch, outcome):
    def fetch(self):
        if outcome == "error":
            raise ValueError("synthetic failure")
        return {"tag_name": "0.0.0"} if outcome == "success" else {}

    monkeypatch.setattr(VersionChecker, "get_latest_version_info", fetch)
    monkeypatch.setattr("videocaptioner.ui.thread.version_checker_thread.get_version_state_cache", lambda: {})
    checker = VersionChecker()
    completed = []
    checker.checkCompleted.connect(lambda: completed.append(True))
    checker.perform_check()
    assert completed == [True]


def test_completed_check_leaves_no_idle_thread(window):
    window._start_background_services()
    thread = window.versionThread
    assert pump_until(thread.isFinished)
    assert thread.wait(1000)


def test_close_during_request_returns_promptly_and_retains_worker(window, monkeypatch):
    entered, release = Event(), Event()

    def fetch(self):
        entered.set()
        release.wait(5)
        self.latest_version = "999.0.0"
        return {"tag_name": self.latest_version}

    monkeypatch.setattr(VersionChecker, "get_latest_version_info", fetch)
    received = []
    monkeypatch.setattr(window, "onNewVersion", lambda *args: received.append(args))
    window._start_background_services()
    thread = window.versionThread
    try:
        assert entered.wait(2)
        started = time.monotonic()
        window.closeEvent(QCloseEvent())
        assert time.monotonic() - started < 0.3
        assert thread.parent() is supervisor()
        assert thread in supervisor().workers
        release.set()
        assert pump_until(thread.isFinished)
        assert thread.wait(1000)
        QApplication.processEvents()
        assert not received
    finally:
        release.set()
        thread.quit()
        assert thread.wait(3000)


def test_delayed_start_does_not_run_after_close(window):
    window.closeEvent(QCloseEvent())
    window._start_background_services()
    assert window.versionThread is None


def test_shutdown_drains_request_without_stopping_qt_timers(window, monkeypatch):
    entered, release, tick = Event(), Event(), Event()

    def fetch(self):
        entered.set()
        release.wait(3)
        return {}

    monkeypatch.setattr(VersionChecker, "get_latest_version_info", fetch)
    window._start_background_services()
    thread = window.versionThread
    try:
        assert entered.wait(2)
        window.closeEvent(QCloseEvent())
        QTimer.singleShot(10, tick.set)
        QTimer.singleShot(50, release.set)
        supervisor().drain()
        assert tick.is_set()
        assert thread.isFinished() and thread.wait(1000)
        assert thread not in supervisor().workers
    finally:
        release.set()
        thread.quit()
        assert thread.wait(3000)
        supervisor().shutting_down = False


def test_queued_notifications_are_ignored_after_close(window, monkeypatch):
    window.closeEvent(QCloseEvent())

    def unexpected_dialog(*args, **kwargs):
        pytest.fail("A closing window must not open another dialog")

    monkeypatch.setattr("videocaptioner.ui.components.UpdateDialog.UpdateDialog", unexpected_dialog)
    monkeypatch.setattr("videocaptioner.ui.view.main_window.MessageBox", unexpected_dialog)
    window.onNewVersion("999.0.0", False, "synthetic update", "https://update.invalid")
    window.onAnnouncement("synthetic announcement")

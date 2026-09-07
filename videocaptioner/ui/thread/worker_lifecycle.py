"""Retain cancelled workers until they finish; keep the Qt event loop responsive."""

from PyQt5 import sip
from PyQt5.QtCore import QEventLoop, QObject, QThread, QTimer
from PyQt5.QtWidgets import QApplication


class WorkerSupervisor(QObject):
    def __init__(self, application):
        super().__init__(application)
        self.workers: set[QThread] = set()
        self.shutting_down = False
        self.timer = QTimer(self)
        self.timer.setInterval(20)
        self.timer.timeout.connect(self.reap)
        application.aboutToQuit.connect(self.drain)

    def retain(self, worker):
        worker.setParent(self)
        self.workers.add(worker)
        self.timer.start()

    def reap(self):
        for worker in tuple(self.workers):
            # Application result signals may fire before QThread.run has returned.
            if worker.isFinished() and worker.wait(0):
                self.workers.discard(worker)
                worker.setParent(None)
        if not self.workers:
            self.timer.stop()

    def drain(self):
        self.shutting_down = True
        for worker in tuple(self.workers):
            cancel_worker(worker)
        self.reap()
        if not self.workers:
            return
        # aboutToQuit is the last opportunity to join. Pump events instead of blocking
        # the GUI in wait(); ordinary page close/cancel returns immediately.
        loop = QEventLoop()
        timer = QTimer()
        timer.timeout.connect(lambda: loop.quit() if not self.workers else None)
        timer.start(20)
        loop.exec_()
        timer.stop()


def supervisor() -> WorkerSupervisor:
    app = QApplication.instance()
    if app is None:
        raise RuntimeError("Worker lifecycle requires a QApplication.")
    current = getattr(app, "_vc_worker_supervisor", None)
    if current is None:
        current = WorkerSupervisor(app)
        setattr(app, "_vc_worker_supervisor", current)
    return current


def retain_worker(worker):
    supervisor().retain(worker)
    return worker


def cancel_worker(worker):
    # Qt clears its interruption flag after run() returns; queued signals outlive it.
    setattr(worker, "_vc_cancel_requested", True)
    for name in ("stop", "cancel"):
        action = getattr(worker, name, None)
        if callable(action):
            action()
            return
    worker.requestInterruption()


def retire_worker(worker):
    retain_worker(worker)
    cancel_worker(worker)


def connect_current(owner, attribute, worker, signal, callback):
    """A late result/error from an old or cancelled worker cannot reset a new job."""
    def deliver(*args):
        if isinstance(owner, QObject) and sip.isdeleted(owner):
            return
        if (getattr(owner, attribute, None) is worker and not worker.isInterruptionRequested()
                and not getattr(worker, "_vc_cancel_requested", False)
                and not supervisor().shutting_down):
            callback(*args)
    signal.connect(deliver)
    if isinstance(owner, QObject):
        def owner_destroyed():
            if not sip.isdeleted(worker) and worker.isRunning():
                cancel_worker(worker)
        owner.destroyed.connect(owner_destroyed)

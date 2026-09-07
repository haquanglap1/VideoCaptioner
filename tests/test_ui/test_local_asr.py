"""Local model controls are lazy; cancellation and queued signals stay owned."""

from contextvars import ContextVar

from PyQt5.QtCore import QEventLoop, QTimer

from videocaptioner.core.asr.local.runtime import LocalRuntimeError
from videocaptioner.ui.common.config import cfg
from videocaptioner.ui.components.local_asr_cards import LocalASRDialog, LocalASRSettingWidget
from videocaptioner.ui.thread.local_asr_thread import LocalASRThread


def test_open_settings_never_calls_runtime_or_network(qapp, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Opening settings must not probe/install")
    monkeypatch.setattr("videocaptioner.ui.thread.local_asr_thread.locate", forbidden)
    monkeypatch.setattr("videocaptioner.ui.thread.local_asr_thread.install", forbidden)
    widget = LocalASRSettingWidget()
    dialog = LocalASRDialog()
    assert dialog.worker is None
    assert dialog.model.count() == 4
    dialog.close()
    widget.close()


def test_task_factory_snapshots_local_options(qapp):
    from videocaptioner.ui.task_factory import TaskFactory
    old_model, old_diarize = cfg.local_asr_model.value, cfg.local_asr_diarize.value
    try:
        cfg.set(cfg.local_asr_model, "qwen-0.6b")
        cfg.set(cfg.local_asr_diarize, True)
        task = TaskFactory.create_transcribe_task("synthetic.wav")
        cfg.set(cfg.local_asr_model, "qwen-1.7b")
        cfg.set(cfg.local_asr_diarize, False)
        assert task.transcribe_config.local_asr.model == "qwen-0.6b"
        assert task.transcribe_config.local_asr.diarize is True
    finally:
        cfg.set(cfg.local_asr_model, old_model)
        cfg.set(cfg.local_asr_diarize, old_diarize)


def test_worker_preserves_context_and_cancel_releases_runtime(qapp, monkeypatch):
    variable = ContextVar("stage", default="unset")
    variable.set("snapshot")
    calls = []
    monkeypatch.setattr("videocaptioner.ui.thread.local_asr_thread.locate", lambda *a, **k: "layout")
    class Runtime:
        def __init__(self, *args):
            pass
        def start(self, check):
            calls.append(variable.get())
            while True:
                check()
                import time
                time.sleep(0.01)
        def close(self):
            calls.append("closed")
    monkeypatch.setattr("videocaptioner.ui.thread.local_asr_thread.LocalRuntime", Runtime)
    worker = LocalASRThread("probe", "qwen-0.6b")
    loop = QEventLoop()
    worker.finished.connect(loop.quit)
    QTimer.singleShot(50, worker.stop)
    QTimer.singleShot(3000, loop.quit)
    worker.start()
    loop.exec_()
    worker.stop()
    assert worker.wait(3000)
    assert calls == ["snapshot", "closed"]
    try:
        worker.check()
    except LocalRuntimeError:
        pass
    else:
        raise AssertionError("Cancellation must survive QThread.finished")


def test_late_install_result_cannot_change_saved_root(qapp, monkeypatch, tmp_path):
    from videocaptioner.ui.thread.worker_lifecycle import (
        cancel_worker,
        connect_current,
        retain_worker,
    )
    dialog = LocalASRDialog()
    worker = LocalASRThread("status", "qwen-0.6b")
    dialog.worker = retain_worker(worker)
    received = []
    connect_current(dialog, "worker", worker, worker.installed, received.append)
    cancel_worker(worker)
    worker.installed.emit(str(tmp_path))
    qapp.processEvents()
    assert not received
    dialog.worker = None
    from videocaptioner.ui.thread.worker_lifecycle import supervisor
    supervisor().workers.discard(worker)
    worker.setParent(None)
    dialog.close()

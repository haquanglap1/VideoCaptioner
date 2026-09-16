"""Local model controls are lazy; cancellation and queued signals stay owned."""

from contextvars import ContextVar

import pytest
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
    monkeypatch.setattr("videocaptioner.ui.thread.local_asr_thread.ensure_model", forbidden)
    widget = LocalASRSettingWidget()
    dialog = LocalASRDialog()
    assert dialog.worker is None
    assert dialog.model.count() == 4
    dialog.close()
    widget.close()


def test_task_factory_snapshots_local_options(qapp):
    from videocaptioner.core.entities import TranscribeModelEnum
    from videocaptioner.ui.task_factory import TaskFactory
    old_model, old_diarize = cfg.local_asr_model.value, cfg.local_asr_diarize.value
    old_engine = cfg.transcribe_model.value
    try:
        cfg.set(cfg.transcribe_model, TranscribeModelEnum.QWEN_LOCAL)
        cfg.set(cfg.local_asr_model, "qwen-0.6b")
        cfg.set(cfg.local_asr_diarize, True)
        task = TaskFactory.create_transcribe_task("synthetic.wav")
        cfg.set(cfg.local_asr_model, "qwen-1.7b")
        cfg.set(cfg.local_asr_diarize, False)
        assert task.transcribe_config.local_asr.model == "qwen-0.6b"
        assert task.transcribe_config.local_asr.diarize is True
    finally:
        cfg.set(cfg.transcribe_model, old_engine)
        cfg.set(cfg.local_asr_model, old_model)
        cfg.set(cfg.local_asr_diarize, old_diarize)


@pytest.mark.parametrize("engine", ["QWEN_LOCAL", "SONIOX", "SCRIBE", "FASTER_WHISPER"])
def test_gui_split_keeps_native_sentence_output_and_qwen_language_is_explicit(qapp, monkeypatch, engine):
    from videocaptioner.core.entities import TranscribeLanguageEnum, TranscribeModelEnum
    from videocaptioner.ui.task_factory import TaskFactory

    monkeypatch.setattr(cfg.transcribe_model, "value", getattr(TranscribeModelEnum, engine))
    monkeypatch.setattr(cfg.transcribe_language, "value", TranscribeLanguageEnum.AUTO)
    monkeypatch.setattr(cfg.need_split, "value", True)
    task = TaskFactory.create_transcribe_task("synthetic.wav", need_next_task=True)
    assert task.transcribe_config.need_word_time_stamp is (engine == "FASTER_WHISPER")
    assert task.transcribe_config.transcribe_language == ("zh" if engine == "QWEN_LOCAL" else "")
    assert cfg.transcribe_language.value == TranscribeLanguageEnum.AUTO


def test_qwen_explicit_non_chinese_language_is_not_overwritten(qapp, monkeypatch):
    from videocaptioner.core.asr.local.pipeline import QwenLocalASR
    from videocaptioner.core.entities import TranscribeLanguageEnum, TranscribeModelEnum
    from videocaptioner.ui.task_factory import TaskFactory

    monkeypatch.setattr(cfg.transcribe_model, "value", TranscribeModelEnum.QWEN_LOCAL)
    monkeypatch.setattr(cfg.transcribe_language, "value", TranscribeLanguageEnum.ENGLISH)
    task = TaskFactory.create_transcribe_task("synthetic.wav")
    assert task.transcribe_config.transcribe_language == "en"
    with pytest.raises(LocalRuntimeError, match="Choose Chinese"):
        QwenLocalASR("unused", task.transcribe_config)


def test_faster_whisper_manager_detects_portable_program(qapp, monkeypatch, tmp_path):
    from videocaptioner.ui.components import FasterWhisperSettingWidget as module

    models = tmp_path / "models"
    directory = models / "tools/Faster-Whisper-XXL"
    directory.mkdir(parents=True)
    (directory / "faster-whisper-xxl.exe").write_bytes(b"x" * module.MIN_PROGRAM_SIZE)
    monkeypatch.setattr(module, "portable_models_path", lambda: models)
    monkeypatch.setattr(module, "BIN_PATH", tmp_path / "empty-bin")
    monkeypatch.setattr(module, "LEGACY_BIN_PATH", tmp_path / "empty-legacy")
    found, versions = module.check_faster_whisper_exists()
    assert found and versions


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


def test_prepare_button_cancels_and_resumes_same_selected_model(qapp, monkeypatch, tmp_path):
    import time

    calls = []
    def prepare(model, root, *, check, progress, **kwargs):
        calls.append((model, root))
        progress("Preparing selected model")
        if len(calls) == 1:
            while True:
                check()
                time.sleep(0.005)
        check()

    monkeypatch.setattr("videocaptioner.ui.thread.local_asr_thread.ensure_model", prepare)
    before = cfg.local_asr_root.value
    cfg.set(cfg.local_asr_root, str(tmp_path / "selected-runtime"))
    dialog = LocalASRDialog()
    dialog.model.setCurrentIndex(1)
    try:
        for attempt in range(2):
            dialog.prepare_button.click()
            worker = dialog.worker
            assert worker is not None and not dialog.prepare_button.isEnabled()
            loop = QEventLoop()
            worker.finished.connect(loop.quit)
            if attempt == 0:
                QTimer.singleShot(50, dialog.cancel_button.click)
            QTimer.singleShot(3000, loop.quit)
            loop.exec_()
            worker.stop()
            assert worker.wait(3000)
            qapp.processEvents()
            assert dialog.worker is None and dialog.prepare_button.isEnabled()
            if attempt == 0:
                assert "cancelled" in dialog.status.text().lower()
                assert "waiting" not in dialog.status.text().lower()
                assert dialog.progress.value() == 0
                dialog.display_stage_status()
                assert "cancelled" in dialog.status.text().lower()
        assert calls == [("qwen-0.6b", str(tmp_path / "selected-runtime"))] * 2
        assert cfg.local_asr_root.value == str(tmp_path / "selected-runtime")
    finally:
        if dialog.worker is not None:
            dialog.worker.stop()
            dialog.worker.wait()
        dialog.close()
        cfg.set(cfg.local_asr_root, before)


@pytest.mark.parametrize("name", ["QWEN_LOCAL", "WHISPER_API", "SONIOX", "SCRIBE", "BIJIAN", "FASTER_WHISPER"])
def test_engine_switch_scopes_local_diarization_without_erasing_preference(qapp, name):
    from videocaptioner.core.entities import TranscribeModelEnum
    from videocaptioner.ui.common.local_asr_settings import local_config

    old_engine, old_diarize = cfg.transcribe_model.value, cfg.local_asr_diarize.value
    try:
        cfg.set(cfg.local_asr_diarize, True)
        cfg.set(cfg.transcribe_model, getattr(TranscribeModelEnum, name))
        assert local_config().diarize is (name in ("QWEN_LOCAL", "WHISPER_API"))
        assert cfg.local_asr_diarize.value is True
        cfg.set(cfg.transcribe_model, TranscribeModelEnum.QWEN_LOCAL)
        assert local_config().diarize is True
    finally:
        cfg.set(cfg.transcribe_model, old_engine)
        cfg.set(cfg.local_asr_diarize, old_diarize)

"""Playback-safe translation, explicit timing UI, and responsive worker teardown."""

import time
from dataclasses import replace
from threading import Event
from types import SimpleNamespace

import pytest
from PyQt5.QtCore import QThread, QTimer, pyqtSignal

from videocaptioner.core.asr.asr_data import ASRData, ASRDataSeg
from videocaptioner.core.asr.review import NativeReview
from videocaptioner.core.editor.adapters import cues_from_asr
from videocaptioner.core.editor.models import EditorProject
from videocaptioner.core.editor.translation import translation_fingerprint
from videocaptioner.core.entities import SubtitleConfig, SubtitleTask, TranslatorServiceEnum
from videocaptioner.core.translate.conversation import Character, ConversationContext
from videocaptioner.core.translate.types import TargetLanguage
from videocaptioner.ui.components.asr_review_dialog import ASRReviewDialog
from videocaptioner.ui.thread.subtitle_thread import SubtitleThread
from videocaptioner.ui.thread.worker_lifecycle import (
    connect_current,
    retain_worker,
    retire_worker,
    supervisor,
)


def test_gui_factory_captures_timeout_for_selection(qapp, tmp_path):
    from videocaptioner.ui.common.config import cfg
    from videocaptioner.ui.task_factory import TaskFactory
    from videocaptioner.ui.thread.subtitle_thread import (
        RetranslateThread,
        create_translator_from_config,
    )
    cfg.set(cfg.llm_request_timeout, 300)
    task = TaskFactory.create_subtitle_task(file_path=str(tmp_path / "source.srt"))
    config = task.subtitle_config
    assert config.llm_request_timeout == 300
    config.translator_service = TranslatorServiceEnum.OPENAI
    worker = RetranslateThread(document().to_json(), config)
    cfg.set(cfg.llm_request_timeout, 120)
    config.llm_request_timeout = 60
    engine = create_translator_from_config(worker.subtitle_config)
    try:
        assert engine.request_timeout == 300
    finally:
        engine.close()


def document():
    return ASRData([ASRDataSeg("合成一。", 0, 1000, cue_id="a"), ASRDataSeg("合成二。", 1000, 2000, cue_id="b")])


def project():
    result = EditorProject("id", "synthetic", "", "", 3000)
    result.cues = cues_from_asr(document())
    return result


@pytest.mark.parametrize("change", ["playhead", "selection", "zoom", "title", "voice", "tts", "unselected_translation"])
def test_irrelevant_state_does_not_invalidate_translation(change):
    data = project()
    initial = translation_fingerprint(data, {"a"})
    if change == "playhead":
        data.playhead_ms = 1000
    elif change == "selection":
        data.selection_start_ms, data.selection_end_ms = 1000, 2000
    elif change == "zoom":
        data.zoom = 2
    elif change == "title":
        data.title = "Renamed"
    elif change == "voice":
        data.cues[0].voice = "manual-voice"
    elif change == "tts":
        data.cues[0].tts_text = "User TTS"
    else:
        data.cues[1].display_text = "Other translation"
    data.touch()
    assert translation_fingerprint(data, {"a"}) == initial


@pytest.mark.parametrize("change", ["identity", "source", "cue_id", "timing", "speaker", "context", "target"])
def test_semantic_change_rejects_stale_translation(change):
    data = project()
    initial = translation_fingerprint(data, {"a"})
    if change == "identity":
        data.project_id = "new-project"
    elif change == "source":
        data.cues[1].source_text += "變"
    elif change == "cue_id":
        data.cues[0].id = "new-cue"
    elif change == "timing":
        data.cues[0].end_ms = 900
    elif change == "speaker":
        data.cues[0].speaker = "anonymous-other"
    elif change == "context":
        data.conversation_context = ConversationContext(characters=(Character("A", "Name"),))
    else:
        data.cues[0].display_text = "Manual translation"
    assert translation_fingerprint(data, {"a"}) != initial


def test_review_ui_edit_undo_and_local_export(qapp, tmp_path, monkeypatch):
    value = {"text": "合成", "tokens": [{"text": "合成", "start_ms": 100, "end_ms": 100}]}
    review = NativeReview.capture(value, "soniox", "synthetic", "scope", 1000, True, True)
    dialog = ASRReviewDialog(review)
    output = tmp_path / "out.json"
    monkeypatch.setattr("videocaptioner.ui.components.asr_review_dialog.QFileDialog.getSaveFileName",
                        lambda *a: (str(output), ""))
    try:
        dialog.export_result()
        assert not output.exists()
        assert dialog.table.currentRow() == 0 and dialog.table.item(0, 7).text()
        dialog.end_ms.setValue(900)
        dialog.apply_timing()
        assert dialog.session.review.overrides
        assert dialog.stack.undo() and dialog.session.review.issues()
        assert dialog.stack.redo()
        dialog.export_result()
        result = ASRData.from_subtitle_file(str(output))
        assert result.segments[0].metadata.timing == "edited"
    finally:
        dialog.deleteLater()


def test_subtitle_worker_config_is_snapshotted_and_cancel_before_start_writes_nothing(qapp, tmp_path):
    config = SubtitleConfig(need_split=False, llm_request_timeout=300, api_key="first", base_url="https://first.invalid/v1")
    task = SubtitleTask(subtitle_path=str(tmp_path / "in.srt"), output_path=str(tmp_path / "out.srt"),
                         asr_data=document(), subtitle_config=config)
    thread = SubtitleThread(task)
    config.llm_request_timeout = 1
    config.api_key = "second"
    task.asr_data.segments[0].text = "Changed"
    assert thread.task.subtitle_config.llm_request_timeout == 300
    assert thread.task.subtitle_config.api_key == "first"
    assert thread.task.asr_data.segments[0].text == "合成一。"
    thread.stop()
    thread.start()
    assert thread.wait(3000)
    assert not (tmp_path / "out.srt").exists()


def test_subtitle_cancel_during_translation_joins_and_publishes_nothing(qapp, tmp_path, monkeypatch):
    entered, release = Event(), Event()
    def request(self, messages):
        entered.set()
        assert release.wait(3)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{"1":"Late result"}'))])
    monkeypatch.setattr("videocaptioner.core.translate.llm_translator.LLMTranslator._request", request)
    data = ASRData([ASRDataSeg("This is a synthetic subtitle sentence.", 0, 2000)])
    out = tmp_path / "out.srt"
    out.write_text("previous output", encoding="utf-8")
    config = SubtitleConfig(need_translate=True, need_split=False, llm_model="gpt-5.6-terra",
                            api_key="test-only", base_url="https://test.invalid/v1", llm_request_timeout=300,
                            target_language=TargetLanguage.VIETNAMESE, translator_service=TranslatorServiceEnum.OPENAI)
    task = SubtitleTask(subtitle_path=str(tmp_path / "in.srt"), output_path=str(out), asr_data=data, subtitle_config=config)
    worker, updates, finished = SubtitleThread(task), [], []
    worker.update_all.connect(updates.append)
    worker.finished.connect(lambda *args: finished.append(args))
    try:
        worker.start()
        assert entered.wait(2)
        worker.stop()
        release.set()
        assert worker.wait(3000)
        qapp.processEvents()
        assert not updates and not finished
        assert out.read_text(encoding="utf-8") == "previous output"
        assert task.asr_data is data and not data.segments[0].translated_text
        assert worker.translator.executor is None
        assert worker.translator._closing_executor is None
    finally:
        release.set()
        worker.stop()
        worker.wait(3000)


def test_cancel_retains_thread_until_finished_without_blocking_ui(qapp):
    entered, release = Event(), Event()
    class SlowWorker(QThread):
        def run(self):
            entered.set()
            release.wait(3)
        def stop(self):
            self.requestInterruption()
    worker = retain_worker(SlowWorker())
    try:
        worker.start()
        assert entered.wait(2)
        started = time.monotonic()
        retire_worker(worker)
        assert time.monotonic() - started < .2
        assert worker in supervisor().workers and worker.isRunning()
        release.set()
        assert worker.wait(3000)
        supervisor().reap()
        assert worker not in supervisor().workers
    finally:
        release.set()
        worker.wait(3000)


def test_quit_drain_keeps_qt_timers_alive_and_joins_workers(qapp):
    release, tick = Event(), Event()
    class Worker(QThread):
        def run(self):
            release.wait(3)
        def stop(self):
            self.requestInterruption()
    worker = retain_worker(Worker())
    worker.start()
    QTimer.singleShot(30, tick.set)
    QTimer.singleShot(70, release.set)
    try:
        supervisor().drain()
        assert tick.is_set() and worker.isFinished()
        assert worker.wait(1000)
    finally:
        release.set()
        worker.wait(3000)
        supervisor().shutting_down = False


def test_old_worker_signal_cannot_overwrite_or_reset_new_worker(qapp):
    class Worker(QThread):
        result = pyqtSignal(str)
    old, new = Worker(), Worker()
    owner, received = SimpleNamespace(worker=old), []
    connect_current(owner, "worker", old, old.result, received.append)
    owner.worker = new
    old.result.emit("late response")
    qapp.processEvents()
    assert not received


def test_cancelled_queued_signal_stays_rejected_after_qt_clears_interruption(qapp):
    emitted, release = Event(), Event()
    class Worker(QThread):
        result = pyqtSignal(str)
        def run(self):
            self.result.emit("queued before cancel")
            emitted.set()
            release.wait(3)
    worker = retain_worker(Worker())
    owner, received = SimpleNamespace(worker=worker), []
    connect_current(owner, "worker", worker, worker.result, received.append)
    try:
        worker.start()
        assert emitted.wait(2)
        retire_worker(worker)
        release.set()
        assert worker.wait(3000)
        assert not worker.isInterruptionRequested()
        qapp.processEvents()
        assert not received
    finally:
        release.set()
        worker.wait(3000)
        supervisor().reap()


def test_editor_translation_survives_playback_and_updates_only_selected(qapp, monkeypatch):
    from videocaptioner.ui.task_factory import TaskFactory
    from videocaptioner.ui.view.video_editor_interface import VideoEditorInterface
    entered, release = Event(), Event()
    class Translator:
        def translate_subtitle(self, data, **kwargs):
            entered.set()
            assert release.wait(3)
            for seg in data:
                seg.translated_text = "Bản dịch"
            return data
        def stop(self):
            release.set()
    config = SubtitleConfig(translator_service=TranslatorServiceEnum.GOOGLE, target_language=TargetLanguage.VIETNAMESE)
    monkeypatch.setattr(TaskFactory, "create_subtitle_task", lambda **kw: SimpleNamespace(subtitle_config=config))
    monkeypatch.setattr("videocaptioner.ui.thread.subtitle_thread.create_translator_from_config", lambda *a, **kw: Translator())
    view = VideoEditorInterface()
    view.project = project()
    view.project.selection_start_ms, view.project.selection_end_ms = 0, 900
    before = replace(view.project.cues[1])
    monkeypatch.setattr(view, "_show_success", lambda *a: None)
    errors = []
    monkeypatch.setattr(view, "_show_error", errors.append)
    worker = None
    try:
        view.translate_selected_cues()
        worker = view._translation_worker
        assert entered.wait(2)
        view.project.playhead_ms = 1500
        view.project.touch()
        release.set()
        assert worker.wait(3000)
        qapp.processEvents()
        assert not errors and view.project.cues[0].display_text == "Bản dịch"
        assert view.project.cues[0].tts_text == "合成一。" and view.project.cues[1] == before
    finally:
        release.set()
        if worker:
            worker.wait(3000)
        view.shutdown()
        view.deleteLater()

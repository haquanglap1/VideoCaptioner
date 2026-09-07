"""Local context UI, lossless handoff and asynchronous selection regression tests."""

from dataclasses import replace
from threading import Event
from types import SimpleNamespace

import pytest
from PyQt5.QtCore import QEventLoop, QTimer

from videocaptioner.core.asr.asr_data import ASRData, ASRDataSeg
from videocaptioner.core.asr.metadata import ASRAudioEvent, ASRMetadata
from videocaptioner.core.editor.commands import EditConversationCommand
from videocaptioner.core.entities import SubtitleConfig, TranslatorServiceEnum
from videocaptioner.core.translate.conversation import Character, ConversationContext, Evidence
from videocaptioner.core.translate.types import TargetLanguage
from videocaptioner.ui.components.conversation_dialog import ConversationDialog
from videocaptioner.ui.thread.subtitle_thread import RetranslateThread
from videocaptioner.ui.view.subtitle_interface import SubtitleInterface


def document():
    return ASRData([ASRDataSeg("你来了。", 0, 1000, cue_id="first"),
                    ASRDataSeg("等了很久。", 1000, 2000, cue_id="second")],
                   [ASRAudioEvent("(music)", 0, 100, ASRMetadata("scribe", "request"))],
                   ConversationContext(characters=(Character("A", "Minh", Evidence("user", "locked")),)))


def test_dialog_is_local_keeps_stable_ids_and_reports_missing_context(qapp, monkeypatch):
    monkeypatch.setattr("videocaptioner.core.llm.owned_request.OwnedLLMRequest.__call__",
                        lambda *a, **kw: pytest.fail("Opening context must not call LLM"))
    data = document()
    dialog = ConversationDialog(data.conversation_context, data.context_snapshot().cues)
    try:
        assert dialog.read_context() == data.conversation_context
        table = dialog.tables["characters"]
        table.item(0, 1).setText("Nhãn mới")
        dialog.apply()
        assert dialog.context.characters[0].id == "A"
        assert dialog.context.characters[0].label == "Nhãn mới"
        assert dialog.context.characters[0].evidence.status == "locked"
        assert "Unknown" in dialog.review.toPlainText()
    finally:
        dialog.deleteLater()


def test_table_load_export_and_handoff_keep_events_context_and_ids(qapp, tmp_path):
    from videocaptioner.core.subtitle.editing import export_subtitle, write_editor_handoff
    data = document()
    path = tmp_path / "input.json"
    data.save(str(path))
    view = SubtitleInterface()
    try:
        view.load_subtitle_file(str(path))
        current = view.current_context_document()
        assert current.to_document() == data.to_document()
        renamed = replace(current.conversation_context, characters=(Character("A", "Đổi tên"),))
        view._context_stack.execute(EditConversationCommand(view._context_data, renamed))
        assert view.current_context_document().conversation_context == renamed
        assert view._context_stack.undo()
        out = tmp_path / "saved.json"
        from videocaptioner.core.entities import SubtitleLayoutEnum
        export_subtitle(view.model._data, str(out), SubtitleLayoutEnum.ONLY_ORIGINAL,
                        events=current.events, context=current.conversation_context)
        assert ASRData.from_subtitle_file(str(out)).to_document() == data.to_document()
        handoff = write_editor_handoff(view.model._data, tmp_path, "handoff", "clip.mp4",
                                       events=current.events, context=current.conversation_context)
        assert ASRData.from_subtitle_file(str(handoff)).to_document() == data.to_document()
    finally:
        view.deleteLater()


def test_retranslate_worker_full_document_selection_association_and_wait(qapp, monkeypatch):
    data = document()
    config = SubtitleConfig(translator_service=TranslatorServiceEnum.GOOGLE, target_language=TargetLanguage.VIETNAMESE)
    seen = []
    class FakeTranslator:
        def translate_subtitle(self, selected, *, context_data):
            seen.append((selected, context_data))
            result = selected.with_segments([s.clone() for s in selected])
            for seg in result:
                seg.translated_text = "Đã đợi lâu."
            return result
        def stop(self):
            pass
    monkeypatch.setattr("videocaptioner.ui.thread.subtitle_thread.create_translator_from_config",
                        lambda *a, **kw: FakeTranslator())
    worker = RetranslateThread({"2": data.to_json()["2"]}, config, context_data=data)
    results, errors = [], []
    loop = QEventLoop()
    worker.finished.connect(lambda result: (results.append(result), loop.quit()))
    worker.error.connect(lambda error: (errors.append(error), loop.quit()))
    timer = QTimer()
    timer.setSingleShot(True)
    timer.timeout.connect(loop.quit)
    timer.start(5000)
    worker.start()
    loop.exec_()
    assert worker.wait(5000)
    timer.stop()
    assert not errors and results == [{"2": "Đã đợi lâu."}]
    assert len(seen[0][0].segments) == 1 and len(seen[0][1].segments) == 2
    assert seen[0][1].conversation_context == data.conversation_context
    assert not data.segments[1].translated_text


def test_stale_table_result_does_not_overwrite_user_edit(qapp, monkeypatch):
    from videocaptioner.core.utils.cache import generate_cache_key
    view = SubtitleInterface()
    try:
        data = document()
        view._context_data = data
        view.model.update_all(data.to_json())
        view._retranslate_version = generate_cache_key(view.current_context_document().to_document())
        view.model._data["1"]["translated_subtitle"] = "User edit"
        errors = []
        monkeypatch.setattr(view, "_on_retranslate_error", errors.append)
        view._retranslate_source = view._context_data
        view._on_retranslate_finished({"1": "Stale"})
        assert errors and view.model._data["1"]["translated_subtitle"] == "User edit"
    finally:
        view.deleteLater()


@pytest.mark.parametrize("stale", [False, True])
def test_editor_selected_translation_command_undo_and_stale_guard(qapp, monkeypatch, stale):
    from videocaptioner.core.editor.adapters import cues_from_asr
    from videocaptioner.core.editor.models import EditorProject
    from videocaptioner.ui.view.video_editor_interface import VideoEditorInterface
    config = SubtitleConfig(translator_service=TranslatorServiceEnum.GOOGLE, target_language=TargetLanguage.VIETNAMESE)
    monkeypatch.setattr("videocaptioner.ui.view.video_editor_interface.TaskFactory.create_subtitle_task",
                        lambda **kw: SimpleNamespace(subtitle_config=config))
    class FakeTranslator:
        def translate_subtitle(self, selected, **kwargs):
            for seg in selected:
                seg.translated_text = "Bạn đã đến."
            return selected
        def stop(self):
            pass
    monkeypatch.setattr("videocaptioner.ui.thread.subtitle_thread.create_translator_from_config",
                        lambda *a, **kw: FakeTranslator())
    view = VideoEditorInterface()
    view.project = EditorProject.empty(duration_ms=3000)
    view.project.cues = cues_from_asr(document())
    view.project.conversation_context = document().conversation_context
    view.project.selection_start_ms, view.project.selection_end_ms = 0, 1000
    errors, successes = [], []
    monkeypatch.setattr(view, "_show_error", errors.append)
    monkeypatch.setattr(view, "_show_success", successes.append)
    original = view.project.cues[0].display_text
    try:
        view.translate_selected_cues()
        worker = view._translation_worker
        if stale:
            view.command_stack.execute(EditConversationCommand(view.project, ConversationContext()))
        loop = QEventLoop()
        timer = QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(loop.quit)
        timer.start(5000)
        worker.finished.connect(loop.quit)
        worker.error.connect(loop.quit)
        loop.exec_()
        assert worker.wait(5000)
        timer.stop()
        if stale:
            assert errors and view.project.cues[0].display_text == original
        else:
            assert successes and view.project.cues[0].display_text == "Bạn đã đến."
            assert view.project.cues[0].tts_text == original
            assert view.command_stack.undo() and view.project.cues[0].display_text == original
            assert view.command_stack.redo() and view.project.cues[0].display_text == "Bạn đã đến."
        assert view.project.cues[1].display_text == document().segments[1].text
    finally:
        view.shutdown()
        view.deleteLater()


def test_application_shutdown_waits_for_context_worker_and_discards_cancelled_output(qapp, monkeypatch):
    entered, release = Event(), Event()
    class SlowTranslator:
        def translate_subtitle(self, selected, **kwargs):
            entered.set()
            assert release.wait(5)
            return selected
        def stop(self):
            release.set()
    monkeypatch.setattr("videocaptioner.ui.thread.subtitle_thread.create_translator_from_config",
                        lambda *a, **kw: SlowTranslator())
    data = document()
    config = SubtitleConfig(translator_service=TranslatorServiceEnum.GOOGLE, target_language=TargetLanguage.VIETNAMESE)
    view = SubtitleInterface()
    worker = RetranslateThread(data.to_json(), config, context_data=data)
    view._retranslate_thread = worker
    received = []
    worker.finished.connect(received.append)
    try:
        worker.start()
        assert entered.wait(5)
        view._shutdown_context_workers()
        # Page shutdown returns immediately; the supervisor retains the worker.
        assert worker.wait(5000)
        qapp.processEvents()
        assert not worker.isRunning() and not received
        assert worker.wait(1000)
    finally:
        release.set()
        worker.stop()
        worker.wait()
        view.deleteLater()

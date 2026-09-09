"""Real QThreads, typed core plans and isolated WAV cache; no service or media renderer."""

import json
import threading
import wave
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest
from PyQt5.QtCore import QEventLoop, QRect, QThread, QTimer
from PyQt5.QtWidgets import QDialog

from videocaptioner.core.dubbing.config import DubbingConfig
from videocaptioner.core.dubbing.engine import DubbingEngine
from videocaptioner.core.dubbing.orchestrator import DubbingOrchestrator
from videocaptioner.core.dubbing.review import DubbingReview
from videocaptioner.core.entities import DubbingTask
from videocaptioner.core.tts import TTSConfig
from videocaptioner.ui.common.config import cfg
from videocaptioner.ui.components.dubbing_review_dialog import DubbingReviewDialog
from videocaptioner.ui.thread import dubbing_thread
from videocaptioner.ui.view import dubbing_interface
from videocaptioner.ui.view.dubbing_interface import DubbingInterface


def settle(worker, qapp):
    try:
        assert worker.wait(5000)
        qapp.processEvents()
    finally:
        if worker.isRunning():
            worker.requestInterruption()
            worker.wait()


@pytest.fixture
def session(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(cfg.dubbing_tts_provider, "value", "openai")
    monkeypatch.setattr(cfg.dubbing_enabled, "value", True)
    monkeypatch.setattr(cfg.dubbing_tts_api_key, "value", "fixture-key")
    monkeypatch.setattr(DubbingOrchestrator, "_video_duration", staticmethod(lambda *_: 12.0))
    monkeypatch.setattr("videocaptioner.core.dubbing.orchestrator.shutil.which", lambda _: "fixture-tool")
    monkeypatch.setattr("videocaptioner.core.dubbing.orchestrator.build_voice_track", lambda *a, **k: True)
    mixed, calls, engine_roots = [], [], []
    default_root = [tmp_path / "cache"]

    def mix(_video, _track, output, **kwargs):
        mixed.append(output)
        Path(output).write_bytes(b"fixture output")
        return True

    class Provider:
        def synthesize(self, data, output_dir, callback=None, max_workers=1):
            assert QThread.currentThread() != qapp.thread()
            for i, segment in enumerate(data.segments):
                calls.append(segment.text)
                path = Path(output_dir) / f"{i}.wav"
                path.parent.mkdir(parents=True, exist_ok=True)
                with wave.open(str(path), "wb") as audio:
                    audio.setnchannels(1)
                    audio.setsampwidth(2)
                    audio.setframerate(8000)
                    audio.writeframes(b"\0\0" * 8000 * (8 if segment.text == "A long sentence." else 1))
                segment.audio_path = str(path)
            return data

    monkeypatch.setattr("videocaptioner.core.dubbing.orchestrator.mix_audio_tracks", mix)

    def engine_factory(*, cache_root=None):
        assert QThread.currentThread() != qapp.thread()
        selected = Path(cache_root) if cache_root else default_root[0]
        engine_roots.append(selected)
        return DubbingEngine(tts_provider_factory=lambda _: Provider(), cache_root=selected)

    monkeypatch.setattr(dubbing_thread, "DubbingEngine", engine_factory)
    video, subtitle, display = (tmp_path / name for name in ("source.mp4", "spoken.srt", "display.srt"))
    video.write_bytes(b"synthetic source, duration supplied by fixture")
    subtitle.write_text("1\n00:00:00,000 --> 00:00:01,000\nA long sentence.\n\n"
                        "2\n00:00:05,000 --> 00:00:06,000\nKeep this.\n", encoding="utf-8")
    display.write_text("1\n00:00:00,000 --> 00:00:01,000\nDisplay only\nNguyên văn\n", encoding="utf-8")
    config = DubbingConfig(enabled=True, strip_cjk=False, rewrite_enabled=False, natural_max_speed=1.0,
                           tts_config=TTSConfig(model="fixture", api_key="fixture-key", base_url="https://fixture.invalid/v1",
                                                voice="fixture", sample_rate=8000))
    task = DubbingTask(video_path=str(video), subtitle_path=str(subtitle), display_subtitle_path=str(display),
                       output_path=str(tmp_path / "output.mp4"), dubbing_config=config)
    view = DubbingInterface()
    shown, forwarded = [], []
    monkeypatch.setattr(view, "_show_report", lambda **_kwargs: shown.append(view._thread.isRunning()))
    view.finished.connect(lambda *args: forwarded.append(args))
    view.set_task(task)
    view.process()
    settle(view._thread, qapp)
    assert task.dubbing_review and view.resume_btn.isEnabled()
    assert shown == [False] and not mixed and not forwarded
    try:
        yield SimpleNamespace(view=view, task=task, calls=calls, mixed=mixed, shown=shown,
                              forwarded=forwarded, video=video, subtitle=subtitle, display=display,
                              seeded_cache=default_root[0], default_root=default_root, engine_roots=engine_roots)
    finally:
        view.request_stop()
        view.wait_for_dubbing_job()
        view.close()
        qapp.processEvents()


def test_edit_one_group_resume_uses_cache_and_display_handoff(session, qapp):
    s = session
    before = s.task.dubbing_review.to_dict()
    files = {path: path.read_bytes() for path in (s.video, s.subtitle, s.display)}
    dialog = DubbingReviewDialog(s.task.dubbing_review)
    try:
        assert dialog.source_text.isReadOnly() and dialog.subtitle_text.isReadOnly()
        assert dialog.original_tts_text.toPlainText() == "A long sentence."
        assert "8.00s" in dialog.issue_label.text()
        dialog.tts_text.setPlainText("Short.")
        dialog.accept()
        assert dialog.result() == QDialog.Accepted
        s.task.dubbing_review = dialog.review
    finally:
        dialog.close()
    edited = s.task.dubbing_review.to_dict()
    assert before["groups"][1] == edited["groups"][1]
    for field in ("cue_ids", "start_time", "subtitle_end_time", "source_text", "subtitle_text", "original_tts_text"):
        assert edited["groups"][0][field] == before["groups"][0][field]
    s.view.resume_btn.click()
    settle(s.view._thread, qapp)
    assert s.calls == ["A long sentence.", "Keep this.", "Short."]
    assert len(s.mixed) == 1
    assert s.task.dubbing_report["summary"]["cache_hits"] == 1
    assert s.forwarded == [(s.task.output_path, str(s.display))]
    assert all(path.read_bytes() == content for path, content in files.items())
    assert s.view._is_pipeline_mode and not s.view._job_busy


def test_dialog_cancel_and_empty_wording_preserve_original(session):
    review = session.task.dubbing_review
    original = review.to_dict()
    dialog = DubbingReviewDialog(review)
    try:
        dialog.tts_text.setPlainText("  ")
        dialog.accept()
        assert dialog.result() != QDialog.Accepted
        assert dialog.error_label.text()
        dialog.tts_text.setPlainText("Discard this")
        dialog.reject()
        assert review.to_dict() == original
    finally:
        dialog.close()


@pytest.mark.parametrize("mismatch", ["video", "display", "voice"])
def test_resume_mismatch_keeps_review_and_never_synthesizes(session, qapp, mismatch):
    s = session
    old = s.task.dubbing_review.to_dict()
    if mismatch == "voice":
        s.task.dubbing_config.tts_config.voice = "different"
    else:
        getattr(s, mismatch).write_bytes(b"changed")
    s.view._resume_review()
    settle(s.view._thread, qapp)
    assert "mismatch" in s.view.status_label.text().lower()
    assert s.task.dubbing_review.to_dict() == old
    assert s.calls == ["A long sentence.", "Keep this."]
    assert not s.mixed and not s.forwarded and not s.view._job_busy
    assert s.view.resume_btn.isEnabled()


def test_save_open_only_on_selection_and_no_synthesis(session, tmp_path, monkeypatch, qapp):
    s = session
    path = tmp_path / "chosen.json"
    monkeypatch.setattr(dubbing_interface.QFileDialog, "getSaveFileName", lambda *a: ("", ""))
    s.view.save_review_btn.click()
    assert s.view._review_thread is None and not path.exists()
    monkeypatch.setattr(dubbing_interface.QFileDialog, "getSaveFileName", lambda *a: (str(path), ""))
    s.view.save_review_btn.click()
    settle(s.view._review_thread, qapp)
    assert path.is_file() and "fixture-key" not in path.read_text(encoding="utf-8")
    data = json.loads(path.read_text(encoding="utf-8"))
    data["groups"][0]["audio_path"] = "../../untrusted.wav"
    path.write_text(json.dumps(data), encoding="utf-8")
    monkeypatch.setattr(dubbing_interface.QFileDialog, "getOpenFileName", lambda *a: (str(path), ""))
    s.view.open_review_btn.click()
    settle(s.view._review_thread, qapp)
    assert s.view._is_pipeline_mode
    assert s.view._task.display_subtitle_path == str(s.display)
    assert s.calls == ["A long sentence.", "Keep this."] and not s.forwarded
    s.view._resume_review()
    settle(s.view._thread, qapp)
    assert s.calls == ["A long sentence.", "Keep this."] and not s.mixed
    assert "untrusted.wav" not in s.view.status_label.text()


def test_explicit_legacy_import_checks_binding_and_discloses_provenance(session, tmp_path, qapp):
    s = session
    data = s.task.dubbing_review.to_dict()
    data.pop("resume_metadata")
    path = tmp_path / "legacy.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    original = s.task.dubbing_review
    s.view._start_review_file("open", str(path))
    settle(s.view._review_thread, qapp)
    assert s.view._task.dubbing_review is original
    assert "checkpoint" in s.view.status_label.text().lower()
    s.view._start_review_file("import", str(path))
    settle(s.view._review_thread, qapp)
    imported = s.view._task.dubbing_review
    assert imported.can_resume
    assert imported.plan.resume_metadata.provenance == "legacy-user-bound"
    assert "historical media" in s.view.review_label.text()
    assert s.calls == ["A long sentence.", "Keep this."] and not s.mixed


def test_manual_import_snapshots_new_selection_and_preserves_old_task_on_failure(session, tmp_path, monkeypatch, qapp):
    s = session
    s.view._is_pipeline_mode = False
    path = tmp_path / "plan.json"
    s.task.dubbing_review.save(path)
    other = tmp_path / "other.mp4"
    other.write_bytes(b"different media")
    s.view.video_path_edit.setText(str(other))
    s.view.subtitle_path_edit.setText(str(s.subtitle))
    monkeypatch.setattr(dubbing_interface.TaskFactory, "create_dubbing_config", lambda: deepcopy(s.task.dubbing_config))
    s.view._start_review_file("import", str(path))
    worker = s.view._review_thread
    settle(worker, qapp)
    assert worker.task.video_path == str(other)
    assert s.view._task is s.task
    assert "mismatch" in s.view.status_label.text().lower()
    assert not s.view._is_pipeline_mode and not s.view._job_busy


def test_manual_reopen_plan_preserves_selected_separate_display(session, tmp_path, monkeypatch, qapp):
    s = session
    path = tmp_path / "plan.json"
    s.task.dubbing_review.with_group_text(s.task.dubbing_review.groups[0].group_id, "Short.").save(path)
    s.view._is_pipeline_mode = False
    s.view._task = None
    s.view.video_path_edit.setText(str(s.video))
    s.view.subtitle_path_edit.setText(str(s.subtitle))
    s.view.display_subtitle_path_edit.setText(str(s.display))
    monkeypatch.setattr(dubbing_interface.TaskFactory, "create_dubbing_config", lambda: deepcopy(s.task.dubbing_config))
    s.view._start_review_file("open", str(path))
    settle(s.view._review_thread, qapp)
    assert s.view._task.display_subtitle_path == str(s.display)
    assert s.view._task.video_path == str(s.video) and not s.view._is_pipeline_mode
    s.view._resume_review()
    settle(s.view._thread, qapp)
    assert len(s.mixed) == 1 and s.calls == ["A long sentence.", "Keep this.", "Short."]
    assert not s.forwarded


@pytest.mark.parametrize("outcome", ["error", "cancel"])
def test_busy_until_native_finish_preserves_review_and_blocks_overlap(session, qapp, monkeypatch, outcome):
    s = session
    released, emitted = threading.Event(), threading.Event()

    class LateWorker(dubbing_thread.DubbingThread):
        def run(self):
            if outcome == "error":
                self.error.emit("fixture failure")
            else:
                self.cancelled.emit()
            emitted.set()
            released.wait(5)

    monkeypatch.setattr(dubbing_interface, "DubbingThread", LateWorker)
    original = s.task.dubbing_review
    s.view._resume_review()
    worker = s.view._thread
    try:
        assert emitted.wait(5)
        qapp.processEvents()
        assert s.view._job_busy and not s.view.manual_dub_btn.isEnabled()
        assert not s.view.resume_btn.isEnabled()
        s.view._resume_review()
        s.view.process()
        assert s.view._thread is worker
        with pytest.raises(RuntimeError, match="bận"):
            s.view.set_task(DubbingTask())
        assert s.task.dubbing_review is original and not s.forwarded
    finally:
        released.set()
        settle(worker, qapp)
    assert not s.view._job_busy and s.view.resume_btn.isEnabled()
    assert not s.forwarded


def test_file_load_runs_off_main_thread_and_cancel_discards_late_result(session, tmp_path, monkeypatch, qapp):
    s = session
    original = s.task.dubbing_review
    loaded = original.with_group_text(original.groups[0].group_id, "Discard late wording")
    started, release = threading.Event(), threading.Event()

    def delayed_load(_path):
        assert QThread.currentThread() != qapp.thread()
        started.set()
        assert release.wait(5)
        return loaded

    monkeypatch.setattr(DubbingReview, "load", delayed_load)
    s.view._start_review_file("open", str(tmp_path / "selected.json"))
    worker = s.view._review_thread
    assert started.wait(5)
    loop = QEventLoop()
    responded = []

    def cancel_from_ui():
        responded.append(True)
        s.view.cancel_job_btn.click()
        release.set()

    worker.finished.connect(loop.quit)
    QTimer.singleShot(0, cancel_from_ui)
    timer = QTimer()
    timer.setSingleShot(True)
    timer.timeout.connect(loop.quit)
    timer.start(5000)
    try:
        loop.exec_()
    finally:
        release.set()
        settle(worker, qapp)
    assert responded and not s.view._job_busy
    assert s.view._task.dubbing_review is original
    assert "hủy" in s.view.status_label.text()
    assert not s.forwarded


def test_editor_action_explains_resume_scope_without_mutating_review(session, qapp):
    s = session
    before = s.task.dubbing_review.to_dict()
    opened = []
    s.view.openInVideoEditorRequested.connect(lambda *args: opened.append(args))
    s.view.open_editor_btn.click()
    qapp.processEvents()
    assert opened == [(str(s.video), str(s.display))]
    assert "tiếp tục kế hoạch ở tab Lồng tiếng" in s.view.editor_scope_label.text()
    assert s.task.dubbing_review.to_dict() == before


def test_success_report_is_readonly_before_pipeline_handoff(session, monkeypatch, qapp):
    s = session
    shown = []
    monkeypatch.setattr(s.view, "_edit_review", lambda: pytest.fail("A completed video must not open editable wording before handoff"))

    class ReadonlyReport:
        def __init__(self, data, parent):
            assert data["summary"]["output_created"]

        def exec_(self):
            shown.append(True)

    monkeypatch.setattr(dubbing_interface, "DubbingReportDialog", ReadonlyReport)
    monkeypatch.setattr(s.view, "_show_report", lambda **kwargs: DubbingInterface._show_report(s.view, **kwargs))
    s.task.dubbing_review = s.task.dubbing_review.with_group_text(s.task.dubbing_review.groups[0].group_id, "Short.")
    s.view._resume_review()
    settle(s.view._thread, qapp)
    assert shown == [True]
    assert s.forwarded == [(s.task.output_path, str(s.display))]


@pytest.mark.parametrize("width", [950, 1050])
def test_review_controls_reachable_in_1050x800_window(session, qapp, width):
    view = session.view
    view.resize(width, 800)
    view.show()
    qapp.processEvents()
    assert view.height() == 800
    assert view.minimumSizeHint().height() <= 800
    scroll = view.scroll_area
    assert scroll.widgetResizable()
    assert scroll.horizontalScrollBar().maximum() == 0
    assert scroll.verticalScrollBar().maximum() > 0
    assert scroll.widget().height() > scroll.viewport().height()
    for button in (view.manual_dub_btn, view.review_btn, view.save_review_btn, view.resume_btn):
        scroll.ensureWidgetVisible(button)
        qapp.processEvents()
        bounds = QRect(button.mapTo(scroll.viewport(), button.rect().topLeft()), button.size())
        assert scroll.viewport().rect().contains(bounds), button.text()
        assert button.isVisibleTo(view) and button.isEnabled()
    assert scroll.verticalScrollBar().value() > 0


def _select_manual_sources(s, monkeypatch):
    s.view._is_pipeline_mode = False
    s.view.video_path_edit.setText(str(s.video))
    s.view.subtitle_path_edit.setText(str(s.subtitle))
    s.view.display_subtitle_path_edit.setText(str(s.display))
    monkeypatch.setattr(dubbing_interface.TaskFactory, "create_dubbing_config", lambda: deepcopy(s.task.dubbing_config))


@pytest.mark.parametrize("pipeline", [False, True])
@pytest.mark.parametrize("operation", ["open", "import"])
def test_selected_cache_reopen_reuses_seeded_wavs_and_snapshots_root(
    session, tmp_path, monkeypatch, qapp, pipeline, operation
):
    s = session
    data = s.task.dubbing_review.to_dict()
    if operation == "import":
        data.pop("resume_metadata")
    data["cache_root"] = str(tmp_path / "untrusted-json-cache")
    data["groups"][0]["audio_path"] = str(tmp_path / "untrusted-audio.wav")
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    s.default_root[0] = tmp_path / "empty-default-cache"
    if not pipeline:
        _select_manual_sources(s, monkeypatch)
    else:
        # Pipeline sources come from its task, while the cache selection is explicit.
        s.view.video_path_edit.setText("not-the-pipeline-source.mp4")
    monkeypatch.setattr(dubbing_interface.QFileDialog, "getExistingDirectory", lambda *a: str(s.seeded_cache))
    s.view.browse_cache_btn.click()
    s.view._start_review_file(operation, str(path))
    settle(s.view._review_thread, qapp)
    task = s.view._task
    assert task.cache_root == str(s.seeded_cache.resolve())
    assert task.video_path == str(s.video) and task.display_subtitle_path == str(s.display)
    assert s.engine_roots[-1] == s.seeded_cache
    assert "untrusted-json-cache" not in s.view.review_label.text()
    assert str(s.seeded_cache) in s.view.review_label.text()
    s.view.cache_root_edit.setText(str(tmp_path / "later-selection"))
    s.view._resume_review()
    settle(s.view._thread, qapp)
    assert s.calls == ["A long sentence.", "Keep this."]
    assert task.dubbing_report["summary"]["cache_hits"] == 2
    assert s.engine_roots[-1] == s.seeded_cache and not s.default_root[0].exists()
    task.dubbing_review = task.dubbing_review.with_group_text(task.dubbing_review.groups[0].group_id, "Short.")
    s.view._resume_review()
    settle(s.view._thread, qapp)
    assert s.calls == ["A long sentence.", "Keep this.", "Short."]
    assert task.dubbing_report["summary"]["cache_hits"] == 1
    assert len(s.mixed) == 1
    assert s.forwarded == ([(task.output_path, str(s.display))] if pipeline else [])
    saved = tmp_path / "saved.json"
    s.view._start_review_file("save", str(saved))
    settle(s.view._review_thread, qapp)
    serialized = saved.read_text(encoding="utf-8")
    assert "cache_root" not in serialized and str(s.seeded_cache) not in serialized


@pytest.mark.parametrize("pipeline", [False, True])
def test_new_job_snapshots_selected_cache_for_manual_and_pipeline(session, tmp_path, monkeypatch, qapp, pipeline):
    s = session
    s.default_root[0] = tmp_path / "empty-default-cache"
    s.view.cache_root_edit.setText(str(s.seeded_cache))
    if pipeline:
        task = DubbingTask(video_path=str(s.video), subtitle_path=str(s.subtitle), display_subtitle_path=str(s.display),
                           output_path=str(tmp_path / "pipeline.mp4"), dubbing_config=deepcopy(s.task.dubbing_config))
        s.view.set_task(task)
        s.view.cache_root_edit.setText(str(tmp_path / "changed-after-snapshot"))
        s.view.process()
    else:
        _select_manual_sources(s, monkeypatch)
        s.view._start_manual_dub()
        s.view.cache_root_edit.setText(str(tmp_path / "changed-after-snapshot"))
    settle(s.view._thread, qapp)
    assert s.view._task.cache_root == str(s.seeded_cache.resolve())
    assert s.view._task.dubbing_report["summary"]["cache_hits"] == 2
    assert s.calls == ["A long sentence.", "Keep this."]
    assert s.engine_roots[-1] == s.seeded_cache and not s.default_root[0].exists()


@pytest.mark.parametrize("operation", ["open", "import", "resume"])
def test_invalid_cache_directory_stops_before_engine_and_keeps_review(session, tmp_path, qapp, operation):
    s = session
    path = tmp_path / "plan.json"
    s.task.dubbing_review.save(path)
    invalid = tmp_path / "not-a-directory"
    if operation == "import":
        invalid.write_text("regular file", encoding="utf-8")
    original, created_engines = s.task.dubbing_review, len(s.engine_roots)
    if operation == "resume":
        s.task.cache_root = str(invalid)
        s.view._resume_review()
        worker = s.view._thread
    else:
        s.view.cache_root_edit.setText(str(invalid))
        s.view._start_review_file(operation, str(path))
        worker = s.view._review_thread
    settle(worker, qapp)
    assert "Thư mục WAV cache" in s.view.status_label.text()
    assert s.view._task.dubbing_review is original
    assert len(s.engine_roots) == created_engines
    assert s.calls == ["A long sentence.", "Keep this."] and not s.forwarded
    assert not s.view._job_busy


def test_json_cache_path_cannot_override_default_cache_selection(session, tmp_path, qapp):
    s = session
    data = s.task.dubbing_review.to_dict()
    data["cache_root"] = str(s.seeded_cache)
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    s.default_root[0] = tmp_path / "fresh-default-cache"
    s.view.cache_root_edit.clear()
    s.view._start_review_file("open", str(path))
    settle(s.view._review_thread, qapp)
    assert s.view._task.cache_root is None
    s.view._resume_review()
    settle(s.view._thread, qapp)
    assert s.engine_roots[-1] == s.default_root[0]
    assert s.view._task.dubbing_report["summary"]["cache_hits"] == 0
    assert s.calls == ["A long sentence.", "Keep this.", "A long sentence.", "Keep this."]

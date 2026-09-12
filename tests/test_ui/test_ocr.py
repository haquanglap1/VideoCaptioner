import io
import time
from contextvars import ContextVar
from dataclasses import replace
from types import SimpleNamespace

import pytest
from PIL import Image
from PyQt5 import sip
from PyQt5.QtCore import QCoreApplication, QEvent, QEventLoop, QPoint, Qt, QTimer
from PyQt5.QtTest import QTest

from tests.test_ocr.test_document import make_document
from videocaptioner.core.editor.commands import CommandStack
from videocaptioner.core.ocr.models import OcrError
from videocaptioner.core.ocr.preview import OcrPreview
from videocaptioner.core.ocr.review import OcrReviewSession, ReviewOcrCueCommand
from videocaptioner.ui.components.ocr_dialog import OcrDialog
from videocaptioner.ui.thread.ocr_thread import OcrWorker


def wait_worker(worker):
    loop = QEventLoop()
    worker.finished.connect(loop.quit)
    timer = QTimer()
    timer.setSingleShot(True)
    timer.timeout.connect(loop.quit)
    timer.start(5000)
    if not worker.isFinished():
        loop.exec_()
    timer.stop()
    if not worker.isFinished():
        worker.stop()
    assert worker.wait(5000)


def test_dialog_open_is_lazy_and_roi_drag_respects_letterbox(qapp, monkeypatch):
    def forbidden(*_a, **_k):
        raise AssertionError("opening must not start IO/model")
    monkeypatch.setattr("videocaptioner.ui.components.ocr_dialog.inspect_installation", forbidden)
    monkeypatch.setattr("videocaptioner.ui.components.ocr_dialog.preview_video", forbidden)
    monkeypatch.setattr("videocaptioner.ui.components.ocr_dialog.manage_cache", forbidden)
    dialog = OcrDialog()
    assert dialog.worker is None and not dialog.scan_button.isEnabled()
    assert not dialog.resume_button.isEnabled()
    assert dialog.cache_mib.value() == 64
    assert not dialog.export_button.isEnabled()
    image = Image.new("RGB", (640, 120), "black")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    doc = make_document()
    dialog.accept_preview(OcrPreview(buffer.getvalue(), doc.visual_source.video, "a" * 64))
    dialog.show()
    qapp.processEvents()
    rect = dialog.canvas.image_rect()
    start = QPoint(round(rect.left() + rect.width() * .1), round(rect.top() + rect.height() * .1))
    end = QPoint(round(rect.left() + rect.width() * .9), round(rect.top() + rect.height() * .9))
    QTest.mousePress(dialog.canvas, Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseRelease(dialog.canvas, Qt.MouseButton.LeftButton, pos=end)
    roi = dialog.canvas.roi
    assert roi is not None and .09 < roi.x < .11 and .78 < roi.width < .82
    assert dialog.scan_button.isEnabled()
    dialog.close()


@pytest.mark.parametrize("mismatch", [False, True])
def test_open_checkpoint_resume_uses_saved_settings_and_keeps_review(qapp, tmp_path, monkeypatch, mismatch):
    from PyQt5.QtCore import QThread

    document = replace(make_document(), complete=False)
    checkpoint = tmp_path / "saved.json"
    document.save(checkpoint)
    original = checkpoint.read_bytes()
    calls = []
    monkeypatch.setattr("videocaptioner.ui.components.ocr_dialog.QFileDialog.getOpenFileName",
                        lambda *_: (str(checkpoint), "JSON"))
    monkeypatch.setattr("videocaptioner.ui.components.ocr_dialog.verify_visual_file", lambda *_a, **_k: None)
    installed = replace(document.config, bridge_sha256="f" * 64) if mismatch else document.config
    monkeypatch.setattr("videocaptioner.ui.thread.ocr_thread.inspect_installation",
                        lambda *_: SimpleNamespace(config=lambda *_: installed, root=tmp_path, bridge=tmp_path / "bridge.py"))

    def scan(source, config, _root, _bridge, **options):
        assert QThread.currentThread() is not qapp.thread()
        assert config == document.config and options["resume_document"] == document
        assert options["expected_source_sha256"] == document.visual_source.snapshot_sha256
        assert options["cache_mib"] == 0
        calls.append(True)
        completed = replace(document, complete=True)
        options["checkpoint"](completed)
        return completed

    monkeypatch.setattr("videocaptioner.ui.thread.ocr_thread.run_cpu_ocr", scan)
    dialog = OcrDialog(source="synthetic.mov")
    dialog.load_review()
    wait_worker(dialog.worker)
    qapp.processEvents()
    assert dialog.resume_button.isEnabled() and dialog.session.document == document
    dialog.start_ms.setValue(99)
    dialog.end_ms.setValue(99999)
    dialog.roi_values[0].setValue(.2)
    dialog.cache_mib.setValue(0)
    dialog.resume_scan()
    worker = dialog.worker
    assert worker.task.resume_document == document and not dialog.resume_button.isEnabled()
    wait_worker(worker)
    qapp.processEvents()
    if mismatch:
        assert not calls and dialog.session.document == document and dialog.resume_button.isEnabled()
        assert "không khớp checkpoint" in dialog.status.text()
    else:
        assert calls == [True] and dialog.session.document.complete
        assert dialog.session.document.cues == document.cues and not dialog.resume_button.isEnabled()
    assert not dialog.export_button.isEnabled() and checkpoint.read_bytes() == original
    dialog.close()
    # Signal closures retain this hidden dialog after close(); release Qt children before qapp teardown.
    dialog.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    assert sip.isdeleted(dialog)


def test_review_requires_verified_crop_keeps_raw_and_undo(qapp):
    dialog = OcrDialog()
    doc = make_document()
    dialog.accept_document(doc)
    cue = doc.cues[0]
    assert "\n" not in dialog.candidate.currentText()
    assert all(line in dialog.candidate.currentText() for line in cue.raw_text.splitlines())
    assert dialog.candidate.itemData(0, Qt.ItemDataRole.ToolTipRole) == cue.raw_text
    assert dialog.candidate.currentData() == cue.candidates[0].id
    assert not dialog.approve_button.isEnabled()
    dialog.note.setText("Known synthetic evidence")
    dialog.approve()
    assert dialog.session.document == doc
    dialog.verified_candidate_id = cue.candidates[0].id
    dialog.approve()
    assert not dialog.session.document.pending_issues
    assert dialog.session.document.cues[0].raw_text == cue.raw_text
    dialog.stack.undo()
    assert dialog.session.document == doc and not dialog.export_button.isEnabled()
    dialog.stack.redo()
    assert dialog.export_button.isEnabled()
    dialog.close()


def test_worker_context_cancel_and_closed_dialog_ignore_late_result(qapp):
    marker = ContextVar("ocr-test", default="unset")
    marker.set("captured")
    seen, delivered = [], []
    def operation(check):
        seen.append(marker.get())
        while True:
            check()
            time.sleep(.005)
    dialog = OcrDialog()
    worker = OcrWorker(operation)
    dialog._start(worker, delivered.append)
    QTimer.singleShot(25, dialog.reject)
    wait_worker(worker)
    assert seen == ["captured"] and not delivered and dialog.worker is None


def test_completed_scan_reaches_100_without_accepting_review(qapp):
    from videocaptioner.core.entities import OcrTask
    from videocaptioner.ui.thread.ocr_thread import OcrThread

    doc = make_document()
    worker = OcrThread(OcrTask("fixture", doc.config.roi, doc.config.selection))
    def complete(check):
        worker.progress.emit(94, "Synthetic scan")
        worker.capture(doc)
        return doc
    worker.operation = complete
    dialog = OcrDialog()
    dialog._start(worker, dialog.accept_document)
    wait_worker(worker)
    qapp.processEvents()
    assert dialog.progress.value() == 100 and dialog.progress.maximum() == 100
    assert dialog.session.document == doc and doc.pending_issues
    assert not dialog.export_button.isEnabled() and not dialog.handoff_button.isEnabled()
    assert not dialog.approve_button.isEnabled() and not dialog.cancel_button.isEnabled()
    dialog.close()


@pytest.mark.parametrize("cancelled", [True, False])
@pytest.mark.parametrize("progress", [0, 94])
def test_failed_scan_keeps_partial_document_and_incomplete_progress(qapp, cancelled, progress):
    from videocaptioner.core.entities import OcrTask
    from videocaptioner.ui.thread.ocr_thread import OcrThread

    doc = replace(make_document(), complete=False)
    worker = OcrThread(OcrTask("fixture", doc.config.roi, doc.config.selection))
    def partial(check):
        worker.progress.emit(progress, "Synthetic scan")
        worker.partial_document = doc
        if cancelled:
            worker.stop()
            check()
        raise OcrError("Synthetic scan failure")
    worker.operation = partial
    dialog = OcrDialog()
    dialog.progress.setValue(100)
    dialog._start(worker, lambda _: None)
    wait_worker(worker)
    qapp.processEvents()
    assert dialog.session.document == doc and not dialog.export_button.isEnabled()
    assert dialog.progress.value() == progress and dialog.progress.maximum() == 100
    assert not dialog.handoff_button.isEnabled() and not dialog.cancel_button.isEnabled()
    dialog.close()


def test_review_command_keeps_ids_and_raw_on_redo():
    doc = make_document()
    session = OcrReviewSession(doc)
    cue = doc.cues[0]
    stack = CommandStack()
    stack.execute(ReviewOcrCueCommand(session, cue.select_candidate(cue.candidates[0].id, "Synthetic evidence")))
    reviewed = session.document
    stack.undo()
    assert session.document == doc
    stack.redo()
    assert session.document == reviewed and reviewed.cues[0].candidates == cue.candidates


def test_cache_management_runs_in_worker_and_preserves_review(qapp, monkeypatch):
    from PyQt5.QtCore import QThread

    from videocaptioner.core.ocr.cache import CacheInfo

    calls = []
    def manage(*, clear, check):
        check()
        assert QThread.currentThread() is not qapp.thread()
        calls.append(clear)
        return CacheInfo(3, 900, 16384)
    monkeypatch.setattr("videocaptioner.ui.components.ocr_dialog.manage_cache", manage)
    dialog = OcrDialog()
    doc = make_document(approved=True)
    dialog.accept_document(doc)
    for clear in (False, True):
        dialog.show_cache(clear=clear)
        worker = dialog.worker
        assert worker is not None
        wait_worker(worker)
        qapp.processEvents()
        assert dialog.session.document == doc and dialog.export_button.isEnabled()
    assert calls == [False, True]
    assert "3" in dialog.status.text()
    dialog.close()

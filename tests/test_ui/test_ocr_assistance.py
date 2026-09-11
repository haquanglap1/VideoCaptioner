"""Synthetic draft requests exercise UI isolation, caching and late delivery."""

from dataclasses import replace
from threading import Event

from tests.test_ocr.test_assistance import response, settings
from tests.test_ocr.test_document import make_document
from tests.test_ui.test_ocr import wait_worker
from videocaptioner.core.ocr.models import OcrError
from videocaptioner.ui.components.ocr_dialog import OcrDialog


def setup_requests(monkeypatch):
    calls = []
    monkeypatch.setattr("videocaptioner.ui.components.ocr_dialog.capture_draft_settings", settings)

    def owned(*_, **_options):
        def send(**kwargs):
            calls.append(kwargs)
            return response()
        return send

    monkeypatch.setattr("videocaptioner.core.ocr.assistance.OwnedLLMRequest", owned)
    return calls


def finish_draft(dialog, qapp):
    worker = dialog.worker
    assert worker is not None
    wait_worker(worker)
    qapp.processEvents()


def test_explicit_draft_reuses_cache_but_never_accepts_or_persists(qapp, monkeypatch, tmp_path):
    calls = setup_requests(monkeypatch)
    doc = make_document()
    dialog = OcrDialog()
    dialog.accept_document(doc)
    assert not calls and dialog.draft_text.toPlainText() == ""
    dialog.translate_current_draft()
    finish_draft(dialog, qapp)
    assert len(calls) == 1 and "Ba học sinh" in dialog.draft_text.toPlainText()
    assert "AI chưa nhìn ảnh" in dialog.draft_text.toPlainText()
    assert dialog.session.document == doc
    assert not dialog.export_button.isEnabled() and not dialog.handoff_button.isEnabled()
    assert not dialog.approve_button.isEnabled()
    dialog.translate_current_draft()
    assert len(calls) == 1 and dialog.worker is None
    path = tmp_path / "review.json"
    dialog.session.document.save(path)
    assert "translation_vi" not in path.read_text(encoding="utf-8")
    dialog.close()


def test_switch_candidate_document_and_model_never_shows_wrong_draft(qapp, monkeypatch):
    calls = setup_requests(monkeypatch)
    dialog = OcrDialog()
    dialog.accept_document(make_document(("学生三人", "学生五人")))
    dialog.translate_current_draft()
    finish_draft(dialog, qapp)
    dialog.candidate.setCurrentIndex(1)
    assert not dialog.draft_text.toPlainText()
    dialog.candidate.setCurrentIndex(0)
    assert "Ba học sinh" in dialog.draft_text.toPlainText()
    monkeypatch.setattr("videocaptioner.ui.components.ocr_dialog.capture_draft_settings",
                        lambda: replace(settings(), model="other-model"))
    dialog.translate_current_draft()
    finish_draft(dialog, qapp)
    assert len(calls) == 2 and calls[-1]["model"] == "other-model"
    dialog.accept_document(make_document(("其他",)))
    assert not dialog.draft_text.toPlainText()
    dialog.close()


def test_draft_closed_before_delivery_does_not_update_ui(qapp, monkeypatch):
    setup_requests(monkeypatch)
    entered, release = Event(), Event()

    def owned(*_, **_options):
        def send(**_kwargs):
            entered.set()
            assert release.wait(5)
            return response()
        return send

    monkeypatch.setattr("videocaptioner.core.ocr.assistance.OwnedLLMRequest", owned)
    dialog = OcrDialog()
    dialog.show()
    qapp.processEvents()
    dialog.accept_document(make_document())
    dialog.translate_current_draft()
    worker = dialog.worker
    assert entered.wait(3)
    dialog.close()
    release.set()
    wait_worker(worker)
    qapp.processEvents()
    assert not dialog._drafts and not dialog.draft_text.toPlainText()
    assert dialog.worker is None


def test_missing_configuration_does_not_start_request(qapp, monkeypatch):
    calls = setup_requests(monkeypatch)

    def missing():
        raise OcrError("Missing synthetic credentials")

    monkeypatch.setattr("videocaptioner.ui.components.ocr_dialog.capture_draft_settings", missing)
    dialog = OcrDialog()
    dialog.accept_document(make_document())
    dialog.translate_current_draft()
    assert not calls and dialog.worker is None
    assert "Cài đặt" in dialog.status.text()
    dialog.close()

"""Source verification runs off the Qt thread and never rebinds a saved review."""

from contextvars import ContextVar
from dataclasses import replace
from threading import Event

from PyQt5.QtCore import QEventLoop, QTimer

from videocaptioner.core.asr.audio_identity import POLICY, AudioIdentity
from videocaptioner.core.asr.local.review import LocalReview
from videocaptioner.core.asr.metadata import StageProvenance
from videocaptioner.ui.components.asr_review_dialog import ASRReviewDialog
from videocaptioner.ui.thread.audio_identity_thread import AudioIdentityThread
from videocaptioner.ui.thread.worker_lifecycle import supervisor


def review():
    return replace(LocalReview.capture_chunks(
        stage=StageProvenance("qwen-local", "model", "revision", "policy"), scope="synthetic",
        durations=[(0, 1000)], texts=["你"], raw=[[{"text": "你", "start_ms": 100, "end_ms": 800}]],
        word_timing=True, audio_identity=AudioIdentity(POLICY, "a" * 64, 16000)), pending_diarization=True)


def wait_for(worker, qapp):
    loop = QEventLoop()
    worker.finished.connect(loop.quit)
    QTimer.singleShot(5000, loop.quit)
    if not worker.isFinished():
        loop.exec_()
    assert worker.wait(5000)
    qapp.processEvents()


def test_audio_verification_worker_snapshots_context_and_reports_result(qapp, monkeypatch):
    context = ContextVar("audio-verification-test", default="wrong")
    context.set("job")
    observed = []
    def verify(identity, path, check):
        check()
        observed.append(context.get())
        return True
    monkeypatch.setattr("videocaptioner.ui.thread.audio_identity_thread.verify_audio_file", verify)
    worker = AudioIdentityThread(review().audio_identity, "synthetic")
    worker.result.connect(lambda *args: observed.append(args))
    context.set("changed")
    worker.start()
    wait_for(worker, qapp)
    assert observed == ["job", (True, "")]


def test_review_mismatch_blocks_export_then_reselection_succeeds(qapp, monkeypatch, tmp_path):
    original = review()
    dialog = ASRReviewDialog(original)
    destination = tmp_path / "result.json"
    paths = iter(["wrong.wav", "original.wav"])
    monkeypatch.setattr("videocaptioner.ui.components.asr_review_dialog.QFileDialog.getOpenFileName", lambda *a: (next(paths), ""))
    monkeypatch.setattr("videocaptioner.ui.components.asr_review_dialog.QFileDialog.getSaveFileName", lambda *a: (str(destination), ""))
    def verify(identity, path, check):
        if path == "wrong.wav":
            raise ValueError("Audio does not match")
        return True
    monkeypatch.setattr("videocaptioner.ui.thread.audio_identity_thread.verify_audio_file", verify)
    try:
        dialog.select_audio()
        wait_for(dialog.audio_worker, qapp)
        assert dialog.audio_check_failed
        dialog.export_result()
        assert not destination.exists()
        dialog.select_audio()
        wait_for(dialog.audio_worker, qapp)
        assert not dialog.audio_check_failed and "matches" in dialog.audio_notice.text()
        dialog.export_result()
        assert destination.is_file() and "pending" in dialog.status.text()
        assert dialog.session.review == original
    finally:
        dialog.reject()
        supervisor().reap()
        dialog.deleteLater()


def test_closing_review_cancels_worker_and_suppresses_late_results(qapp, monkeypatch):
    entered = Event()
    def verify(identity, path, check):
        entered.set()
        while True:
            check()
            Event().wait(.01)
    monkeypatch.setattr("videocaptioner.ui.thread.audio_identity_thread.verify_audio_file", verify)
    monkeypatch.setattr("videocaptioner.ui.components.asr_review_dialog.QFileDialog.getOpenFileName", lambda *a: ("synthetic", ""))
    dialog = ASRReviewDialog(review())
    dialog.select_audio()
    worker = dialog.audio_worker
    assert entered.wait(2)
    dialog.reject()
    wait_for(worker, qapp)
    assert dialog.audio_worker is None
    assert "Checking" in dialog.audio_notice.text()
    supervisor().reap()
    dialog.deleteLater()


def test_legacy_review_is_not_marked_verified(qapp):
    dialog = ASRReviewDialog(replace(review(), audio_identity=None))
    try:
        dialog.audio_checked(False, "")
        assert "cannot verify" in dialog.audio_notice.text()
        assert dialog.session.review.audio_identity is None
    finally:
        dialog.deleteLater()

"""Opt-in wording preview must preserve display text and binding semantics."""

from contextlib import nullcontext

import pytest

from videocaptioner.core.dubbing.vietnamese_text import read_integer, suggest_vietnamese


@pytest.fixture(scope="session")
def retained_application():
    from PyQt5.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.mark.parametrize("number,expected", [(0, "không"), (5, "năm"), (15, "mười lăm"),
    (21, "hai mươi mốt"), (101, "một trăm lẻ một"), (1001, "một nghìn không trăm lẻ một"),
    (2_000_001, "hai triệu không trăm lẻ một")])
def test_integer_reading(number, expected):
    assert read_integer(number) == expected


def test_suggestions_preserve_punctuation_and_expand_only_known_forms():
    text = "TP.HCM: mua 2,5 kg gạo, giá 25 USD! Còn 5%?"
    result = suggest_vietnamese(text)
    assert result.text == "thành phố Hồ Chí Minh: mua hai phẩy năm ki lô gam gạo, giá hai mươi lăm đô la Mỹ! Còn năm phần trăm?"
    assert not result.warnings
    assert text == "TP.HCM: mua 2,5 kg gạo, giá 25 USD! Còn 5%?"


def test_ambiguous_numbers_dates_codes_and_time_remain_for_review():
    text = "Ngày 02/10/2026, lúc 12:30; mã 0012, CPU3, giá 1.500. Không bỏ... dấu câu!"
    result = suggest_vietnamese(text)
    assert result.text == text
    assert len(result.warnings) == 4


def test_prepare_review_never_synthesizes_and_keeps_original(tmp_path, monkeypatch):
    from videocaptioner.core.dubbing.config import DubbingConfig
    from videocaptioner.core.dubbing.engine import DubbingEngine
    from videocaptioner.core.dubbing.orchestrator import DubbingOrchestrator
    from videocaptioner.core.tts import TTSConfig

    video, subtitle = tmp_path / "input.mp4", tmp_path / "input.srt"
    video.write_bytes(b"synthetic-video")
    original = "1\n00:00:01,000 --> 00:00:07,000\nMua 2 kg gạo.\n"
    subtitle.write_text(original, encoding="utf-8")
    config = DubbingConfig(tts_config=TTSConfig("fake", "", ""), rewrite_enabled=False)
    engine = DubbingEngine(tts_provider_factory=lambda _: pytest.fail("Preview must not synthesize"))
    monkeypatch.setattr(engine, "_managed_runtime_context", lambda *a: nullcontext())
    monkeypatch.setattr(DubbingOrchestrator, "_validate", staticmethod(lambda *a: None))
    monkeypatch.setattr(DubbingOrchestrator, "_video_duration", staticmethod(lambda *a: 10))
    review = engine.prepare_review(str(video), str(subtitle), config)
    assert review.can_resume and len(review.groups) == 1
    group = review.groups[0]
    approved = review.with_group_text(group.group_id, suggest_vietnamese(group.tts_text).text)
    assert approved.groups[0].tts_text == "Mua hai ki lô gam gạo."
    assert approved.groups[0].subtitle_text == "Mua 2 kg gạo."
    assert approved.groups[0].cue_ids == group.cue_ids
    assert subtitle.read_text(encoding="utf-8") == original
    assert not group.audio_path


def test_dialog_suggestion_is_preview_until_accepted(retained_application):
    from videocaptioner.core.dubbing.models import DubbingGroup, DubbingPlan, DubbingTimingMode
    from videocaptioner.core.dubbing.review import DubbingReview
    from videocaptioner.ui.components.dubbing_review_dialog import DubbingReviewDialog

    app = retained_application
    group = DubbingGroup("g-1", [1], 0, 5, 5, 5, "Mua 2 kg.", "Mua 2 kg.", "Mua 2 kg.")
    plan = DubbingPlan("source.srt", "vi", "omnivoice-local", "test", "female", DubbingTimingMode.NATURAL,
        "2026-10-02", groups=[group])
    original = DubbingReview(plan)
    dialog = DubbingReviewDialog(original)
    dialog._suggest_wording()
    assert dialog.tts_text.toPlainText() == "Mua hai ki lô gam."
    assert original.groups[0].tts_text == "Mua 2 kg."
    dialog.reject()
    assert original.groups[0].tts_text == "Mua 2 kg."
    dialog = DubbingReviewDialog(original)
    dialog._suggest_wording()
    dialog.accept()
    assert dialog.review.groups[0].tts_text == "Mua hai ki lô gam."
    assert dialog.review.groups[0].subtitle_text == "Mua 2 kg."
    dialog.close()
    app.processEvents()


def test_prepare_thread_runs_off_ui_thread_and_joins(retained_application, monkeypatch):
    from types import SimpleNamespace

    from PyQt5.QtCore import QEventLoop, QThread, QTimer

    from videocaptioner.core.dubbing.config import DubbingConfig
    from videocaptioner.core.entities import DubbingTask
    from videocaptioner.ui.thread import dubbing_thread

    prepared = object()
    def prepare(*args, **kwargs):
        assert QThread.currentThread() != retained_application.thread()
        return prepared
    monkeypatch.setattr(dubbing_thread, "_engine_for_task", lambda _: SimpleNamespace(prepare_review=prepare))
    task = DubbingTask(video_path="video.mp4", subtitle_path="words.srt", dubbing_config=DubbingConfig())
    worker = dubbing_thread.DubbingReviewFileThread("prepare", "", task)
    values, errors = [], []
    worker.result.connect(values.append)
    worker.error.connect(errors.append)
    loop = QEventLoop()
    worker.finished.connect(loop.quit)
    QTimer.singleShot(5000, loop.quit)
    worker.start()
    loop.exec_()
    worker.wait()
    assert not errors and values == [prepared]

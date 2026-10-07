"""Series context reaches SubtitleConfig from Settings and the video sidecar; the dialog saves to cfg."""

from PyQt5.QtCore import QEventLoop, QTimer

from videocaptioner.core.translate.series_context import VideoContext, save_video_context
from videocaptioner.ui.common.config import cfg
from videocaptioner.ui.task_factory import TaskFactory


def test_subtitle_task_carries_sidecar_and_series_note(qapp, tmp_path, monkeypatch):
    video = tmp_path / "ep1.mp4"
    video.write_bytes(b"v")
    subtitle = tmp_path / "ep1.srt"
    subtitle.write_text("1\n00:00:00,000 --> 00:00:01,000\nx\n", encoding="utf-8")
    save_video_context(video, VideoContext.make(title="PV 修行", parts=["P1", "P2"]))
    monkeypatch.setattr(cfg.translate_series_context, "value", "清宵 = sư phụ")
    task = TaskFactory.create_subtitle_task(str(subtitle), str(video))
    notes = task.subtitle_config.context_notes
    assert "Title: PV 修行" in notes and "Parts: P1 | P2" in notes and "清宵 = sư phụ" in notes
    monkeypatch.setattr(cfg.translate_series_context, "value", "")
    assert "<series_notes>" not in TaskFactory.create_subtitle_task(str(subtitle), str(video)).subtitle_config.context_notes
    assert TaskFactory.create_subtitle_task(str(subtitle), None).subtitle_config.context_notes == ""


def test_dialog_fetch_fills_notes_off_thread_and_save_writes_cfg(qapp, monkeypatch):
    from videocaptioner.ui.components import series_context_dialog

    monkeypatch.setattr(cfg.translate_series_context, "value", "old note")
    monkeypatch.setattr(series_context_dialog, "fetch_video_context",
                        lambda url, cookies=None: VideoContext.make(title="T", description="D", url=url))
    dialog = series_context_dialog.SeriesContextDialog()
    assert dialog.notes.toPlainText() == "old note"
    dialog.url.setText("https://www.youtube.com/watch?v=x")
    dialog.fetch()
    worker = dialog.worker
    assert worker is not None
    loop = QEventLoop()
    worker.finished.connect(loop.quit)
    QTimer.singleShot(5000, loop.quit)
    if not worker.isFinished():
        loop.exec_()
    assert worker.wait(5000)
    qapp.processEvents()
    text = dialog.notes.toPlainText()
    assert text.startswith("## Video\nTitle: T\nDescription:\nD") and text.endswith("old note")
    saved = []
    monkeypatch.setattr(cfg, "set", lambda item, value, *a, **k: saved.append((item, value)))
    dialog.save()
    assert saved and saved[0][0] is cfg.translate_series_context and saved[0][1].endswith("old note")
    assert "Đã lưu" in dialog.status.text()
    dialog.close()

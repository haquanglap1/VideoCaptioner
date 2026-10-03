"""Download URL persistence and translated batch states stay separate from queue logic."""

import json

import pytest
from PyQt5.QtCore import Qt

from videocaptioner.config import TRANSLATIONS_PATH
from videocaptioner.core.entities import BatchTaskStatus
from videocaptioner.ui.common.config import cfg, recent_download_url, remember_download_url
from videocaptioner.ui.common.json_translator import JsonTranslator
from videocaptioner.ui.components.playlist_dialog import PlaylistDialog
from videocaptioner.ui.view import batch_process_interface as batch_ui
from videocaptioner.ui.view.task_creation_interface import TaskCreationInterface


@pytest.fixture
def vietnamese(qapp):
    translator = JsonTranslator(TRANSLATIONS_PATH / "VideoCaptioner_vi_VN.json")
    qapp.installTranslator(translator)
    try:
        yield
    finally:
        qapp.removeTranslator(translator)


def test_recent_url_is_saved_and_restored_without_starting_network(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(cfg.last_download_url, "value", "")
    monkeypatch.setattr(cfg.work_dir, "value", str(tmp_path))
    page = TaskCreationInterface()
    page.search_input.setText("https://www.bilibili.com/video/BVfixture?vd_source=tracking&p=2")
    page.search_input.textEdited.emit(page.search_input.text())
    saved = json.loads(cfg.file.read_text(encoding="utf-8"))
    expected = "https://www.bilibili.com/video/BVfixture?p=2"
    assert saved["Download"]["LastUrl"] == expected
    page.close()
    reopened = TaskCreationInterface()
    assert reopened.search_input.text() == expected
    reopened.playlist_button.click()
    dialog = reopened._playlist_dialog
    assert dialog.url_edit.text() == expected and dialog._worker is None
    dialog.url_edit.setText("https://example.test/new-list")
    dialog.url_edit.textEdited.emit(dialog.url_edit.text())
    assert json.loads(cfg.file.read_text(encoding="utf-8"))["Download"]["LastUrl"] == "https://example.test/new-list"
    dialog.close()
    reopened.close()
    fresh = PlaylistDialog("", str(tmp_path), "")
    assert fresh.url_edit.text() == "https://example.test/new-list" and fresh._worker is None
    fresh.close()


@pytest.mark.parametrize("value", ["", "video.mp4", "file:///private", "https://user:password@example.test/video"])
def test_local_files_and_invalid_urls_do_not_replace_history(monkeypatch, value):
    monkeypatch.setattr(cfg.last_download_url, "value", "https://example.test/kept")
    remember_download_url(value)
    assert recent_download_url() == "https://example.test/kept"


def test_batch_translated_states_do_not_control_queue_by_display_text(qapp, tmp_path, monkeypatch, vietnamese):
    media = tmp_path / "fixture.mp4"
    media.write_bytes(b"fixture")
    page = batch_ui.BatchProcessInterface()
    page.add_files([str(media)])
    item = page.task_table.item(0, 2)
    assert item.text() == "Đang chờ" and item.data(Qt.UserRole) == BatchTaskStatus.WAITING
    queued = []
    monkeypatch.setattr(page.batch_thread, "add_task", queued.append)
    monkeypatch.setattr(batch_ui.InfoBar, "success", lambda *a, **k: None)
    item.setText("Display text may change with the locale")
    page.start_all_tasks()
    assert len(queued) == 1 and queued[0].file_path == str(media)
    page.update_task_progress(str(media), 20, str(BatchTaskStatus.RUNNING))
    assert item.text() == "Đang xử lý" and item.data(Qt.UserRole) == BatchTaskStatus.RUNNING
    page.on_task_completed(str(media))
    assert item.text() == "Đã hoàn tất" and item.data(Qt.UserRole) == BatchTaskStatus.COMPLETED
    assert page.task_table.cellWidget(0, 1).value() == 100
    page.close()


def test_failed_batch_row_shows_vietnamese_reason_and_preserves_technical_error(qapp, tmp_path, monkeypatch, vietnamese):
    media = tmp_path / "fixture.mp4"
    media.write_bytes(b"fixture")
    page = batch_ui.BatchProcessInterface()
    page.add_files([str(media)])
    error = "Faster-Whisper returned a non-positive native interval; review required."
    page.on_task_error(str(media), error)
    page.update_task_progress(str(media), 100, "转录失败")
    item = page.task_table.item(0, 2)
    assert item.text() == "Thất bại" and item.data(Qt.UserRole) == BatchTaskStatus.FAILED
    assert "thời điểm kết thúc" in item.toolTip() and error in item.toolTip()
    dialogs = []
    class Dialog:
        def __init__(self, title, text, parent):
            dialogs.append((title, text))
            self.contentLabel = self.yesButton = self.cancelButton = self
        def setTextFormat(self, value):
            assert value == Qt.PlainText
        def setText(self, value):
            assert value == "Đóng"
        def hide(self):
            pass
        def exec_(self):
            pass
    monkeypatch.setattr(batch_ui, "MessageBox", Dialog)
    monkeypatch.setattr(page, "open_output_folder", lambda _: pytest.fail("Failed rows must show the error"))
    page.on_table_double_clicked(page.task_table.model().index(0, 2))
    assert dialogs[0][0] == "Chi tiết lỗi" and error in dialogs[0][1]
    page.close()

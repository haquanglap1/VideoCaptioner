"""Actual Qt worker lifecycle, explicit selection/handoff and no automatic processing."""

import time
from pathlib import Path

from PyQt5.QtCore import Qt, QThread

from videocaptioner.core.playlist import (
    PlaylistEntry,
    PlaylistInfo,
    PlaylistItemResult,
    PlaylistResult,
)
from videocaptioner.ui.components.playlist_dialog import PlaylistDialog
from videocaptioner.ui.thread import playlist_thread
from videocaptioner.ui.view.batch_process_interface import BatchProcessInterface
from videocaptioner.ui.view.task_creation_interface import TaskCreationInterface


def settle(worker, qapp):
    try:
        assert worker.wait(5000)
        qapp.processEvents()
    finally:
        if worker.isRunning():
            worker.requestInterruption()
            worker.wait()


def source():
    return PlaylistInfo("https://example.test/list", "Fixture", (
        PlaylistEntry(1, "one", "Z first", "https://example.test/one", 5),
        PlaylistEntry(2, "two", "A second", "https://example.test/two", 6),
        PlaylistEntry(3, "missing", "Unavailable", "", unavailable_reason="Private item"),
    ))


def test_dialog_explicit_discovery_selection_results_and_handoff(qapp, tmp_path, monkeypatch):
    calls = []
    playlist = source()
    def discover(url, **kwargs):
        assert QThread.currentThread() != qapp.thread()
        calls.append("discover")
        return playlist
    def download(info, selected, output, **kwargs):
        assert QThread.currentThread() != qapp.thread()
        assert selected == playlist.entries[:1]
        calls.append("download")
        path = tmp_path / "one.mp4"
        path.write_bytes(b"fixture media")
        result = PlaylistItemResult(1, "downloaded", str(path))
        kwargs["progress"](result, 100)
        return PlaylistResult((result,))
    monkeypatch.setattr(playlist_thread, "discover_playlist", discover)
    monkeypatch.setattr(playlist_thread, "download_playlist", download)
    dialog = PlaylistDialog(playlist.source_url, str(tmp_path), "")
    handed_off = []
    dialog.files_ready.connect(handed_off.append)
    assert not calls and not dialog.download_btn.isEnabled()
    dialog.scan_btn.click()
    settle(dialog._worker, qapp)
    assert dialog.table.rowCount() == 3
    assert dialog.table.item(2, 0).checkState() == Qt.CheckState.Unchecked
    dialog.none_btn.click()
    dialog.table.item(0, 0).setCheckState(Qt.CheckState.Checked)
    dialog.download_btn.click()
    settle(dialog._worker, qapp)
    assert calls == ["discover", "download"] and handed_off == []
    assert dialog.handoff_btn.isEnabled()
    dialog.handoff_btn.click()
    assert handed_off == [[str(tmp_path / "one.mp4")]]
    dialog._invalidate_list()
    assert not dialog.download_btn.isEnabled() and dialog.info is None
    dialog.close()


def test_close_cancels_discovery_without_late_table_update(qapp, tmp_path, monkeypatch):
    entered = []
    def discover(url, **kwargs):
        entered.append(True)
        while not kwargs["cancelled"]():
            time.sleep(.005)
        return source()  # A late transport result must not repaint a closed dialog.
    monkeypatch.setattr(playlist_thread, "discover_playlist", discover)
    dialog = PlaylistDialog("https://example.test/list", str(tmp_path), "")
    dialog.scan_btn.click()
    deadline = time.monotonic() + 2
    while not entered and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(.005)
    assert entered
    dialog.reject()
    settle(dialog._worker, qapp)
    assert dialog.info is None and dialog.table.rowCount() == 0


def test_task_creation_opens_playlist_without_calling_single_pipeline(qapp, tmp_path, monkeypatch):
    from videocaptioner.ui.common.config import cfg
    monkeypatch.setattr(cfg.work_dir, "value", str(tmp_path))
    page = TaskCreationInterface()
    single, batch = [], []
    page.finished.connect(single.append)
    page.playlist_files_ready.connect(batch.append)
    page.search_input.setText("https://www.bilibili.com/video/BVfixture")
    page.playlist_button.click()
    dialog = page._playlist_dialog
    assert dialog.url_edit.text().endswith("BVfixture") and dialog._worker is None
    dialog.completed[1] = str(tmp_path / "one.mp4")
    dialog._handoff()
    assert batch == [[str(tmp_path / "one.mp4")]] and single == []
    dialog.close()
    page.close()


def test_batch_preserves_playlist_order_and_does_not_start_processing(qapp, tmp_path):
    paths = [tmp_path / name for name in ("Z first.mp4", "A second.mp4")]
    for path in paths:
        path.write_bytes(b"fixture media")
    page = BatchProcessInterface()
    page.add_files([str(p) for p in paths], preserve_order=True)
    assert [page.task_table.item(i, 0).toolTip() for i in range(2)] == [str(p) for p in paths]
    assert not page.batch_thread.isRunning()
    assert all(Path(page.task_table.item(i, 0).toolTip()).is_file() for i in range(2))
    page.close()

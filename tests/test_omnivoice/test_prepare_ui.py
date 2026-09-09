"""Qt prepare controls over a real loopback socket; settings/dependencies stay isolated."""

import errno
import shutil

import pytest
from PyQt5.QtCore import QEventLoop, QThread, QTimer

from videocaptioner.core.tts.omnivoice import prepare
from videocaptioner.ui.common.config import cfg
from videocaptioner.ui.components.omnivoice_panel import OmniVoicePanel


def finish_worker(panel, app, on_progress=None):
    panel.prepare_button.click()
    worker = panel.worker
    assert worker is not None
    progress = []
    worker.progress.connect(progress.append)
    if on_progress:
        worker.progress.connect(on_progress)
    loop = QEventLoop()
    worker.finished.connect(loop.quit)
    timer = QTimer()
    timer.setSingleShot(True)
    timer.timeout.connect(loop.quit)
    timer.start(10000)
    try:
        loop.exec_()
    finally:
        timer.stop()
        if worker.isRunning():
            panel.stop()
        assert worker.wait(5000)
        app.processEvents()
    return worker, progress


def test_gui_cancel_finishes_and_resumes_partial(omni_qapp, staged_runtime, loopback_download):
    panel = OmniVoicePanel()
    panel.runtime_edit.setText(str(staged_runtime))
    loopback_download.slow = True
    cancelled = []
    control_states = []

    def cancel_after_bytes(message):
        if "MiB" in message and "0.0 MiB" not in message and not cancelled:
            control_states.append((panel.runtime_edit.isEnabled(), panel.browse_runtime_button.isEnabled(),
                                   QThread.currentThread() is omni_qapp.thread()))
            cancelled.append(True)
            panel.prepare_button.click()
            control_states.append(panel.prepare_button.isEnabled())

    try:
        old_worker, progress = finish_worker(panel, omni_qapp, cancel_after_bytes)
        assert cancelled and any("MiB" in item for item in progress)
        assert control_states == [(False, False, True), False]
        assert "Đã hủy" in panel.status_label.text()
        assert "Đang dừng" not in panel.status_label.text()
        assert panel.worker is None and panel.prepare_button.isEnabled()
        assert panel.runtime_edit.isEnabled()
        offset = (staged_runtime / "model/weights.bin.part").stat().st_size
        assert 0 < offset < len(loopback_download.payload)
        assert not (staged_runtime / "ready.json").exists()
        old_worker.prepared.emit("late-root")
        old_worker.progress.emit("late progress")
        omni_qapp.processEvents()
        assert "Đã hủy" in panel.status_label.text()
        assert panel.runtime_edit.text() == str(staged_runtime)
        loopback_download.slow = False
        finish_worker(panel, omni_qapp)
        assert loopback_download.requests[-1]["range"] == f"bytes={offset}-"
        assert panel.status_label.text() == "OmniVoice: Ready"
        assert panel.worker is None and panel.prepare_button.isEnabled()
        request_count = len(loopback_download.requests)
        _, progress = finish_worker(panel, omni_qapp)
        assert "Verifying installed OmniVoice" in progress
        assert len(loopback_download.requests) == request_count
        assert panel.status_label.text() == "OmniVoice: Ready"
    finally:
        panel.close()


@pytest.mark.parametrize("failure", ["interrupt", "corrupt", "disk"])
def test_gui_failure_unlocks_controls_without_activating_target(
    omni_qapp, staged_runtime, loopback_download, monkeypatch, failure,
):
    active = staged_runtime.parent / "active"
    shutil.copytree(staged_runtime, active)
    (active / "model").mkdir()
    (active / "model/weights.bin").write_bytes(loopback_download.payload)
    (active / "ready.json").write_bytes((active / "owner.json").read_bytes())
    active_before = {path.relative_to(active): path.read_bytes() for path in active.rglob("*") if path.is_file()}
    before = cfg.omnivoice_runtime.value
    cfg.set(cfg.omnivoice_runtime, str(active))
    panel = OmniVoicePanel()
    panel.runtime_edit.setText(str(staged_runtime))
    loopback_download.mode = failure
    disk_usage = prepare.shutil.disk_usage
    if failure == "disk":
        def full_disk(*args):
            raise OSError(errno.ENOSPC, "fixture disk full")
        monkeypatch.setattr(prepare.shutil, "disk_usage", full_disk)
    try:
        finish_worker(panel, omni_qapp)
        assert panel.prepare_button.isEnabled() and panel.runtime_edit.isEnabled()
        assert panel.worker is None
        assert "Ready" not in panel.status_label.text()
        assert ("disk" if failure == "disk" else "checksum" if failure == "corrupt" else "interrupted") in panel.status_label.text()
        assert not (staged_runtime / "ready.json").exists()
        assert {path.relative_to(active): path.read_bytes() for path in active.rglob("*") if path.is_file()} == active_before
        prepare.verify(active)
        assert cfg.omnivoice_runtime.value == str(active)
        part = staged_runtime / "model/weights.bin.part"
        offset = part.stat().st_size if part.exists() else 0
        loopback_download.mode = "complete"
        monkeypatch.setattr(prepare.shutil, "disk_usage", disk_usage)
        finish_worker(panel, omni_qapp)
        assert loopback_download.requests[-1]["range"] == (f"bytes={offset}-" if offset else None)
        assert panel.status_label.text() == "OmniVoice: Ready"
        assert cfg.omnivoice_runtime.value == str(staged_runtime)
        assert {path.relative_to(active): path.read_bytes() for path in active.rglob("*") if path.is_file()} == active_before
    finally:
        panel.close()
        cfg.set(cfg.omnivoice_runtime, before)

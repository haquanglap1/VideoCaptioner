# pyright: reportAttributeAccessIssue=false

import sys
from pathlib import Path

import pytest
from PyQt5.QtCore import QEventLoop, QTimer
from PyQt5.QtWidgets import QApplication
from qfluentwidgets import InfoBar, PushButton

from videocaptioner.core.tts.vieneu.model_updater import (
    VieNeuModelPaths,
    VieNeuModelUpdater,
    VieNeuStateStore,
)
from videocaptioner.core.tts.vieneu.models import VieNeuModelState
from videocaptioner.core.tts.vieneu.runtime_locator import VieNeuRuntimeLocator
from videocaptioner.core.tts.vieneu.runtime_manager import VieNeuRuntimeManager
from videocaptioner.core.tts.vieneu.service import (
    VIENEU_RUNTIME_INSTALL_MESSAGE,
    VieNeuManagedService,
    set_vieneu_service_for_tests,
)
from videocaptioner.ui.thread.vieneu_runtime_thread import VieNeuRuntimeThread
from videocaptioner.ui.view.dubbing_interface import DubbingInterface


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication(sys.argv)


def make_service(tmp_path, fake_bridge):
    store = VieNeuStateStore(VieNeuModelPaths.under(tmp_path / "models"))
    model = store.paths.hf_cache / "snapshots" / ("a" * 40)
    dependency = store.paths.hf_cache / "snapshots" / ("d" * 40)
    model.mkdir(parents=True)
    dependency.mkdir(parents=True)
    store.save(
        VieNeuModelState(
            active_revision="a" * 40,
            active_snapshot=store.relative_snapshot(model),
            tokenizer_revision="d" * 40,
            tokenizer_snapshot=store.relative_snapshot(dependency),
            codec_revision="d" * 40,
            codec_snapshot=store.relative_snapshot(dependency),
        )
    )
    return VieNeuManagedService(
        manager=VieNeuRuntimeManager(),
        store=store,
        explicit_runtime=Path(sys.executable),
        explicit_bridge=fake_bridge,
    )


class OfferHub:
    """Hub double: one remote revision, downloads materialise instantly."""

    def __init__(self, revision="b" * 40):
        self.revision = revision
        self.download_calls = 0

    def remote_revision(self, repository_id):
        return self.revision

    def snapshot_download(
        self, repository_id, revision, cache_dir, *, progress_callback=None, cancel_event=None
    ):
        self.download_calls += 1
        snapshot = Path(cache_dir) / "snapshots" / revision
        snapshot.mkdir(parents=True, exist_ok=True)
        (snapshot / "config.json").write_text("{}", encoding="utf-8")
        if progress_callback:
            progress_callback(1, 1, "Fetching 1 files [it]")
        return snapshot


def test_runtime_thread_fetches_voices_without_importing_widgets(qapp, tmp_path, fake_bridge):
    service = make_service(tmp_path, fake_bridge)
    thread = VieNeuRuntimeThread("voices", service=service)
    loop = QEventLoop()
    received = {}
    thread.result.connect(lambda action, result: received.update(action=action, result=result))
    thread.error.connect(lambda action, error: received.update(error=(action, error)))
    thread.finished.connect(loop.quit)
    timer = QTimer()
    timer.setSingleShot(True)
    timer.timeout.connect(loop.quit)
    timer.start(7000)
    thread.start()
    loop.exec_()
    thread.wait(1000)
    service.shutdown()
    assert "error" not in received
    assert received["action"] == "voices"
    assert received["result"][0]["id"] == "fake-voice"
    source = Path(VieNeuRuntimeThread.__module__.replace(".", "/") + ".py")
    module_source = (
        Path(__file__).resolve().parents[2]
        / "videocaptioner"
        / "ui"
        / "thread"
        / "vieneu_runtime_thread.py"
    ).read_text(encoding="utf-8")
    assert "QtWidgets" not in module_source
    assert source.name == "vieneu_runtime_thread.py"


def test_gui_managed_provider_hides_api_configuration_and_keeps_local_ai(qapp, tmp_path, fake_bridge):
    service = make_service(tmp_path, fake_bridge)
    set_vieneu_service_for_tests(service)
    widget = DubbingInterface()
    try:
        assert widget.provider_combo.count() == 4
        assert widget.provider_combo.itemText(2) == "Local AI"
        assert widget.provider_combo.itemText(3) == "VieNeu Local"
        widget.provider_combo.setCurrentIndex(3)
        qapp.processEvents()
        assert widget.vieneu_widget.isVisible() is False  # parent widget is not shown yet
        assert widget.api_key_edit.isEnabledTo(widget.settings_widget) is False
        assert widget.api_base_edit.isEnabledTo(widget.settings_widget) is False
        assert widget.model_edit.isEnabledTo(widget.settings_widget) is False
        assert widget.sample_rate_combo.isEnabledTo(widget.settings_widget) is False
        widget.show()
        qapp.processEvents()
        assert widget.vieneu_widget.isVisible() is True
        widget.provider_combo.setCurrentIndex(2)
        assert widget.api_base_edit.isEnabledTo(widget.settings_widget) is True
    finally:
        widget.close()
        service.shutdown()
        set_vieneu_service_for_tests(None)


def test_gui_disables_vieneu_actions_when_base_build_has_no_runtime(qapp, tmp_path):
    store = VieNeuStateStore(VieNeuModelPaths.under(tmp_path / "models"))
    service = VieNeuManagedService(
        manager=VieNeuRuntimeManager(locator=VieNeuRuntimeLocator(app_root=tmp_path / "app")),
        store=store,
    )
    set_vieneu_service_for_tests(service)
    widget = DubbingInterface()
    try:
        widget.provider_combo.setCurrentIndex(3)
        widget.show()
        qapp.processEvents()
        assert service.update_prerequisite_error() == VIENEU_RUNTIME_INSTALL_MESSAGE
        assert widget.vieneu_update_btn.isEnabled() is False
        assert widget.vieneu_start_stop_btn.isEnabled() is False
        assert widget.fetch_voice_btn.isEnabled() is False
        assert "Runtime not installed" in widget.vieneu_status_label.text()
        assert widget.vieneu_update_btn.toolTip() == VIENEU_RUNTIME_INSTALL_MESSAGE
    finally:
        widget.close()
        service.shutdown()
        set_vieneu_service_for_tests(None)


def _wait_for_vieneu(qapp, widget, timeout_s: float = 20.0) -> None:
    import time

    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        qapp.processEvents()
        if not widget._vieneu_pending_action and not any(
            thread.isRunning() for thread in widget._vieneu_threads
        ):
            qapp.processEvents()
            return
        time.sleep(0.05)
    raise AssertionError("VieNeu GUI threads did not settle in time")


def test_gui_queues_voice_fetch_behind_running_action_and_autoloads_after_start(
    qapp, tmp_path, fake_bridge
):
    """Clicking "Tải danh sách" while Start/auto-update runs must not be dropped.

    The launch auto-update used to run outside the tab's thread set, and a
    second request was silently ignored while its button already said
    "Đang tải...", so the voice list never arrived.
    """
    service = make_service(tmp_path, fake_bridge)
    set_vieneu_service_for_tests(service)
    widget = DubbingInterface()
    try:
        widget.provider_combo.setCurrentIndex(3)
        widget.voice_combo.setText("alloy")
        widget._start_vieneu_action("start")
        assert any(thread.isRunning() for thread in widget._vieneu_threads)
        widget._fetch_voices()
        assert widget._vieneu_pending_action == "voices"
        assert widget.fetch_voice_btn.isEnabledTo(widget.settings_widget) is False

        _wait_for_vieneu(qapp, widget)
        assert widget.fetch_voice_btn.isEnabledTo(widget.settings_widget) is True
        assert widget.fetch_voice_btn.text() == "Tải danh sách"
        assert widget.voice_combo.text() == "fake-voice"
        assert service.manager.process_id
    finally:
        widget.shutdown_vieneu_threads()
        widget.close()
        service.shutdown()
        set_vieneu_service_for_tests(None)


def test_gui_launch_check_offers_update_and_downloads_only_on_click(
    qapp, tmp_path, fake_bridge
):
    """Auto update at startup checks the hub; the 1.7 GB pull waits for a click."""
    service = make_service(tmp_path, fake_bridge)
    hub = OfferHub()
    service.updater = VieNeuModelUpdater(store=service.store, hub=hub)
    set_vieneu_service_for_tests(service)
    widget = DubbingInterface()
    try:
        widget.provider_combo.setCurrentIndex(3)
        widget.show()
        qapp.processEvents()
        widget.start_launch_update_check()
        _wait_for_vieneu(qapp, widget)

        assert hub.download_calls == 0
        assert service.manager.process_id is None
        assert widget._vieneu_offered_revision == "b" * 40
        assert "b" * 12 in widget.vieneu_status_label.text()
        assert widget.progress_bar.isVisible() is False
        offers = [
            bar for bar in widget.findChildren(InfoBar)
            if bar.titleLabel.text() == "VieNeu model update available"
        ]
        assert len(offers) == 1
        assert "b" * 12 in offers[0].contentLabel.text()
        button = next(
            child for child in offers[0].findChildren(PushButton)
            if child.text() == "Download and activate"
        )

        button.click()
        _wait_for_vieneu(qapp, widget, timeout_s=40.0)

        assert hub.download_calls >= 2  # pinned dependencies + the model
        assert service.model_state().active_revision == "b" * 40
        assert service.model_state().previous_revision == "a" * 40
        assert service.manager.identity and service.manager.identity.model_revision == "b" * 40
        assert widget._vieneu_offered_revision == ""
        assert widget.progress_bar.isVisible() is True
        assert widget.progress_bar.value() == 100
        assert any(
            bar.titleLabel.text() == "VieNeu model updated"
            for bar in widget.findChildren(InfoBar)
        )
    finally:
        widget.shutdown_vieneu_threads()
        widget.close()
        service.shutdown()
        set_vieneu_service_for_tests(None)


def test_gui_manual_check_reports_current_model_without_offer(qapp, tmp_path, fake_bridge):
    service = make_service(tmp_path, fake_bridge)
    hub = OfferHub(revision="a" * 40)
    service.updater = VieNeuModelUpdater(store=service.store, hub=hub)
    set_vieneu_service_for_tests(service)
    widget = DubbingInterface()
    try:
        widget.provider_combo.setCurrentIndex(3)
        # The tab's controls stay disabled until dubbing is switched on.
        widget.enable_switch.setChecked(True)
        widget.show()
        qapp.processEvents()
        assert widget.vieneu_update_btn.isEnabled()
        widget.vieneu_update_btn.click()
        _wait_for_vieneu(qapp, widget)

        assert hub.download_calls == 0
        assert widget._vieneu_offered_revision == ""
        titles = [bar.titleLabel.text() for bar in widget.findChildren(InfoBar)]
        assert "VieNeu model is up to date" in titles
        assert "VieNeu model update available" not in titles
    finally:
        widget.shutdown_vieneu_threads()
        widget.close()
        service.shutdown()
        set_vieneu_service_for_tests(None)


def test_gui_start_alone_fills_voice_list(qapp, tmp_path, fake_bridge):
    service = make_service(tmp_path, fake_bridge)
    set_vieneu_service_for_tests(service)
    widget = DubbingInterface()
    try:
        widget.provider_combo.setCurrentIndex(3)
        widget.voice_combo.clear()
        widget._start_vieneu_action("start")
        _wait_for_vieneu(qapp, widget)
        assert [widget.voice_combo.itemText(i) for i in range(widget.voice_combo.count())] == [
            "fake-voice"
        ]
        assert widget.vieneu_start_stop_btn.text() == "Stop"
    finally:
        widget.shutdown_vieneu_threads()
        widget.close()
        service.shutdown()
        set_vieneu_service_for_tests(None)

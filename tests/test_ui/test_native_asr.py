"""Offline settings/probe and QThread lifecycle coverage."""

import asyncio
from copy import deepcopy

import pytest
from PyQt5.QtCore import QEventLoop, QTimer

from videocaptioner.core.asr.native_profiles import NativeASRConfig
from videocaptioner.ui.common.config import cfg, native_asr_settings


@pytest.fixture(autouse=True)
def settings():
    names = [name for name in dir(cfg) if name.startswith(("soniox_", "scribe_"))]
    names += ["transcribe_model", "transcribe_language"]
    before = {name: deepcopy(getattr(cfg, name).value) for name in names}
    yield
    for name, value in before.items():
        item = getattr(cfg, name)
        item.blockSignals(True)
        item.value = value
        item.blockSignals(False)
    for controller in native_asr_settings:
        controller.base = controller.base_item.value


@pytest.mark.parametrize("surface", ["settings", "soniox", "scribe"])
def test_open_settings_never_calls_network_or_resets_credentials(qapp, monkeypatch, surface):
    from videocaptioner.ui.components.NativeASRSettingWidget import NativeASRSettingWidget
    from videocaptioner.ui.view.setting_interface import SettingInterface
    monkeypatch.setattr("httpx.AsyncClient.request", lambda *a, **k: pytest.fail("opening must be offline"))
    cfg.set(cfg.soniox_api_key, "soniox-test-key")
    cfg.set(cfg.scribe_api_key, "scribe-test-key")
    before = cfg.toDict()
    page = SettingInterface() if surface == "settings" else NativeASRSettingWidget(surface)
    for provider in ("Soniox", "Scribe"):
        assert cfg.toDict()[provider] == before[provider]
    page.close()
    page.deleteLater()


def test_key_switching_is_provider_and_endpoint_scoped(qapp):
    cfg.set(cfg.soniox_api_key, "soniox-test-key")
    cfg.set(cfg.scribe_api_key, "scribe-test-key")
    before = cfg.soniox_api_base.value
    cfg.set(cfg.soniox_api_base, "https://elsewhere.example/v1")
    assert cfg.soniox_api_key.value == ""
    assert cfg.scribe_api_key.value == "scribe-test-key"
    cfg.set(cfg.soniox_api_base, before)
    assert cfg.soniox_api_key.value == "soniox-test-key"


def test_probe_qthread_keeps_context_and_waits_after_cancel(qapp, monkeypatch):
    from contextvars import ContextVar

    from videocaptioner.core.asr.native_api import run_cancellable
    from videocaptioner.ui.thread.native_asr_thread import NativeASRProbeThread
    context = ContextVar("native-test", default="missing")
    context.set("captured")
    observed = []
    def probe(config, check):
        assert context.get() == "captured"
        async def pending():
            try:
                await asyncio.sleep(60)
            finally:
                observed.append("socket-closed")
        run_cancellable(pending(), check)
    monkeypatch.setattr("videocaptioner.core.asr.native_api.probe_service", probe)
    worker = NativeASRProbeThread(NativeASRConfig("soniox", "test-key"))
    loop = QEventLoop()
    worker.finished.connect(loop.quit)
    worker.result.connect(observed.append)
    QTimer.singleShot(50, worker.requestInterruption)
    QTimer.singleShot(3000, loop.quit)
    worker.start()
    try:
        loop.exec_()
    finally:
        worker.requestInterruption()
        assert worker.wait(3000)
    assert "socket-closed" in observed
    assert any("cancelled" in message for message in observed)


def test_subtitle_task_displays_metadata_instead_of_reimporting_srt(qapp, tmp_path):
    from videocaptioner.core.asr.asr_data import ASRData, ASRDataSeg
    from videocaptioner.core.asr.metadata import ASRMetadata
    from videocaptioner.core.entities import SubtitleTask
    from videocaptioner.ui.view.subtitle_interface import SubtitleInterface
    data = ASRData([ASRDataSeg("你好", 0, 100, metadata=ASRMetadata("soniox", "job", "1"))])
    path = tmp_path / "source.srt"
    data.save(str(path))
    page = SubtitleInterface()
    page.set_task(SubtitleTask(subtitle_path=str(path), asr_data=data))
    assert page.model._data == data.to_json()
    page.close()
    page.deleteLater()

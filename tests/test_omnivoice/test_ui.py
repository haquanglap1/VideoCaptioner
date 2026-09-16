"""Provider switching exposes local controls without touching VieNeu state."""

import pytest

pytest.importorskip("PyQt5")
from PyQt5.QtWidgets import QApplication

from videocaptioner.core.dubbing.config import TTSProviderEnum
from videocaptioner.ui.common.config import cfg
from videocaptioner.ui.task_factory import TaskFactory
from videocaptioner.ui.view.dubbing_interface import DubbingInterface


@pytest.fixture(scope="session", autouse=True)
def keep_qt_application():
    app = QApplication.instance() or QApplication([])
    yield app


def test_select_omnivoice_and_return_to_vieneu(monkeypatch):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr("videocaptioner.ui.components.omnivoice_panel.prepare_runtime", lambda *a, **kw: pytest.fail("Opening controls must not download"))
    view = DubbingInterface()
    view.provider_combo.setCurrentIndex(4)
    assert not view.omnivoice_panel.isHidden() and view.vieneu_widget.isHidden()
    assert not view.api_key_edit.isEnabled() and not view.fetch_voice_btn.isEnabled()
    assert view.voice_combo.text() == "auto"
    cfg.set(cfg.dubbing_enabled, True)
    config = TaskFactory.create_dubbing_config()
    assert config.tts_provider == TTSProviderEnum.OMNIVOICE_LOCAL
    view.provider_combo.setCurrentIndex(3)
    assert view.omnivoice_panel.isHidden() and not view.vieneu_widget.isHidden()
    assert TaskFactory.create_dubbing_config().tts_provider == TTSProviderEnum.VIENEU_LOCAL
    view.close()
    app.processEvents()


def test_sequential_controls_roundtrip_without_changing_legacy():
    app = QApplication.instance() or QApplication([])
    view = DubbingInterface()
    view.enable_switch.setChecked(True)
    view.timing_mode_combo.setCurrentIndex(0)
    view.unresolved_combo.setCurrentIndex(2)
    view.start_delay_spinbox.setValue(1500)
    assert view.start_delay_spinbox.isEnabled()
    view._save_settings()
    config = TaskFactory.create_dubbing_config()
    assert config.unresolved_policy.value == "sequential" and config.max_start_delay_ms == 1500
    view.timing_mode_combo.setCurrentIndex(1)
    assert not view.start_delay_spinbox.isEnabled()
    view.close()
    app.processEvents()

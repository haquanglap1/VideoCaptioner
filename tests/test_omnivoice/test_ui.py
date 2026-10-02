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


@pytest.fixture(autouse=True)
def restore_voice_settings():
    items = [cfg.omnivoice_voice_id, cfg.omnivoice_reference_audio, cfg.omnivoice_reference_text,
             cfg.dubbing_tts_provider, cfg.dubbing_tts_voice]
    values = [item.value for item in items]
    yield
    for item, value in zip(items, values):
        cfg.set(item, value)


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


def test_full_text_sequential_settings_reach_task_factory():
    app = QApplication.instance() or QApplication([])
    view = DubbingInterface()
    view.enable_switch.setChecked(True)
    view.timing_mode_combo.setCurrentIndex(0)
    view.unresolved_combo.setCurrentIndex(2)
    view.speed_slider.setValue(10)
    view.natural_speed_slider.setValue(100)
    view.start_delay_spinbox.setValue(1000)
    view.rewrite_switch.setChecked(False)
    view._save_settings()
    config = TaskFactory.create_dubbing_config()
    assert config is not None
    assert config.tts_config.speed == config.natural_max_speed == 1.0
    assert config.max_start_delay_ms == 1000 and config.silence_guard_ms == 80
    assert config.unresolved_policy.value == "sequential"
    assert config.timing_mode.value == "natural" and config.rewrite_enabled is False
    view.close()
    app.processEvents()


def test_fixed_voice_selection_ignores_old_reference_and_survives_reopen():
    cfg.set(cfg.omnivoice_voice_id, "vi-female-2")
    cfg.set(cfg.omnivoice_reference_audio, "old-private-reference.wav")
    cfg.set(cfg.omnivoice_reference_text, "Old words")
    view = DubbingInterface()
    view.provider_combo.setCurrentIndex(4)
    view.enable_switch.setChecked(True)
    view._save_settings()
    config = TaskFactory.create_dubbing_config()
    assert config.tts_config.voice == "vi-female-2"
    assert not config.omnivoice.reference_audio and not config.omnivoice.reference_text
    assert view.voice_row.isHidden()
    assert view.omnivoice_panel.reference_widget.isHidden()
    view.close()
    reopened = DubbingInterface()
    assert reopened.omnivoice_panel.selected_voice() == "vi-female-2"
    panel = reopened.omnivoice_panel
    panel.voice_list.setCurrentIndex(panel.voice_list.findData("reference"))
    reopened._save_settings()
    config = TaskFactory.create_dubbing_config()
    assert config.omnivoice.reference_audio == "old-private-reference.wav"
    assert config.omnivoice.reference_text == "Old words"
    reopened.close()


def test_voice_sample_player_uses_selected_bundled_wav(monkeypatch):
    from videocaptioner.ui.components.omnivoice_panel import OmniVoicePanel

    cfg.set(cfg.omnivoice_voice_id, "vi-male-2")
    panel = OmniVoicePanel()
    played = []
    monkeypatch.setattr(panel.player, "play", lambda: played.append(True))
    panel.preview_voice()
    assert played == [True]
    assert panel.player.media().canonicalUrl().toLocalFile().endswith("vi-male-2.wav")
    panel.stop()
    panel.close()


def test_import_worker_adds_named_voice_and_joins():
    from PyQt5.QtCore import QEventLoop, QTimer

    from videocaptioner.core.tts.omnivoice.voices import resolve_voice
    from videocaptioner.ui.components.omnivoice_panel import OmniVoicePanel

    panel = OmniVoicePanel()
    profile = resolve_voice("vi-female-1")
    panel.reference_audio.setText(str(profile.audio_path))
    panel.reference_text.setText(profile.transcript)
    panel.voice_name.setText("My saved narrator")
    panel.import_voice()
    worker = panel.voice_worker
    loop = QEventLoop()
    worker.finished.connect(loop.quit)
    QTimer.singleShot(10000, loop.quit)
    loop.exec_()
    worker.wait()
    assert panel.selected_voice().startswith("saved-")
    assert resolve_voice(panel.selected_voice()).name == "My saved narrator"
    assert cfg.omnivoice_voice_id.value == panel.selected_voice()
    panel.stop()
    panel.close()


def test_browsing_reference_clears_stale_transcript_and_reads_matching_txt(tmp_path, monkeypatch):
    from videocaptioner.ui.components.omnivoice_panel import OmniVoicePanel

    path = tmp_path / "new.wav"
    path.touch()
    monkeypatch.setattr("videocaptioner.ui.components.omnivoice_panel.QFileDialog.getOpenFileName",
        lambda *a, **k: (str(path), ""))
    panel = OmniVoicePanel()
    panel.reference_text.setText("Wrong old words")
    panel.browse_reference()
    assert not panel.reference_text.text()
    path.with_suffix(".txt").write_text("Đúng lời mẫu.", encoding="utf-8-sig")
    panel.browse_reference()
    assert panel.reference_text.text() == "Đúng lời mẫu."
    panel.stop()
    panel.close()

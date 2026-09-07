"""Settings migration, credential routing and worker regression tests."""

from copy import deepcopy

import pytest

from videocaptioner.core.asr.api_profiles import endpoint_identity
from videocaptioner.ui.common.config import cfg, whisper_settings


@pytest.fixture(autouse=True)
def whisper_config():
    names = [name for name in dir(cfg) if name.startswith("whisper_api_")] + ["transcribe_language"]
    original = {name: deepcopy(getattr(cfg, name).value) for name in names}
    cfg.set(cfg.whisper_api_provider, "custom")
    cfg.set(cfg.whisper_api_saved_profiles, {})
    cfg.set(cfg.whisper_api_endpoint_keys, {})
    cfg.set(cfg.whisper_api_base, "https://custom.example/v1")
    cfg.set(cfg.whisper_api_key, "custom-test-key")
    cfg.set(cfg.whisper_api_model, "my-manual-alias")
    cfg.set(cfg.whisper_api_prompt, "Synthetic test hint")
    cfg.set(cfg.whisper_api_request_profile, "whisper")
    yield
    for name, value in original.items():
        item = getattr(cfg, name)
        item.blockSignals(True)
        item.value = value
        item.blockSignals(False)
    whisper_settings.base = cfg.whisper_api_base.value
    whisper_settings.provider = cfg.whisper_api_provider.value


@pytest.mark.parametrize("surface", ["settings", "dialog"])
def test_open_preserves_custom_settings_and_makes_no_request(qapp, monkeypatch, surface):
    from videocaptioner.ui.components.WhisperAPISettingWidget import WhisperAPISettingWidget
    from videocaptioner.ui.view.setting_interface import SettingInterface

    monkeypatch.setattr("videocaptioner.core.asr.api_transcription.create_client",
                        lambda *a: pytest.fail("opening settings must be offline"))
    before = cfg.toDict()
    language = cfg.transcribe_language.value
    page = SettingInterface() if surface == "settings" else WhisperAPISettingWidget()
    assert cfg.toDict()["WhisperAPI"] == before["WhisperAPI"]
    assert cfg.transcribe_language.value == language
    cards = page.whisperProfileCards if surface == "settings" else page.profile_cards
    assert "timestamps" in cards.profile.contentLabel.text()
    page.deleteLater()


def test_presets_restore_custom_values_and_never_reuse_another_endpoint_key(qapp):
    from videocaptioner.ui.components.WhisperAPISettingWidget import WhisperAPISettingWidget

    page = WhisperAPISettingWidget()
    language = cfg.transcribe_language.value
    page.profile_cards.provider.comboBox.setCurrentText("VideoCaptioner API")
    assert cfg.whisper_api_base.value == "https://api.videocaptioner.cn/v1"
    assert cfg.whisper_api_key.value == ""
    assert cfg.whisper_api_model.value == "whisper-1"
    cfg.set(cfg.whisper_api_key, "gateway-test-key")
    page.model_card.comboBox.setText("gpt-4o-transcribe")
    assert "alignment" in page.profile_cards.profile.contentLabel.text()
    page.profile_cards.provider.comboBox.setCurrentText("Groq")
    assert cfg.whisper_api_key.value == ""
    assert cfg.whisper_api_model.value == "whisper-large-v3"
    page.profile_cards.provider.comboBox.setCurrentText("VideoCaptioner API")
    assert cfg.whisper_api_key.value == "gateway-test-key"
    assert cfg.whisper_api_model.value == "gpt-4o-transcribe"
    page.profile_cards.provider.comboBox.setCurrentText("Custom")
    assert cfg.whisper_api_key.value == "custom-test-key"
    assert cfg.whisper_api_base.value == "https://custom.example/v1"
    assert cfg.whisper_api_model.value == "my-manual-alias"
    assert cfg.whisper_api_prompt.value == "Synthetic test hint"
    assert cfg.whisper_api_request_profile.value == "whisper"
    assert cfg.transcribe_language.value == language
    page.deleteLater()


def test_manual_base_change_binds_keys_and_reopen_preserves_empty_key(qapp):
    from videocaptioner.ui.components.WhisperAPISettingWidget import WhisperAPISettingWidget

    page = WhisperAPISettingWidget()
    page.base_url_card.lineEdit.setText("https://CUSTOM.example:443/v1/")
    assert cfg.whisper_api_key.value == "custom-test-key"
    page.base_url_card.lineEdit.setText("https://other.example/v1")
    assert cfg.whisper_api_key.value == ""
    assert cfg.whisper_api_endpoint_keys.value[endpoint_identity("https://custom.example")] == "custom-test-key"
    second = WhisperAPISettingWidget()
    assert second.api_key_card.lineEdit.text() == ""
    second.base_url_card.lineEdit.setText("https://custom.example/v1")
    assert page.api_key_card.lineEdit.text() == "custom-test-key"
    page.deleteLater()
    second.deleteLater()


def test_probe_worker_captures_profile_and_context_and_is_joined(qapp, monkeypatch):
    from contextvars import ContextVar

    from PyQt5.QtCore import QEventLoop, QTimer

    from videocaptioner.ui.thread.whisper_connection_thread import WhisperConnectionThread

    context = ContextVar("probe-test", default="missing")
    context.set("job-one")
    observed = []
    def probe(base, key, model, **kwargs):
        observed.append((context.get(), model, kwargs))
        return True, "Recognition succeeded without timestamps."
    monkeypatch.setattr("videocaptioner.ui.thread.whisper_connection_thread.check_whisper_connection", probe)
    thread = WhisperConnectionThread("https://example.com", "fake", "manual", "custom", "json-text")
    context.set("job-two")
    loop = QEventLoop()
    result = []
    thread.finished.connect(lambda ok, message: (result.append((ok, message)), loop.quit()))
    QTimer.singleShot(3000, loop.quit)
    thread.start()
    loop.exec_()
    assert thread.wait(3000)
    assert result[0][0]
    assert observed == [("job-one", "manual", {"provider": "custom", "request_profile": "json-text"})]

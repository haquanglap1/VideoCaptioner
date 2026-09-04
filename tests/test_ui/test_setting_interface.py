"""Offscreen regression tests for the settings page's provider/service switching."""

import pytest

from videocaptioner.core.entities import (
    LLMServiceEnum,
    TranscribeModelEnum,
    TranslatorServiceEnum,
)
from videocaptioner.core.llm.services import LLM_SERVICE_PRESETS
from videocaptioner.ui.common.config import cfg


@pytest.fixture
def view(qapp):
    from videocaptioner.ui.view.setting_interface import SettingInterface

    cfg.set(cfg.ollama_api_key, "")
    cfg.set(cfg.lm_studio_api_key, "typed-by-user")
    page = SettingInterface()
    yield page
    page.deleteLater()


def _select(view, card, member):
    card.comboBox.setCurrentText(view.tr(member.value))


def test_every_preset_has_bound_cards(view):
    for preset in LLM_SERVICE_PRESETS.values():
        for suffix in ("api_key", "api_base", "model"):
            assert hasattr(view, f"{preset.config_attr}_{suffix}_card")
    assert set(view.llm_service_configs) == set(LLMServiceEnum)
    assert view.openai_api_base_card.lineEdit.isReadOnly() is False
    assert view.deepseek_api_base_card.lineEdit.isReadOnly() is True
    assert view.gemini_api_base_card.lineEdit.isReadOnly() is True


def test_llm_service_switch_shows_one_provider_and_fills_local_key(view):
    _select(view, view.llmServiceCard, LLMServiceEnum.OLLAMA)
    assert view.ollama_api_key_card.isVisibleTo(view)
    assert view.ollama_model_card.isVisibleTo(view)
    assert not view.openai_api_key_card.isVisibleTo(view)
    assert not view.openaiOfficialApiCard.isVisibleTo(view)
    assert view.ollama_api_key_card.lineEdit.text() == "ollama"

    _select(view, view.llmServiceCard, LLMServiceEnum.LM_STUDIO)
    assert view.lm_studio_api_key_card.lineEdit.text() == "typed-by-user"
    assert not view.ollama_api_key_card.isVisibleTo(view)

    _select(view, view.llmServiceCard, LLMServiceEnum.OPENAI)
    assert view.openai_api_key_card.isVisibleTo(view)
    assert view.openaiOfficialApiCard.isVisibleTo(view)
    assert not view.lm_studio_api_key_card.isVisibleTo(view)


def test_translator_switch_toggles_service_cards(view):
    _select(view, view.translatorServiceCard, TranslatorServiceEnum.DEEPLX)
    assert view.deeplxEndpointCard.isVisibleTo(view)
    assert not view.needReflectTranslateCard.isVisibleTo(view)
    assert not view.batchSizeCard.isVisibleTo(view)

    _select(view, view.translatorServiceCard, TranslatorServiceEnum.OPENAI)
    assert not view.deeplxEndpointCard.isVisibleTo(view)
    assert view.needReflectTranslateCard.isVisibleTo(view)
    assert view.batchSizeCard.isVisibleTo(view)

    _select(view, view.translatorServiceCard, TranslatorServiceEnum.BING)
    assert not view.deeplxEndpointCard.isVisibleTo(view)
    assert not view.needReflectTranslateCard.isVisibleTo(view)


def test_transcribe_model_switch_toggles_whisper_cards(view):
    _select(view, view.transcribeModelCard, TranscribeModelEnum.WHISPER_API)
    assert view.whisperApiKeyCard.isVisibleTo(view)
    assert view.checkWhisperConnectionCard.isVisibleTo(view)
    assert not view.fasterWhisperManagerCard.isVisibleTo(view)

    _select(view, view.transcribeModelCard, TranscribeModelEnum.FASTER_WHISPER)
    assert view.fasterWhisperManagerCard.isVisibleTo(view)
    assert not view.whisperApiKeyCard.isVisibleTo(view)

    _select(view, view.transcribeModelCard, TranscribeModelEnum.BIJIAN)
    assert not view.fasterWhisperManagerCard.isVisibleTo(view)
    assert not view.whisperApiBaseCard.isVisibleTo(view)


def test_whisper_check_warns_before_starting_a_thread(view, monkeypatch):
    started = []
    monkeypatch.setattr(
        "videocaptioner.ui.view.setting_interface.WhisperConnectionThread",
        lambda *args: started.append(args) or _NeverStarts(),
    )
    view.whisperApiBaseCard.lineEdit.setText("")
    view.whisperApiKeyCard.lineEdit.setText("key")
    view.whisperApiModelCard.comboBox.setCurrentText("whisper-1")
    view.checkWhisperConnection()
    assert started == []
    assert view.checkWhisperConnectionCard.button.isEnabled()


class _NeverStarts:
    def start(self):
        raise AssertionError("thread must not start with missing fields")

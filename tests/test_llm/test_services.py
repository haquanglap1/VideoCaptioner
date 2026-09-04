"""LLM provider presets shared by the settings page and the CLI."""

import pytest

from videocaptioner.core.entities import (
    LLMServiceEnum,
    TranslatorServiceEnum,
    enum_from_display,
)
from videocaptioner.core.llm import services


def test_every_service_has_a_preset_with_unique_keys():
    assert set(services.LLM_SERVICE_PRESETS) == set(LLMServiceEnum)
    prefixes = [p.settings_prefix for p in services.LLM_SERVICE_PRESETS.values()]
    attrs = [p.config_attr for p in services.LLM_SERVICE_PRESETS.values()]
    assert len(set(prefixes)) == len(prefixes)
    assert len(set(attrs)) == len(attrs)
    for preset in services.LLM_SERVICE_PRESETS.values():
        assert preset.default_base.startswith("http")
        assert preset.default_models


def test_settings_prefix_lookup_matches_cli_mapping():
    from videocaptioner.cli.config import GUI_LLM_SERVICE_PREFIX

    assert services.settings_prefix_for("LM Studio") == "LmStudio"
    assert services.settings_prefix_for("OpenAI 兼容") == "OpenAI"
    assert services.settings_prefix_for("nope") is None
    assert services.settings_prefix_for(None) is None
    assert GUI_LLM_SERVICE_PREFIX == {
        service.value: preset.settings_prefix
        for service, preset in services.LLM_SERVICE_PRESETS.items()
    }


def test_only_local_and_compatible_providers_can_edit_base_url():
    editable = {
        service
        for service, preset in services.LLM_SERVICE_PRESETS.items()
        if preset.base_url_editable
    }
    assert editable == {
        LLMServiceEnum.OPENAI,
        LLMServiceEnum.OLLAMA,
        LLMServiceEnum.LM_STUDIO,
    }


def test_fill_default_api_key_only_touches_blank_local_keys():
    assert services.fill_default_api_key(LLMServiceEnum.OLLAMA, "") == "ollama"
    assert services.fill_default_api_key(LLMServiceEnum.OLLAMA, "   ") == "ollama"
    assert services.fill_default_api_key(LLMServiceEnum.LM_STUDIO, "") == "lm-studio"
    assert services.fill_default_api_key(LLMServiceEnum.OLLAMA, "mine") == "mine"
    assert services.fill_default_api_key(LLMServiceEnum.OPENAI, "") == ""
    assert services.fill_default_api_key(LLMServiceEnum.DEEPSEEK, "sk-x") == "sk-x"


def test_missing_whisper_api_fields_reports_in_page_order():
    assert services.missing_whisper_api_fields("", "", "") == ["base_url", "api_key", "model"]
    assert services.missing_whisper_api_fields("https://x", " ", "whisper-1") == ["api_key"]
    assert services.missing_whisper_api_fields("https://x", "k", "whisper-1") == []


def test_enum_from_display_accepts_raw_and_translated_text():
    translations = {"DeepLx 翻译": "Dịch DeepLx"}
    tr = lambda value: translations.get(value, value)  # noqa: E731
    assert enum_from_display(TranslatorServiceEnum, "DeepLx 翻译", tr) is TranslatorServiceEnum.DEEPLX
    assert enum_from_display(TranslatorServiceEnum, "Dịch DeepLx", tr) is TranslatorServiceEnum.DEEPLX
    assert enum_from_display(LLMServiceEnum, "Ollama") is LLMServiceEnum.OLLAMA
    with pytest.raises(ValueError):
        enum_from_display(LLMServiceEnum, "Dịch DeepLx", tr)

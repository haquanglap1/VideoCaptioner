"""LLM provider presets shared by the settings page and the CLI config layer.

The GUI persists one key/base/model triple per provider under
``LLM.<prefix>_API_Key`` / ``_API_Base`` / ``_Model`` in ``settings.json`` and
the CLI mirrors the selected provider's triple into its own config. Keeping
the table here means neither side hard-codes provider knowledge, and the
settings view only maps presets onto cards.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from videocaptioner.core.entities import LLMServiceEnum


@dataclass(frozen=True)
class LLMServicePreset:
    """Static knowledge about one OpenAI-compatible provider."""

    settings_prefix: str
    """Prefix of the ``LLM.<prefix>_*`` keys in ``settings.json``."""
    config_attr: str
    """Prefix of the ``cfg.<attr>_api_key`` / ``_api_base`` / ``_model`` items."""
    default_base: str
    default_models: Tuple[str, ...]
    base_url_editable: bool = False
    """Hosted providers have one endpoint; local/compatible ones can be edited."""
    default_api_key: str = ""
    """Local servers accept any token; filled in when the field is blank."""
    key_placeholder: str = "sk-"


LLM_SERVICE_PRESETS: Dict[LLMServiceEnum, LLMServicePreset] = {
    LLMServiceEnum.OPENAI: LLMServicePreset(
        settings_prefix="OpenAI",
        config_attr="openai",
        default_base="https://api.openai.com/v1",
        default_models=(
            "gemini-2.5-pro",
            "gpt-5",
            "claude-sonnet-4-5-20250929",
            "gemini-2.5-flash",
            "claude-haiku-4-5-20251001",
        ),
        base_url_editable=True,
    ),
    LLMServiceEnum.SILICON_CLOUD: LLMServicePreset(
        settings_prefix="SiliconCloud",
        config_attr="silicon_cloud",
        default_base="https://api.siliconflow.cn/v1",
        default_models=("moonshotai/Kimi-K2-Instruct-0905", "deepseek-ai/DeepSeek-V3"),
    ),
    LLMServiceEnum.DEEPSEEK: LLMServicePreset(
        settings_prefix="DeepSeek",
        config_attr="deepseek",
        default_base="https://api.deepseek.com/v1",
        default_models=("deepseek-chat", "deepseek-reasoner"),
    ),
    LLMServiceEnum.OLLAMA: LLMServicePreset(
        settings_prefix="Ollama",
        config_attr="ollama",
        default_base="http://localhost:11434/v1",
        default_models=("qwen3:8b",),
        base_url_editable=True,
        default_api_key="ollama",
        key_placeholder="",
    ),
    LLMServiceEnum.LM_STUDIO: LLMServicePreset(
        settings_prefix="LmStudio",
        config_attr="lm_studio",
        default_base="http://localhost:1234/v1",
        default_models=("qwen3:8b",),
        base_url_editable=True,
        default_api_key="lm-studio",
    ),
    LLMServiceEnum.GEMINI: LLMServicePreset(
        settings_prefix="Gemini",
        config_attr="gemini",
        default_base="https://generativelanguage.googleapis.com/v1beta/openai/",
        default_models=("gemini-2.5-pro", "gemini-2.5-flash", "gemini-2.0-flash-lite"),
    ),
    LLMServiceEnum.CHATGLM: LLMServicePreset(
        settings_prefix="ChatGLM",
        config_attr="chatglm",
        default_base="https://open.bigmodel.cn/api/paas/v4",
        default_models=("glm-4-plus", "glm-4-air-250414", "glm-4-flash"),
    ),
}


def llm_service_preset(service: LLMServiceEnum) -> LLMServicePreset:
    return LLM_SERVICE_PRESETS[service]


def settings_prefix_for(service_value: Optional[str]) -> Optional[str]:
    """``LLM.LLMService`` value from ``settings.json`` -> per-service key prefix."""
    for service, preset in LLM_SERVICE_PRESETS.items():
        if service.value == service_value:
            return preset.settings_prefix
    return None


def fill_default_api_key(service: LLMServiceEnum, current: str) -> str:
    """Keep a typed key; otherwise the provider's placeholder token, if any."""
    if (current or "").strip():
        return current
    return LLM_SERVICE_PRESETS[service].default_api_key


WHISPER_API_FIELDS: Tuple[str, ...] = ("base_url", "api_key", "model")


def missing_whisper_api_fields(base_url: str, api_key: str, model: str) -> List[str]:
    """Names of the blank Whisper API fields, in the order the page reports them."""
    values = dict(zip(WHISPER_API_FIELDS, (base_url, api_key, model)))
    return [name for name in WHISPER_API_FIELDS if not (values[name] or "").strip()]

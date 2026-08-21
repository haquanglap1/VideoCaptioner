"""Public translation API with provider modules loaded on demand."""

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from videocaptioner.core.entities import SubtitleProcessData as SubtitleProcessData

    from .base import BaseTranslator as BaseTranslator
    from .bing_translator import BingTranslator as BingTranslator
    from .deeplx_translator import DeepLXTranslator as DeepLXTranslator
    from .factory import TranslatorFactory as TranslatorFactory
    from .google_translator import GoogleTranslator as GoogleTranslator
    from .llm_translator import LLMTranslator as LLMTranslator
    from .types import TargetLanguage as TargetLanguage
    from .types import TranslatorType as TranslatorType

_EXPORTS = {
    "SubtitleProcessData": ("videocaptioner.core.entities", "SubtitleProcessData"),
    "BaseTranslator": (".base", "BaseTranslator"),
    "BingTranslator": (".bing_translator", "BingTranslator"),
    "DeepLXTranslator": (".deeplx_translator", "DeepLXTranslator"),
    "GoogleTranslator": (".google_translator", "GoogleTranslator"),
    "LLMTranslator": (".llm_translator", "LLMTranslator"),
    "TranslatorFactory": (".factory", "TranslatorFactory"),
    "TargetLanguage": (".types", "TargetLanguage"),
    "TranslatorType": (".types", "TranslatorType"),
}

__all__ = [
    "SubtitleProcessData",
    "BaseTranslator",
    "BingTranslator",
    "DeepLXTranslator",
    "GoogleTranslator",
    "LLMTranslator",
    "TranslatorFactory",
    "TargetLanguage",
    "TranslatorType",
]


def __getattr__(name: str) -> Any:
    try:
        module_name, attribute = _EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from exc
    value = getattr(import_module(module_name, __name__), attribute)
    globals()[name] = value
    return value

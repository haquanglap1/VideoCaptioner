"""Public LLM API without importing the OpenAI SDK during GUI startup."""

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .check_llm import check_llm_connection as check_llm_connection
    from .check_llm import get_available_models as get_available_models
    from .check_whisper import check_whisper_connection as check_whisper_connection
    from .client import LLMCredentials as LLMCredentials
    from .client import call_llm as call_llm
    from .client import configure_llm_client as configure_llm_client
    from .client import get_llm_client as get_llm_client
    from .client import get_llm_credentials as get_llm_credentials
    from .client import reset_llm_client as reset_llm_client

_EXPORTS = {
    "LLMCredentials": (".client", "LLMCredentials"),
    "call_llm": (".client", "call_llm"),
    "configure_llm_client": (".client", "configure_llm_client"),
    "get_llm_client": (".client", "get_llm_client"),
    "get_llm_credentials": (".client", "get_llm_credentials"),
    "reset_llm_client": (".client", "reset_llm_client"),
    "check_llm_connection": (".check_llm", "check_llm_connection"),
    "get_available_models": (".check_llm", "get_available_models"),
    "check_whisper_connection": (".check_whisper", "check_whisper_connection"),
}

__all__ = [
    "LLMCredentials",
    "call_llm",
    "configure_llm_client",
    "get_llm_client",
    "get_llm_credentials",
    "reset_llm_client",
    "check_llm_connection",
    "get_available_models",
    "check_whisper_connection",
]


def __getattr__(name: str) -> Any:
    if name == "request_logger":
        value = import_module(".request_logger", __name__)
        globals()[name] = value
        return value
    try:
        module_name, attribute = _EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from exc
    value = getattr(import_module(module_name, __name__), attribute)
    globals()[name] = value
    return value

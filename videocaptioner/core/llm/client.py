"""Unified LLM client for the application."""

import os
import threading
from dataclasses import dataclass, field
from typing import Any, List, Optional
from urllib.parse import urlparse, urlunparse

import openai
from openai import OpenAI
from tenacity import (
    RetryCallState,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_random_exponential,
)

from videocaptioner.core.utils.cache import get_llm_cache, memoize
from videocaptioner.core.utils.logger import setup_logger

from .request_logger import create_logging_http_client, log_llm_response

_global_client: Optional[OpenAI] = None
_client_credentials: Optional["LLMCredentials"] = None
_configured_credentials: Optional["LLMCredentials"] = None
_client_lock = threading.Lock()

logger = setup_logger("llm_client")


def normalize_base_url(base_url: str) -> str:
    """Normalize API base URL by ensuring /v1 suffix when needed."""
    url = base_url.strip()
    parsed = urlparse(url)
    path = parsed.path.rstrip("/")

    if not path:
        path = "/v1"

    normalized = urlunparse(
        (
            parsed.scheme,
            parsed.netloc,
            path,
            parsed.params,
            parsed.query,
            parsed.fragment,
        )
    )

    return normalized


@dataclass(frozen=True)
class LLMCredentials:
    """Credentials for an OpenAI-compatible endpoint.

    Passed around explicitly instead of through ``os.environ`` so an API key
    never leaks into child processes (FFmpeg, whisper, the VieNeu sidecar).
    """

    api_key: str = field(repr=False)
    base_url: str = ""

    def __post_init__(self) -> None:
        api_key = (self.api_key or "").strip()
        base_url = (self.base_url or "").strip()
        object.__setattr__(self, "api_key", api_key)
        object.__setattr__(
            self, "base_url", normalize_base_url(base_url) if base_url else ""
        )

    @property
    def is_complete(self) -> bool:
        return bool(self.api_key and self.base_url)

    @classmethod
    def from_environment(cls) -> "LLMCredentials":
        """Read-only fallback for shells that export ``OPENAI_*``; nothing is written back."""
        return cls(
            api_key=os.getenv("OPENAI_API_KEY", ""),
            base_url=os.getenv("OPENAI_BASE_URL", ""),
        )


def configure_llm_client(credentials: Optional[LLMCredentials]) -> None:
    """Set the credentials ``get_llm_client()`` uses when none are passed.

    ``None`` clears them, leaving only the ``OPENAI_*`` environment fallback.
    The cached client is rebuilt lazily on the next call.
    """
    global _configured_credentials
    with _client_lock:
        _configured_credentials = credentials


def get_llm_credentials() -> LLMCredentials:
    """Configured credentials, else the read-only ``OPENAI_*`` environment fallback."""
    with _client_lock:
        configured = _configured_credentials
    if configured is not None and configured.is_complete:
        return configured
    return LLMCredentials.from_environment()


def reset_llm_client() -> None:
    """Force the next get_llm_client() to build a fresh OpenAI client.

    Call this when LLM credentials are updated by the user so that the
    singleton does not keep serving requests with stale auth.
    """
    global _global_client, _client_credentials
    with _client_lock:
        _global_client = None
        _client_credentials = None


def get_llm_client(credentials: Optional[LLMCredentials] = None) -> OpenAI:
    """Get the shared LLM client (thread-safe, credential-aware).

    ``credentials`` overrides the configured ones for this call. The client is
    rebuilt whenever the effective credentials change, so updates from the UI
    take effect without restarting the app.
    """
    global _global_client, _client_credentials

    current = credentials if credentials is not None else get_llm_credentials()
    if not current.is_complete:
        raise ValueError(
            "LLM credentials are not configured: set the API key and base URL "
            "in settings, or export OPENAI_BASE_URL and OPENAI_API_KEY"
        )

    with _client_lock:
        if _global_client is None or _client_credentials != current:
            if _global_client is not None:
                logger.info("LLM credentials changed, rebuilding OpenAI client")
            _global_client = OpenAI(
                base_url=current.base_url,
                api_key=current.api_key,
                http_client=create_logging_http_client(),
            )
            _client_credentials = current

    return _global_client


def before_sleep_log(retry_state: RetryCallState) -> None:
    logger.warning(
        "Rate Limit Error, sleeping and retrying... Please lower your thread concurrency or use better OpenAI API."
    )


@retry(
    stop=stop_after_attempt(10),
    wait=wait_random_exponential(multiplier=1, min=5, max=60),
    retry=retry_if_exception_type(openai.RateLimitError),
    before_sleep=before_sleep_log,
)
def _call_llm_api(
    messages: List[dict],
    model: str,
    temperature: float = 1,
    **kwargs: Any,
) -> Any:
    """实际调用 LLM API（带重试）"""
    client = get_llm_client()

    response = client.chat.completions.create(
        model=model,
        messages=messages,  # pyright: ignore[reportArgumentType]
        temperature=temperature,
        **kwargs,
    )

    # 记录响应内容
    log_llm_response(response)

    return response


@memoize(get_llm_cache(), expire=3600, typed=True)
def call_llm(
    messages: List[dict],
    model: str,
    temperature: float = 1,
    **kwargs: Any,
) -> Any:
    """Call LLM API with automatic caching."""
    response = _call_llm_api(messages, model, temperature, **kwargs)

    if not (
        response
        and hasattr(response, "choices")
        and response.choices
        and len(response.choices) > 0
        and hasattr(response.choices[0], "message")
        and response.choices[0].message.content
    ):
        raise ValueError("Invalid OpenAI API response: empty choices or content")

    return response

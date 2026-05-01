"""Unified LLM client for the application."""

import os
import threading
from typing import Any, List, Optional, Tuple
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
_client_credentials: Optional[Tuple[str, str]] = None
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


def reset_llm_client() -> None:
    """Force the next get_llm_client() to build a fresh OpenAI client.

    Call this when LLM credentials are updated by the user so that the
    singleton does not keep serving requests with stale auth.
    """
    global _global_client, _client_credentials
    with _client_lock:
        _global_client = None
        _client_credentials = None


def get_llm_client() -> OpenAI:
    """Get global LLM client instance (thread-safe, credential-aware).

    The client is rebuilt automatically when OPENAI_BASE_URL or
    OPENAI_API_KEY change between calls, so updates from the UI take effect
    without restarting the app.
    """
    global _global_client, _client_credentials

    base_url = normalize_base_url(os.getenv("OPENAI_BASE_URL", "").strip())
    api_key = os.getenv("OPENAI_API_KEY", "").strip()

    if not base_url or not api_key:
        raise ValueError(
            "OPENAI_BASE_URL and OPENAI_API_KEY environment variables must be set"
        )

    current = (base_url, api_key)

    with _client_lock:
        if _global_client is None or _client_credentials != current:
            if _global_client is not None:
                logger.info("LLM credentials changed, rebuilding OpenAI client")
            _global_client = OpenAI(
                base_url=base_url,
                api_key=api_key,
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

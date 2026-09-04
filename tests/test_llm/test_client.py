"""Tests for explicit LLM credentials: no os.environ writes, env is read-only."""

import os

import pytest

from videocaptioner.core.llm.client import (
    LLMCredentials,
    configure_llm_client,
    get_llm_client,
    get_llm_credentials,
    reset_llm_client,
)


@pytest.fixture(autouse=True)
def _clean_credential_state(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    configure_llm_client(None)
    reset_llm_client()
    yield
    configure_llm_client(None)
    reset_llm_client()


def test_credentials_are_normalised_and_key_is_hidden_from_repr():
    creds = LLMCredentials(api_key="  sk-secret  ", base_url=" https://api.example.com/ ")
    assert creds.api_key == "sk-secret"
    assert creds.base_url == "https://api.example.com/v1"
    assert creds.is_complete
    assert "sk-secret" not in repr(creds)


def test_blank_credentials_are_incomplete():
    assert not LLMCredentials(api_key="", base_url="https://x.invalid/v1").is_complete
    assert not LLMCredentials(api_key="k", base_url="   ").is_complete


def test_missing_credentials_raise_and_leave_environ_untouched():
    with pytest.raises(ValueError, match="not configured"):
        get_llm_client()
    assert "OPENAI_API_KEY" not in os.environ
    assert "OPENAI_BASE_URL" not in os.environ


def test_environment_is_a_read_only_fallback(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "env-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://env.invalid")
    assert get_llm_credentials() == LLMCredentials("env-key", "https://env.invalid/v1")
    client = get_llm_client()
    assert client.api_key == "env-key"
    assert str(client.base_url).startswith("https://env.invalid/v1")


def test_configured_credentials_win_over_environment(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "env-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://env.invalid/v1")
    configure_llm_client(LLMCredentials("cfg-key", "https://cfg.invalid/v1"))
    assert get_llm_credentials().api_key == "cfg-key"
    assert get_llm_client().api_key == "cfg-key"
    # Registering credentials never exports them.
    assert os.environ["OPENAI_API_KEY"] == "env-key"


def test_incomplete_configured_credentials_fall_back_to_environment(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "env-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://env.invalid/v1")
    configure_llm_client(LLMCredentials("only-key", ""))
    assert get_llm_credentials().api_key == "env-key"


def test_explicit_credentials_override_per_call_and_rebuild_the_client():
    configure_llm_client(LLMCredentials("a-key", "https://a.invalid/v1"))
    first = get_llm_client()
    assert get_llm_client() is first

    override = get_llm_client(LLMCredentials("b-key", "https://b.invalid/v1"))
    assert override is not first
    assert override.api_key == "b-key"

    # The next default call sees the configured credentials again.
    assert get_llm_client().api_key == "a-key"
    assert "OPENAI_API_KEY" not in os.environ


def test_configure_none_clears_credentials():
    configure_llm_client(LLMCredentials("a-key", "https://a.invalid/v1"))
    configure_llm_client(None)
    with pytest.raises(ValueError):
        get_llm_client()

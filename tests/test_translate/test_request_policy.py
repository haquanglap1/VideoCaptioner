"""Finite owned HTTP requests, stable job settings, and compact context payloads."""

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, fields
from threading import Event

import httpx
import openai
import pytest

from videocaptioner.cli.config import build_config, save_config_value
from videocaptioner.cli.main import main
from videocaptioner.core.asr.asr_data import ASRData, ASRDataSeg
from videocaptioner.core.entities import SubtitleConfig
from videocaptioner.core.llm.client import LLMCredentials, configure_llm_client
from videocaptioner.core.llm.context import get_task_context, set_task_context, submit_with_context
from videocaptioner.core.llm.owned_request import OwnedLLMRequest
from videocaptioner.core.llm.request_policy import validate_request_timeout
from videocaptioner.core.translate.conversation import (
    ConversationContext,
    CueAssignment,
    Evidence,
    Scope,
)
from videocaptioner.core.translate.llm_translator import LLMTranslator
from videocaptioner.core.translate.types import TargetLanguage


@pytest.mark.parametrize("value", [0, 601, -1, True, 2.5, float("nan"), float("inf"), "unlimited", "1.1", None])
def test_timeout_validation_rejects_unbounded_or_ambiguous_values(value):
    with pytest.raises(ValueError, match="1 to 600"):
        validate_request_timeout(value)
    with pytest.raises(ValueError):
        SubtitleConfig(llm_request_timeout=value)


def test_timeout_defaults_config_and_cli_validation(tmp_path, monkeypatch):
    assert SubtitleConfig().llm_request_timeout == 120
    config_file = tmp_path / "config.toml"
    save_config_value("llm.request_timeout", "300", config_file)
    assert build_config(config_path=config_file)["llm"]["request_timeout"] == 300
    monkeypatch.setenv("VIDEOCAPTIONER_LLM_REQUEST_TIMEOUT", "400")
    assert validate_request_timeout(build_config(config_path=config_file)["llm"]["request_timeout"]) == 400
    assert build_config({"llm": {"request_timeout": 250}}, config_file)["llm"]["request_timeout"] == 250
    with pytest.raises(ValueError):
        save_config_value("llm.request_timeout", "0", config_file)
    source = tmp_path / "input.srt"
    source.write_text("1\n00:00:00,000 --> 00:00:01,000\nSynthetic\n", encoding="utf-8")
    assert main(["subtitle", str(source), "--no-optimize", "--no-split", "--llm-timeout", "0"]) == 2


def wire_client(monkeypatch, handler):
    actual = openai.AsyncOpenAI
    observed = []
    closed = Event()

    class Transport(httpx.MockTransport):
        async def aclose(self):
            closed.set()
            await super().aclose()

    class Client(actual):
        def __init__(self, **kwargs):
            observed.append((kwargs["timeout"], kwargs["api_key"], kwargs["base_url"], kwargs["max_retries"]))
            # The production client remains real; only the transport is replaced.
            kwargs["http_client"] = httpx.AsyncClient(transport=Transport(handler))
            super().__init__(**kwargs)
    monkeypatch.setattr(openai, "AsyncOpenAI", Client)
    return observed, closed


def response():
    return httpx.Response(200, json={"id": "test", "model": "gpt-5.6-terra", "object": "chat.completion",
                                   "created": 0, "choices": [{"index": 0, "finish_reason": "stop",
                                   "message": {"role": "assistant", "content": '{"1":"Test"}'}}]})


def test_translation_snapshots_credentials_timeout_and_model_before_start(monkeypatch, tmp_path):
    from diskcache import Cache

    cache = Cache(str(tmp_path / "cache"))
    monkeypatch.setattr("videocaptioner.core.translate.base.get_translate_cache", lambda: cache)
    configure_llm_client(LLMCredentials("first", "https://first.invalid/v1"))
    engine = LLMTranslator(1, 10, TargetLanguage.VIETNAMESE, "gpt-5.6-terra", "", False, None, request_timeout=300)
    configure_llm_client(LLMCredentials("second", "https://second.invalid/v1"))
    requests = []
    async def handler(request):
        requests.append(json.loads(request.content))
        return response()
    observed, closed = wire_client(monkeypatch, handler)
    try:
        engine.translate_subtitle(ASRData([ASRDataSeg("合成。", 0, 1000)]))
        assert observed == [(300, "first", "https://first.invalid/v1", 0)]
        assert requests[0]["model"] == "gpt-5.6-terra" and closed.is_set()
    finally:
        engine.close()
        cache.close()
        configure_llm_client(None)


@pytest.mark.parametrize("late_result", [False, True])
def test_cancel_closes_socket_joins_late_response_and_keeps_context(monkeypatch, late_result):
    entered, cancelled, stopped = Event(), Event(), Event()
    contexts = []
    async def handler(request):
        contexts.append(get_task_context())
        entered.set()
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            if late_result:
                return response()
            raise
        finally:
            stopped.set()
    observed, closed = wire_client(monkeypatch, handler)
    call = OwnedLLMRequest(LLMCredentials("test", "https://test.invalid/v1"), 300, cancelled.is_set)
    set_task_context("review-job", "", "translate")
    with ThreadPoolExecutor(1) as pool:
        future = submit_with_context(pool, call, [{"role": "user", "content": "合成"}], "gpt-5.6-terra")
        assert entered.wait(3)
        cancelled.set()
        with pytest.raises(RuntimeError, match="cancelled"):
            future.result(3)
    assert stopped.is_set() and closed.is_set() and len(observed) == 1
    assert contexts[0].task_id == "review-job"


def test_deadline_cancels_and_does_not_retry_post(monkeypatch):
    cancelled = Event()
    async def handler(request):
        try:
            await asyncio.sleep(60)
        finally:
            cancelled.set()
    observed, closed = wire_client(monkeypatch, handler)
    call = OwnedLLMRequest(LLMCredentials("test", "https://test.invalid/v1"), 1)
    with pytest.raises(RuntimeError, match="timed out"):
        call([], "gpt-5.6-terra")
    assert cancelled.is_set() and closed.is_set() and len(observed) == 1


@pytest.mark.parametrize("status", [401, 429, 500])
def test_http_error_has_no_body_or_retry(monkeypatch, status):
    observed, closed = wire_client(monkeypatch, lambda request: httpx.Response(status, json={"error": "private-body"}))
    with pytest.raises(RuntimeError) as caught:
        OwnedLLMRequest(LLMCredentials("secret", "https://test.invalid/v1"), 300)([], "gpt-5.6-terra")
    assert str(status) in str(caught.value) and "private-body" not in str(caught.value)
    assert "secret" not in str(caught.value) and len(observed) == 1 and closed.is_set()


def test_compact_payload_retains_windows_without_repeated_unknown_reviews():
    data = ASRData([ASRDataSeg("他说明天再来。", i * 1000, i * 1000 + 900, cue_id=f"c{i}") for i in range(30)])
    data.conversation_context = ConversationContext(assignments=tuple(
        CueAssignment(f"a{i}", Scope(cue_ids=(f"c{i}",)), evidence=Evidence("text", "proposed", (f"c{i}",)))
        for i in range(30)))
    snapshot = data.context_snapshot()
    selected = tuple(c.id for c in snapshot.cues)
    old = {"policy": "conversation-context-v1", "characters": [],
           "selected": [asdict(c) for c in snapshot.resolved],
           "source_window": [asdict(c) for c in snapshot.cues], "review": snapshot.review}
    new = snapshot.request_data(selected)
    def encode(value):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()
    assert len(encode(new)) < len(encode(old)) * .55
    assert [c["id"] for c in new["source_window"]] == list(selected)
    short = snapshot.request_data(("c15",))
    assert {c["id"] for c in short["source_window"]} == {f"c{i}" for i in range(11, 20)}
    assert "Unknown addressee" not in json.dumps(new)
    assert set(short["selected"][0]) == {"id"}
    assert not any(item.evidence.status == "confirmed" for f in fields(data.conversation_context)
                   for item in getattr(data.conversation_context, f.name))

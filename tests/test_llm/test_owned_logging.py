"""Owned async transports must produce correctly paired terminal journal entries."""

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import httpx
import pytest

from tests.test_translate.test_request_policy import wire_client
from videocaptioner.core.llm import request_logger
from videocaptioner.core.llm.client import LLMCredentials
from videocaptioner.core.llm.context import (
    clear_task_context,
    set_task_context,
    submit_with_context,
)
from videocaptioner.core.llm.log_summary import log_outcome, log_usage
from videocaptioner.core.llm.owned_request import OwnedLLMRequest


def response(marker="reply", usage=True):
    payload = {"id": "fixture", "object": "chat.completion", "created": 1, "model": "synthetic-model",
               "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": marker}}],
               "usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120,
                         "prompt_tokens_details": {"cached_tokens": 60},
                         "completion_tokens_details": {"reasoning_tokens": 5}} if usage else None}
    return httpx.Response(200, json=payload)


@pytest.fixture
def entries(monkeypatch):
    result = []
    monkeypatch.setattr(request_logger, "_write_log", result.append)
    yield result
    clear_task_context()


def test_owned_success_logs_request_response_usage_and_safe_endpoint(monkeypatch, entries):
    wire_client(monkeypatch, lambda _: response("reply synthetic-key"))
    set_task_context("job-1", "folder/fixture.mp4", "translate")
    call = OwnedLLMRequest(LLMCredentials("synthetic-key", "https://test.invalid/v1?private=query"), 30)
    call([{"role": "user", "content": "fixture"}], "synthetic-model", max_completion_tokens=1000)
    assert len(entries) == 1
    entry = entries[0]
    assert entry["task_id"] == "job-1" and entry["file_name"] == "fixture.mp4" and entry["stage"] == "translate"
    assert entry["status"] == 200 and entry["outcome"] == "success"
    assert entry["request"]["messages"][0]["content"] == "fixture"
    assert entry["response"]["choices"][0]["message"]["content"] == "reply [redacted]"
    assert entry["url"] == "https://test.invalid/v1/chat/completions"
    assert "synthetic-key" not in json.dumps(entry) and "private=query" not in json.dumps(entry)
    usage = log_usage(entry)
    assert (usage.prompt, usage.completion, usage.total, usage.cached, usage.reasoning) == (100, 20, 120, 60, 5)


def test_private_vision_log_keeps_usage_but_not_text_or_image(monkeypatch, entries):
    wire_client(monkeypatch, lambda _: response("PRIVATE_RESPONSE"))
    messages = [{"role": "user", "content": [{"type": "text", "text": "PRIVATE_PROMPT"},
                 {"type": "image_url", "image_url": {"url": "data:image/png;base64,PRIVATE_IMAGE"}}]}]
    OwnedLLMRequest(LLMCredentials("synthetic-key", "https://test.invalid/v1"), log_content=False)(messages, "synthetic-model")
    assert len(entries) == 1 and "PRIVATE" not in json.dumps(entries)
    assert entries[0]["request"]["messages"][0]["images"] == 1
    assert entries[0]["response"]["usage"]["total_tokens"] == 120
    assert not entries[0]["content_logged"]


@pytest.mark.parametrize("status", [401, 429, 500])
def test_http_failure_is_logged_once_without_body_or_fake_zero(monkeypatch, entries, status):
    observed, _ = wire_client(monkeypatch, lambda _: httpx.Response(status, json={"error": "PRIVATE_ERROR"}))
    with pytest.raises(RuntimeError):
        OwnedLLMRequest(LLMCredentials("synthetic-key", "https://test.invalid/v1"))([], "synthetic-model")
    assert len(observed) == len(entries) == 1
    assert entries[0]["outcome"] == "http_error" and entries[0]["status"] == status
    assert "PRIVATE_ERROR" not in json.dumps(entries) and log_usage(entries[0]).total is None


def test_timeout_is_logged_without_retry(monkeypatch, entries):
    async def handler(_):
        await asyncio.sleep(30)
        return response()
    observed, closed = wire_client(monkeypatch, handler)
    with pytest.raises(RuntimeError, match="timed out"):
        OwnedLLMRequest(LLMCredentials("synthetic-key", "https://test.invalid/v1"), 1)([], "synthetic-model")
    assert len(observed) == len(entries) == 1 and closed.is_set()
    assert entries[0]["outcome"] == "timeout" and log_usage(entries[0]).total is None


def test_cancelled_request_keeps_context_and_logs_one_terminal_event(monkeypatch, entries):
    entered, cancelled = Event(), Event()
    async def handler(_):
        entered.set()
        await asyncio.sleep(30)
        return response()
    observed, closed = wire_client(monkeypatch, handler)
    set_task_context("cancel-job", "", "ocr-vision")
    call = OwnedLLMRequest(LLMCredentials("synthetic-key", "https://test.invalid/v1"), 30, cancelled.is_set, False)
    with ThreadPoolExecutor(1) as pool:
        future = submit_with_context(pool, call, [], "synthetic-model")
        assert entered.wait(3)
        cancelled.set()
        with pytest.raises(RuntimeError, match="cancelled"):
            future.result(3)
    assert len(observed) == len(entries) == 1 and closed.is_set()
    assert entries[0]["outcome"] == "cancelled" and entries[0]["task_id"] == "cancel-job"


def test_concurrent_owned_calls_pair_context_and_reply(monkeypatch, entries):
    async def handler(request):
        marker = json.loads(request.content)["messages"][0]["content"]
        await asyncio.sleep(.02)
        return response(marker + "-reply")
    wire_client(monkeypatch, handler)
    def run(marker):
        set_task_context(marker, "", "translate")
        return OwnedLLMRequest(LLMCredentials("synthetic-key", "https://test.invalid/v1"))(
            [{"role": "user", "content": marker}], "synthetic-model")
    with ThreadPoolExecutor(3) as pool:
        list(pool.map(run, ("one", "two", "three")))
    assert len(entries) == 3
    for entry in entries:
        assert entry["request"]["messages"][0]["content"] == entry["task_id"]
        assert entry["response"]["choices"][0]["message"]["content"] == entry["task_id"] + "-reply"


def test_missing_usage_is_not_zero_and_legacy_logs_remain_readable():
    assert log_usage({"response": {"usage": None}}).total is None
    assert log_usage({"response": {"usage": {"prompt_tokens": 0}}}).total is None
    assert log_usage({"response": {"usage": {"prompt_tokens": 0, "completion_tokens": 0}}}).total == 0
    assert log_outcome({"status": 200}) == "success"
    assert log_outcome({"status": 429}) == "http_error"

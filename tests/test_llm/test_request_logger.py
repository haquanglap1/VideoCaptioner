"""Regression tests for request/response pairing in the LLM request logger."""

import json
import threading
from types import SimpleNamespace

import httpx
import pytest

from videocaptioner.core.llm import request_logger

CHAT_URL = "https://api.example.com/v1/chat/completions"


@pytest.fixture(autouse=True)
def clear_pending_slot():
    request_logger._current_request.set(None)
    yield
    request_logger._current_request.set(None)


def _chat_request(marker: str) -> httpx.Request:
    body = {"messages": [{"role": "user", "content": marker}]}
    return httpx.Request("POST", CHAT_URL, content=json.dumps(body).encode("utf-8"))


def _sdk_response(marker: str):
    return SimpleNamespace(model_dump=lambda: {"choices": [{"message": {"content": marker}}]})


def _marker(entry: dict) -> str:
    return entry["request"]["messages"][0]["content"]


def test_pairs_request_with_response_of_the_same_call(monkeypatch):
    entries = []
    monkeypatch.setattr(request_logger, "_write_log", entries.append)

    request = _chat_request("hello")
    request_logger._on_request(request)
    request_logger._on_response(httpx.Response(200, request=request))
    request_logger.log_llm_response(_sdk_response("hello-reply"))

    assert len(entries) == 1
    assert _marker(entries[0]) == "hello"
    assert entries[0]["response"]["choices"][0]["message"]["content"] == "hello-reply"
    assert entries[0]["status"] == 200

    # The slot is cleared, so a stray call cannot reuse the previous request.
    request_logger.log_llm_response(_sdk_response("orphan"))
    assert len(entries) == 1


def test_concurrent_threads_keep_their_own_request(monkeypatch):
    entries = []
    lock = threading.Lock()

    def capture(entry):
        with lock:
            entries.append(entry)

    monkeypatch.setattr(request_logger, "_write_log", capture)

    workers = 4
    # Every thread registers its request before any of them logs a response,
    # which is exactly the interleaving the old shared dict got wrong.
    barrier = threading.Barrier(workers)

    def worker(marker: str) -> None:
        request = _chat_request(marker)
        request_logger._on_request(request)
        barrier.wait()
        request_logger._on_response(httpx.Response(200, request=request))
        barrier.wait()
        request_logger.log_llm_response(_sdk_response(f"{marker}-reply"))

    threads = [threading.Thread(target=worker, args=(f"m{i}",)) for i in range(workers)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(entries) == workers
    for entry in entries:
        expected = f"{_marker(entry)}-reply"
        assert entry["response"]["choices"][0]["message"]["content"] == expected


def test_retry_keeps_only_the_last_attempt(monkeypatch):
    entries = []
    monkeypatch.setattr(request_logger, "_write_log", entries.append)

    first = _chat_request("attempt-1")
    request_logger._on_request(first)
    request_logger._on_response(httpx.Response(429, request=first))
    second = _chat_request("attempt-2")
    request_logger._on_request(second)
    request_logger._on_response(httpx.Response(200, request=second))
    request_logger.log_llm_response(_sdk_response("ok"))

    assert len(entries) == 1
    assert _marker(entries[0]) == "attempt-2"
    assert entries[0]["status"] == 200


def test_ignores_requests_that_are_not_chat_completions(monkeypatch):
    entries = []
    monkeypatch.setattr(request_logger, "_write_log", entries.append)

    request = httpx.Request("GET", "https://api.example.com/v1/models")
    request_logger._on_request(request)
    request_logger._on_response(httpx.Response(200, request=request))
    request_logger.log_llm_response(_sdk_response("x"))

    assert entries == []

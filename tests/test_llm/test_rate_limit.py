"""Recover known rejections without re-posting ambiguous network failures."""

import json
import time
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import httpx
import pytest

from tests.test_translate.test_request_policy import response, wire_client
from videocaptioner.core.asr.asr_data import ASRData, ASRDataSeg
from videocaptioner.core.llm import rate_limit, request_logger
from videocaptioner.core.llm.client import LLMCredentials
from videocaptioner.core.llm.owned_request import OwnedLLMRequest
from videocaptioner.core.llm.rate_limit import LLMRateLimitError, rate_limit_error
from videocaptioner.core.optimize.optimize import SubtitleOptimizer
from videocaptioner.core.split.split_by_llm import split_by_llm


@pytest.fixture(autouse=True)
def quick_backoff(monkeypatch):
    monkeypatch.setattr(rate_limit, "BACKOFF_SECONDS", .01)


def call():
    return OwnedLLMRequest(LLMCredentials("private-key", "https://fixture.invalid/v1"), 10)


def test_recovery_honors_retry_after_and_does_not_log_body(monkeypatch):
    attempts, entries = [], []
    def handler(_):
        attempts.append(time.monotonic())
        return (httpx.Response(429, headers={"retry-after": ".2"}, json={"error": {"message": "PRIVATE"}})
                if len(attempts) == 1 else response())
    wire_client(monkeypatch, handler)
    monkeypatch.setattr(request_logger, "_write_log", entries.append)
    assert call()([], "fixture").choices
    assert len(attempts) == 2 and attempts[1] - attempts[0] >= .2
    assert [e["status"] for e in entries] == [429, 200]
    assert "PRIVATE" not in json.dumps(entries)


def test_quota_is_terminal_for_entire_job_without_retry(monkeypatch):
    import traceback
    observed, _ = wire_client(monkeypatch, lambda _: httpx.Response(429,
        json={"error": {"code": "insufficient_quota", "message": "private-key PRIVATE"}}))
    job = call()
    for _ in range(2):
        with pytest.raises(LLMRateLimitError, match="hạn mức") as caught:
            job([], "fixture")
        assert caught.value.kind == "quota" and "PRIVATE" not in str(caught.value)
        assert "PRIVATE" not in "".join(traceback.format_exception(caught.value))
    assert len(observed) == 1


def test_parallel_rejections_do_not_retry_every_chunk(monkeypatch):
    observed, _ = wire_client(monkeypatch, lambda _: httpx.Response(429, json={"error": "busy"}))
    job = call()
    with ThreadPoolExecutor(10) as pool:
        futures = [pool.submit(job, [], "fixture") for _ in range(20)]
        for future in futures:
            with pytest.raises(LLMRateLimitError):
                future.result(5)
    assert 3 <= len(observed) <= 5


def test_cancelling_cooldown_does_not_send_retry(monkeypatch):
    entered, cancelled = Event(), Event()
    def handler(_):
        entered.set()
        return httpx.Response(429, headers={"retry-after": "5"}, json={"error": "busy"})
    observed, _ = wire_client(monkeypatch, handler)
    job = OwnedLLMRequest(call().credentials, 10, cancelled.is_set)
    with ThreadPoolExecutor(1) as pool:
        future = pool.submit(job, [], "fixture")
        assert entered.wait(2)
        cancelled.set()
        with pytest.raises(RuntimeError, match="cancelled"):
            future.result(2)
    assert len(observed) == 1


def test_admission_wait_does_not_consume_provider_timeout(monkeypatch):
    import asyncio
    entered = Event()
    async def handler(_):
        entered.set()
        await asyncio.sleep(.65)
        return response()
    observed, _ = wire_client(monkeypatch, handler)
    job = OwnedLLMRequest(call().credentials, 1)
    job._gate.limit = 1
    with ThreadPoolExecutor(2) as pool:
        first = pool.submit(job, [], "fixture")
        assert entered.wait(2)
        second = pool.submit(job, [], "fixture")
        assert first.result(3).choices
        assert second.result(3).choices
    assert len(observed) == 2


@pytest.mark.parametrize("header", ["nan", "inf", "-2", "bad date"])
def test_invalid_retry_after_is_bounded(header):
    from types import SimpleNamespace
    exc = RuntimeError()
    exc.response = SimpleNamespace(headers={"retry-after": header})
    assert rate_limit_error(exc).retry_after == 0


def test_split_and_optimizer_do_not_swallow_provider_rejection():
    def rejected(**_):
        raise LLMRateLimitError("quota")
    with pytest.raises(LLMRateLimitError):
        split_by_llm("synthetic text", request=rejected)
    optimizer = SubtitleOptimizer(2, 1, "fixture", "", request=rejected)
    try:
        with pytest.raises(LLMRateLimitError):
            optimizer.optimize_subtitle(ASRData([ASRDataSeg("hello", 0, 1000)]))
    finally:
        optimizer.close()

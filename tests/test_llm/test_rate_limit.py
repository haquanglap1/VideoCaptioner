"""Recover known rejections without re-posting ambiguous network failures."""

import json
import time
from concurrent.futures import ThreadPoolExecutor
from threading import Event, Lock

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
    # Up to ten initial requests, then two shared recovery probes.
    assert 3 <= len(observed) <= 12


@pytest.mark.parametrize("threads", [1, 3, 20])
def test_configured_threads_reach_transport_without_hidden_cap(monkeypatch, threads):
    import asyncio

    from videocaptioner.core.entities import SubtitleConfig, TranslatorServiceEnum
    from videocaptioner.ui.thread.subtitle_thread import create_translator_from_config

    lock, wave_ready, release = Lock(), Event(), Event()
    active = peak = requests = 0
    async def handler(request):
        nonlocal active, peak, requests
        with lock:
            active += 1
            requests += 1
            peak = max(peak, active)
            if active == threads:
                wave_ready.set()
        try:
            while not release.is_set():
                await asyncio.sleep(.01)
            body = json.loads(request.content)
            owned = json.loads(body["messages"][1]["content"])["owned_cues"]
            value = {"subtitle_translations": {c["id"]: "Translation." for c in owned},
                     "speech_blocks": [{"cue_ids": [c["id"]], "text": "Translation."} for c in owned]}
            return httpx.Response(200, json={"id": "test", "model": "fixture", "object": "chat.completion",
                "created": 0, "choices": [{"index": 0, "finish_reason": "stop",
                    "message": {"role": "assistant", "content": json.dumps(value)}}]})
        finally:
            with lock:
                active -= 1
    wire_client(monkeypatch, handler)
    engine = create_translator_from_config(SubtitleConfig(thread_num=threads, batch_size=1,
        translator_service=TranslatorServiceEnum.OPENAI,
        dialogue_translation=True, api_key="fixture", base_url="https://fixture.invalid/v1", llm_model="fixture"))
    engine.reuse_cached_chunks = False
    data = ASRData([ASRDataSeg("Synthetic source.", i * 2000, i * 2000 + 500) for i in range(40)])
    try:
        with ThreadPoolExecutor(1) as pool:
            future = pool.submit(engine.translate_subtitle, data)
            try:
                assert wave_ready.wait(5), f"Configured {threads} workers, observed only {peak} concurrent requests"
            finally:
                release.set()
            result = future.result(10)
        assert peak == threads and requests == 40 and active == 0
        assert len(result.segments) == 40
    finally:
        release.set()
        engine.close()


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


@pytest.mark.parametrize("limit", [1, 3, 20])
def test_independent_jobs_share_selected_total_request_limit(monkeypatch, limit):
    import asyncio

    from videocaptioner.core.llm.rate_limit import RateLimitGate, llm_admission_scope

    lock, reached, release = Lock(), Event(), Event()
    active = peak = 0
    async def handler(_):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
            if active == limit:
                reached.set()
        try:
            while not release.is_set():
                await asyncio.sleep(.01)
            return response()
        finally:
            with lock:
                active -= 1
    observed, _ = wire_client(monkeypatch, handler)
    shared = RateLimitGate(limit)
    with llm_admission_scope(shared):
        jobs = [call() for _ in range(3)]
    assert call()._gate is not shared
    with ThreadPoolExecutor(30) as pool:
        futures = [pool.submit(jobs[i % 3], [], "fixture") for i in range(30)]
        try:
            assert reached.wait(5)
            assert peak == limit
        finally:
            release.set()
        for future in futures:
            assert future.result(10).choices
    assert peak == limit and active == shared.active == 0 and len(observed) == 30


def test_shared_quota_and_cancellation_do_not_leak_between_jobs(monkeypatch):
    from videocaptioner.core.llm.rate_limit import RateLimitGate, llm_admission_scope

    cancelled = Event()
    rejecting = Event()
    observed, _ = wire_client(monkeypatch, lambda _: httpx.Response(429,
        json={"error": {"code": "insufficient_quota"}}) if rejecting.is_set() else response())
    with llm_admission_scope(RateLimitGate(1)):
        first = OwnedLLMRequest(call().credentials, 5, cancelled.is_set)
        second = call()
    cancelled.set()
    with pytest.raises(RuntimeError, match="cancelled"):
        first([], "fixture")
    assert second([], "fixture").choices and len(observed) == 1
    monkeypatch.setattr(rate_limit, "BACKOFF_SECONDS", .01)
    rejecting.set()
    with pytest.raises(LLMRateLimitError):
        second([], "fixture")
    cancelled.clear()
    with pytest.raises(LLMRateLimitError):
        first([], "fixture")
    assert len(observed) == 2 and first._gate.active == 0

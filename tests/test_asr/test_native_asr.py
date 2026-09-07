"""Native API contracts. All media, identities and transports are synthetic/offline."""

import asyncio
import json
import wave
from dataclasses import replace

import httpx
import pytest

from videocaptioner.core.asr import native_api
from videocaptioner.core.asr.api_profiles import ASRAPIError
from videocaptioner.core.asr.native_api import NativeAPIError, NativeASR
from videocaptioner.core.asr.native_profiles import NATIVE_PROFILES, NativeASRConfig
from videocaptioner.core.asr.native_result import native_cues, parse_native

FILE_ID = "11111111-1111-4111-8111-111111111111"
JOB_ID = "22222222-2222-4222-8222-222222222222"


def soniox_result():
    return {"text": "王小明，2026年。你好！", "tokens": [
        {"text": "王小明", "start_ms": 100, "end_ms": 600, "speaker": "1"},
        {"text": "，", "start_ms": 600, "end_ms": 600, "speaker": "1"},
        {"text": "2026", "start_ms": 700, "end_ms": 1100, "speaker": "1"},
        {"text": "年。", "start_ms": 1100, "end_ms": 1300, "speaker": "1"},
        {"text": "你好！", "start_ms": 1200, "end_ms": 1700, "speaker": "2"},
    ]}


def scribe_result():
    return {"text": "王小明， 2026年。(笑)你好！", "words": [
        {"text": "王小明，", "start": .1, "end": .6, "speaker_id": "speaker_0", "type": "word"},
        {"text": " ", "type": "spacing"},
        {"text": "2026年。", "start": .7, "end": 1.3, "speaker_id": "speaker_0", "type": "word"},
        {"text": "(笑)", "start": 1.3, "end": 1.5, "type": "audio_event"},
        {"text": "你好！", "start": 1.2, "end": 1.7, "speaker_id": "speaker_1", "type": "word"},
    ]}


@pytest.mark.parametrize("provider,factory", [("soniox", soniox_result), ("scribe", scribe_result)])
def test_text_timing_overlap_and_scoped_speakers(provider, factory):
    data = parse_native(factory(), provider, 2000, "request-a", True)
    assert "".join(seg.text for seg in data).replace(" ", "") == "王小明，2026年。你好！"
    assert data.segments[-1].start_time == 1200
    assert data.segments[-2].end_time == 1300
    assert len({seg.speaker for seg in data}) == 2
    other = parse_native(factory(), provider, 2000, "request-b", True)
    assert not {seg.speaker for seg in data} & {seg.speaker for seg in other}
    before = [(seg.start_time, seg.end_time) for seg in data]
    data.optimize_timing()
    assert [(seg.start_time, seg.end_time) for seg in data] == before
    cues = native_cues(data)
    assert "".join(seg.text for seg in cues) == "".join(seg.text for seg in data)
    assert cues.segments[-1].start_time == 1200
    assert "speaker" not in cues.to_srt()
    assert "(笑)" not in cues.to_srt()
    if provider == "scribe":
        assert data.events[0].start_ms == 1300


@pytest.mark.parametrize("speaker", [None, "", "  "])
def test_unknown_speaker_is_not_inferred(speaker):
    value = {"text": "好", "tokens": [{"text": "好", "start_ms": 1, "end_ms": 99, "speaker": speaker}]}
    assert parse_native(value, "soniox", 100, "job", True).segments[0].speaker is None


def test_diarization_off_discards_unrequested_speaker_labels():
    assert all(seg.speaker is None for seg in parse_native(soniox_result(), "soniox", 2000, "a", False))


@pytest.mark.parametrize("provider,factory,start,end", [
    ("soniox", soniox_result, "start_ms", "end_ms"), ("scribe", scribe_result, "start", "end")])
@pytest.mark.parametrize("change", ["missing", "nan", "negative", "inverted", "bounds", "bool", "zero", "string"])
def test_bad_timing_never_creates_subtitles(provider, factory, start, end, change):
    value = factory()
    token = value["tokens" if provider == "soniox" else "words"][0]
    if change == "missing":
        del token[start]
    elif change == "nan":
        token[start] = float("nan")
    elif change == "negative":
        token[start] = -1
    elif change == "inverted":
        token[start] = 900
    elif change == "bounds":
        token[end] = 3000
    elif change == "bool":
        token[start] = True
    elif change == "zero":
        token[start] = token[end]
    else:
        token[start] = "0.1"
    with pytest.raises(ASRAPIError, match="timestamp|duration"):
        parse_native(value, provider, 2000, "a", True)


def test_silence_events_subwords_and_coverage():
    assert not parse_native({"text": "", "tokens": []}, "soniox", 1000, "a", True).has_data()
    event = {"text": "(music)", "type": "audio_event", "start": 0, "end": 1}
    result = parse_native({"text": "(music)", "words": [event]}, "scribe", 1000, "a", True)
    assert result.events and not result.has_data()
    value = {"text": "Hello world!", "tokens": [
        {"text": "Hel", "start_ms": 0, "end_ms": 100},
        {"text": "lo", "start_ms": 100, "end_ms": 200},
        {"text": " world!", "start_ms": 300, "end_ms": 800},
    ]}
    result = parse_native(value, "soniox", 1000, "a", True)
    assert [s.text for s in result] == ["Hello", " world!"]
    value["text"] += " extra"
    with pytest.raises(ASRAPIError, match="coverage"):
        parse_native(value, "soniox", 1000, "a", True)


@pytest.fixture
def audio(tmp_path, monkeypatch):
    path = tmp_path / "private-name.wav"
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(16000)
        handle.writeframes(b"\0\0" * 32000)
    monkeypatch.setattr(native_api, "audio_duration", lambda *a: 2000)
    return path


class SonioxServer:
    def __init__(self):
        self.requests = []
        self.polls = []
        self.post_error = None
        self.delete_status = 204

    async def __call__(self, request):
        self.requests.append(request)
        assert request.headers["Authorization"] == "Bearer soniox-test-key"
        assert "xi-api-key" not in request.headers
        route = request.url.path
        if request.method == "DELETE":
            return httpx.Response(self.delete_status)
        if route == "/v1/files":
            content = await request.aread()
            assert b'filename="audio.wav"' in content and b"private-name" not in content
            return httpx.Response(201, json={"id": FILE_ID})
        if request.method == "POST":
            payload = json.loads(await request.aread())
            assert payload == {"model": "stt-async-v5", "file_id": FILE_ID,
                               "enable_speaker_diarization": True, "language_hints": ["zh"]}
            if self.post_error:
                if isinstance(self.post_error, Exception):
                    raise self.post_error
                return httpx.Response(self.post_error, json={"secret": "raw-private-response"})
            return httpx.Response(201, json={"id": JOB_ID})
        if route.endswith("/transcript"):
            return httpx.Response(200, json=soniox_result())
        status = self.polls.pop(0) if self.polls else "completed"
        if isinstance(status, int):
            return httpx.Response(status, headers={"Retry-After": "0"})
        return httpx.Response(200, json={"status": status})


def make_soniox(audio, server, **kwargs):
    return NativeASR(str(audio), NativeASRConfig("soniox", "soniox-test-key"), "zh",
                     transport=httpx.MockTransport(server), use_cache=False, **kwargs)


def test_soniox_wire_poll_retry_and_owned_cleanup(audio):
    server = SonioxServer()
    server.polls = [429, 503, "completed"]
    job = make_soniox(audio, server)
    assert job.run().segments
    assert job.state.status == "succeeded" and job.state.remote == "deleted"
    assert sum(r.method == "POST" for r in server.requests) == 2
    assert [r.url.path for r in server.requests if r.method == "DELETE"] == [
        f"/v1/transcriptions/{JOB_ID}", f"/v1/files/{FILE_ID}"]


@pytest.mark.parametrize("error", [401, 403, 404, 413, 429, 500,
                                  httpx.ReadTimeout("private-response"), httpx.ConnectError("private-response")])
def test_submit_is_never_repeated_when_rejected_or_uncertain(audio, error):
    server = SonioxServer()
    server.post_error = error
    job = make_soniox(audio, server)
    with pytest.raises(NativeAPIError) as caught:
        job.run()
    assert job.state.status == ("timeout" if isinstance(error, httpx.TimeoutException) else "failed")
    assert "raw-private-response" not in str(caught.value)
    assert "soniox-test-key" not in str(caught.value)
    assert sum(r.method == "POST" and r.url.path == "/v1/transcriptions" for r in server.requests) == 1
    if error == 500 or isinstance(error, Exception):
        assert caught.value.uncertain
        assert not any(r.method == "DELETE" for r in server.requests)


@pytest.mark.parametrize("stage", ["upload", "submit", "poll", "result"])
def test_cancel_in_flight_at_each_stage(audio, stage):
    server = SonioxServer()
    entered = False
    cancelled = False
    async def transport(request):
        nonlocal entered, cancelled
        route = request.url.path
        actual = ("upload" if route == "/v1/files" else "submit" if request.method == "POST"
                  else "result" if route.endswith("/transcript") else "poll")
        if request.method != "DELETE" and actual == stage:
            entered = True
            try:
                await asyncio.sleep(60)
            finally:
                cancelled = True
        return await server(request)
    job = make_soniox(audio, transport)
    def callback(*args):
        if entered:
            raise InterruptedError("cancel")
    with pytest.raises(InterruptedError):
        job.run(callback)
    assert cancelled and job.state.status == "cancelled"
    assert all(r.url.path in (f"/v1/transcriptions/{JOB_ID}", f"/v1/files/{FILE_ID}")
               for r in server.requests if r.method == "DELETE")


def test_remote_processing_cannot_be_deleted_does_not_remove_input(audio, monkeypatch):
    from types import SimpleNamespace

    server = SonioxServer()
    server.polls = ["processing"]
    server.delete_status = 409
    now = [0.0]
    monkeypatch.setattr(native_api, "time", SimpleNamespace(monotonic=lambda: now[0]))
    async def transport(request):
        response = await server(request)
        if request.method == "GET" and request.url.path == f"/v1/transcriptions/{JOB_ID}":
            # Expire after observing processing, independently of Windows timer granularity.
            now[0] = 3601.0
        return response
    job = make_soniox(audio, transport)
    with pytest.raises(NativeAPIError, match="timed out"):
        job.run()
    assert job.state.status == "timeout"
    assert native_api.REMOTE_NOTICE in job.state.warnings
    assert not any(r.method == "DELETE" and "/files/" in r.url.path for r in server.requests)


@pytest.mark.parametrize("polls", [["error"], [500, 500, 500], ["unexpected"]])
def test_job_fail_and_poll_retry_exhaustion(audio, polls):
    server = SonioxServer()
    server.polls = polls
    job = make_soniox(audio, server)
    with pytest.raises(NativeAPIError):
        job.run()
    assert sum(r.method == "POST" for r in server.requests) == 2
    assert job.state.status == "failed"


def test_scribe_wire_native_headers_model_and_events(audio):
    async def transport(request):
        assert request.url.path == "/v1/speech-to-text"
        assert request.headers["xi-api-key"] == "scribe-test-key"
        assert "Authorization" not in request.headers
        body = await request.aread()
        for field, value in [("model_id", "scribe_v2"), ("diarize", "true"),
                             ("language_code", "zh"), ("tag_audio_events", "true"),
                             ("timestamps_granularity", "word"), ("webhook", "false")]:
            assert f'name="{field}"\r\n\r\n{value}'.encode() in body
        assert b"private-name" not in body and b"response_format" not in body
        return httpx.Response(200, json=scribe_result())
    job = NativeASR(str(audio), NativeASRConfig("scribe", "scribe-test-key"), "zh",
                    transport=httpx.MockTransport(transport), use_cache=False)
    assert len(job.run().events) == 1


@pytest.mark.parametrize("provider", ["soniox", "scribe"])
def test_limits_checked_before_network(audio, provider, monkeypatch):
    profile = NATIVE_PROFILES[provider]
    monkeypatch.setitem(NATIVE_PROFILES, provider, replace(profile, max_upload_bytes=100))
    job = NativeASR(str(audio), NativeASRConfig(provider, "test-key"))
    with pytest.raises(NativeAPIError, match="upload limit"):
        job.run()
    monkeypatch.setitem(NATIVE_PROFILES, provider, profile)
    monkeypatch.setattr(native_api, "audio_duration", lambda *a: profile.max_duration_ms + 1)
    with pytest.raises(NativeAPIError, match="duration"):
        job.run()


def test_fingerprint_options_endpoint_model_language_audio_and_no_secrets(audio):
    cfg = NativeASRConfig("soniox", "private-key").validated()
    def key(config=cfg, lang="zh"):
        return native_api.audio_fingerprint(audio, config, lang, lambda: None)
    baseline = key()
    assert baseline == key(replace(cfg, api_key="another-key"))
    assert baseline != key(replace(cfg, diarize=False))
    assert baseline != key(replace(cfg, api_base="https://another.example/v1"))
    assert baseline != key(replace(cfg, model="another-model"))
    assert baseline != key(lang="")
    assert "private" not in baseline and len(baseline.split("-")[-1]) == 64


def test_cache_retains_scope_and_never_stores_remote_ids(audio, monkeypatch):
    class Cache(dict):
        def set(self, key, value, **kwargs):
            self[key] = value
    cache = Cache()
    monkeypatch.setattr(native_api, "get_asr_cache", lambda: cache)
    monkeypatch.setattr(native_api, "is_cache_enabled", lambda: True)
    server = SonioxServer()
    job = make_soniox(audio, server)
    job.use_cache = True
    first = job.run()
    count = len(server.requests)
    second = job.run()
    assert len(server.requests) == count
    assert first.to_json() == second.to_json()
    serialized = json.dumps(cache)
    assert FILE_ID not in serialized and JOB_ID not in serialized and "test-key" not in serialized


@pytest.mark.parametrize("status", [400, 401, 403, 404, 413, 422, 429, 500])
def test_scribe_errors_never_retry_paid_request(audio, status):
    calls = []
    async def transport(request):
        calls.append(request)
        return httpx.Response(status, json={"detail": "private-provider-body"})
    job = NativeASR(str(audio), NativeASRConfig("scribe", "scribe-key"),
                    transport=httpx.MockTransport(transport), use_cache=False)
    with pytest.raises(NativeAPIError) as caught:
        job.run()
    assert len(calls) == 1
    assert "private-provider-body" not in str(caught.value)
    assert caught.value.uncertain == (status >= 500)


@pytest.mark.parametrize("cancel", [True, False])
def test_scribe_cancel_or_timeout_closes_request_and_reports_remote_uncertainty(audio, cancel):
    entered = False
    closed = False
    async def transport(request):
        nonlocal entered, closed
        entered = True
        try:
            await asyncio.sleep(60)
        finally:
            closed = True
        return httpx.Response(500)
    job = NativeASR(str(audio), NativeASRConfig("scribe", "test-key"),
                    transport=httpx.MockTransport(transport), use_cache=False,
                    deadline_seconds=5 if cancel else .01)
    def callback(*args):
        if entered and cancel:
            raise InterruptedError
    with pytest.raises(InterruptedError if cancel else NativeAPIError):
        job.run(callback)
    assert closed and native_api.REMOTE_NOTICE in job.state.warnings
    assert job.state.status == ("cancelled" if cancel else "timeout")


def test_scribe_only_deletes_its_returned_transcript(audio):
    calls = []
    async def transport(request):
        calls.append((request.method, request.url.path))
        if request.method == "DELETE":
            return httpx.Response(200, json={"status": "ok"})
        return httpx.Response(200, json={**scribe_result(), "transcription_id": "owned-transcript"})
    job = NativeASR(str(audio), NativeASRConfig("scribe", "test-key"),
                    transport=httpx.MockTransport(transport), use_cache=False)
    job.run()
    assert calls == [("POST", "/v1/speech-to-text"), ("DELETE", "/v1/speech-to-text/transcripts/owned-transcript")]
    assert job.state.remote == "deleted"


@pytest.mark.parametrize("stage", ["upload", "submit"])
def test_missing_resource_id_is_uncertain_and_does_not_resubmit(audio, stage):
    calls = []
    async def transport(request):
        calls.append(request)
        if stage == "submit" and request.url.path == "/v1/files":
            return httpx.Response(201, json={"id": FILE_ID})
        return httpx.Response(201, json={"id": "../../not-an-owned-resource"})
    job = make_soniox(audio, transport)
    with pytest.raises(NativeAPIError) as caught:
        job.run()
    assert caught.value.uncertain and caught.value.stage == stage
    assert len(calls) == (1 if stage == "upload" else 2)


def test_cancel_before_upload_does_not_create_resource(audio):
    server = SonioxServer()
    job = make_soniox(audio, server)
    def cancel(*args):
        raise InterruptedError
    with pytest.raises(InterruptedError):
        job.run(cancel)
    assert job.state.status == "cancelled" and not server.requests


def test_cancel_between_upload_and_submit_removes_file_without_creating_job(audio):
    server = SonioxServer()
    job = make_soniox(audio, server)
    def callback(*args):
        if job.state.stage == "submit":
            raise InterruptedError
    with pytest.raises(InterruptedError):
        job.run(callback)
    assert [(r.method, r.url.path) for r in server.requests] == [
        ("POST", "/v1/files"), ("DELETE", f"/v1/files/{FILE_ID}")]
    assert not job.state.warnings


@pytest.mark.parametrize("provider,route", [("soniox", "/v1/models"), ("scribe", "/v1/user")])
def test_probe_is_read_only_and_does_not_return_personal_or_catalog_payload(provider, route):
    calls = []
    async def transport(request):
        calls.append(request)
        assert request.method == "GET" and request.url.path == route
        return httpx.Response(200, json={"private_account_data": "must-be-discarded"})
    result = native_api.probe_service(NativeASRConfig(provider, "test-key"), lambda: None,
                                     transport=httpx.MockTransport(transport))
    assert result is None and len(calls) == 1


@pytest.mark.parametrize("value", [None, [], {}, {"text": "a", "tokens": None},
                                    {"text": "", "tokens": [{"type": "unexpected", "text": "x"}]}])
def test_malformed_response_fails_closed(value):
    with pytest.raises(ASRAPIError):
        parse_native(value, "soniox", 1000, "scope", True)

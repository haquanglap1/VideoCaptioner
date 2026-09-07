"""Offline wire contracts, timing and privacy regressions (no provider credentials)."""

import io
import traceback
import wave
from dataclasses import replace

import httpx
import openai
import pytest

from videocaptioner.core.asr import api_transcription as api
from videocaptioner.core.asr.api_profiles import (
    JSON_TEXT,
    WHISPER,
    ASRAPIError,
    MissingTimingError,
    normalize_endpoint,
    resolve_profile,
)
from videocaptioner.core.asr.whisper_api import WhisperAPI


@pytest.fixture
def wav():
    data = io.BytesIO()
    with wave.open(data, "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(16000)
        stream.writeframes(b"\0\0" * 160)
    return data.getvalue()


@pytest.fixture(autouse=True)
def isolated_asr_cache(monkeypatch):
    class Cache(dict):
        def get(self, key, default=None):
            return super().get(key, default)

        def set(self, key, value, **kwargs):
            self[key] = value

    cache = Cache()
    monkeypatch.setattr("videocaptioner.core.asr.base.get_asr_cache", lambda: cache)
    return cache


@pytest.mark.parametrize("provider,model", [
    ("custom", "legacy-private-alias"), ("openai", "whisper-1"),
    ("videocaptioner", "whisper-1"), ("groq", "whisper-large-v3"),
    ("groq", "whisper-large-v3-turbo"),
])
@pytest.mark.parametrize("word", [False, True])
def test_whisper_request(wav, provider, model, word):
    request = api.build_request(wav, model, resolve_profile(model, provider=provider),
                                language="zh", word_timing=word)
    assert request["response_format"] == "verbose_json"
    assert request["timestamp_granularities"] == (["word", "segment"] if word else ["segment"])
    assert request["language"] == "zh"
    assert request["prompt"] == api.DEFAULT_ZH_PROMPT
    assert request["file"] == ("audio.wav", wav, "audio/wav")


@pytest.mark.parametrize("provider", ["custom", "openai", "videocaptioner"])
@pytest.mark.parametrize("model", ["gpt-4o-transcribe", "gpt-4o-mini-transcribe"])
def test_gpt_json_request_has_no_timestamp_fields(wav, provider, model):
    request = api.build_request(wav, model, resolve_profile(model, provider=provider),
                                language="auto", word_timing=True)
    assert request["response_format"] == "json"
    assert "timestamp_granularities" not in request
    assert "language" not in request
    assert "prompt" not in request


def test_custom_explicit_profile_and_unknown_names():
    assert resolve_profile("new-alias", "json-text") is JSON_TEXT
    assert resolve_profile("new-alias", "whisper") is WHISPER
    assert resolve_profile("some-transcribe-name") is WHISPER
    for kwargs in ({"profile": "bad"}, {"provider": "bad"}):
        with pytest.raises(ASRAPIError):
            resolve_profile("whisper-1", **kwargs)
    with pytest.raises(ASRAPIError, match="JSON text"):
        resolve_profile("gpt-4o-transcribe", "whisper")


@pytest.mark.parametrize("base,expected", [
    (" https://EXAMPLE.com/ ", "https://example.com/v1"),
    ("https://example.com:443/v1/", "https://example.com/v1"),
    ("https://api.groq.com/openai/v1", "https://api.groq.com/openai/v1"),
    ("http://localhost:8080/api", "http://localhost:8080/api"),
])
def test_endpoint_normalization(base, expected):
    assert normalize_endpoint(base) == expected


@pytest.mark.parametrize("base", ["", "file:///private/path", "https://secret@host/v1",
                                  "https://host/v1?key=secret", "https://host/v1#secret"])
def test_endpoint_errors_do_not_echo_secrets(base):
    with pytest.raises(ASRAPIError) as error:
        normalize_endpoint(base)
    assert "secret" not in str(error.value)
    assert "/private/path" not in str(error.value)


@pytest.mark.parametrize("data,filename,mime", [
    (b"ID3fake", "audio.mp3", "audio/mpeg"),
    (b"\xff\xfbdata", "audio.mp3", "audio/mpeg"),
    (b"fLaCdata", "audio.flac", "audio/flac"),
    (b"\0\0\0\x18ftypM4A ", "audio.m4a", "audio/mp4"),
])
def test_upload_mime_follows_bytes(data, filename, mime):
    assert api.audio_attachment(data, 100) == (filename, data, mime)


def test_upload_limit_checks_bytes_before_client(wav, monkeypatch):
    with pytest.raises(ASRAPIError, match="upload limit"):
        api.build_request(wav, "whisper-1", replace(WHISPER, max_upload_bytes=len(wav) - 1))
    assert api.build_request(wav, "whisper-1", replace(WHISPER, max_upload_bytes=len(wav)))
    for data in (b"", b"not audio"):
        with pytest.raises(ASRAPIError):
            api.build_request(data, "whisper-1", WHISPER)
    asr = WhisperAPI(wav, "whisper-1", base_url="https://example.com", api_key="fake")
    asr.profile = replace(WHISPER, max_upload_bytes=1)
    monkeypatch.setattr("videocaptioner.core.asr.whisper_api.create_client",
                        lambda *a: pytest.fail("oversize upload must not create client"))
    with pytest.raises(ASRAPIError, match="upload limit"):
        asr.run()


def test_subtitle_preflight_precedes_audio_io_and_upload(monkeypatch):
    from videocaptioner.core.asr.transcribe import transcribe
    from videocaptioner.core.entities import TranscribeConfig, TranscribeModelEnum

    monkeypatch.setattr("videocaptioner.core.asr.whisper_api.create_client",
                        lambda *a: pytest.fail("text-only subtitle flow must not upload"))
    with pytest.raises(MissingTimingError, match="alignment"):
        WhisperAPI("does-not-exist.wav", "gpt-4o-transcribe")
    with pytest.raises(MissingTimingError, match="alignment"):
        transcribe("does-not-exist.wav", TranscribeConfig(
            transcribe_model=TranscribeModelEnum.WHISPER_API,
            whisper_api_model="gpt-4o-mini-transcribe",
        ))


def test_words_segments_and_seconds_to_ms():
    words = [{"word": "你好", "start": 0.125, "end": 1.234}]
    segments = [{"text": " 你好。 ", "start": 0.1, "end": 1.3}]
    result = api.parse_response({"text": "你好。", "words": words, "segments": segments})
    assert result.timing_level == "word"
    assert result.subtitle_segments(True)[0].start_time == 125
    assert result.subtitle_segments(True)[0].end_time == 1234
    assert result.subtitle_segments(False)[0].text == "你好。"
    assert api.parse_response({"words": words}).subtitle_segments(False)[0].start_time == 125
    sentence = api.parse_response({"segments": segments})
    assert sentence.timing_level == "segment"
    assert sentence.subtitle_segments(False)[0].end_time == 1300
    with pytest.raises(MissingTimingError, match="Disable word timestamps"):
        sentence.subtitle_segments(True)


def test_text_only_and_silence_do_not_fabricate_timing():
    result = api.parse_response({"text": "A synthetic test sentence."})
    assert result.timing_level == "none"
    with pytest.raises(MissingTimingError, match="alignment"):
        result.subtitle_segments(False)
    for data in ({"text": ""}, {"text": "", "words": [], "segments": []}):
        assert api.parse_response(data).subtitle_segments(True) == []


@pytest.mark.parametrize("response", [
    "html", [], {}, {"error": "secret"}, {"text": None}, {"segments": "invalid"},
    {"words": [{"word": "test"}]},
    *({"segments": [{"text": "test", "start": start, "end": end}]}
      for start, end in [(None, 1), (0, "NaN"), (0, float("inf")), (-1, 1), (2, 1), (True, 1)]),
])
def test_malformed_response_is_domain_error(response):
    with pytest.raises(ASRAPIError):
        api.parse_response(response)


def test_cache_fingerprint_is_stable_private_and_isolated(wav):
    def asr(**kwargs):
        return WhisperAPI(wav, **{
            "whisper_model": "whisper-1", "base_url": "https://one.example/v1", "api_key": "secret-key",
            "language": "zh", "prompt": "private prompt", **kwargs,
        })
    baseline = asr()._get_key()
    assert baseline.startswith("v2-") and len(baseline) == 67
    assert asr(base_url="https://ONE.example:443/v1/", api_key="different")._get_key() == baseline
    for kwargs in ({"base_url": "https://two.example"}, {"whisper_model": "alias"},
                   {"language": "en"}, {"prompt": "changed"}, {"need_word_time_stamp": True}):
        assert asr(**kwargs)._get_key() != baseline
    assert asr(prompt="")._get_key() == asr(prompt=api.DEFAULT_ZH_PROMPT)._get_key()
    assert asr(language="auto")._get_key() == asr(language="")._get_key()
    assert not any(value in baseline for value in ("secret-key", "private prompt", "one.example"))


def test_wire_probe_and_subtitle_share_parser(wav, tmp_path, monkeypatch):
    import videocaptioner.core.llm.check_whisper as probe

    requests = []
    def handler(request):
        requests.append(request)
        assert request.url.path == "/openai/v1/audio/transcriptions"
        assert request.headers["authorization"] == "Bearer fake-test-key"
        body = request.read()
        assert b'filename="audio.wav"' in body
        assert b"Content-Type: audio/wav" in body
        if b"gpt-4o-transcribe" in body:
            assert b"timestamp_granularities" not in body
            assert b"verbose_json" not in body
            return httpx.Response(200, json={"text": "Synthetic speech."})
        return httpx.Response(200, json={"segments": [{"text": "Synthetic speech.", "start": 0.1, "end": 1.1}]})

    def client(*args):
        return openai.OpenAI(base_url="https://test.example/openai/v1", api_key="fake-test-key",
                             max_retries=0, http_client=httpx.Client(transport=httpx.MockTransport(handler)))

    audio_path = tmp_path / "private-name.mp3"
    audio_path.write_bytes(wav)  # Extension deliberately differs from the actual bytes.
    monkeypatch.setattr(probe, "TEST_AUDIO_PATH", audio_path)
    monkeypatch.setattr(probe, "create_client", client)
    monkeypatch.setattr("videocaptioner.core.asr.whisper_api.create_client", client)
    success, message = probe.check_whisper_connection("https://test.example", "fake", "gpt-4o-transcribe")
    assert success and "without timestamps" in message and "S2" in message
    asr = WhisperAPI(str(audio_path), "whisper-1", base_url="https://test.example", api_key="fake")
    result = asr.run()
    assert result.segments[0].start_time == 100
    success, message = probe.check_whisper_connection("https://test.example", "fake", "whisper-1")
    assert success and "segment timestamps" in message
    assert len(requests) == 3


@pytest.mark.parametrize("status,attempts", [(400, 1), (401, 1), (403, 1), (404, 1), (413, 1),
                                           (429, 3), (500, 3), (503, 3), (302, 1)])
def test_status_retry_bound_and_safe_error(wav, status, attempts, monkeypatch):
    calls, sleeps = [], []
    def handler(request):
        calls.append(request)
        return httpx.Response(status, json={"error": {"message": "secret-key private-prompt private-path"}},
                              headers={"Retry-After": "999999", "Location": "https://other.example"})
    monkeypatch.setattr(api.time, "sleep", sleeps.append)
    with openai.OpenAI(base_url="https://test.example/v1", api_key="fake", max_retries=0,
                      http_client=httpx.Client(transport=httpx.MockTransport(handler))) as client:
        with pytest.raises(ASRAPIError) as error:
            api.submit_transcription(client, api.build_request(wav, "whisper-1", WHISPER))
    assert len(calls) == attempts
    assert sleeps == ([0.5, 1.0] if attempts == 3 else [])
    rendered = "".join(traceback.format_exception(error.value))
    assert "secret-key" not in rendered and "private-prompt" not in rendered and "private-path" not in rendered


@pytest.mark.parametrize("failure", [httpx.ReadTimeout, httpx.ConnectError])
def test_network_retry_bound(wav, failure, monkeypatch):
    calls = []
    def handler(request):
        calls.append(request)
        raise failure("private network response", request=request)
    monkeypatch.setattr(api.time, "sleep", lambda _: None)
    with openai.OpenAI(base_url="https://test.example", api_key="fake", max_retries=0,
                      http_client=httpx.Client(transport=httpx.MockTransport(handler))) as client:
        with pytest.raises(ASRAPIError):
            api.submit_transcription(client, api.build_request(wav, "whisper-1", WHISPER))
    assert len(calls) == 3


def test_client_has_finite_timeout_no_sdk_retries_or_redirects():
    with api.create_client("https://example.com", "fake") as client:
        assert client.max_retries == 0
        assert client.timeout.read == 120
        assert client.timeout.connect == 10
        assert client._client.follow_redirects is False


def test_cache_does_not_read_legacy_or_log_prompt_and_reuses_new_result(wav, isolated_asr_cache, monkeypatch):
    logs, calls = [], []
    monkeypatch.setattr("videocaptioner.core.asr.base.is_cache_enabled", lambda: True)
    monkeypatch.setattr("videocaptioner.core.asr.base.logger.info", lambda *a: logs.append(str(a)))
    asr = WhisperAPI(wav, "whisper-1", base_url="https://test.example", api_key="private-test-key",
                     prompt="private-test-prompt", use_cache=True)
    legacy_key = f"WhisperAPI:{asr.crc32_hex}-whisper-1-zh-private-test-prompt"
    isolated_asr_cache[legacy_key] = {"text": "wrong legacy result"}
    def submit():
        calls.append(True)
        return {"segments": [{"text": "Synthetic text.", "start": 0, "end": 1}]}
    monkeypatch.setattr(asr, "_submit", submit)
    assert asr.run().segments[0].text == "Synthetic text."
    assert asr.run().segments[0].text == "Synthetic text."
    assert len(calls) == 1
    assert legacy_key in isolated_asr_cache  # No destructive migration.
    assert "private-test-prompt" not in str(logs)
    assert "private-test-key" not in str(logs)
    assert "test.example" not in str(logs)


def test_config_diagnostic_omits_request_secrets():
    from videocaptioner.core.entities import TranscribeConfig, TranscribeModelEnum

    config = TranscribeConfig(
        transcribe_model=TranscribeModelEnum.WHISPER_API,
        whisper_api_key="private-test-key", whisper_api_prompt="private-test-prompt",
        whisper_api_base="https://test.example/private-path", whisper_api_model="private-model",
    )
    assert "private" not in config.print_config()

"""Offline Google/DeepLX failures must not publish or cache partial batches."""

import html
import json
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import requests
from diskcache import Cache

from videocaptioner.core.asr.asr_data import ASRData, ASRDataSeg
from videocaptioner.core.entities import SubtitleProcessData
from videocaptioner.core.translate.base import logger
from videocaptioner.core.translate.deeplx_translator import DeepLXTranslator
from videocaptioner.core.translate.google_translator import GoogleTranslator
from videocaptioner.core.translate.types import TargetLanguage
from videocaptioner.core.utils.cache import generate_cache_key


def response(body="", *, status=200):
    result = requests.Response()
    result.status_code = status
    result.url = "https://translation.invalid/private-endpoint"
    result.encoding = "utf-8"
    result._content = body.encode("utf-8")
    result._content_consumed = True
    result.close = Mock(wraps=result.close)
    return result


def success(provider, text="Đã dịch."):
    if provider == "google":
        return response(f'<div class="result-container">{html.escape(text)}</div>')
    return response(json.dumps({"code": 200, "data": text}))


def chunk():
    return [SubtitleProcessData(index=i, original_text=text, cue_id=f"cue-{i}")
            for i, text in enumerate(("First sentence.", "Second sentence."), 1)]


@pytest.fixture(params=["google", "deeplx"])
def engine(request, monkeypatch, tmp_path):
    with Cache(str(tmp_path / "translation-cache")) as cache:
        session = Mock(spec=requests.Session)
        monkeypatch.setattr(requests, "Session", lambda: session)
        monkeypatch.setattr("videocaptioner.core.translate.base.get_translate_cache", lambda: cache)
        monkeypatch.setattr(logger, "propagate", True)
        updates = []
        provider = request.param
        if provider == "google":
            translator = GoogleTranslator(2, 5, TargetLanguage.VIETNAMESE, 20, updates.append)
            send = session.get
        else:
            translator = DeepLXTranslator(2, 5, TargetLanguage.VIETNAMESE, 20, updates.append,
                                          endpoint="https://translation.invalid/private-endpoint")
            send = session.post
        try:
            yield SimpleNamespace(translator=translator, session=session, send=send,
                                  cache=cache, updates=updates, provider=provider)
        finally:
            translator.close()


@pytest.mark.parametrize("status", [400, 401, 403, 404, 429, 500])
def test_http_error_is_not_success_or_cached(engine, status, caplog):
    reply = response("private-response", status=status)
    engine.send.return_value = reply
    source = chunk()
    before = deepcopy(source)
    with pytest.raises(RuntimeError, match=f"HTTP {status}") as error:
        engine.translator._safe_translate_chunk(source)
    assert source == before
    assert not engine.updates and len(engine.cache) == 0
    assert engine.send.call_count == 1
    reply.close.assert_called_once()
    for private in ("private-response", "private-endpoint"):
        assert private not in str(error.value) + caplog.text


@pytest.mark.parametrize("exception", [requests.Timeout, requests.ConnectionError, requests.exceptions.InvalidURL])
def test_transport_error_is_sanitized_and_not_cached(engine, exception, caplog):
    engine.send.side_effect = exception("private-request private-endpoint")
    with pytest.raises(RuntimeError, match="request failed") as error:
        engine.translator._safe_translate_chunk(chunk())
    assert "private-request" not in str(error.value) + caplog.text
    assert "private-endpoint" not in str(error.value) + caplog.text
    assert not engine.updates and len(engine.cache) == 0
    assert engine.send.call_count == 1


@pytest.mark.parametrize("failure", ["http", "transport", "missing", "empty", "whitespace"])
def test_failure_in_middle_of_batch_leaves_all_rows_unchanged(engine, failure):
    if failure == "http":
        bad = response("private-response", status=500)
    elif failure == "transport":
        bad = requests.Timeout("private-request")
    elif failure == "missing":
        bad = response("{}")
    else:
        bad = success(engine.provider, "" if failure == "empty" else " \n\t\u00a0")
    engine.send.side_effect = [success(engine.provider), bad, success(engine.provider)]
    source = chunk() + [SubtitleProcessData(index=3, original_text="Third sentence.")]
    source[0].translated_text = "Previously reviewed."
    before = deepcopy(source)
    with pytest.raises(RuntimeError):
        engine.translator._safe_translate_chunk(source)
    assert source == before
    assert not engine.updates and len(engine.cache) == 0
    assert engine.send.call_count == 2


@pytest.mark.parametrize("cancel_at", [1, 2])
def test_cancel_during_request_discards_pending_batch(engine, cancel_at):
    def send(*args, **kwargs):
        if engine.send.call_count == cancel_at:
            engine.translator.stop()
        return success(engine.provider)

    engine.send.side_effect = send
    source = chunk()
    before = deepcopy(source)
    with pytest.raises(RuntimeError, match="cancelled"):
        engine.translator._safe_translate_chunk(source)
    assert source == before
    assert not engine.updates and len(engine.cache) == 0
    assert engine.send.call_count == cancel_at


def test_cancel_before_request_does_not_call_service(engine):
    engine.translator.stop()
    with pytest.raises(RuntimeError, match="cancelled"):
        engine.translator._safe_translate_chunk(chunk())
    engine.send.assert_not_called()
    assert not engine.updates and len(engine.cache) == 0


def test_one_failed_chunk_prevents_successful_document(engine):
    engine.translator.batch_num = 1

    def send(*args, **kwargs):
        text = kwargs["params"]["q"] if engine.provider == "google" else kwargs["json"]["text"]
        return response(status=500) if text == "1" else success(engine.provider)

    engine.send.side_effect = send
    source = ASRData([ASRDataSeg(text=str(i), start_time=i * 1000, end_time=(i + 1) * 1000)
                      for i in range(3)])
    before = source.to_document()
    with pytest.raises(RuntimeError, match="1/3 segments failed"):
        engine.translator.translate_subtitle(source)
    assert source.to_document() == before
    assert len(engine.cache) == 2
    assert all(row.translated_text for batch in engine.updates for row in batch)


@pytest.mark.parametrize("old_text", ["", "Truncated legacy translation."])
def test_legacy_cache_is_preserved_but_not_reused(engine, old_text):
    source = chunk()
    old_key = f"{type(engine.translator).__name__}:{generate_cache_key(source)}:{engine.translator.target_language.value}"
    cached = deepcopy(source)
    for row in cached:
        row.translated_text = old_text
    engine.cache.set(old_key, cached)
    engine.send.return_value = success(engine.provider)
    for _ in range(2):
        result = engine.translator._safe_translate_chunk(chunk())
        assert [row.translated_text for row in result] == ["Đã dịch.", "Đã dịch."]
    assert engine.send.call_count == 2
    assert len(engine.updates) == 2
    assert engine.cache.get(old_key) == cached
    assert len(engine.cache) == 2


def test_failure_can_be_retried_without_a_poisoned_cache(engine):
    engine.send.side_effect = [success(engine.provider), response(status=500)]
    with pytest.raises(RuntimeError):
        engine.translator._safe_translate_chunk(chunk())
    engine.send.side_effect = None
    engine.send.return_value = success(engine.provider)
    result = engine.translator._safe_translate_chunk(chunk())
    assert all(row.translated_text == "Đã dịch." for row in result)
    assert engine.send.call_count == 4 and len(engine.cache) == 1


def test_success_preserves_full_text_metadata_and_closes_responses(engine):
    source = chunk()
    source[0].original_text = "A & B < C\n" + "x" * 4990
    before = deepcopy(source)
    replies = [success(engine.provider, "Một & <hai>."), success(engine.provider, "Ba.")]
    engine.send.side_effect = replies
    result = engine.translator._safe_translate_chunk(source)
    assert [row.translated_text for row in result] == ["Một & <hai>.", "Ba."]
    assert [(row.index, row.cue_id, row.original_text) for row in result] == [
        (row.index, row.cue_id, row.original_text) for row in before]
    for call, row, reply in zip(engine.send.call_args_list, before, replies):
        sent = call.kwargs["params"]["q"] if engine.provider == "google" else call.kwargs["json"]["text"]
        assert sent == row.original_text and call.kwargs["timeout"] == 20
        reply.close.assert_called_once()
    assert len(engine.cache) == 1 and len(engine.updates) == 1


def test_close_releases_session_after_pool(engine):
    engine.translator.close()
    engine.session.close.assert_called_once()
    assert engine.translator.executor is None
    assert engine.translator._closing_executor is None


@pytest.mark.parametrize("body", [
    "", "<html>private-response</html>", '<div class="result-container"></div>',
    '<div class="t0">&nbsp; \n</div>',
    '<div class="result-container">Partial<span>lost text</span></div>',
    '<div class="result-container">Partial<',
    '<div class="t0">One</div><div class="t0">Two</div>',
])
@pytest.mark.parametrize("engine", ["google"], indirect=True)
def test_google_invalid_body_is_rejected(engine, body, caplog):
    engine.send.return_value = response(body)
    with pytest.raises(RuntimeError, match="Malformed Google") as error:
        engine.translator._safe_translate_chunk(chunk())
    assert "private-response" not in str(error.value) + caplog.text
    assert not engine.updates and len(engine.cache) == 0


@pytest.mark.parametrize("engine", ["google"], indirect=True)
def test_google_rejects_long_input_before_sending_any_row(engine):
    source = chunk()
    source[1].original_text = "x" * 5001
    engine.send.return_value = success(engine.provider)
    with pytest.raises(RuntimeError, match="split the long subtitle"):
        engine.translator._safe_translate_chunk(source)
    engine.send.assert_not_called()
    assert not engine.updates and len(engine.cache) == 0


@pytest.mark.parametrize("payload", [
    None, [], "private-response", {}, {"data": None}, {"data": []}, {"data": 1},
    {"data": {"private-response": "bad"}}, {"data": ""}, {"data": " \n\t"},
    {"code": 500, "data": "private-response"}, {"code": "200", "data": "private-response"},
])
@pytest.mark.parametrize("engine", ["deeplx"], indirect=True)
def test_deeplx_invalid_payload_is_rejected(engine, payload, caplog):
    engine.send.return_value = response(json.dumps(payload))
    with pytest.raises(RuntimeError, match="Malformed DeepLX") as error:
        engine.translator._safe_translate_chunk(chunk())
    assert "private-response" not in str(error.value) + caplog.text
    assert not engine.updates and len(engine.cache) == 0


@pytest.mark.parametrize("engine", ["deeplx"], indirect=True)
def test_deeplx_invalid_json_does_not_expose_body(engine, caplog):
    engine.send.return_value = response("private-response")
    with pytest.raises(RuntimeError, match="Malformed DeepLX") as error:
        engine.translator._safe_translate_chunk(chunk())
    assert "private-response" not in str(error.value) + caplog.text
    assert not engine.updates and len(engine.cache) == 0


@pytest.mark.parametrize("engine", ["deeplx"], indirect=True)
def test_deeplx_endpoint_and_target_partition_cache(engine):
    engine.send.return_value = success(engine.provider)
    original_endpoint = engine.translator.endpoint
    original_key = engine.translator._get_cache_key(chunk())
    engine.translator._safe_translate_chunk(chunk())
    engine.translator.endpoint = "https://second.invalid/translate?token=synthetic-secret"
    changed_key = engine.translator._get_cache_key(chunk())
    assert changed_key != original_key
    assert all(value not in changed_key for value in ("https://", "second.invalid", "synthetic-secret"))
    engine.translator._safe_translate_chunk(chunk())
    engine.translator.target_language = TargetLanguage.ENGLISH
    assert engine.translator._get_cache_key(chunk()) not in (original_key, changed_key)
    engine.translator.target_language = TargetLanguage.VIETNAMESE
    engine.translator.endpoint = original_endpoint
    assert engine.translator._get_cache_key(chunk()) == original_key
    engine.translator._safe_translate_chunk(chunk())
    assert engine.send.call_count == 4 and len(engine.cache) == 2


@pytest.mark.parametrize("engine", ["google"], indirect=True)
def test_google_legacy_container_remains_supported(engine):
    engine.send.return_value = response('<div class="t0">A &amp; B.</div>')
    result = engine.translator._safe_translate_chunk(chunk())
    assert all(row.translated_text == "A & B." for row in result)


@pytest.mark.parametrize("engine", ["deeplx"], indirect=True)
def test_deeplx_data_only_response_remains_supported(engine):
    engine.send.return_value = response(json.dumps({"data": "Đã dịch."}))
    result = engine.translator._safe_translate_chunk(chunk())
    assert all(row.translated_text == "Đã dịch." for row in result)


@pytest.mark.parametrize("engine", ["deeplx"], indirect=True)
def test_deeplx_effective_endpoint_controls_cache_identity(engine, monkeypatch):
    explicit_key = engine.translator._get_cache_key(chunk())
    monkeypatch.setenv("DEEPLX_ENDPOINT", f"  {engine.translator.endpoint}  ")
    from_environment = DeepLXTranslator(1, 5, TargetLanguage.VIETNAMESE, 20, None)
    try:
        assert from_environment._get_cache_key(chunk()) == explicit_key
        monkeypatch.setenv("DEEPLX_ENDPOINT", "https://different.invalid/translate")
        overridden = DeepLXTranslator(1, 5, TargetLanguage.VIETNAMESE, 20, None,
                                      endpoint=f"  {engine.translator.endpoint}  ")
        try:
            assert overridden._get_cache_key(chunk()) == explicit_key
        finally:
            overridden.close()
    finally:
        from_environment.close()

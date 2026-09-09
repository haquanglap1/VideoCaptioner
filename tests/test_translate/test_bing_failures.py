"""Bing failures must not publish or cache missing translations."""

import json
from threading import Barrier
from unittest.mock import Mock

import pytest
import requests
from diskcache import Cache

from videocaptioner.core.asr.asr_data import ASRData, ASRDataSeg
from videocaptioner.core.entities import SubtitleProcessData
from videocaptioner.core.translate.bing_translator import BingTranslator
from videocaptioner.core.translate.types import TargetLanguage
from videocaptioner.core.utils.cache import generate_cache_key


def response(payload=None, *, status=200, text=None):
    result = requests.Response()
    result.status_code = status
    result.url = "https://translation.invalid/translate"
    result._content = (text if text is not None else json.dumps(payload)).encode()
    result._content_consumed = True
    return result


def translated(*texts):
    return [{"translations": [{"text": text, "to": "vi"}]} for text in texts]


@pytest.fixture
def engine(monkeypatch, tmp_path):
    with Cache(str(tmp_path / "cache")) as cache:
        session = Mock(spec=requests.Session)
        session.get.return_value = response(text="synthetic-token")
        monkeypatch.setattr(requests, "Session", lambda: session)
        monkeypatch.setattr("videocaptioner.core.translate.base.get_translate_cache", lambda: cache)
        updates = []
        translator = BingTranslator(2, 10, TargetLanguage.VIETNAMESE, updates.append)
        try:
            yield translator, session, cache, updates
        finally:
            translator.close()


def chunk():
    return [SubtitleProcessData(index=i, original_text=text) for i, text in
            enumerate(("First sentence.", "Second sentence."), 1)]


@pytest.mark.parametrize("status", [400, 404, 429, 500])
def test_http_failure_is_not_success_or_cached(engine, status):
    translator, session, cache, updates = engine
    session.post.return_value = response(status=status, text="private-response")
    source = chunk()
    with pytest.raises(RuntimeError, match=f"HTTP {status}") as error:
        translator._safe_translate_chunk(source)
    assert "private-response" not in str(error.value)
    assert not any(row.translated_text for row in source)
    assert not updates and len(cache) == 0
    assert session.post.call_count == 1


@pytest.mark.parametrize("payload", [
    [], translated("Only one."), translated("One.", "Two.", "Extra."),
    translated("One.", ""), translated("One.", "   "),
    translated("One.", {"invalid": "private-response"}),
    [{"translations": [{"text": "One."}]}, {"translations": []}],
    {"error": "private-response"},
])
def test_malformed_batch_is_atomic_and_not_cached(engine, payload):
    translator, session, cache, updates = engine
    session.post.return_value = response(payload)
    source = chunk()
    with pytest.raises(RuntimeError, match="Malformed") as error:
        translator._safe_translate_chunk(source)
    assert "private-response" not in str(error.value)
    assert not any(row.translated_text for row in source)
    assert not updates and len(cache) == 0


def test_auth_refresh_retries_failed_chunk_once(engine):
    translator, session, cache, updates = engine
    session.get.return_value = response(text="replacement-token")
    session.post.side_effect = [response(status=401), response(translated("Một.", "Hai."))]
    result = translator._safe_translate_chunk(chunk())
    assert [row.translated_text for row in result] == ["Một.", "Hai."]
    assert session.post.call_count == 2 and session.get.call_count == 2
    assert session.post.call_args_list[0].kwargs["headers"]["authorization"] == "Bearer synthetic-token"
    assert session.post.call_args_list[1].kwargs["headers"]["authorization"] == "Bearer replacement-token"
    assert len(cache) == 1 and len(updates) == 1


def test_repeated_auth_failure_is_bounded(engine):
    translator, session, cache, updates = engine
    session.post.return_value = response(status=401)
    with pytest.raises(RuntimeError, match="HTTP 401"):
        translator._safe_translate_chunk(chunk())
    assert session.post.call_count == 2 and session.get.call_count == 2
    assert not updates and len(cache) == 0


def test_one_failed_chunk_prevents_successful_document(engine):
    translator, session, _cache, _updates = engine
    translator.batch_num = 1
    session.post.side_effect = [response(translated("Một.")), response(translated("Hai.")), response(status=500)]
    source = ASRData([ASRDataSeg(text=str(i), start_time=i * 1000, end_time=(i + 1) * 1000)
                      for i in range(3)])
    before = source.to_document()
    with pytest.raises(RuntimeError, match="1/3 segments failed"):
        translator.translate_subtitle(source)
    assert source.to_document() == before


def test_old_empty_cache_is_not_reused_and_valid_result_is_cached(engine):
    translator, session, cache, _updates = engine
    old = chunk()
    old_key = f"BingTranslator:{generate_cache_key(old)}:{translator.target_language.value}"
    cache.set(old_key, old)
    session.post.return_value = response(translated("Một.", "Hai."))
    for _ in range(2):
        result = translator._safe_translate_chunk(chunk())
        assert [row.translated_text for row in result] == ["Một.", "Hai."]
    assert session.post.call_count == 1
    assert cache.get(old_key) == old


def test_transport_failure_does_not_expose_response_or_cache(engine):
    translator, session, cache, updates = engine
    session.post.side_effect = requests.Timeout("private-request")
    with pytest.raises(RuntimeError) as error:
        translator._safe_translate_chunk(chunk())
    assert "private-request" not in str(error.value)
    assert not updates and len(cache) == 0


def test_long_subtitle_is_rejected_instead_of_truncated(engine):
    translator, session, cache, updates = engine
    source = [SubtitleProcessData(index=1, original_text="x" * 5001)]
    with pytest.raises(RuntimeError, match="split the long subtitle"):
        translator._safe_translate_chunk(source)
    session.post.assert_not_called()
    assert not updates and len(cache) == 0


def test_cancel_during_request_does_not_publish_or_cache(engine):
    translator, session, cache, updates = engine

    def cancelled_response(*args, **kwargs):
        translator.stop()
        return response(translated("Một.", "Hai."))

    session.post.side_effect = cancelled_response
    source = chunk()
    with pytest.raises(RuntimeError, match="cancelled"):
        translator._safe_translate_chunk(source)
    assert not any(row.translated_text for row in source)
    assert not updates and len(cache) == 0


@pytest.mark.parametrize("auth_response", [response(status=404), response(text=" ")])
def test_authentication_failure_closes_owned_resources(monkeypatch, auth_response):
    session = Mock(spec=requests.Session)
    session.get.return_value = auth_response
    monkeypatch.setattr(requests, "Session", lambda: session)
    monkeypatch.setattr("videocaptioner.core.translate.base.get_translate_cache", lambda: {})
    closed = []
    original_close = BingTranslator.close

    def observe_close(self):
        original_close(self)
        closed.append(self.executor is None and self._closing_executor is None)

    monkeypatch.setattr(BingTranslator, "close", observe_close)
    with pytest.raises(RuntimeError, match="Bing authentication"):
        BingTranslator(1, 10, TargetLanguage.VIETNAMESE, None)
    assert closed == [True]
    session.close.assert_called_once()


def test_concurrent_expired_chunks_share_one_token_refresh(engine):
    translator, session, _cache, _updates = engine
    barrier = Barrier(2)
    translator.batch_num = 1
    session.get.return_value = response(text="replacement-token")

    def post(*args, **kwargs):
        if kwargs["headers"]["authorization"] == "Bearer synthetic-token":
            barrier.wait(timeout=3)
            return response(status=401)
        return response(translated("Đã dịch."))

    session.post.side_effect = post
    source = ASRData([ASRDataSeg(text=str(i), start_time=i * 1000, end_time=(i + 1) * 1000)
                      for i in range(2)])
    result = translator.translate_subtitle(source)
    assert all(seg.translated_text == "Đã dịch." for seg in result)
    assert session.get.call_count == 2
    assert session.post.call_count == 4

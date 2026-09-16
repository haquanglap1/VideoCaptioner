"""Incomplete LLM batches must not become successful source-text fallbacks."""

import json
from types import SimpleNamespace

import pytest

from videocaptioner.core.asr.asr_data import ASRData, ASRDataSeg
from videocaptioner.core.llm.client import LLMCredentials
from videocaptioner.core.translate.llm_translator import LLMTranslator
from videocaptioner.core.translate.types import TargetLanguage


class MemoryCache:
    def __init__(self):
        self.values = {}

    def get(self, key, default=None):
        return self.values.get(key, default)

    def set(self, key, value, expire=None):
        self.values[key] = value

    def delete(self, key):
        self.values.pop(key, None)


@pytest.fixture
def engine(monkeypatch):
    cache = MemoryCache()
    monkeypatch.setattr("videocaptioner.core.translate.base.get_translate_cache", lambda: cache)
    translator = LLMTranslator(
        1, 10, TargetLanguage.VIETNAMESE, "synthetic-model", "", False, None,
        credentials=LLMCredentials("synthetic-key", "https://translation.invalid/v1"),
    )
    try:
        yield translator, cache
    finally:
        translator.stop()


def source_data():
    return ASRData([
        ASRDataSeg("第一句。", 100, 1000, cue_id="synthetic-1"),
        ASRDataSeg("第二句。", 1100, 2000, cue_id="synthetic-2"),
    ])


def response(payload):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(
        content=json.dumps(payload, ensure_ascii=False),
    ))])


@pytest.mark.parametrize("payload", [
    {"1": "Câu thứ nhất."},
    {"1": "Câu thứ nhất.", "2": ""},
    {"1": "Câu thứ nhất.", "2": {"unexpected": "Câu thứ hai."}},
    {"1": "Câu thứ nhất.", "2": "Câu thứ hai.", "3": "Câu ngoài yêu cầu."},
])
def test_invalid_plain_batch_fails_without_publishing_or_caching(engine, monkeypatch, payload):
    translator, cache = engine
    data = source_data()
    before = data.to_document()
    calls = []

    def request(messages):
        calls.append(len(messages))
        return response(payload)

    monkeypatch.setattr(translator, "_request", request)
    with pytest.raises(RuntimeError, match="Malformed"):
        translator.translate_subtitle(data)
    assert len(calls) == translator.MAX_STEPS
    assert data.to_document() == before
    assert not cache.values


def test_repaired_complete_batch_preserves_source_and_is_cached(engine, monkeypatch):
    translator, cache = engine
    data = source_data()
    before = data.to_document()
    calls = []

    def request(messages):
        calls.append(len(messages))
        return response({"1": "Câu thứ nhất."} if len(calls) == 1 else {
            "1": "Câu thứ nhất.", "2": "Câu thứ hai.",
        })

    monkeypatch.setattr(translator, "_request", request)
    result = translator.translate_subtitle(data)
    assert [s.translated_text for s in result.segments] == ["Câu thứ nhất.", "Câu thứ hai."]
    assert [(s.cue_id, s.start_time, s.end_time) for s in result.segments] == [
        ("synthetic-1", 100, 1000), ("synthetic-2", 1100, 2000),
    ]
    assert data.to_document() == before
    assert len(calls) == 2
    assert len(cache.values) == 1
    cached = translator.translate_subtitle(data)
    assert [s.translated_text for s in cached.segments] == ["Câu thứ nhất.", "Câu thứ hai."]
    assert len(calls) == 2

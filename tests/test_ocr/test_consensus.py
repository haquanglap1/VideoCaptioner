from dataclasses import replace

import pytest

from videocaptioner.core.ocr.consensus import CacheScope, CandidateRead, ReadCache, choose_read
from videocaptioner.core.ocr.models import EngineRead, OcrError, ReadLine

from .test_tracking import frame


def read(text, score=0.9):
    return EngineRead(tuple(ReadLine(line, score, ((0, 0), (10, 0), (10, 10), (0, 10)))
                            for line in text.split("\n")), "fixture-revision")


def test_choose_whole_real_read_no_hybrid_and_preserve_script():
    raw = ("學生三人？\n名字", "學生五人？\n名字", "學生三人?\n名字")
    candidates = tuple(CandidateRead(i, str(i), read(text), False) for i, text in enumerate(raw))
    result = choose_read(candidates)
    assert result.text in raw
    assert "engine_disagreement" in result.issues
    assert "uncalibrated_profile" in result.issues


def test_cache_agreement_is_not_independent_verification():
    raw = read("学生三人")
    result = choose_read((CandidateRead(1, "same", raw, False), CandidateRead(2, "same", raw, True)))
    assert "insufficient_independent_crops" in result.issues


def test_cache_scope_and_bounded_eviction(text_image):
    scope = CacheScope("a" * 64, "b" * 64, "c" * 64)
    cache = ReadCache(scope, max_bytes=1000, max_entries=1)
    first, second = frame(text_image(), 0), frame(text_image("学生五人"), 1)
    a, _ = cache.key(first)
    b, _ = cache.key(second)
    assert a != b
    for field in ("source_sha256", "profile_sha256", "policy_sha256"):
        assert ReadCache(replace(scope, **{field: "d" * 64})).key(first)[0] != a
    cache.put(a, read("学生三人"))
    cache.put(b, read("学生五人"))
    assert cache.get(a) is None and cache.get(b).text == "学生五人"
    assert cache.size <= 1000


def test_malformed_score_and_empty_reads():
    cache = ReadCache(CacheScope("a" * 64, "b" * 64, "c" * 64))
    with pytest.raises(OcrError):
        cache.put("key", read("bad", float("nan")))
    result = choose_read((CandidateRead(1, "hash", EngineRead((), "fixture-revision"), False),))
    assert result.text == "" and "empty_engine_read" in result.issues

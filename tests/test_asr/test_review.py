"""Synthetic recognition review; no private transcript, provider account or media."""

import json
import wave
from dataclasses import replace

import httpx
import pytest
from diskcache import Cache

from videocaptioner.core.asr import native_api
from videocaptioner.core.asr.asr_data import ASRData
from videocaptioner.core.asr.native_profiles import NativeASRConfig
from videocaptioner.core.asr.review import (
    EditReviewTimingCommand,
    NativeReview,
    NativeReviewRequired,
    ReviewSession,
)
from videocaptioner.core.editor.commands import CommandStack


def recognition(word="你", speaker="1", provider="soniox"):
    if provider == "soniox":
        return {"text": "先。" + word + "末。", "tokens": [
            {"text": "先。", "start_ms": 100, "end_ms": 900, "speaker": "2"},
            {"text": word, "start_ms": 800, "end_ms": 800, "speaker": speaker},
            {"text": "末。", "start_ms": 1100, "end_ms": 1600},
        ], "headers": {"Authorization": "synthetic-secret"}, "id": "remote-private-id"}
    return {"text": word + " (music)", "words": [
        {"text": word, "start": .8, "end": .8, "speaker_id": speaker, "type": "word"},
        {"text": " ", "type": "spacing"},
        {"text": "(music)", "start": 0, "end": 1, "type": "audio_event"},
    ], "transcription_id": "remote-private-id"}


def capture(value=None, **kwargs):
    return NativeReview.capture(value or recognition(), kwargs.get("provider", "soniox"),
                                "synthetic-model", "local-scope", 2000, True, True)


@pytest.mark.parametrize("word", ["hello", "lo", "你", "中文"])
@pytest.mark.parametrize("speaker", ["1", None])
@pytest.mark.parametrize("provider", ["soniox", "scribe"])
def test_zero_word_subword_cjk_roundtrip_edit_undo_resume(tmp_path, word, speaker, provider):
    review = capture(recognition(word, speaker, provider), provider=provider)
    path = review.save(tmp_path / "recognition.json")
    assert NativeReview.load(path) == review
    assert len(review.issues()) == 1
    assert "synthetic-secret" not in path.read_text(encoding="utf-8")
    assert "remote-private-id" not in path.read_text(encoding="utf-8")
    issue = review.issues()[0]
    with pytest.raises(ValueError, match="review"):
        review.resume()
    session, stack = ReviewSession(review), CommandStack()
    stack.execute(EditReviewTimingCommand(session, issue.token_id, 800, 1000))
    fixed = session.review
    result = fixed.resume()
    edited = next(s for s in result if issue.token_id in s.metadata.token_ids)
    assert edited.metadata.timing == "edited"
    assert edited.metadata.scope == "local-scope"
    assert edited.metadata.speaker == speaker
    assert edited.start_time == 800 and edited.end_time == 1000
    assert review.tokens == fixed.tokens
    assert fixed.overrides[0].source == "user"
    assert stack.undo() and session.review == review and session.review.issues()
    assert stack.redo() and session.review == fixed
    fixed.save(path)
    assert NativeReview.load(path).resume().to_document() == result.to_document()
    out = tmp_path / "accepted.json"
    result.save(str(out))
    assert ASRData.from_subtitle_file(str(out)).to_document() == result.to_document()
    if provider == "soniox":
        assert result.segments[0].end_time > result.segments[1].start_time  # native overlap survives
        assert len(result) == 3
    else:
        assert len(result.events) == 1 and len(result) == 1


@pytest.mark.parametrize("bad", [None, -1, "0.8", float("nan"), True, 3000])
def test_invalid_raw_times_survive_local_storage_without_becoming_valid(tmp_path, bad):
    value = recognition()
    value["tokens"][1]["start_ms"] = bad
    review = capture(value)
    loaded = NativeReview.load(review.save(tmp_path / "invalid.json"))
    assert loaded.issues()
    assert loaded.edit_timing(loaded.tokens[1].id, 800, 950).resume().segments


def test_raw_original_cannot_be_edited_without_explicit_override():
    payload = capture().to_dict()
    payload["tokens"][1]["end"] = 1000
    with pytest.raises(ValueError, match="Invalid ASR review"):
        NativeReview.from_dict(payload)


@pytest.mark.parametrize("start,end", [(1, 1), (-1, 2), (1, 2001), (False, 2), (1.1, 2)])
def test_invalid_user_edit_is_atomic(start, end):
    review = capture()
    session, stack = ReviewSession(review), CommandStack()
    with pytest.raises(ValueError):
        stack.execute(EditReviewTimingCommand(session, review.tokens[1].id, start, end))
    assert session.review == review and not stack.can_undo


def test_resume_revalidates_coverage_and_never_returns_prefix():
    review = capture()
    fixed = review.edit_timing(review.tokens[1].id, 800, 950)
    with pytest.raises(ValueError, match="coverage"):
        replace(fixed, text=fixed.text + "多").resume()


def test_native_failure_keeps_full_review_separate_from_success_cache_and_never_resubmits(tmp_path, monkeypatch):
    audio = tmp_path / "synthetic.wav"
    with wave.open(str(audio), "wb") as handle:
        handle.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
        handle.writeframes(b"\0\0" * 32000)
    cache = Cache(str(tmp_path / "cache"))
    monkeypatch.setattr(native_api, "get_asr_cache", lambda: cache)
    monkeypatch.setattr(native_api, "is_cache_enabled", lambda: True)
    monkeypatch.setattr(native_api, "audio_duration", lambda *a: 2000)
    file_id = "11111111-1111-4111-8111-111111111111"
    job_id = "22222222-2222-4222-8222-222222222222"
    requests = []

    async def server(request):
        requests.append((request.method, request.url.path))
        if request.method == "DELETE":
            return httpx.Response(204)
        if request.method == "POST":
            return httpx.Response(200, json={"id": file_id if request.url.path.endswith("files") else job_id})
        if request.url.path.endswith("transcript"):
            return httpx.Response(200, json=recognition())
        return httpx.Response(200, json={"status": "completed"})

    job = native_api.NativeASR(str(audio), NativeASRConfig("soniox", api_key="test-only"),
                               transport=httpx.MockTransport(server))
    try:
        with pytest.raises(NativeReviewRequired) as caught:
            job.run()
        error = caught.value
        assert error.path.is_file() and job.state.status == "review_required"
        assert len(cache) == 0 and job.state.remote == "deleted"
        assert len([m for m, _ in requests if m == "POST"]) == 2
        assert [p for m, p in requests if m == "DELETE"] == [f"/v1/transcriptions/{job_id}", f"/v1/files/{file_id}"]
        before = list(requests)
        review = NativeReview.load(error.path)
        fixed = review.edit_timing(review.tokens[1].id, 800, 950)
        fixed.resume()
        assert requests == before and len(cache) == 0
        assert "test-only" not in json.dumps(review.to_dict())
        assert "先。" not in str(error)
    finally:
        cache.close()


def test_grouped_resume_keeps_all_token_associations_and_marks_edits():
    value = {"text": "Hello world", "tokens": [
        {"text": "Hel", "start_ms": 10, "end_ms": 100, "speaker": "1"},
        {"text": "lo", "start_ms": 100, "end_ms": 200, "speaker": "1"},
        {"text": " world", "start_ms": 200, "end_ms": 200, "speaker": "1"},
    ]}
    review = replace(capture(value), word_timing=False)
    fixed = review.edit_timing(review.tokens[2].id, 200, 900)
    result = fixed.resume()
    assert "".join(s.text for s in result) == value["text"]
    assert [t for s in result for t in s.metadata.token_ids] == [t.id for t in review.tokens]
    assert result.segments[-1].metadata.timing == "edited"
    assert len(result) == 1

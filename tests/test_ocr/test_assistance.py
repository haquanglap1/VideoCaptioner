"""Text drafts must not become OCR evidence or leak more than one candidate."""

import json
from dataclasses import replace
from types import SimpleNamespace

import pytest

from tests.test_ocr.test_document import make_document
from videocaptioner.core.llm.client import LLMCredentials
from videocaptioner.core.ocr.assistance import OcrDraftSettings, comparison_note, translate_draft
from videocaptioner.core.ocr.models import OcrError


def settings():
    return OcrDraftSettings(LLMCredentials("synthetic-key", "https://example.test/v1"), "synthetic-model", 300)


def response(content=None, *, finish="stop", usage=None):
    if content is None:
        content = json.dumps({"translation_vi": "Ba học sinh\nNăm 2026.", "uncertainties_vi": []}, ensure_ascii=False)
    return SimpleNamespace(choices=[SimpleNamespace(finish_reason=finish, message=SimpleNamespace(content=content))],
                           usage=usage)


def test_draft_sends_only_selected_text_preserves_review_and_records_usage():
    doc = make_document(("学生三人\n2026年。", "学生五人\n2026年。"))
    before = doc.to_dict()
    candidate = doc.cues[0].candidates[1]
    sent = []

    def send(**kwargs):
        sent.append(kwargs)
        return response(usage=SimpleNamespace(prompt_tokens=21, completion_tokens=18))

    draft = translate_draft(doc, candidate, settings(), request=send)
    assert len(sent) == 1
    assert json.loads(sent[0]["messages"][1]["content"]) == {"source_text": candidate.raw.text}
    payload = json.dumps(sent)
    assert doc.id not in payload and doc.visual_source.snapshot_sha256 not in payload and "synthetic-key" not in payload
    assert "image_url" not in payload and "学生三人" not in sent[0]["messages"][1]["content"]
    assert sent[0]["max_completion_tokens"] == 1000
    assert draft.document_id == doc.id and draft.candidate_id == candidate.id and draft.source_text == candidate.raw.text
    assert (draft.prompt_tokens, draft.completion_tokens) == (21, 18)
    assert doc.to_dict() == before and doc.pending_issues
    assert doc.cues[0].selected_candidate_id is None


@pytest.mark.parametrize("content,finish", [
    ('{"translation_vi":"x","uncertainties_vi":[],"accepted":true}', "stop"),
    ('{"translation_vi":"x","translation_vi":"y","uncertainties_vi":[]}', "stop"),
    ('{"translation_vi":"","uncertainties_vi":[]}', "stop"),
    ('{"translation_vi":"x","uncertainties_vi":"uncertain"}', "stop"),
    ('{"translation_vi":"x","uncertainties_vi":[1]}', "stop"),
    ('{"translation_vi":"x","uncertainties_vi":["", "note"]}', "stop"),
    ('{"translation_vi":"x","uncertainties_vi":[]}', "length"),
    ('{"translation_vi":"x","uncertainties_vi":[]}', "content_filter"),
    (None, "stop"),
    ("[]", "stop"),
    ("```json\n{}\n```", "stop"),
    ("x" * 8193, "stop"),
], ids=["extra-field", "duplicate", "empty", "wrong-notes-type", "nontext-note", "empty-note",
        "truncated", "filtered", "no-content", "array", "markdown", "too-long"])
def test_bad_response_keeps_review_without_retry(content, finish):
    doc = make_document()
    calls = []

    def send(**kwargs):
        calls.append(kwargs)
        value = response("{}", finish=finish)
        value.choices[0].message.content = content
        return value

    with pytest.raises(OcrError, match="không hợp lệ"):
        translate_draft(doc, doc.cues[0].candidates[0], settings(), request=send)
    assert len(calls) == 1 and doc.pending_issues


def test_unknown_candidate_or_empty_text_never_sends():
    doc = make_document()

    def forbidden(**_):
        pytest.fail("No request should be sent")

    other = make_document(("其他",)).cues[0].candidates[0]
    with pytest.raises(OcrError, match="không thuộc"):
        translate_draft(doc, other, settings(), request=forbidden)
    empty = make_document(("",))
    with pytest.raises(OcrError, match="rỗng"):
        translate_draft(empty, empty.cues[0].candidates[0], settings(), request=forbidden)


def test_cancel_after_response_discards_draft_and_sanitizes_failure():
    doc = make_document()
    cancelled = False

    def check():
        if cancelled:
            raise OcrError("Cancelled synthetic task")

    def send(**_):
        nonlocal cancelled
        cancelled = True
        return response()

    with pytest.raises(OcrError, match="Cancelled"):
        translate_draft(doc, doc.cues[0].candidates[0], settings(), request=send, check=check)

    def fail(**_):
        raise RuntimeError("synthetic-secret and private transcript")

    with pytest.raises(OcrError) as error:
        translate_draft(doc, doc.cues[0].candidates[0], settings(), request=fail)
    assert "synthetic-secret" not in str(error.value) and "private transcript" not in str(error.value)


def test_owned_request_uses_finite_timeout_and_cancel_callback(monkeypatch):
    doc = make_document()
    seen = []

    def owned(credentials, timeout, cancelled, *, log_content):
        seen.append((credentials, timeout, cancelled(), log_content))
        return lambda **_: response()

    monkeypatch.setattr("videocaptioner.core.ocr.assistance.OwnedLLMRequest", owned)
    draft = translate_draft(doc, doc.cues[0].candidates[0], settings())
    assert seen == [(settings().credentials, 300, False, False)]
    assert draft.prompt_tokens is None and draft.completion_tokens is None
    assert "synthetic-key" not in repr(settings())


@pytest.mark.parametrize("texts,expected", [
    (("学生三人", "学生三人"), "vẫn có thể cùng bỏ sót chữ"),
    (("学生三人？", "学生三人?"), "còn khác dấu câu"),
    (("学生三人", "学生五人"), "khác chữ hoặc số"),
    (("学生三人", ""), "rỗng hoặc thiếu"),
])
def test_comparison_does_not_guess_which_candidate_is_correct(texts, expected):
    cue = make_document(texts).cues[0]
    assert expected in comparison_note(cue)
    assert expected in comparison_note(replace(cue, candidates=tuple(reversed(cue.candidates))))

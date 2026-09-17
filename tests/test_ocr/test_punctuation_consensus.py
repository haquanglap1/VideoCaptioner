"""Synthetic crop evidence; no transcripts or media from the quality pilot."""

import hashlib
from dataclasses import replace
from fractions import Fraction

import pytest
from PIL import Image, ImageDraw

from videocaptioner.core.ocr.consensus import CandidateRead, choose_read
from videocaptioner.core.ocr.models import EngineRead, ReadLine
from videocaptioner.core.ocr.punctuation_consensus import choose_witnessed_read

from .test_tracking import frame


def sample(dots=3, *, score=.99, right=100, text="sample", index=0):
    image = Image.new("RGB", (200, 60), (40, 40, 40))
    draw = ImageDraw.Draw(image)
    draw.text((12, 14), "sample", fill="white")
    for x in range(110, 110 + dots * 12, 12):
        draw.ellipse((x, 24, x + 3, 27), fill="white")
    value = frame(image, index)
    raw = EngineRead((ReadLine(text, score, ((10, 10), (right, 10), (right, 42), (10, 42))),), "test-revision")
    return CandidateRead(value.pts, hashlib.sha256(value.rgb).hexdigest(), raw, False), value


def test_visible_tail_must_not_lose_to_confidence_of_clipped_crop():
    short, first = sample()
    whole, last = sample(score=.98, right=145, text="sample...", index=1)
    assert choose_read((short, whole)).selected_index == 0
    result = choose_witnessed_read((short, whole), (first, last))
    assert result.selected_index == 1
    assert result.text == whole.text
    assert "engine_disagreement" in result.issues


@pytest.mark.parametrize("dots,text,right", [(0, "sample...", 145), (2, "sample...", 145),
                                           (3, "sample?", 145), (3, "sampleX...", 145),
                                           (3, "sample...", 100), (3, "different...", 145)])
def test_no_promotion_without_unchanged_ink_and_clipped_dot_tail(dots, text, right):
    short, first = sample(dots=dots)
    whole, last = sample(score=.98, right=right, text=text, index=1)
    assert choose_witnessed_read((short, whole), (first, last)) == choose_read((short, whole))


def test_frame_hash_and_revision_are_required():
    short, first = sample()
    whole, last = sample(score=.98, right=145, text="sample...", index=1)
    for candidates, frames in [((replace(short, crop_sha256="0" * 64), whole), (first, last)),
                               ((short, whole), (first,)),
                               ((short, replace(whole, raw=replace(whole.raw, revision="other"))), (first, last))]:
        assert choose_witnessed_read(candidates, frames) == choose_read(candidates)


def test_cache_flag_does_not_change_selection_or_remove_issues():
    short, first = sample()
    whole, last = sample(score=.98, right=145, text="sample...", index=1)
    result = choose_witnessed_read((short, whole), (first, last))
    cached = tuple(replace(c, cache_hit=True) for c in (short, whole))
    assert choose_witnessed_read(cached, (first, last)) == result
    assert "uncalibrated_profile" in result.issues


@pytest.mark.parametrize("change", ["fade", "shift", "extra-dot", "multiline", "same-box"])
def test_uncertain_or_changed_punctuation_keeps_baseline(change):
    short, first = sample()
    whole, last = sample(score=.98, right=145, text="sample...", index=1)
    if change in ("fade", "shift"):
        image = Image.frombytes("RGB", (first.width, first.height), first.rgb)
        if change == "fade":
            image = image.point(lambda level: level // 2)
        else:
            image = image.transform(image.size, Image.Transform.AFFINE, (1, 0, 5, 0, 1, 0))
        first = replace(first, rgb=image.tobytes())
        short = replace(short, crop_sha256=hashlib.sha256(first.rgb).hexdigest())
    elif change == "extra-dot":
        whole, last = sample(dots=4, score=.98, right=160, text="sample....", index=1)
    elif change == "multiline":
        whole = replace(whole, raw=replace(whole.raw, lines=whole.raw.lines * 2))
    else:
        short = replace(short, raw=replace(short.raw, lines=(replace(short.raw.lines[0], box=whole.raw.lines[0].box),)))
    assert choose_witnessed_read((short, whole), (first, last)) == choose_read((short, whole))


def test_pipeline_routes_version_and_cache_without_rewriting_raw():
    from videocaptioner.core.ocr.consensus import CacheScope, ReadCache
    from videocaptioner.core.ocr.pipeline import OcrPipeline
    from videocaptioner.core.ocr.punctuation_consensus import POLICY
    from videocaptioner.core.ocr.tracking import TrackedRegion

    short, first = sample()
    whole, last = sample(score=.98, right=145, text="sample...", index=1)
    # Distinct image bytes make this a real cache-parity test instead of two equal keys.
    raw = bytearray(last.rgb)
    raw[0] += 1
    last = replace(last, rgb=bytes(raw))
    region = TrackedRegion(Fraction(0), Fraction(200), first.pts, last.pts, (first, last), (),
                           (Fraction(0), Fraction(0)), (Fraction(200), Fraction(200)))
    calls = []
    def recognize(value, check):
        check()
        calls.append(value.pts)
        return short.raw if value.pts == first.pts else whole.raw
    pipeline = OcrPipeline(recognize, ReadCache(CacheScope("a" * 64, "b" * 64, "c" * 64)),
                           consensus_policy=POLICY)
    fresh = pipeline._recognize(region)
    cached = pipeline._recognize(region)
    assert fresh.consensus == cached.consensus
    assert fresh.consensus.selected_index == 1
    assert tuple(c.raw for c in fresh.reads) == (short.raw, whole.raw)
    assert calls == [first.pts, last.pts]
    assert pipeline.metrics.fresh_calls == pipeline.metrics.cache_hits == 2


def test_version_changes_document_identity_and_resume_requires_same_policy():
    from videocaptioner.core.ocr.document import OcrDocument, document_id
    from videocaptioner.core.ocr.models import OcrError
    from videocaptioner.core.ocr.punctuation_consensus import POLICY
    from videocaptioner.core.ocr.resume import validate_resume

    from .test_document import make_document

    old = make_document()
    config = replace(old.config, consensus_policy=POLICY)
    assert document_id(old.visual_source, config) != old.id
    new = OcrDocument(document_id(old.visual_source, config), old.visual_source, config, (), False)
    assert OcrDocument.from_dict(new.to_dict()) == new
    validate_resume(new, config)
    with pytest.raises(OcrError):
        validate_resume(new, old.config)
    assert OcrDocument.from_dict(old.to_dict()) == old
    with pytest.raises(OcrError, match="consensus"):
        replace(config, consensus_policy="unknown")

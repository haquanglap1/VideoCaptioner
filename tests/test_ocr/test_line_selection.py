"""Spatial selection, raw lineage and backward compatibility; no OCR inference."""

from dataclasses import replace
from fractions import Fraction

import pytest

from videocaptioner.core.asr.asr_data import ASRData
from videocaptioner.core.ocr.codec import digest
from videocaptioner.core.ocr.consensus import CacheScope, CandidateRead, ReadCache, choose_read
from videocaptioner.core.ocr.document import OcrDocument, cue_from_region, document_id
from videocaptioner.core.ocr.line_selection import LineSelectionPolicy, selected_text
from videocaptioner.core.ocr.models import EngineRead, OcrError, ReadLine, RoiFrame
from videocaptioner.core.ocr.pipeline import OcrPipeline, RegionResult
from videocaptioner.core.ocr.resume import validate_resume
from videocaptioner.core.ocr.tracking import TrackedRegion

from .test_document import make_document


def line(text, x=80, y=8, width=300, height=64, score=.9):
    return ReadLine(text, score, ((float(x), float(y)), (float(x + width), float(y)),
                                 (float(x + width), float(y + height)), (float(x), float(y + height))))


def selected_document():
    old = make_document()
    config = replace(old.config, line_selection=LineSelectionPolicy())
    raw = EngineRead((line("  e\u0301，學生 "), line("Menu", y=90, height=15),
                      line("。", x=390, y=66, width=10, height=10)), config.profile_sha256)
    identifier = document_id(old.visual_source, config)
    read = CandidateRead(3200, "1" * 64, raw, False, config.line_selection.select(raw, 120))
    region = RegionResult(Fraction(200), Fraction(500), (read,), choose_read((read,)), (),
                          (Fraction(200), Fraction(200)), (Fraction(500), Fraction(500)), 3200, 3400)
    return OcrDocument(identifier, old.visual_source, config, (cue_from_region(identifier, region),), True)


def test_detached_punctuation_and_unicode_survive_without_modifying_raw():
    doc = selected_document()
    cue = doc.cues[0]
    assert cue.text == "  e\u0301，學生 \n。"
    assert cue.raw_text == "  e\u0301，學生 \nMenu\n。"
    assert cue.candidates[0].selected_line_indices == (0, 2)
    assert cue.selected_candidate_id is None and cue.edited_text is None and not cue.resolved_issues
    assert not doc.export_issues


def test_two_anchors_keep_second_line_and_one_frame_punctuation_change():
    policy = LineSelectionPolicy((.25, .75))
    for ending in ("。", "！", "。"):
        raw = EngineRead((line("First", y=8, height=25), line("UI", y=43, height=10),
                          line("Second" + ending, y=63, height=25)), "fixture")
        assert selected_text(raw, policy.select(raw, 100)) == "First\nSecond" + ending
    assert policy.select(EngineRead((), "fixture"), 100) == ()


def test_same_row_and_mixed_boxes_are_retained_as_observed_not_repaired():
    raw = EngineRead((line("Subtitle + UI"), line("Same-row background", x=450)), "fixture")
    assert selected_text(raw, LineSelectionPolicy().select(raw, 100)) == raw.text
    # A distant UI bullet cannot attach through another punctuation fragment.
    raw = EngineRead((line("Target"), line("。", x=400, y=68, width=10, height=8),
                      line("•", x=432, y=68, width=8, height=8)), "fixture")
    assert LineSelectionPolicy().select(raw, 100) == (0, 1)


@pytest.mark.parametrize("anchors", [(), (.8, .2), (.5, .5), (float("nan"),), (0,), (1,), (True,)])
def test_invalid_positions_are_processing_errors(anchors):
    with pytest.raises(OcrError):
        LineSelectionPolicy(anchors)


def test_cache_pipeline_consensus_and_empty_selection_use_selected_lines():
    doc = selected_document()
    raw = doc.cues[0].candidates[0].raw
    frame = RoiFrame(0, 3200, Fraction(1, 1000), Fraction(200), 640, 120, b"x" * (640 * 120 * 3))
    region = TrackedRegion(Fraction(200), Fraction(500), 3200, 3400, (frame,), (),
                           (Fraction(200), Fraction(200)), (Fraction(500), Fraction(500)))
    cache = ReadCache(CacheScope("a" * 64, "b" * 64, "c" * 64))
    pipeline = OcrPipeline(lambda *_: raw, cache, line_selection=doc.config.line_selection)
    before = digest(raw)
    first, warm = pipeline._recognize(region), pipeline._recognize(region)
    assert first.consensus.text == warm.consensus.text == doc.cues[0].text
    assert pipeline.metrics.fresh_calls == 1 and pipeline.metrics.cache_hits == 1
    assert first.reads[0].raw is raw and warm.reads[0].raw is raw and digest(raw) == before
    # A high-confidence UI row must not affect candidate choice.
    other_raw = EngineRead((replace(raw.lines[0], score=.8), replace(raw.lines[1], score=1),
                            replace(raw.lines[2], score=.8)), raw.revision)
    other = CandidateRead(3300, "2" * 64, other_raw, False, (0, 2))
    assert choose_read((other, first.reads[0])).selected_index == 1
    empty = OcrPipeline(lambda *_: raw, cache, line_selection=LineSelectionPolicy((.99,)))._recognize(region)
    config = replace(doc.config, line_selection=LineSelectionPolicy((.99,)))
    identifier = document_id(doc.visual_source, config)
    incomplete_text = OcrDocument(identifier, doc.visual_source, config, (cue_from_region(identifier, empty),), True)
    assert any("empty_engine_read" in issue for issue in incomplete_text.export_issues)


def test_export_metadata_roundtrip_and_resume_keep_selection_and_old_ids(tmp_path):
    doc = selected_document()
    before = doc.to_dict()
    path = tmp_path / "selected.json"
    doc.save(path)
    assert OcrDocument.load(path) == doc
    data = doc.resume(doc.visual_source)
    output = tmp_path / "subtitles.json"
    data.save(str(output))
    reopened = ASRData.from_subtitle_file(str(output))
    assert reopened.segments[0].text == doc.cues[0].text
    assert reopened.segments[0].ocr_metadata.observations == doc.cues
    assert doc.to_dict() == before
    partial = replace(doc, complete=False)
    validate_resume(partial, doc.config)
    with pytest.raises(OcrError):
        validate_resume(partial, replace(doc.config, line_selection=None))
    with pytest.raises(OcrError):
        partial.resume(doc.visual_source)
    legacy = make_document(approved=True)
    payload = legacy.to_dict()
    assert "line_selection" not in payload["config"]
    assert all("selected_line_indices" not in c for c in payload["cues"][0]["candidates"])
    assert OcrDocument.from_dict(payload) == legacy
    assert legacy.id != doc.id


@pytest.mark.parametrize("indices", [[1], [], [0, 2, 2], [True], [99], None])
def test_saved_line_selection_cannot_be_forged(indices):
    payload = selected_document().to_dict()
    payload["cues"][0]["candidates"][0]["selected_line_indices"] = indices
    with pytest.raises(OcrError):
        OcrDocument.from_dict(payload)

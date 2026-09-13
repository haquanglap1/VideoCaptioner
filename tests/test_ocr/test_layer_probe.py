"""Contract checks for the offline experiment; passing these does not accept its policy."""

import hashlib
import json
from dataclasses import replace
from fractions import Fraction
from pathlib import Path

import pytest
from PIL import Image

from scripts.ocr_layer_probe import (
    expected_spans,
    fixtures,
    line_fixtures,
    main,
    measure,
    persistent_edges,
    probe_signals,
    propose_lines,
    saved_evidence,
    signature,
    spans,
)
from videocaptioner.core.ocr.codec import digest
from videocaptioner.core.ocr.consensus import CandidateRead, choose_read
from videocaptioner.core.ocr.document import OcrDocument, cue_from_region
from videocaptioner.core.ocr.models import EngineRead, OcrError, ReadLine
from videocaptioner.core.ocr.pipeline import RegionResult
from videocaptioner.core.ocr.tracking import EdgeSignature

from .test_document import make_document


def test_filter_cannot_create_edges_absent_from_center():
    full = EdgeSignature((0xffff,), 16, 100)
    center = EdgeSignature((0x0fff,), 12, 80)
    result = persistent_edges((full, full, center, full, full))
    assert result.tiles == center.tiles
    assert result.strength == center.strength
    blank = EdgeSignature((), 0, 0)
    assert not persistent_edges((full, full, blank, full, full)).present


def test_short_real_change_is_lost_and_must_not_be_called_a_fix():
    # Even with perfect masks and no background, one-frame glyph evidence is erased.
    original = EdgeSignature((0xffff,), 16, 100)
    changed = EdgeSignature((0xffffffff,), 32, 100)
    inputs = [original] * 5 + [changed] + [original] * 5
    assert spans(inputs, 0) == [(0, 5), (5, 6), (6, 11)]
    assert spans(probe_signals(inputs), 2) == [(2, 9)]


@pytest.mark.parametrize("count", [0, 1, 4, 6])
def test_no_padding_or_fake_temporal_observations(count):
    with pytest.raises(OcrError, match="five real"):
        persistent_edges((EdgeSignature((), 0, 0),) * count)


def test_geometry_change_and_short_selection_are_errors():
    with pytest.raises(OcrError, match="geometry"):
        persistent_edges((EdgeSignature((1,), 1, 1),) * 4 + (EdgeSignature((1, 2), 2, 1),))
    with pytest.raises(OcrError, match="context"):
        probe_signals([EdgeSignature((), 0, 0)] * 4)


def test_three_frame_change_and_blank_repeat_remain_separate():
    first = EdgeSignature((0xffff,), 16, 100)
    second = EdgeSignature((0xffffffff,), 32, 100)
    blank = EdgeSignature((), 0, 0)
    result = spans(probe_signals([first] * 5 + [second] * 3 + [blank] * 5 + [first] * 5), 2)
    assert result == [(2, 5), (5, 8), (13, 16)]


def test_line_proposal_keeps_raw_unicode_order_and_provenance():
    small = ReadLine("Menu", 1, ((0, 0), (30, 0), (30, 10), (0, 10)))
    first = ReadLine("  e\u0301，學生。 ", 0.1, ((0, 0), (100, 0), (100, 50), (0, 50)))
    second = ReadLine("１２件！", 0.2, ((0, 55), (100, 55), (100, 90), (0, 90)))
    raw = EngineRead((first, small, second), "fixture")
    before = digest(raw)
    proposal = propose_lines(raw)
    assert proposal.raw is raw and digest(raw) == before
    assert proposal.indices == (0, 2)
    assert proposal.rejected_indices == (1,)
    assert proposal.text == first.text + "\n" + second.text


def test_size_selection_rejection_cases_are_visible():
    results = {row["name"]: row for row in line_fixtures()}
    assert results["small_background"]["accept"]
    assert results["two_lines"]["accept"]
    for name in ("punctuation_fragment", "equal_size_background", "mixed_single_box"):
        assert not results[name]["accept"]
    assert all(row["raw_unchanged"] for row in results.values())


def test_zero_height_line_is_processing_error():
    raw = EngineRead((ReadLine("text", 1, ((0, 0), (5, 0), (5, 0), (0, 0))),), "fixture")
    with pytest.raises(OcrError, match="geometry"):
        propose_lines(raw)


def test_authored_timing_preserves_repeat_and_single_frame_change():
    assert expected_spans(["A", "A", "", "A", "B", "A", ""]) == [(0, 2), (3, 4), (4, 5), (5, 6)]


def test_fast_scrolling_blank_is_suppressed_without_false_subtitles():
    cases = fixtures(Path(__file__).parents[2] / "resource/fonts/NotoSansSC-Regular.ttf")
    case = next(case for case in cases if case.name == "blank_scrolling")
    result = measure(case)
    assert result["expected_spans"] == []
    assert result["clean_overlay_spans"] == []
    assert result["proposed_spans"] == []
    assert result["accept"]


def test_solid_roi_does_not_acquire_edges():
    item = signature(Image.new("RGB", (1128, 94), "white"), 420)
    assert not persistent_edges((item,) * 5).present


def test_probe_refuses_existing_output_before_reading_any_evidence(tmp_path):
    marker = tmp_path / "receipt.json"
    marker.write_text(json.dumps({"old": True}))
    with pytest.raises(FileExistsError):
        main(["--output", str(tmp_path)])
    assert json.loads(marker.read_text()) == {"old": True}


@pytest.fixture
def saved_probe_fixture(tmp_path, text_image):
    image = text_image()
    crop_hash = hashlib.sha256(image.tobytes()).hexdigest()
    document = make_document()
    raw = document.cues[0].candidates[0].raw
    reads = (CandidateRead(3202, crop_hash, raw, False),)
    region = RegionResult(Fraction(200), Fraction(205), reads, choose_read(reads), (),
                          (Fraction(200), Fraction(200)), (Fraction(205), Fraction(205)), 3200, 3204)
    document = replace(document, cues=(cue_from_region(document.id, region),), complete=False)
    checkpoint = tmp_path / "partial.ocr.json"
    document.save(checkpoint)
    diagnosis = tmp_path / "diagnosis"
    roi = diagnosis / "roi"
    roi.mkdir(parents=True)
    observations = []
    for pts in range(3200, 3205):
        image.save(roi / f"pts-{pts}.png")
        observations.append({"pts": pts, "crop_sha256": crop_hash})
    (diagnosis / "frame-observations.json").write_text(json.dumps(observations))
    output = tmp_path / "probe"
    output.mkdir()
    return diagnosis, checkpoint, output


def test_partial_checkpoint_remains_partial_and_proposals_cannot_be_exported(saved_probe_fixture):
    diagnosis, checkpoint, output = saved_probe_fixture
    original = checkpoint.read_bytes()
    result = saved_evidence(diagnosis, checkpoint, output)
    assert result["frames_verified"] == 5 and result["candidate_crops_verified"] == 1
    assert checkpoint.read_bytes() == original
    document = OcrDocument.load(checkpoint)
    assert not document.complete
    assert document.export_issues
    assert document.cues[0].selected_candidate_id is None
    proposals = json.loads((output / "line-proposals.local.json").read_text(encoding="utf-8"))
    row = proposals["proposals"][0]
    assert row["candidate_id"] == document.cues[0].candidates[0].id
    assert row["proposed_text"] == document.cues[0].candidates[0].raw.text
    assert row["frame_pts"] == 3202
    assert proposals["checkpoint_sha256"] == hashlib.sha256(original).hexdigest()
    with pytest.raises(OcrError):
        OcrDocument.from_dict(proposals)


@pytest.mark.parametrize("corruption", ["pixels", "geometry", "pts"])
def test_saved_evidence_mismatch_does_not_create_proposals(saved_probe_fixture, corruption):
    diagnosis, checkpoint, output = saved_probe_fixture
    original = checkpoint.read_bytes()
    if corruption in ("pixels", "geometry"):
        size = (640, 120) if corruption == "pixels" else (320, 60)
        Image.new("RGB", size, "red").save(diagnosis / "roi/pts-3200.png")
    else:
        path = diagnosis / "frame-observations.json"
        rows = json.loads(path.read_text())
        rows[1]["pts"] = rows[0]["pts"]
        path.write_text(json.dumps(rows))
    with pytest.raises(OcrError):
        saved_evidence(diagnosis, checkpoint, output)
    assert checkpoint.read_bytes() == original
    assert list(output.iterdir()) == []

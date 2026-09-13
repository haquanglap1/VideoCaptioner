"""Regressions for the independent probe; harness pass does not accept the hypothesis."""

import hashlib
import json
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from scripts.ocr_layer_probe import Fixture, signature, spans
from scripts.ocr_style_probe import (
    exact_line_subsets,
    main,
    measure_style,
    saved_style_evidence,
    style_cases,
    style_mask,
    text_reachability,
)
from videocaptioner.core.ocr.codec import digest
from videocaptioner.core.ocr.document import OcrDocument
from videocaptioner.core.ocr.models import EngineRead, OcrError, ReadLine

from . import test_layer_probe as layer_tests

saved_probe_fixture = layer_tests.saved_probe_fixture


def dot_image(x=12):
    image = Image.new("RGB", (64, 32), (248, 248, 248))
    draw = ImageDraw.Draw(image)
    draw.rectangle((x + 3, 15, x + 5, 17), fill=(50, 50, 50))
    draw.rectangle((x, 12, x + 2, 14), fill="white")
    return image


def symbol_image(x=12):
    image = dot_image(x)
    draw = ImageDraw.Draw(image)
    draw.rectangle((x + 11, 15, x + 13, 17), fill=(50, 50, 50))
    draw.rectangle((x + 8, 12, x + 10, 14), fill="white")
    return image


def test_detached_small_punctuation_is_retained_without_height_pruning():
    result = style_mask(dot_image())
    assert result.histogram()[255] == 9
    assert result.getpixel((12, 12)) == 255


def test_isolated_dot_pixels_survive_but_do_not_meet_tracker_presence_floor():
    mask = style_mask(dot_image())
    assert mask.histogram()[255] == 9
    assert not signature(mask, 0).present


def test_one_frame_change_and_repeat_after_blank_are_not_temporally_erased():
    first, changed = symbol_image(), symbol_image(36)
    blank = Image.new("RGB", first.size, (248, 248, 248))
    images = [first, first, changed, first, blank, first]
    assert spans([signature(style_mask(im), i) for i, im in enumerate(images)]) == [
        (0, 2), (2, 3), (3, 4), (5, 6)]


@pytest.mark.parametrize("color", [(0, 0, 0), (248, 248, 248), (255, 255, 255)])
def test_solid_background_and_spatial_borders_create_no_stroke(color):
    assert style_mask(Image.new("RGB", (32, 32), color)).getbbox() is None


def test_selected_pixels_are_observed_bright_pixels_input_is_unchanged():
    image = dot_image()
    before = image.tobytes()
    selected = style_mask(image)
    observed_bright = image.convert("L").point([255 if v >= 248 else 0 for v in range(256)])
    assert all(not a or b for a, b in zip(selected.tobytes(), observed_bright.tobytes()))
    assert image.tobytes() == before


def test_dark_glyph_hole_is_a_false_positive_not_semantic_subtitle_evidence():
    image = Image.new("RGB", (32, 32), (248, 248, 248))
    draw = ImageDraw.Draw(image)
    draw.rectangle((8, 8, 22, 22), fill=50)
    draw.rectangle((12, 12, 17, 17), fill=(248, 248, 248))
    assert style_mask(image).getbbox() is not None


def test_invalid_image_and_fixture_geometry_are_processing_errors():
    with pytest.raises(OcrError, match="at least"):
        style_mask(Image.new("RGB", (8, 32)))
    fixture = Fixture("bad", [dot_image()], [], ["x"])
    with pytest.raises(OcrError, match="counts"):
        measure_style(fixture)
    fixture.clean_images = [Image.new("RGB", (32, 32))]
    with pytest.raises(OcrError, match="geometry"):
        measure_style(fixture)


def test_author_pixel_metric_catches_missing_strokes_even_with_correct_span():
    image = symbol_image()
    draw = ImageDraw.Draw(image)
    # A visible white fragment without a qualifying shadow must count as missing.
    draw.rectangle((48, 12, 49, 13), fill="white")
    result = measure_style(Fixture("lost_fragment", [image], [image], ["authored"]))
    assert result["tracking_accept"]
    assert not result["pixel_accept"]
    assert result["pixel_metrics"][0]["target_visible_pixels_lost"] == 4


def test_same_style_background_cannot_be_proven_subtitle_from_appearance():
    cases = style_cases(Path(__file__).parents[2] / "resource/fonts/NotoSansSC-Regular.ttf")
    assert {c.name for c in cases} >= {"fade", "paused_background", "two_lines", "brief_one_character"}
    case = cases[-1]
    assert case.images[0].tobytes() == cases[0].clean_images[0].tobytes()
    result = measure_style(case)
    assert result["expected_spans"] == []
    assert result["proposed_spans"]
    assert not result["accept"]


def test_whole_line_oracle_preserves_unicode_order_whitespace_and_raw():
    def line(text):
        return ReadLine(text, 0.1, ((0, 0), (10, 0), (10, 10), (0, 10)))
    first, period = " e\u0301，學生 ", "。"
    raw = EngineRead((line(first), line("Menu"), line(period)), "fixture")
    before = digest(raw)
    assert exact_line_subsets(raw, first + "\n" + period) == ((0, 2),)
    assert exact_line_subsets(raw, " é，學生 \n。") == ()
    assert digest(raw) == before


def test_mixed_box_is_unreachable_even_with_perfect_line_selection():
    results = {row["name"]: row for row in text_reachability()}
    assert results["punctuation_fragment"]["exact_subsets"] == ((0, 1),)
    assert results["equal_size_background"]["target_reachable"]
    assert not results["mixed_single_box"]["target_reachable"]
    assert not any(r["selection_algorithm_measured"] for r in results.values())


def test_oracle_bound_is_not_a_limit_on_product_ocr():
    line = ReadLine("x", 1, ((0, 0), (10, 0), (10, 10), (0, 10)))
    with pytest.raises(OcrError, match="12 raw lines"):
        exact_line_subsets(EngineRead((line,) * 13, "fixture"), "x")


def test_existing_output_is_refused_without_touching_it(tmp_path):
    marker = tmp_path / "receipt.json"
    marker.write_bytes(b"existing evidence")
    with pytest.raises(FileExistsError):
        main(["--output", str(tmp_path)])
    assert marker.read_bytes() == b"existing evidence"


def mapping_file(checkpoint, tmp_path):
    source = OcrDocument.load(checkpoint).visual_source
    mapping = tmp_path / "video-inputs.json"
    # Nonexistent path proves that replay does not open the original source video.
    mapping.write_text(json.dumps([{"video": 2, "source": "not-opened.mp4",
                                    "source_sha256": source.snapshot_sha256,
                                    "size": source.size_bytes}]))
    return mapping


def test_saved_sidecar_preserves_partial_raw_ids_pts_and_cannot_export(saved_probe_fixture, tmp_path):
    diagnosis, checkpoint, output = saved_probe_fixture
    original = checkpoint.read_bytes()
    result = saved_style_evidence(diagnosis, checkpoint, mapping_file(checkpoint, tmp_path), output)
    assert result["frames_verified"] == 5 and result["candidate_crops_verified"] == 1
    assert not result["checkpoint_complete"] and not result["subtitle_success"]
    assert checkpoint.read_bytes() == original
    assert OcrDocument.load(checkpoint).export_issues
    sidecar = json.loads((output / "line-evidence.local.json").read_text(encoding="utf-8"))
    candidate = OcrDocument.load(checkpoint).cues[0].candidates[0]
    assert sidecar["checkpoint_sha256"] == hashlib.sha256(original).hexdigest()
    row = sidecar["candidates"][0]
    assert row["candidate_id"] == candidate.id and row["frame_pts"] == candidate.frame_pts
    assert row["selected_line_indices"] is None and row["proposed_text"] is None
    with pytest.raises(OcrError):
        OcrDocument.from_dict(sidecar)


@pytest.mark.parametrize("corruption", ["mapping", "pixels", "pts", "geometry", "candidate"])
def test_evidence_mismatch_writes_no_proposals(saved_probe_fixture, tmp_path, corruption):
    diagnosis, checkpoint, output = saved_probe_fixture
    mapping = mapping_file(checkpoint, tmp_path)
    if corruption == "mapping":
        mapping.write_text("[]")
    elif corruption in ("pixels", "geometry"):
        with Image.open(diagnosis / "roi/pts-3200.png") as im:
            size = im.size if corruption == "pixels" else (11, 11)
        Image.new("RGB", size, "red").save(diagnosis / "roi/pts-3200.png")
    elif corruption == "pts":
        observations = diagnosis / "frame-observations.json"
        rows = json.loads(observations.read_text())
        rows[1]["pts"] = rows[0]["pts"]
        observations.write_text(json.dumps(rows))
    else:
        # Keep a valid document identity but remove the frame containing its candidate.
        observations = diagnosis / "frame-observations.json"
        rows = json.loads(observations.read_text())[:2]
        observations.write_text(json.dumps(rows))
    original = checkpoint.read_bytes()
    with pytest.raises(OcrError):
        saved_style_evidence(diagnosis, checkpoint, mapping, output)
    assert checkpoint.read_bytes() == original
    assert list(output.iterdir()) == []

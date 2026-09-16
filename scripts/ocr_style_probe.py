"""Offline, single-frame bright-stroke/shadow hypothesis; never imported by the app.

The CLI writes an exclusive plan before measuring generated fixtures or saved PNGs.
Exit 2 rejects the hypothesis; exit 1 is a processing failure. No OCR is performed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from itertools import combinations
from pathlib import Path

from PIL import Image, ImageChops, ImageFilter

from scripts.ocr_layer_probe import Fixture, expected_spans, fixtures, signature, spans, write_json
from videocaptioner.core.ocr.consensus import validate_read
from videocaptioner.core.ocr.models import EngineRead, OcrError, ReadLine
from videocaptioner.core.ocr.tracking import same_shape

POLICY = "probe-bright-opening11-shadow3-v1"
PLAN = {
    "policy": POLICY,
    "hypothesis": "Bright narrow strokes with a darker down-right shadow separate the subtitle on each real frame",
    "opening_size": 11,
    "minimum_luminance": 248,
    "minimum_opening_residual": 3,
    "shadow_offset_xy": [3, 3],
    "minimum_shadow_contrast": 16,
    "temporal_window": 1,
    "parameter_sweep": False,
    "tracking_acceptance": "Exact authored spans and same_shape equivalence to independently masked clean overlays on every frame",
    "pixel_acceptance": "Retain every visible bright target pixel and select no pixel absent from the masked clean overlay",
    "text_acceptance": "Exact target text must be reachable from whole original raw lines; no substring editing or normalization",
    "mixed_box_policy": "Report unreachable text; any future masked OCR needs a separate derived read and provenance",
    "boundary_policy": "Measure every supplied frame; unsupported spatial border is explicitly zero; no temporal padding",
    "new_inference_gate": "Do not invoke OCR when any synthetic tracking, pixel or text gate fails",
    "ocr_requests": 0, "api_calls": 0, "model_loads": 0, "video_decodes": 0,
    "production_policy_changed": False,
}


def style_mask(image: Image.Image) -> Image.Image:
    """Retain only observed bright pixels with local ridge and shadow support.

    This tests one appearance prior, not a semantic subtitle/background classifier.
    No component-height pruning, temporal voting, dilation or glyph reconstruction.
    """
    if image.width < 11 or image.height < 11:
        raise OcrError("Style probe needs images at least 11 by 11 pixels")
    gray = image.convert("L")
    opened = gray.filter(ImageFilter.MinFilter(11)).filter(ImageFilter.MaxFilter(11))
    ridge = ImageChops.subtract(gray, opened).point([255 if i >= 3 else 0 for i in range(256)])
    bright = gray.point([255 if i >= 248 else 0 for i in range(256)])
    # White padding makes unsupported shadow samples fail instead of wrapping to the other edge.
    shadow = Image.new("L", gray.size, 255)
    shadow.paste(gray.crop((3, 3, gray.width, gray.height)), (0, 0))
    contrast = ImageChops.subtract(gray, shadow).point([255 if i >= 16 else 0 for i in range(256)])
    return ImageChops.darker(ImageChops.darker(ridge, bright), contrast)


def pixel_count(mask: Image.Image) -> int:
    return sum(mask.histogram()[1:])


def image_sha(image: Image.Image) -> str:
    return hashlib.sha256(image.convert("RGB").tobytes()).hexdigest()


def measure_style(case: Fixture) -> dict:
    if (not case.images or len(case.images) != len(case.clean_images)
            or len(case.images) != len(case.labels)):
        raise OcrError("Fixture frame/label counts differ")
    geometry = case.images[0].size
    if any(im.size != geometry for im in case.images + case.clean_images):
        raise OcrError("Fixture geometry changed")
    masks = [style_mask(im) for im in case.images]
    clean_masks = [style_mask(im) for im in case.clean_images]
    signals = [signature(im, i) for i, im in enumerate(masks)]
    clean_signals = [signature(im, i) for i, im in enumerate(clean_masks)]
    # The old renderer's neutral background is 248. Positive residuals are visible
    # bright target pixels; shadow/quantized-away glyph pixels are outside this metric.
    targets = [im.convert("L").point([255 if v > 248 else 0 for v in range(256)])
               for im in case.clean_images]
    rows = []
    for i, (mask, clean, target) in enumerate(zip(masks, clean_masks, targets)):
        rows.append({
            "frame_index": i, "input_rgb_sha256": image_sha(case.images[i]),
            "target_visible_pixels": pixel_count(target),
            "target_visible_pixels_lost": pixel_count(ImageChops.subtract(target, mask)),
            "pixels_absent_from_clean_mask": pixel_count(ImageChops.subtract(mask, clean)),
        })
    expected = expected_spans(case.labels)
    observed = spans(signals)
    mismatch = [i for i, (actual, clean) in enumerate(zip(signals, clean_signals))
                if actual.present != clean.present or (actual.present and not same_shape(actual, clean))]
    tracking_pass = observed == expected and not mismatch
    pixels_pass = all(not row["target_visible_pixels_lost"]
                      and not row["pixels_absent_from_clean_mask"] for row in rows)
    return {"name": case.name, "frames": len(rows), "expected_spans": expected,
            "proposed_spans": observed, "clean_mask_spans": spans(clean_signals),
            "signal_mismatch_frames": mismatch, "tracking_accept": tracking_pass,
            "pixel_accept": pixels_pass, "accept": tracking_pass and pixels_pass,
            "unmeasured_boundary_frames": [], "pixel_metrics": rows}


def style_cases(font_path: Path) -> list[Fixture]:
    cases = fixtures(font_path)
    # Identical rendered text can belong to the background. Its authored layer
    # assignment is different, while the observed pixels contain the same style.
    background = cases[0].clean_images
    cases.append(Fixture("same_style_background", background,
                         [Image.new("RGB", im.size, (248, 248, 248)) for im in background],
                         [""] * len(background)))
    return cases


def exact_line_subsets(raw: EngineRead, target: str) -> tuple[tuple[int, ...], ...]:
    """Fixture-only upper bound for ANY whole-line selector; target is author-known.

    This is not an algorithm for selecting video text. Enumeration is bounded to
    small synthetic cases, and never receives a transcript from the private video.
    """
    validate_read(raw)
    if len(raw.lines) > 12:
        raise OcrError("Fixture oracle is limited to 12 raw lines")
    return tuple(indices for count in range(len(raw.lines) + 1)
                 for indices in combinations(range(len(raw.lines)), count)
                 if "\n".join(raw.lines[i].text for i in indices) == target)


def text_reachability() -> list[dict]:
    def line(text, x, y, width, height):
        return ReadLine(text, 0.9, ((x, y), (x + width, y),
                                   (x + width, y + height), (x, y + height)))

    first = line("学生三人，2026年。", 80, 8, 680, 64)
    small = line("Menu 24", 350, 60, 150, 18)
    second = line("今天收到12件礼物。", 80, 49, 680, 32)
    period = line("。", 770, 62, 12, 10)
    large = line(small.text, 350, 8, 300, 64)
    mixed = line(first.text + " " + small.text, 80, 8, 900, 64)
    specs = [
        ("small_background", (first, small), first.text),
        ("two_lines", (first, second, small), first.text + "\n" + second.text),
        ("punctuation_fragment", (first, period, small), first.text + "\n" + period.text),
        ("equal_size_background", (first, large), first.text),
        ("mixed_single_box", (mixed,), first.text),
    ]
    return [{"name": name, "exact_subsets": exact_line_subsets(EngineRead(lines, "authored-v1"), target),
             "target_reachable": bool(exact_line_subsets(EngineRead(lines, "authored-v1"), target)),
             "selection_algorithm_measured": False, "ocr_accuracy_measured": False}
            for name, lines, target in specs]


def saved_style_evidence(diagnosis: Path, checkpoint: Path, mapping: Path, output: Path) -> dict:
    """Verify saved pixels/identity, then write diagnostic sidecars only."""
    from videocaptioner.core.ocr.document import OcrDocument

    original = checkpoint.read_bytes()
    document = OcrDocument.from_dict(json.loads(original))
    sources = json.loads(mapping.read_text(encoding="utf-8"))
    matches = [row for row in sources if row["video"] == 2]
    if (len(matches) != 1 or matches[0]["source_sha256"] != document.visual_source.snapshot_sha256
            or matches[0]["size"] != document.visual_source.size_bytes):
        raise OcrError("Video 2 mapping does not match the checkpoint")
    # The mapped private path is deliberately not opened: this experiment consumes saved PNGs.
    observations = json.loads((diagnosis / "frame-observations.json").read_text(encoding="utf-8"))
    pts = [row["pts"] for row in observations]
    if (not pts or any(type(p) is not int for p in pts)
            or any(b != a + 1 for a, b in zip(pts, pts[1:]))):
        raise OcrError("Saved evidence needs consecutive integer PTS")
    video = document.visual_source.video
    rect = document.config.roi.pixels(*video.geometry.display_size)
    images, hashes, timelines = {}, {}, {}
    for row in observations:
        p = row["pts"]
        with Image.open(diagnosis / "roi" / f"pts-{p}.png") as image:
            rgb = image.convert("RGB")
        timeline = (p * video.time_base - video.timeline_origin) * 1000
        selection = document.config.selection
        if (rgb.size != (rect.width, rect.height)
                or not selection.start_ms <= timeline < selection.end_ms):
            raise OcrError("Saved ROI geometry/timing does not match checkpoint")
        actual = image_sha(rgb)
        if actual != row["crop_sha256"]:
            raise OcrError("Saved ROI pixels do not match observation")
        images[p], hashes[p], timelines[p] = rgb, actual, str(timeline)
    for cue in document.cues:
        for candidate in cue.candidates:
            if hashes.get(candidate.frame_pts) != candidate.crop_sha256:
                raise OcrError("Saved candidate pixels do not match checkpoint")

    masks = {p: style_mask(images[p]) for p in pts}
    signals = [signature(masks[p], p) for p in pts]
    rows = []
    for cue in document.cues:
        for candidate in cue.candidates:
            rows.append({"document_id": document.id, "cue_id": cue.id, "candidate_id": candidate.id,
                         "frame_pts": candidate.frame_pts, "crop_sha256": candidate.crop_sha256,
                         "profile_sha256": candidate.raw.revision,
                         "mask_rgb_sha256": image_sha(masks[candidate.frame_pts]),
                         "raw_line_indices": list(range(len(candidate.raw.lines))),
                         "selected_line_indices": None, "proposed_text": None,
                         "status": "unresolved_no_derived_read",
                         "reason": "Pixel mask is not character attribution; mixed boxes cannot be cleaned by selecting substrings"})
    if checkpoint.read_bytes() != original:
        raise OcrError("Checkpoint changed during probe")
    common = {"policy": POLICY, "source": document.visual_source.to_dict(),
              "checkpoint_sha256": hashlib.sha256(original).hexdigest(),
              "not_an_ocr_document": True, "recognition_accuracy_measured": False}
    write_json(output / "line-evidence.local.json", {
        **common, "schema": "ocr-style-probe-lines-v1", "candidates": rows})
    write_json(output / "signal-provenance.local.json", {
        **common, "schema": "ocr-style-probe-signals-v1", "frames": [
            {"pts": p, "timeline_ms": timelines[p], "input_crop_sha256": hashes[p],
             "support_pts": [p], "mask_rgb_sha256": image_sha(masks[p]),
             "selected_pixels": pixel_count(masks[p])} for p in pts]})
    for p in pts:
        masks[p].save(output / f"mask-pts-{p}.png")
    return {"frames_verified": len(pts), "candidate_crops_verified": len(rows),
            "proposed_signal_spans": spans(signals, pts[0]), "unmeasured_boundary_pts": [],
            "raw_lines": sum(len(c.raw.lines) for cue in document.cues for c in cue.candidates),
            "derived_reads": 0, "unresolved_candidates": len(rows),
            "checkpoint_complete": document.complete, "checkpoint_unchanged": True,
            "subtitle_success": False, "recognition_accuracy_measured": False}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--diagnosis", type=Path)
    parser.add_argument("--checkpoint", type=Path)
    parser.add_argument("--mapping", type=Path)
    args = parser.parse_args(argv)
    if sum(value is not None for value in (args.diagnosis, args.checkpoint, args.mapping)) not in (0, 3):
        parser.error("--diagnosis, --checkpoint and --mapping must be supplied together")
    args.output.mkdir(parents=True, exist_ok=False)
    script = Path(__file__).read_bytes()
    write_json(args.output / "plan.json", {**PLAN, "script_sha256": hashlib.sha256(script).hexdigest()})
    (args.output / "probe-source.py").write_bytes(script)
    results = []
    for case in style_cases(Path(__file__).resolve().parents[1] / "resource/fonts/NotoSansSC-Regular.ttf"):
        results.append(measure_style(case))
        style_mask(case.images[12]).save(args.output / f"synthetic-{case.name}-mask.png")
    text_results = text_reachability()
    evidence = None
    if args.diagnosis is not None:
        evidence = saved_style_evidence(args.diagnosis, args.checkpoint, args.mapping, args.output)
    accepted = all(row["accept"] for row in results) and all(row["target_reachable"] for row in text_results)
    receipt = {"harness_completed": True, "hypothesis_accepted": accepted,
               "production_ready": False, "synthetic": results, "text_reachability": text_results,
               "saved_evidence": evidence, "ocr_requests": 0, "api_calls": 0,
               "model_loads": 0, "video_decodes": 0}
    write_json(args.output / "receipt.json", receipt)
    print(json.dumps({"harness_completed": True, "hypothesis_accepted": accepted,
                      "tracking_accepted": sum(r["tracking_accept"] for r in results),
                      "pixel_accepted": sum(r["pixel_accept"] for r in results),
                      "cases": len(results), "production_ready": False}))
    return 0 if accepted else 2


if __name__ == "__main__":
    def offline_guard(event, args):
        if event.startswith("socket.") or event in ("subprocess.Popen", "os.system"):
            raise RuntimeError("The style probe forbids network and child processes")

    sys.addaudithook(offline_guard)
    raise SystemExit(main())

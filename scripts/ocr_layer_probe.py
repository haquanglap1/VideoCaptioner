"""Offline hypothesis probe; never used by OCR scan, resume, cache or export.

Run with ``python -B -m scripts.ocr_layer_probe --output NEW_DIRECTORY``.
Exit 2 means the hypothesis failed its acceptance checks, not a broken harness.
No OCR, decoder, network or model is invoked. All images are generated or supplied PNGs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass
from fractions import Fraction
from itertools import combinations
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from videocaptioner.core.ocr.consensus import validate_read
from videocaptioner.core.ocr.models import EngineRead, OcrError, ReadLine, RoiFrame
from videocaptioner.core.ocr.tracking import EdgeSignature, edge_signature, same_shape

POLICY = "probe-temporal-3of5-center-and-height-0.6-v1"
SIZE = (1128, 94)


def signature(image: Image.Image, pts: int) -> EdgeSignature:
    rgb = image.convert("RGB")
    return edge_signature(RoiFrame(pts, pts, Fraction(1, 30), Fraction(pts * 100, 3),
                                   rgb.width, rgb.height, rgb.tobytes()))


def persistent_edges(window: tuple[EdgeSignature, ...]) -> EdgeSignature:
    """Keep center-frame edges supported in at least three of five observations.

    The center intersection forbids adding a glyph absent from the actual frame.
    Full context is mandatory: no padding/duplication at selection boundaries.
    """
    if len(window) != 5:
        raise OcrError("The probe requires five real observations")
    count = max(len(item.tiles) for item in window)
    if any(len(item.tiles) not in (0, count) for item in window):
        raise OcrError("Probe frame geometry changed")
    tiles = []
    padded = [item.tiles or (0,) * count for item in window]
    for column in zip(*padded):
        supported = 0
        for a, b, c in combinations(column, 3):
            supported |= a & b & c
        tiles.append(supported & column[2])
    return EdgeSignature(tuple(tiles), sum(t.bit_count() for t in tiles), window[2].strength)


def probe_signals(signals: list[EdgeSignature]) -> list[EdgeSignature]:
    if len(signals) < 5:
        raise OcrError("Insufficient temporal context for the probe")
    return [persistent_edges(tuple(signals[i - 2:i + 3])) for i in range(2, len(signals) - 2)]


def spans(signals: list[EdgeSignature], offset: int = 0) -> list[tuple[int, int]]:
    """Measure half-open frame intervals with the existing local tile comparison.

    This is a signal diagnostic, not RegionTracker or a replacement timing policy.
    It deliberately has no OCR candidate, confidence or review state.
    """
    result = []
    start, reference = None, None
    for i, item in enumerate(signals, offset):
        if start is not None and reference is not None:
            if not item.present or not same_shape(reference, item):
                result.append((start, i))
                start, reference = None, None
        if item.present and start is None:
            start, reference = i, item
    if start is not None:
        result.append((start, offset + len(signals)))
    return result


@dataclass(frozen=True)
class LineProposal:
    policy: str
    raw: EngineRead
    indices: tuple[int, ...]
    rejected_indices: tuple[int, ...]

    @property
    def text(self) -> str:
        # A proposal references original lines; it never edits or merges raw codepoints.
        return "\n".join(self.raw.lines[i].text for i in self.indices)


def propose_lines(raw: EngineRead) -> LineProposal:
    """Test size separation; this cannot distinguish equal-size background text."""
    validate_read(raw)
    heights = [max(p[1] for p in line.box) - min(p[1] for p in line.box) for line in raw.lines]
    if any(height <= 0 for height in heights):
        raise OcrError("Probe needs nonempty line geometry")
    cutoff = max(heights, default=0) * 0.6
    chosen = tuple(i for i, height in enumerate(heights) if height >= cutoff)
    return LineProposal(POLICY, raw, chosen, tuple(i for i in range(len(heights)) if i not in chosen))


def line_fixtures() -> list[dict]:
    """Author-specified detector outputs, not recognition results or model accuracy."""
    def line(text, x, y, width, height):
        return ReadLine(text, 0.9, ((x, y), (x + width, y),
                                   (x + width, y + height), (x, y + height)))

    target = line("学生三人，2026年。", 80, 8, 680, 64)
    small = line("Menu 24", 350, 60, 150, 18)
    second = line("今天收到12件礼物。", 80, 49, 680, 32)
    first = line("学生三人，2026年。", 80, 5, 680, 32)
    period = line("。", 770, 62, 12, 10)
    large_background = line("Menu 24", 350, 8, 300, 64)
    mixed = line("学生三人，2026年。 Menu 24", 80, 8, 900, 64)
    specs = [
        ("small_background", (target, small), (0,), target.text),
        ("two_lines", (first, second, small), (0, 1), first.text + "\n" + second.text),
        ("punctuation_fragment", (target, period, small), (0, 1), target.text + "\n" + period.text),
        ("equal_size_background", (target, large_background), (0,), target.text),
        ("mixed_single_box", (mixed,), (0,), target.text),
    ]
    results = []
    for name, lines, expected_indices, expected_text in specs:
        raw = EngineRead(lines, "synthetic-author-fixture-v1")
        proposal = propose_lines(raw)
        results.append({"name": name, "expected_indices": expected_indices,
                        "selected_indices": proposal.indices,
                        "exact_text_retained": proposal.text == expected_text,
                        "raw_unchanged": proposal.raw is raw,
                        "accept": proposal.indices == expected_indices and proposal.text == expected_text})
    return results


@dataclass
class Fixture:
    name: str
    images: list[Image.Image]
    clean_images: list[Image.Image]
    labels: list[str]


def fixtures(font_path: Path) -> list[Fixture]:
    """Author-labelled overlays, including controls that a temporal filter must not hide."""
    small = ImageFont.truetype(str(font_path), 18)
    large = ImageFont.truetype(str(font_path), 56)
    double = ImageFont.truetype(str(font_path), 28)
    first, changed, punct = "学生三人，2026年。", "学生五人，2026年。", "学生三人，2026年！"
    two = "学生三人，2026年。\n今天收到12件礼物。"
    two_changed = "学生三人，2026年。\n今天收到13件礼物。"
    normal = [first] * 24
    specs = [
        ("fixed", normal, None, False),
        ("one_character", [first] * 12 + [changed] * 12, None, False),
        ("punctuation", [first] * 12 + [punct] * 12, None, False),
        ("two_lines", [two] * 12 + [two_changed] * 12, None, False),
        ("fade", [""] * 3 + [first] * 18 + [""] * 3,
         [0] * 3 + [32, 96, 160] + [255] * 12 + [160, 96, 32] + [0] * 3, False),
        ("blank_repeat", [first] * 8 + [""] * 8 + [first] * 8, None, False),
        ("brief_one_character", [first] * 12 + [changed] + [first] * 11, None, False),
        ("paused_background", normal, None, True),
        ("blank_scrolling", [""] * 24, None, False),
    ]
    output = []
    for name, labels, levels, paused in specs:
        images, clean = [], []
        for index, label in enumerate(labels):
            background = Image.new("RGB", SIZE, (248, 248, 248))
            draw = ImageDraw.Draw(background)
            shift = 0 if paused else (index * 9) % 120
            for x in (310, 760):
                for y in range(-120, 200, 40):
                    draw.text((x, y - shift), "Menu 24 / tools", font=small, fill=(65, 65, 65))
                draw.ellipse((x - 36, 23 - shift, x - 8, 51 - shift), fill=(50, 100, 180))
            alpha = 255 if levels is None else levels[index]
            glyph = Image.new("L", SIZE)
            font = double if "\n" in label else large
            ImageDraw.Draw(glyph).multiline_text((80, 0), label, font=font, fill=255, spacing=3)
            shadow = Image.new("L", SIZE)
            shadow.paste(glyph, (3, 3))
            shadow = shadow.filter(ImageFilter.GaussianBlur(1.2))
            for base, collection in ((background, images), (Image.new("RGB", SIZE, (248, 248, 248)), clean)):
                composed = Image.composite(Image.new("RGB", SIZE, (50, 50, 50)), base, shadow)
                composed = Image.composite(Image.new("RGB", SIZE, "white"), composed, glyph)
                collection.append(Image.blend(base, composed, alpha / 255))
        output.append(Fixture(name, images, clean, labels))
    return output


def expected_spans(labels: list[str]) -> list[tuple[int, int]]:
    result = []
    start = 0
    for i in range(1, len(labels) + 1):
        if i == len(labels) or labels[i] != labels[start]:
            if labels[start]:
                result.append((start, i))
            start = i
    return result


def measure(case: Fixture) -> dict:
    signals = [signature(im, i) for i, im in enumerate(case.images)]
    clean = [signature(im, i) for i, im in enumerate(case.clean_images)]
    proposed = probe_signals(signals)
    expected = [(max(2, a), min(len(signals) - 2, b)) for a, b in expected_spans(case.labels)
                if a < len(signals) - 2 and b > 2]
    observed = spans(proposed, 2)
    mismatches = [i for i, item in enumerate(proposed, 2)
                  if item.present != clean[i].present or (item.present and not same_shape(item, clean[i]))]
    return {"name": case.name, "frames": len(signals), "expected_spans": expected,
            "clean_overlay_spans": spans(clean[2:-2], 2),
            "baseline_spans": spans(signals[2:-2], 2), "proposed_spans": observed,
            "signal_mismatch_frames": mismatches,
            "accept": observed == expected and not mismatches,
            "unmeasured_boundary_frames": [0, 1, len(signals) - 2, len(signals) - 1]}


def write_json(path: Path, value) -> None:
    with path.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")


def saved_evidence(diagnosis: Path, checkpoint: Path, output: Path) -> dict:
    """Read the explicitly supplied evidence; no original video is opened."""
    from videocaptioner.core.ocr.document import OcrDocument

    original = checkpoint.read_bytes()
    document = OcrDocument.from_dict(json.loads(original))
    observations = json.loads((diagnosis / "frame-observations.json").read_text(encoding="utf-8"))
    pts = [row["pts"] for row in observations]
    if (len(pts) < 5 or any(type(p) is not int for p in pts)
            or any(b != a + 1 for a, b in zip(pts, pts[1:]))):
        raise OcrError("Saved evidence needs consecutive PTS")
    video = document.visual_source.video
    rect = document.config.roi.pixels(*video.geometry.display_size)
    signals, hashes = [], {}
    for row in observations:
        path = diagnosis / "roi" / f"pts-{row['pts']}.png"
        with Image.open(path) as image:
            rgb = image.convert("RGB")
            timeline = (row["pts"] * video.time_base - video.timeline_origin) * 1000
            selection = document.config.selection
            if (rgb.size != (rect.width, rect.height)
                    or not selection.start_ms <= timeline < selection.end_ms):
                raise OcrError("Saved ROI geometry/timing does not match the checkpoint")
            actual = hashlib.sha256(rgb.tobytes()).hexdigest()
            if actual != row["crop_sha256"]:
                raise OcrError("Saved ROI pixels do not match their observation")
            hashes[row["pts"]] = actual
            signals.append(signature(rgb, row["pts"]))
    proposals = []
    for cue in document.cues:
        for candidate in cue.candidates:
            if hashes.get(candidate.frame_pts) != candidate.crop_sha256:
                raise OcrError("Saved candidate pixels do not match the checkpoint")
            proposal = propose_lines(candidate.raw)
            proposals.append({"document_id": document.id, "cue_id": cue.id,
                              "candidate_id": candidate.id, "frame_pts": candidate.frame_pts,
                              "crop_sha256": candidate.crop_sha256,
                              "profile_sha256": candidate.raw.revision,
                              "selected_line_indices": proposal.indices,
                              "rejected_line_indices": proposal.rejected_indices,
                              "proposed_text": proposal.text})
    if checkpoint.read_bytes() != original:
        raise OcrError("Input checkpoint changed during the probe")
    write_json(output / "line-proposals.local.json", {
        "schema": "ocr-layer-probe-proposals-v1", "policy": POLICY,
        "source": document.visual_source.to_dict(),
        "checkpoint_sha256": hashlib.sha256(original).hexdigest(),
        "not_an_ocr_document": True, "proposals": proposals})
    filtered = probe_signals(signals)
    write_json(output / "signal-provenance.local.json", {
        "policy": POLICY, "source": document.visual_source.to_dict(),
        "frames": [{"center_pts": pts[i], "window_pts": pts[i - 2:i + 3],
                    "window_crop_sha256": [hashes[p] for p in pts[i - 2:i + 3]],
                    "raw_edges": signals[i].edge_count, "filtered_edges": item.edge_count}
                   for i, item in enumerate(filtered, 2)]})
    return {"frames_verified": len(pts), "candidate_crops_verified": len(proposals),
            "raw_lines": sum(len(c.raw.lines) for cue in document.cues for c in cue.candidates),
            "proposed_lines": sum(len(p["selected_line_indices"]) for p in proposals),
            "raw_signal_spans": spans(signals[2:-2], pts[2]),
            "proposed_signal_spans": spans(filtered, pts[2]),
            "unmeasured_boundary_pts": pts[:2] + pts[-2:],
            "recognition_accuracy_measured": False,
            "checkpoint_unchanged": True}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--diagnosis", type=Path)
    parser.add_argument("--checkpoint", type=Path)
    args = parser.parse_args(argv)
    if (args.diagnosis is None) != (args.checkpoint is None):
        parser.error("--diagnosis and --checkpoint must be supplied together")
    # Exclusive output: a rejected experiment and its plan are never overwritten.
    args.output.mkdir(parents=True, exist_ok=False)
    write_json(args.output / "plan.json", {
        "policy": POLICY, "window": 5, "minimum_support": 3, "intersect_center": True,
        "line_minimum_relative_height": 0.6, "parameter_sweep": False,
        "tracking_acceptance": "Exact author-labelled spans and clean-overlay tile equivalence on every measured frame",
        "line_acceptance": "All target raw lines retained; all background raw lines excluded, including punctuation fragments",
        "boundary_policy": "First/last two frames explicitly unmeasured; no padding or inferred timing",
        "ocr_requests": 0, "api_calls": 0, "model_loads": 0, "video_decodes": 0,
        "production_policy_changed": False})
    cases = fixtures(Path(__file__).resolve().parents[1] / "resource/fonts/NotoSansSC-Regular.ttf")
    results = []
    for case in cases:
        results.append(measure(case))
        case.images[12].save(args.output / f"synthetic-{case.name}.png")
    evidence = None
    if args.diagnosis is not None:
        evidence = saved_evidence(args.diagnosis, args.checkpoint, args.output)
    line_results = line_fixtures()
    accepted = all(row["accept"] for row in results)
    lines_accepted = all(row["accept"] for row in line_results)
    write_json(args.output / "receipt.json", {
        "harness_completed": True, "tracking_hypothesis_accepted": accepted,
        "line_hypothesis_accepted": lines_accepted,
        "synthetic": results, "line_fixtures": line_results, "saved_evidence": evidence,
        "production_ready": False, "ocr_requests": 0, "api_calls": 0,
        "model_loads": 0, "video_decodes": 0})
    print(json.dumps({"harness_completed": True, "tracking_hypothesis_accepted": accepted,
                      "accepted_cases": sum(row["accept"] for row in results), "cases": len(results),
                      "production_ready": False}))
    return 0 if accepted and lines_accepted else 2


if __name__ == "__main__":
    def offline_guard(event, args):
        if event.startswith("socket.") or event in ("subprocess.Popen", "os.system"):
            raise RuntimeError("The layer probe forbids network and child processes")

    sys.addaudithook(offline_guard)
    raise SystemExit(main())

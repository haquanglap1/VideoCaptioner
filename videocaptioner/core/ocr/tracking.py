"""Conservative edge-based tracking of one fixed subtitle region, with bounded candidates."""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from fractions import Fraction
from typing import Callable, cast

from PIL import Image, ImageChops, ImageDraw, ImageFilter

from .models import FrameSpan, OcrError, RoiFrame, VisualDecision

CHARACTER_TRACKING_WORKERS = {
    "character-features-v1": "ocr_tracking_worker.py",
    "character-features-v2": "ocr_tracking_worker_v2.py",
    "character-features-v3": "ocr_tracking_worker_v3.py",
}


@dataclass(frozen=True)
class EdgeSignature:
    tiles: tuple[int, ...]
    edge_count: int
    strength: float
    present_threshold: int = 12
    # "tiles" flags any changed local tile; "overlap" needs most strokes to stay in place.
    compare: str = "tiles"

    @property
    def present(self) -> bool:
        return self.edge_count >= self.present_threshold


def edge_signature(frame: RoiFrame) -> EdgeSignature:
    image = Image.frombytes("RGB", (frame.width, frame.height), frame.rgb).convert("L")
    factor = min(1, 960 / frame.width, 240 / frame.height)
    if factor < 1:
        image = image.resize((max(3, round(frame.width * factor)),
                              max(3, round(frame.height * factor))), Image.Resampling.BILINEAR)
    low, high = cast(tuple[int, int], image.getextrema())  # image is explicitly mode L.
    if high - low < 4:
        # FIND_EDGES can amplify one-level codec noise eightfold into a false glyph.
        return EdgeSignature((), 0, 0)
    edge = image.filter(ImageFilter.FIND_EDGES)
    ImageDraw.Draw(edge).rectangle((0, 0, edge.width - 1, edge.height - 1), outline=0)
    histogram = edge.histogram()
    peak = max((i for i, count in enumerate(histogram) if count), default=0)
    threshold = max(8, round(peak * 0.22))
    mask = edge.point([255 if value >= threshold else 0 for value in range(256)])
    # Local tiles catch a changed glyph even when the rest of a long line is identical.
    tiles = []
    for y in range(0, mask.height, 16):
        for x in range(0, mask.width, 16):
            tile = mask.crop((x, y, x + 16, y + 16)).convert("1")
            tiles.append(int.from_bytes(tile.tobytes(), "big"))
    return EdgeSignature(tuple(tiles), sum(t.bit_count() for t in tiles),
                         sum(i * n for i, n in enumerate(histogram)) / max(1, sum(histogram[8:])))


BRIGHT_LEVEL, TOPHAT_LEVEL, OPENING_SIZE = 160, 50, 7
STROKE_PRESENT_PIXELS, STROKE_IOU, STROKE_SETTLE_MS = 24, 0.55, 150
MIN_BAND_PX, MIN_SEGMENTS, MIN_SPAN_PX = 5, 3, 24


def _stroke_gray(frame: RoiFrame) -> tuple[Image.Image, float]:
    image = Image.frombytes("RGB", (frame.width, frame.height), frame.rgb).convert("L")
    factor = min(1, 960 / frame.width, 240 / frame.height)
    if factor < 1:
        image = image.resize((max(3, round(frame.width * factor)),
                              max(3, round(frame.height * factor))), Image.Resampling.BILINEAR)
    return image, factor


def stroke_mask(image: Image.Image) -> Image.Image:
    """Bright pixels thinner than the opening kernel: glyph strokes, not panning scenery or highlights."""
    opened = image.filter(ImageFilter.MinFilter(OPENING_SIZE)).filter(ImageFilter.MaxFilter(OPENING_SIZE))
    tophat = ImageChops.subtract(image, opened)
    bright = image.point([255 if value >= BRIGHT_LEVEL else 0 for value in range(256)])
    thin = tophat.point([255 if value >= TOPHAT_LEVEL else 0 for value in range(256)])
    return ImageChops.multiply(bright, thin)


def _runs(values: bytes, threshold: int) -> list[tuple[int, int]]:
    runs, start = [], None
    for index, value in enumerate(bytes(values) + b"\0"):
        if value >= threshold and start is None:
            start = index
        elif value < threshold and start is not None:
            runs.append((start, index))
            start = None
    return runs


def text_band(mask: Image.Image) -> tuple[int, int, int, int] | None:
    """The horizontal band of glyphs: dense rows, several separated strokes, no long line."""
    width, height = mask.size
    rows = mask.resize((1, height), Image.Resampling.BOX).tobytes()  # mean brightness per row
    peak = max(rows)
    if peak * width < 255 * MIN_BAND_PX:
        return None
    bands = _runs(rows, max(1, round(peak * 0.2)))
    top, bottom = max(bands, key=lambda run: sum(rows[run[0]:run[1]]))
    top, bottom = max(0, top - 2), min(height, bottom + 2)
    if bottom - top < MIN_BAND_PX:
        return None
    columns = mask.crop((0, top, width, bottom)).resize((width, 1), Image.Resampling.BOX).tobytes()
    segments = _runs(columns, 1)
    if not segments:
        return None
    left, right = segments[0][0], segments[-1][1]
    if (len(segments) < MIN_SEGMENTS or right - left < MIN_SPAN_PX
            or max(end - start for start, end in segments) > 4 * (bottom - top)):
        return None
    return left, top, right, bottom


def _band_mask(frame: RoiFrame) -> tuple[Image.Image, tuple[int, int, int, int] | None, float]:
    image, factor = _stroke_gray(frame)
    mask = stroke_mask(image)
    ImageDraw.Draw(mask).rectangle((0, 0, mask.width - 1, mask.height - 1), outline=0)
    band = text_band(mask)
    if band is None:
        return mask, None, factor
    keep = Image.new("L", mask.size, 0)
    ImageDraw.Draw(keep).rectangle((band[0], band[1], band[2] - 1, band[3] - 1), fill=255)
    return ImageChops.multiply(mask, keep), band, factor


def _tiles(mask: Image.Image) -> tuple[int, ...]:
    tiles = []
    for y in range(0, mask.height, 16):
        for x in range(0, mask.width, 16):
            tile = mask.crop((x, y, x + 16, y + 16)).convert("1")
            tiles.append(int.from_bytes(tile.tobytes(), "big"))
    return tuple(tiles)


def stroke_signature(frame: RoiFrame) -> EdgeSignature:
    """Tracks the glyph strokes of one text band; frames are compared by stroke overlap, not tiles."""
    mask, band, _ = _band_mask(frame)
    if band is None:
        return EdgeSignature((), 0, 0, STROKE_PRESENT_PIXELS, "overlap")
    tiles = _tiles(mask)
    count = sum(t.bit_count() for t in tiles)
    return EdgeSignature(tiles, count, float(count), STROKE_PRESENT_PIXELS, "overlap")


def text_bounds(frame: RoiFrame) -> tuple[int, int, int, int] | None:
    """Glyph band in frame pixels with a glyph-sized margin; None when no text band is found."""
    mask, band, factor = _band_mask(frame)
    if band is None or sum(mask.histogram()[128:]) < STROKE_PRESENT_PIXELS:
        return None
    left, top, right, bottom = (v / factor for v in band)
    height = max(bottom - top, 8)
    return (max(0, math.floor(left - height / 2)), max(0, math.floor(top - height * .35)),
            min(frame.width, math.ceil(right + height / 2)), min(frame.height, math.ceil(bottom + height * .35)))


SIGNATURES = {"edge-tiles-ocr2-v1": edge_signature, "text-strokes-v1": stroke_signature}


def same_shape(left: EdgeSignature, right: EdgeSignature) -> bool:
    if len(left.tiles) != len(right.tiles):
        return False
    if left.compare == right.compare == "overlap":
        union = sum((a | b).bit_count() for a, b in zip(left.tiles, right.tiles))
        shared = sum((a & b).bit_count() for a, b in zip(left.tiles, right.tiles))
        return union == 0 or shared / union >= STROKE_IOU
    for a, b in zip(left.tiles, right.tiles):
        changed, occupied = (a ^ b).bit_count(), (a | b).bit_count()
        if changed >= 6 and changed / max(1, occupied) > 0.30:
            return False
    return True


@dataclass(frozen=True)
class TrackedRegion:
    start_ms: Fraction
    end_ms: Fraction
    first_pts: int
    last_pts: int
    candidates: tuple[RoiFrame, ...]
    issues: tuple[str, ...]
    # Bounds bracket the whole observed transition when a fade prevents a sharp edge.
    start_window_ms: tuple[Fraction, Fraction]
    end_window_ms: tuple[Fraction, Fraction]
    # The sharpest observed frame; batch readers that send one crop per cue prefer it.
    best_pts: int | None = None


def select_candidates(region: TrackedRegion, limit: int | None) -> tuple[RoiFrame, ...]:
    """Sharpest frame first, then boundary frames; pipeline and resume must agree on this."""
    frames = region.candidates
    if limit is None or len(frames) <= limit:
        return frames
    best = [f for f in frames if f.pts == region.best_pts]
    rest = [f for f in frames if f.pts != region.best_pts]
    return tuple((best + rest)[:limit])


@dataclass
class _Active:
    start: FrameSpan
    last: FrameSpan
    signature: EdgeSignature
    first: RoiFrame
    best: RoiFrame
    latest: RoiFrame
    best_strength: float
    min_strength: float
    issues: set[str] = field(default_factory=set)


class RegionTracker:
    def __init__(self, *, max_hold_ms: int = 30000, initial_issues: tuple[str, ...] = (),
                 signature: Callable[[RoiFrame], EdgeSignature] = edge_signature, settle_ms: int = 0):
        if type(max_hold_ms) is not int or not 100 <= max_hold_ms <= 300000:
            raise OcrError("Invalid track holding limit")
        self.max_hold_ms = max_hold_ms
        self.signature = signature
        if type(settle_ms) is not int or not 0 <= settle_ms <= 1000:
            raise OcrError("Invalid track settling window")
        self.settle_ms = settle_ms
        self.initial_issues = initial_issues
        self.active: _Active | None = None
        self.previous_end: Fraction | None = None
        self.peak_candidates = 0

    def _finish(self) -> TrackedRegion | None:
        active = self.active
        if active is None:
            return None
        frames = {f.pts: f for f in (active.first, active.best, active.latest)}
        issues = set(active.issues)
        if active.start.clipped_start:
            issues.add("selection_clipped_start")
        if active.last.clipped_end:
            issues.add("selection_clipped_end")
        if active.last.uncertain_end:
            issues.add("unknown_last_frame_duration")
        fade = active.min_strength < active.best_strength * 0.7
        if fade:
            issues.add("fade_or_contrast_change")
        start, end = active.start.start_ms, active.last.end_ms
        uncertain = fade or "track_holding_limit" in issues or "uncertain_boundary" in issues
        end_lower = start if uncertain else (active.last.start_ms if active.last.uncertain_end else end)
        self.active = None
        return TrackedRegion(start, end, active.first.pts, active.latest.pts,
                             tuple(frames.values()), tuple(sorted(issues)),
                             (start, end if uncertain else start), (end_lower, end), active.best.pts)

    def feed(self, span: FrameSpan, decision: VisualDecision | None = None) -> TrackedRegion | None:
        if span.start_ms >= span.end_ms or (self.previous_end is not None
                                            and span.start_ms != self.previous_end):
            raise OcrError("Tracking requires consecutive, nonempty frame spans")
        self.previous_end = span.end_ms
        signature = self.signature(span.frame)
        present = decision.present if decision else signature.present
        if decision:
            signature = replace(signature, strength=decision.quality)
        closed = None
        if self.active is not None:
            if decision and decision.uncertain and not decision.changed:
                self.active.issues.add("uncertain_boundary")
            timeout = span.start_ms - self.active.start.start_ms >= self.max_hold_ms
            if timeout:
                self.active.issues.add("track_holding_limit")
            changed = decision.changed if decision else not same_shape(self.active.signature, signature)
            if (changed and present and decision is None and self.settle_ms
                    and span.start_ms - self.active.start.start_ms < self.settle_ms):
                # Fade-in frames still settle into the same cue; follow the newest shape instead of splitting.
                self.active.signature = signature
                self.active.issues.add("fade_or_contrast_change")
                changed = False
            if timeout or not present or changed:
                closed = self._finish()
                if timeout and present:
                    # Splitting at the memory/time policy is not a measured text transition.
                    self._begin(span, signature)
                    assert self.active is not None
                    self.active.issues.add("track_holding_limit")
                    return closed
        if present:
            if self.active is None:
                self._begin(span, signature)
            else:
                active = self.active
                active.last, active.latest = span, span.frame
                active.min_strength = min(active.min_strength, signature.strength)
                if signature.strength > active.best_strength:
                    active.best, active.best_strength = span.frame, signature.strength
                    # Compare against the sharpest observation, avoiding gradual signature drift.
                    active.signature = signature
                self.peak_candidates = max(self.peak_candidates,
                                           len({active.first.pts, active.best.pts, active.latest.pts}))
        return closed

    def _begin(self, span: FrameSpan, signature: EdgeSignature) -> None:
        self.active = _Active(span, span, signature, span.frame, span.frame, span.frame,
                              signature.strength, signature.strength, set(self.initial_issues))
        self.initial_issues = ()
        self.peak_candidates = max(self.peak_candidates, 1)

    def finish(self) -> TrackedRegion | None:
        return self._finish()

"""Conservative edge-based tracking of one fixed subtitle region, with bounded candidates."""

from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction
from typing import cast

from PIL import Image, ImageDraw, ImageFilter

from .models import FrameSpan, OcrError, RoiFrame


@dataclass(frozen=True)
class EdgeSignature:
    tiles: tuple[int, ...]
    edge_count: int
    strength: float

    @property
    def present(self) -> bool:
        return self.edge_count >= 12


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


def same_shape(left: EdgeSignature, right: EdgeSignature) -> bool:
    if len(left.tiles) != len(right.tiles):
        return False
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
    def __init__(self, *, max_hold_ms: int = 30000):
        if type(max_hold_ms) is not int or not 100 <= max_hold_ms <= 300000:
            raise OcrError("Invalid track holding limit")
        self.max_hold_ms = max_hold_ms
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
        uncertain = fade or "track_holding_limit" in issues
        end_lower = start if uncertain else (active.last.start_ms if active.last.uncertain_end else end)
        self.active = None
        return TrackedRegion(start, end, active.first.pts, active.latest.pts,
                             tuple(frames.values()), tuple(sorted(issues)),
                             (start, end if uncertain else start), (end_lower, end))

    def feed(self, span: FrameSpan) -> TrackedRegion | None:
        if span.start_ms >= span.end_ms or (self.previous_end is not None
                                            and span.start_ms != self.previous_end):
            raise OcrError("Tracking requires consecutive, nonempty frame spans")
        self.previous_end = span.end_ms
        signature = edge_signature(span.frame)
        closed = None
        if self.active is not None:
            timeout = span.start_ms - self.active.start.start_ms >= self.max_hold_ms
            if timeout:
                self.active.issues.add("track_holding_limit")
            if timeout or not signature.present or not same_shape(self.active.signature, signature):
                closed = self._finish()
                if timeout and signature.present:
                    # Splitting at the memory/time policy is not a measured text transition.
                    self._begin(span, signature)
                    assert self.active is not None
                    self.active.issues.add("track_holding_limit")
                    return closed
        if signature.present:
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
                              signature.strength, signature.strength)
        self.peak_candidates = max(self.peak_candidates, 1)

    def finish(self) -> TrackedRegion | None:
        return self._finish()

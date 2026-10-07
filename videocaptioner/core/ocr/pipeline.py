"""Streaming OCR-2 orchestration with injected recognition; no public export or GUI yet."""

from __future__ import annotations

import time
from dataclasses import dataclass
from fractions import Fraction
from typing import Callable, Iterator, Protocol, Sequence

from .consensus import CandidateRead, Consensus, ReadCache, choose_read
from .decoder import RoiDecoder
from .line_selection import LineSelectionPolicy
from .models import Check, EngineRead, OcrError, RoiFrame, Selection, VisualDecision
from .punctuation_consensus import POLICY, choose_witnessed_read
from .tracking import (
    SIGNATURES,
    STROKE_SETTLE_MS,
    RegionTracker,
    TrackedRegion,
    edge_signature,
    select_candidates,
    stroke_signature,
)


class Recognizer(Protocol):
    def __call__(self, frame: RoiFrame, check: Check) -> EngineRead:
        """Recognize in a separately supervised process; honor check/timeout while waiting."""
        ...


class BatchRecognizer(Protocol):
    """Reads several crops per request; the pipeline buffers whole regions to fill one request."""

    rows_per_request: int

    def recognize_many(self, frames: Sequence[RoiFrame], check: Check) -> Sequence[EngineRead]:
        ...


@dataclass(frozen=True)
class RegionResult:
    start_ms: Fraction
    end_ms: Fraction
    reads: tuple[CandidateRead, ...]
    consensus: Consensus
    issues: tuple[str, ...]
    start_window_ms: tuple[Fraction, Fraction]
    end_window_ms: tuple[Fraction, Fraction]
    first_pts: int | None = None
    last_pts: int | None = None

    @property
    def needs_review(self) -> bool:
        return bool(self.issues or self.consensus.issues)


@dataclass
class PipelineMetrics:
    roi_frames: int = 0
    tracks: int = 0
    candidate_crops: int = 0
    fresh_calls: int = 0
    cache_hits: int = 0
    review_regions: int = 0
    empty_regions: int = 0
    short_regions: int = 0
    tracking_s: float = 0
    recognition_call_s: float = 0
    pipeline_wall_s: float = 0  # Includes overlap with decode and time spent by the consumer.


@dataclass
class _Slot:
    frame: RoiFrame
    key: str
    crop_hash: str
    raw: EngineRead | None
    hit: bool


class OcrPipeline:
    def __init__(self, recognizer: Recognizer | BatchRecognizer, cache: ReadCache, *, check: Check = lambda: None,
                 line_selection: LineSelectionPolicy | None = None,
                 visual_reader: Callable[[RoiFrame, EngineRead | None], VisualDecision] | None = None,
                 frame_progress: Callable[[Fraction], None] = lambda _: None,
                 consensus_policy: str = "exact-read-uncalibrated-v1",
                 candidate_limit: int | None = None, drop_empty: bool = False,
                 tracking_policy: str = "edge-tiles-ocr2-v1", min_region_ms: int = 0):
        self.recognizer, self.cache, self.check = recognizer, cache, check
        self.line_selection = line_selection
        self.visual_reader = visual_reader
        self.frame_progress = frame_progress
        if consensus_policy not in ("exact-read-uncalibrated-v1", POLICY):
            raise OcrError("Unknown OCR consensus policy")
        if candidate_limit is not None and (type(candidate_limit) is not int or not 1 <= candidate_limit <= 3):
            raise OcrError("OCR candidate limit must be 1..3 crops per cue")
        self.consensus_policy = consensus_policy
        self.candidate_limit, self.drop_empty = candidate_limit, drop_empty
        if type(min_region_ms) is not int or not 0 <= min_region_ms <= 2000:
            raise OcrError("OCR minimum region duration must be 0..2000 ms")
        self.min_region_ms = min_region_ms
        # Character tracking keeps edge signatures; its worker decision overrides them per frame.
        self.signature = SIGNATURES.get(tracking_policy, edge_signature)
        self.batch = hasattr(recognizer, "recognize_many")
        self.rows_per_request = getattr(recognizer, "rows_per_request", 0) if self.batch else 0
        if self.batch and (type(self.rows_per_request) is not int or self.rows_per_request < 1):
            raise OcrError("Batch OCR recognizer needs a positive rows_per_request")
        self.metrics = PipelineMetrics()
        self.started = False

    def _frames(self, region: TrackedRegion) -> tuple[RoiFrame, ...]:
        return select_candidates(region, self.candidate_limit)

    def _result(self, region: TrackedRegion, slots: Sequence[_Slot]) -> RegionResult:
        reads = []
        for slot in slots:
            assert slot.raw is not None
            indices = self.line_selection.select(slot.raw, slot.frame.height) if self.line_selection else None
            reads.append(CandidateRead(slot.frame.pts, slot.crop_hash, slot.raw, slot.hit, indices))
        consensus = (choose_witnessed_read(tuple(reads), region.candidates) if self.consensus_policy == POLICY
                     else choose_read(tuple(reads)))
        result = RegionResult(region.start_ms, region.end_ms, tuple(reads), consensus,
                              region.issues, region.start_window_ms, region.end_window_ms,
                              region.first_pts, region.last_pts)
        self.metrics.tracks += 1
        self.metrics.review_regions += result.needs_review
        return result

    def _recognize(self, region: TrackedRegion) -> RegionResult:
        slots = []
        for frame in self._frames(region):
            self.check()
            self.metrics.candidate_crops += 1
            key, crop_hash = self.cache.key(frame)
            raw = self.cache.get(key)
            hit = raw is not None
            if raw is None:
                self.metrics.fresh_calls += 1
                begun = time.monotonic()
                try:
                    raw = self.recognizer(frame, self.check)  # type: ignore[operator]
                    self.check()
                finally:
                    self.metrics.recognition_call_s += time.monotonic() - begun
                self.cache.put(key, raw)
            else:
                self.metrics.cache_hits += 1
            slots.append(_Slot(frame, key, crop_hash, raw, hit))
        return self._result(region, slots)

    def _recognize_batch(self, regions: Sequence[TrackedRegion]) -> list[RegionResult]:
        plan: list[list[_Slot]] = []
        pending: dict[str, list[_Slot]] = {}
        for region in regions:
            slots = []
            for frame in self._frames(region):
                self.check()
                self.metrics.candidate_crops += 1
                key, crop_hash = self.cache.key(frame)
                raw = self.cache.get(key)
                slot = _Slot(frame, key, crop_hash, raw, raw is not None)
                if raw is None:
                    # Identical crops across cues share one row of the request.
                    pending.setdefault(key, []).append(slot)
                else:
                    self.metrics.cache_hits += 1
                slots.append(slot)
            plan.append(slots)
        keys = list(pending)
        for start in range(0, len(keys), self.rows_per_request):
            chunk = keys[start:start + self.rows_per_request]
            self.metrics.fresh_calls += len(chunk)
            begun = time.monotonic()
            try:
                raws = self.recognizer.recognize_many(  # type: ignore[union-attr]
                    [pending[key][0].frame for key in chunk], self.check)
                self.check()
            finally:
                self.metrics.recognition_call_s += time.monotonic() - begun
            if len(raws) != len(chunk):
                raise OcrError("Batch OCR recognizer returned a different number of reads")
            for key, raw in zip(chunk, raws):
                self.cache.put(key, raw)
                for slot in pending[key]:
                    slot.raw = raw
        return [self._result(region, slots) for region, slots in zip(regions, plan)]

    def _emit(self, result: RegionResult) -> Iterator[RegionResult]:
        if self.drop_empty and not result.consensus.text.strip():
            # The reader saw no subtitle in this tracked region; nothing is exported or reviewed.
            self.metrics.empty_regions += 1
            return
        yield result

    def run(self, decoder: RoiDecoder, selection: Selection, *, start_ms: Fraction | None = None,
            initial_issues: tuple[str, ...] = (),
            accept_region: Callable[[TrackedRegion], bool] = lambda _: True) -> Iterator[RegionResult]:
        if self.started:
            raise OcrError("Create a new OCR pipeline for each run")
        self.started = True
        tracker = RegionTracker(initial_issues=initial_issues, signature=self.signature,
                                settle_ms=STROKE_SETTLE_MS if self.signature is stroke_signature else 0)
        observed_regions = 0
        begun = time.monotonic()
        original_check = decoder.check
        pending: list[TrackedRegion] = []
        pending_rows = 0

        def check():
            original_check()
            self.check()

        def flush() -> Iterator[RegionResult]:
            nonlocal pending_rows
            results = self._recognize_batch(pending) if pending else []
            pending.clear()
            pending_rows = 0
            for result in results:
                yield from self._emit(result)

        def handle(region: TrackedRegion) -> Iterator[RegionResult]:
            nonlocal pending_rows
            if self.min_region_ms and region.end_ms - region.start_ms < self.min_region_ms:
                # A subtitle never lasts one or two frames; such flashes are scenery, not text.
                self.metrics.short_regions += 1
                return
            if not self.batch:
                yield from self._emit(self._recognize(region))
                return
            pending.append(region)
            pending_rows += len(self._frames(region))
            if pending_rows >= self.rows_per_request:
                yield from flush()

        decoder.check = check
        try:
            with decoder:
                spans = decoder.spans(selection) if start_ms is None else decoder.spans(selection, start_ms=start_ms)
                for span in spans:
                    self.check()
                    self.metrics.roi_frames += 1
                    started = time.monotonic()
                    decision = None
                    if self.visual_reader:
                        key, _ = self.cache.key(span.frame)
                        decision = self.visual_reader(span.frame, self.cache.get(key))
                    region = tracker.feed(span, decision)
                    self.metrics.tracking_s += time.monotonic() - started
                    self.frame_progress(span.end_ms)
                    if region is not None:
                        observed_regions += 1
                        if accept_region(region):
                            yield from handle(region)
                region = tracker.finish()
                if region is not None:
                    observed_regions += 1
                    if accept_region(region):
                        yield from handle(region)
                if self.batch:
                    yield from flush()
                if not observed_regions:
                    raise OcrError("No subtitle region detected; review the ROI/selection")
        finally:
            decoder.check = original_check
            self.metrics.pipeline_wall_s = time.monotonic() - begun

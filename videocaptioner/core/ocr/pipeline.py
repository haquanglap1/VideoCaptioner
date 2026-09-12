"""Streaming OCR-2 orchestration with injected recognition; no public export or GUI yet."""

from __future__ import annotations

import time
from dataclasses import dataclass
from fractions import Fraction
from typing import Callable, Iterator, Protocol

from .consensus import CandidateRead, Consensus, ReadCache, choose_read
from .decoder import RoiDecoder
from .models import Check, EngineRead, OcrError, RoiFrame, Selection
from .tracking import RegionTracker, TrackedRegion


class Recognizer(Protocol):
    def __call__(self, frame: RoiFrame, check: Check) -> EngineRead:
        """Recognize in a separately supervised process; honor check/timeout while waiting."""
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
    tracking_s: float = 0
    recognition_call_s: float = 0
    pipeline_wall_s: float = 0  # Includes overlap with decode and time spent by the consumer.


class OcrPipeline:
    def __init__(self, recognizer: Recognizer, cache: ReadCache, *, check: Check = lambda: None):
        self.recognizer, self.cache, self.check = recognizer, cache, check
        self.metrics = PipelineMetrics()
        self.started = False

    def _recognize(self, region: TrackedRegion) -> RegionResult:
        reads = []
        for frame in region.candidates:
            self.check()
            self.metrics.candidate_crops += 1
            key, crop_hash = self.cache.key(frame)
            raw = self.cache.get(key)
            hit = raw is not None
            if raw is None:
                self.metrics.fresh_calls += 1
                begun = time.monotonic()
                try:
                    raw = self.recognizer(frame, self.check)
                    self.check()
                finally:
                    self.metrics.recognition_call_s += time.monotonic() - begun
                self.cache.put(key, raw)
            else:
                self.metrics.cache_hits += 1
            reads.append(CandidateRead(frame.pts, crop_hash, raw, hit))
        result = RegionResult(region.start_ms, region.end_ms, tuple(reads), choose_read(tuple(reads)),
                              region.issues, region.start_window_ms, region.end_window_ms,
                              region.first_pts, region.last_pts)
        self.metrics.tracks += 1
        self.metrics.review_regions += result.needs_review
        return result

    def run(self, decoder: RoiDecoder, selection: Selection, *, start_ms: Fraction | None = None,
            initial_issues: tuple[str, ...] = (),
            accept_region: Callable[[TrackedRegion], bool] = lambda _: True) -> Iterator[RegionResult]:
        if self.started:
            raise OcrError("Create a new OCR pipeline for each run")
        self.started = True
        tracker = RegionTracker(initial_issues=initial_issues)
        observed_regions = 0
        begun = time.monotonic()
        original_check = decoder.check

        def check():
            original_check()
            self.check()

        decoder.check = check
        try:
            with decoder:
                spans = decoder.spans(selection) if start_ms is None else decoder.spans(selection, start_ms=start_ms)
                for span in spans:
                    self.check()
                    self.metrics.roi_frames += 1
                    started = time.monotonic()
                    region = tracker.feed(span)
                    self.metrics.tracking_s += time.monotonic() - started
                    if region is not None:
                        observed_regions += 1
                        if accept_region(region):
                            yield self._recognize(region)
                region = tracker.finish()
                if region is not None:
                    observed_regions += 1
                    if accept_region(region):
                        yield self._recognize(region)
                if not observed_regions:
                    raise OcrError("No subtitle region detected; review the ROI/selection")
        finally:
            decoder.check = original_check
            self.metrics.pipeline_wall_s = time.monotonic() - begun

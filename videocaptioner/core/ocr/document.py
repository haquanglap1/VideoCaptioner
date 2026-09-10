"""Immutable OCR observations and explicit review decisions; never synthesize missing text."""

from __future__ import annotations

from dataclasses import dataclass, replace
from fractions import Fraction
from pathlib import Path, PurePosixPath
from typing import Any, Literal

from .codec import atomic_json, decode, digest, encode, read_json, sha256
from .consensus import validate_read
from .geometry import Roi
from .identity import VisualSourceIdentity
from .models import EngineRead, OcrError, Selection
from .pipeline import RegionResult
from .profile import OcrProfileSnapshot

TEXT_ISSUES = frozenset({"engine_disagreement", "insufficient_independent_crops", "uncalibrated_profile",
                         "low_engine_score"})
TIMING_ISSUES = frozenset({"selection_clipped_start", "selection_clipped_end", "unknown_last_frame_duration",
                           "fade_or_contrast_change", "track_holding_limit", "uncertain_boundary",
                           "submillisecond_span"})
HARD_ISSUES = frozenset({"no_engine_read", "empty_engine_read", "model_revision_mismatch"})


@dataclass(frozen=True)
class OcrConfig:
    roi: Roi
    selection: Selection
    profile_sha256: str
    bridge_sha256: str
    language: str = "zh"
    tracking_policy: Literal["edge-tiles-ocr2-v1"] = "edge-tiles-ocr2-v1"
    consensus_policy: Literal["exact-read-uncalibrated-v1"] = "exact-read-uncalibrated-v1"
    profile_snapshot: OcrProfileSnapshot | None = None

    def __post_init__(self) -> None:
        sha256(self.profile_sha256)
        sha256(self.bridge_sha256)
        if self.language != "zh":
            raise OcrError("The installed OCR profile supports the explicit zh configuration")


@dataclass(frozen=True)
class OcrCandidate:
    id: str
    frame_pts: int
    crop_sha256: str
    raw: EngineRead
    cache_hit: bool
    crop_reference: str = ""

    def __post_init__(self) -> None:
        sha256(self.crop_sha256)
        validate_read(self.raw)
        if not self.id.startswith("candidate-") or len(self.id) != 42 or type(self.frame_pts) is not int:
            raise OcrError("Invalid OCR candidate identity")
        if self.crop_reference:
            path = PurePosixPath(self.crop_reference)
            if path.is_absolute() or ".." in path.parts or ":" in self.crop_reference or "\\" in self.crop_reference:
                raise OcrError("OCR crop references must be relative to the saved document")


@dataclass(frozen=True)
class OcrCue:
    id: str
    measured_start_ms: int
    measured_end_ms: int
    exact_start_ms: Fraction
    exact_end_ms: Fraction
    first_pts: int
    last_pts: int
    start_window_ms: tuple[Fraction, Fraction]
    end_window_ms: tuple[Fraction, Fraction]
    candidates: tuple[OcrCandidate, ...]
    raw_candidate_id: str | None
    raw_text: str
    issues: tuple[str, ...]
    selected_candidate_id: str | None = None
    edited_text: str | None = None
    edited_start_ms: int | None = None
    edited_end_ms: int | None = None
    resolved_issues: tuple[str, ...] = ()
    text_review_note: str = ""
    timing_review_note: str = ""

    def __post_init__(self) -> None:
        if not self.id.startswith("ocr-cue-") or len(self.id) != 40:
            raise OcrError("Invalid OCR cue identity")
        if (self.exact_start_ms < 0 or self.exact_end_ms <= self.exact_start_ms
                or self.first_pts > self.last_pts
                or (self.measured_start_ms, self.measured_end_ms)
                != (round(self.exact_start_ms), round(self.exact_end_ms))):
            raise OcrError("Invalid measured OCR timing")
        for window, boundary in ((self.start_window_ms, self.exact_start_ms),
                                  (self.end_window_ms, self.exact_end_ms)):
            if window[0] < 0 or not window[0] <= boundary <= window[1]:
                raise OcrError("Invalid OCR boundary uncertainty")
        ids = [c.id for c in self.candidates]
        if len(ids) != len(set(ids)) or len(ids) > 3:
            raise OcrError("Duplicate or excessive OCR candidates")
        if self.raw_candidate_id is None:
            if self.raw_text or self.candidates:
                raise OcrError("Missing raw candidate reference")
        elif self.candidate(self.raw_candidate_id).raw.text != self.raw_text:
            raise OcrError("Raw OCR text does not match its engine read")
        if self.selected_candidate_id is not None:
            selected = self.candidate(self.selected_candidate_id)
            if self.edited_text != selected.raw.text or not selected.raw.text.strip() or not self.text_review_note.strip():
                raise OcrError("A review must select one complete engine read with a note")
        elif self.edited_text is not None or self.text_review_note:
            raise OcrError("Edited OCR text requires an explicit candidate selection")
        if (self.edited_start_ms is None) != (self.edited_end_ms is None):
            raise OcrError("Both edited OCR boundaries are required")
        if self.edited_start_ms is not None:
            if (self.edited_end_ms is None or not 0 <= self.edited_start_ms < self.edited_end_ms
                    or not self.timing_review_note.strip()):
                raise OcrError("Invalid explicit OCR timing review")
        elif self.timing_review_note:
            raise OcrError("Timing review note needs explicit boundaries")
        if (len(set(self.issues)) != len(self.issues) or len(set(self.resolved_issues)) != len(self.resolved_issues)
                or not set(self.resolved_issues) <= set(self.all_issues)
                or set(self.resolved_issues) & HARD_ISSUES):
            raise OcrError("Invalid OCR review resolution")
        if set(self.resolved_issues) & TEXT_ISSUES and self.selected_candidate_id is None:
            raise OcrError("Text review requires an explicit candidate")
        if set(self.resolved_issues) & TIMING_ISSUES and self.edited_start_ms is None:
            raise OcrError("Timing uncertainty requires explicit reviewed boundaries")
        if set(self.resolved_issues) - TEXT_ISSUES - TIMING_ISSUES:
            raise OcrError("Unknown OCR issues cannot be acknowledged")

    def candidate(self, candidate_id: str) -> OcrCandidate:
        for candidate in self.candidates:
            if candidate.id == candidate_id:
                return candidate
        raise OcrError("Unknown OCR candidate")

    @property
    def all_issues(self) -> tuple[str, ...]:
        issues = set(self.issues)
        if not self.candidates:
            issues.add("no_engine_read")
        if not self.text.strip() or any(not c.raw.text.strip() for c in self.candidates):
            issues.add("empty_engine_read")
        if len({c.raw.revision for c in self.candidates}) > 1:
            issues.add("model_revision_mismatch")
        if len({c.raw.text for c in self.candidates}) > 1:
            issues.add("engine_disagreement")
        if len({c.crop_sha256 for c in self.candidates}) < 2:
            issues.add("insufficient_independent_crops")
        # This schema pins the currently uncalibrated policy. Agreement is not correctness.
        issues.add("uncalibrated_profile")
        if any(a != b for a, b in (self.start_window_ms, self.end_window_ms)):
            issues.add("uncertain_boundary")
        if self.measured_start_ms >= self.measured_end_ms:
            issues.add("submillisecond_span")
        return tuple(sorted(issues))

    @property
    def pending_issues(self) -> tuple[str, ...]:
        return tuple(i for i in self.all_issues if i not in self.resolved_issues)

    @property
    def text(self) -> str:
        return self.raw_text if self.edited_text is None else self.edited_text

    @property
    def start_ms(self) -> int:
        return self.measured_start_ms if self.edited_start_ms is None else self.edited_start_ms

    @property
    def end_ms(self) -> int:
        return self.measured_end_ms if self.edited_end_ms is None else self.edited_end_ms

    def select_candidate(self, candidate_id: str, note: str) -> OcrCue:
        text = self.candidate(candidate_id).raw.text
        resolved = set(self.resolved_issues) | (set(self.all_issues) & TEXT_ISSUES)
        return replace(self, selected_candidate_id=candidate_id, edited_text=text,
                       text_review_note=note, resolved_issues=tuple(sorted(resolved)))

    def review_timing(self, start_ms: int, end_ms: int, note: str) -> OcrCue:
        if type(start_ms) is not int or type(end_ms) is not int:
            raise OcrError("OCR timing must use integer milliseconds")
        return replace(self, edited_start_ms=start_ms, edited_end_ms=end_ms, timing_review_note=note,
                       resolved_issues=tuple(sorted(set(self.resolved_issues) | (set(self.all_issues) & TIMING_ISSUES))))


@dataclass(frozen=True)
class OcrMetrics:
    frames: int = 0
    tracks: int = 0
    candidate_crops: int = 0
    fresh_calls: int = 0
    cache_hits: int = 0
    decode_pipeline_wall_s: float = 0
    tracking_s: float = 0
    recognition_wait_s: float = 0
    job_wall_s: float = 0
    worker_requests: int | None = None
    worker_responses: int | None = None
    detector_attempts: int | None = None
    recognizer_attempts: int | None = None
    classifier_attempts: int | None = None
    worker_inference_s: float | None = None
    worker_process_wall_s: float | None = None

    def __post_init__(self) -> None:
        import math

        if any(not math.isfinite(v) or v < 0 for v in encode(self).values() if v is not None):
            raise OcrError("Invalid OCR metrics")


@dataclass(frozen=True)
class OcrDocument:
    id: str
    visual_source: VisualSourceIdentity
    config: OcrConfig
    cues: tuple[OcrCue, ...]
    complete: bool
    metrics: OcrMetrics = OcrMetrics()
    schema: Literal["ocr-document-v1"] = "ocr-document-v1"

    def __post_init__(self) -> None:
        if self.id != document_id(self.visual_source, self.config) or self.schema != "ocr-document-v1":
            raise OcrError("OCR document identity mismatch")
        if self.config.selection != self.visual_source.selection:
            raise OcrError("OCR selection mismatch")
        if type(self.complete) is not bool or len(self.cues) > 100000:
            raise OcrError("Invalid OCR completion state")
        ids = [c.id for c in self.cues]
        if len(set(ids)) != len(ids):
            raise OcrError("Duplicate OCR cue IDs")
        previous = Fraction(self.config.selection.start_ms)
        for cue in self.cues:
            if cue.exact_start_ms < previous or cue.exact_end_ms > self.config.selection.end_ms:
                raise OcrError("OCR measurements overlap or exceed selection")
            previous = cue.exact_end_ms
            if cue.id != cue_id(self.id, cue.exact_start_ms, cue.exact_end_ms, cue.first_pts, cue.last_pts):
                raise OcrError("OCR cue identity mismatch")
            if not self.config.selection.start_ms <= cue.start_ms <= cue.end_ms <= self.config.selection.end_ms:
                raise OcrError("Reviewed OCR timing exceeds selection")
            video = self.visual_source.video
            first_ms = (cue.first_pts * video.time_base - video.timeline_origin) * 1000
            last_ms = (cue.last_pts * video.time_base - video.timeline_origin) * 1000
            if first_ms > cue.exact_start_ms or last_ms >= cue.exact_end_ms:
                raise OcrError("OCR boundary PTS do not match the source timeline")
            for candidate in cue.candidates:
                if candidate.raw.revision != self.config.profile_sha256:
                    raise OcrError("OCR engine revision does not match the saved profile")
                if candidate.id != candidate_id(self.id, candidate.frame_pts, candidate.crop_sha256, candidate.raw):
                    raise OcrError("OCR candidate identity mismatch")
                if not cue.first_pts <= candidate.frame_pts <= cue.last_pts:
                    raise OcrError("OCR candidate lies outside its observed track")

    @property
    def pending_issues(self) -> tuple[str, ...]:
        issues = []
        if not self.complete:
            issues.append("incomplete_scan")
        if self.config.profile_snapshot is None:
            issues.append("missing_profile_snapshot")
        if not self.cues:
            issues.append("no_cues")
        previous_end = self.config.selection.start_ms
        for cue in self.cues:
            issues.extend(f"{cue.id}:{issue}" for issue in cue.pending_issues)
            if cue.start_ms < previous_end or cue.end_ms <= cue.start_ms:
                issues.append(f"{cue.id}:invalid_export_timing")
            previous_end = max(previous_end, cue.end_ms)
        return tuple(issues)

    def replace_cue(self, cue: OcrCue) -> OcrDocument:
        if cue.id not in {c.id for c in self.cues}:
            raise OcrError("Unknown OCR cue")
        return replace(self, cues=tuple(cue if c.id == cue.id else c for c in self.cues))

    def to_dict(self) -> dict:
        return encode(self)

    @classmethod
    def from_dict(cls, value: Any) -> OcrDocument:
        return decode(cls, value)

    @classmethod
    def load(cls, path: str | Path) -> OcrDocument:
        return cls.from_dict(read_json(Path(path)))

    def save(self, path: str | Path) -> None:
        value = self.to_dict()
        self.from_dict(value)
        atomic_json(Path(path), value)

    def resume(self, actual_source: VisualSourceIdentity):
        from .adapters import document_to_subtitles

        self.visual_source.require_match(actual_source)
        if self.pending_issues:
            raise OcrError("OCR review is unresolved; complete source, text and timing review before export")
        return document_to_subtitles(self)


def document_id(source: VisualSourceIdentity, config: OcrConfig) -> str:
    return "ocr-" + digest([encode(source), encode(config)])[:32]


def candidate_id(document: str, pts: int, crop_hash: str, raw: EngineRead) -> str:
    return "candidate-" + digest([document, pts, crop_hash, encode(decode(EngineRead, encode(raw)))])[:32]


def cue_id(document: str, start: Fraction, end: Fraction, first_pts: int, last_pts: int) -> str:
    return "ocr-cue-" + digest([document, encode(start), encode(end), first_pts, last_pts])[:32]


def cue_from_region(document: str, region: RegionResult) -> OcrCue:
    candidates = tuple(OcrCandidate(candidate_id(document, c.frame_pts, c.crop_sha256, c.raw),
                                     c.frame_pts, c.crop_sha256, c.raw, c.cache_hit) for c in region.reads)
    if region.first_pts is None or region.last_pts is None:
        raise OcrError("OCR region lacks observed boundary PTS")
    selected = region.consensus.selected_index
    if selected is not None and not 0 <= selected < len(candidates):
        raise OcrError("Invalid OCR consensus reference")
    return OcrCue(cue_id(document, region.start_ms, region.end_ms, region.first_pts, region.last_pts),
                  round(region.start_ms), round(region.end_ms), region.start_ms, region.end_ms,
                  region.first_pts, region.last_pts, region.start_window_ms, region.end_window_ms,
                  candidates, candidates[selected].id if selected is not None else None,
                  region.consensus.text, tuple(sorted(set(region.issues + region.consensus.issues))))

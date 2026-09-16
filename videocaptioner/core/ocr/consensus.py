"""Whole-engine-read consensus and a byte-limited, source/profile-specific memory cache."""

from __future__ import annotations

import hashlib
import json
import math
from collections import Counter, OrderedDict
from dataclasses import asdict, dataclass

from .line_selection import selected_text
from .models import EngineRead, OcrError, RoiFrame


def validate_read(read: EngineRead) -> None:
    if not isinstance(read, EngineRead) or not read.revision or len(read.lines) > 32:
        raise OcrError("Invalid OCR engine response")
    for line in read.lines:
        if (not isinstance(line.text, str) or len(line.text) > 4096
                or not math.isfinite(line.score) or not 0 <= line.score <= 1
                or len(line.box) != 4
                or any(not math.isfinite(v) for point in line.box for v in point)
                or any(len(point) != 2 for point in line.box)):
            raise OcrError("Invalid OCR line response")


@dataclass(frozen=True)
class CandidateRead:
    frame_pts: int
    crop_sha256: str
    raw: EngineRead
    cache_hit: bool
    selected_line_indices: tuple[int, ...] | None = None

    @property
    def text(self) -> str:
        return selected_text(self.raw, self.selected_line_indices)

    @property
    def min_score(self) -> float:
        indices = range(len(self.raw.lines)) if self.selected_line_indices is None else self.selected_line_indices
        return min((self.raw.lines[i].score for i in indices), default=0)


@dataclass(frozen=True)
class Consensus:
    selected_index: int | None
    text: str
    issues: tuple[str, ...]


def choose_read(candidates: tuple[CandidateRead, ...], *, calibrated_min_score: float | None = None) -> Consensus:
    if calibrated_min_score is not None and not 0 <= calibrated_min_score <= 1:
        raise OcrError("Invalid calibrated OCR threshold")
    if not candidates:
        return Consensus(None, "", ("no_engine_read",))
    for candidate in candidates:
        validate_read(candidate.raw)
    texts = [item.text for item in candidates]
    counts = Counter(texts)
    # Exact codepoints and line breaks: no script conversion, interpolation or name repair.
    selected = max(range(len(candidates)), key=lambda i: (bool(texts[i].strip()), counts[texts[i]],
                   candidates[i].min_score, -i))
    issues = set()
    if not texts[selected].strip():
        issues.add("empty_engine_read")
    if len(counts) > 1:
        issues.add("engine_disagreement")
    if len({c.crop_sha256 for c in candidates}) < 2:
        issues.add("insufficient_independent_crops")
    if len({c.raw.revision for c in candidates}) != 1:
        issues.add("model_revision_mismatch")
    if calibrated_min_score is None:
        issues.add("uncalibrated_profile")
    elif any(c.min_score < calibrated_min_score for c in candidates):
        issues.add("low_engine_score")
    return Consensus(selected, texts[selected], tuple(sorted(issues)))


@dataclass(frozen=True)
class CacheScope:
    source_sha256: str
    profile_sha256: str
    policy_sha256: str  # Includes ROI, transform, selection and tracking/consensus policy.

    def __post_init__(self) -> None:
        for value in (self.source_sha256, self.profile_sha256, self.policy_sha256):
            if len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
                raise OcrError("OCR cache scope needs SHA-256 identities")


class ReadCache:
    """Job-owned raw values only; cached agreement does not become accepted review state."""

    def __init__(self, scope: CacheScope, max_bytes: int = 1024 * 1024, max_entries: int = 256):
        if max_bytes <= 0 or max_entries <= 0:
            raise OcrError("Invalid OCR cache limit")
        self.scope, self.max_bytes, self.max_entries = scope, max_bytes, max_entries
        self.entries: OrderedDict[str, tuple[EngineRead, int]] = OrderedDict()
        self.size = 0

    def key(self, frame: RoiFrame) -> tuple[str, str]:
        crop_hash = hashlib.sha256(frame.rgb).hexdigest()
        payload = [asdict(self.scope), frame.width, frame.height, crop_hash]
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest(), crop_hash

    def get(self, key: str) -> EngineRead | None:
        entry = self.entries.get(key)
        if entry is None:
            return None
        self.entries.move_to_end(key)
        return entry[0]

    def put(self, key: str, read: EngineRead) -> None:
        validate_read(read)
        size = len(json.dumps(asdict(read), ensure_ascii=False).encode("utf-8")) + len(key)
        old = self.entries.pop(key, None)
        if old:
            self.size -= old[1]
        if size > self.max_bytes:
            return
        while self.entries and (self.size + size > self.max_bytes or len(self.entries) >= self.max_entries):
            _, (_, removed) = self.entries.popitem(last=False)
            self.size -= removed
        self.entries[key] = read, size
        self.size += size

"""Stable domain models for natural dubbing plans and reports."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Iterable


class _StringEnum(str, Enum):
    def __str__(self) -> str:
        return self.value


class DubbingTextSource(_StringEnum):
    AUTO = "auto"
    TRANSLATED = "translated"
    ORIGINAL = "original"


class DubbingTimingMode(_StringEnum):
    NATURAL = "natural"
    LEGACY = "legacy"


class UnresolvedFitPolicy(_StringEnum):
    REVIEW = "review"
    ALLOW_OVERLAP = "allow-overlap"


class DubbingFitStatus(_StringEnum):
    PENDING = "pending"
    CACHED = "cached"
    FIT = "fit"
    REWRITTEN = "rewritten"
    SPEED_ADJUSTED = "speed-adjusted"
    NEEDS_REVIEW = "needs-review"
    FAILED = "failed"


class DubbingValidationError(ValueError):
    """Raised when the requested dubbing text cannot be resolved safely."""


class DubbingReviewRequired(RuntimeError):
    """Raised when Natural REVIEW blocks mixing."""

    def __init__(self, report_path: str = "", reason: str = ""):
        self.report_path = report_path
        self.reason = reason or "Lồng tiếng cần xem lại vì một số câu vẫn vượt khung thời gian."
        suffix = f" Report: {report_path}" if report_path else ""
        super().__init__(f"{self.reason}{suffix}")


class DubbingProviderError(RuntimeError):
    """Raised when one or more TTS groups fail."""

    def __init__(self, report_path: str = "", reason: str = ""):
        self.report_path = report_path
        self.reason = reason or "Nhà cung cấp TTS không tạo được audio hợp lệ."
        suffix = f" Report: {report_path}" if report_path else ""
        super().__init__(f"{self.reason}{suffix}")


@dataclass
class DubbingCue:
    cue_id: int | str
    start_time: float
    end_time: float
    source_text: str
    subtitle_text: str
    tts_text: str
    speaker: str = ""
    voice: str = ""
    group_id: str = ""
    original_index: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class DubbingGroup:
    group_id: str
    cue_ids: list[int | str]
    start_time: float
    subtitle_end_time: float
    available_end_time: float
    available_duration: float
    source_text: str
    subtitle_text: str
    tts_text: str
    predicted_duration: float = 0.0
    measured_duration: float = 0.0
    fit_ratio: float = 0.0
    attempt_count: int = 0
    action_taken: str = ""
    fit_status: DubbingFitStatus = DubbingFitStatus.PENDING
    needs_review: bool = False
    cache_key: str = ""
    audio_path: str = ""
    warnings: list[str] = field(default_factory=list)


@dataclass
class DubbingPlan:
    source_path: str
    target_language: str
    provider: str
    model: str
    voice: str
    timing_mode: DubbingTimingMode
    created_at: str
    groups: list[DubbingGroup]
    summary: dict[str, Any] = field(default_factory=dict)
    schema_version: str = "dubbing-plan-v1"

    def __post_init__(self) -> None:
        self.source_path = Path(self.source_path).name

    def to_dict(self, *, report_dir: Path | None = None) -> dict[str, Any]:
        data = asdict(self)
        data["timing_mode"] = self.timing_mode.value
        for group_data, group in zip(data["groups"], self.groups):
            group_data["fit_status"] = group.fit_status.value
            if not math.isfinite(group.fit_ratio):
                group_data["fit_ratio"] = None
            audio_path = Path(group.audio_path) if group.audio_path else None
            if audio_path:
                if report_dir:
                    try:
                        group_data["audio_path"] = str(audio_path.resolve().relative_to(report_dir.resolve()))
                    except ValueError:
                        group_data["audio_path"] = audio_path.name
                else:
                    group_data["audio_path"] = audio_path.name
        return data


@dataclass
class DubbingReport:
    plan: DubbingPlan
    report_path: str = ""
    schema_version: str = "dubbing-report-v1"

    def to_dict(self) -> dict[str, Any]:
        report_dir = Path(self.report_path).parent if self.report_path else None
        data = self.plan.to_dict(report_dir=report_dir)
        data["plan_schema_version"] = data.pop("schema_version")
        data["schema_version"] = self.schema_version
        return data


def resolve_dubbing_text(segment: Any, source_mode: DubbingTextSource) -> str:
    """Resolve the exact text sent to TTS without changing display subtitles."""
    source = str(getattr(segment, "text", "") or "").strip()
    translated = str(getattr(segment, "translated_text", "") or "").strip()
    if source_mode == DubbingTextSource.TRANSLATED:
        if not translated:
            raise DubbingValidationError(
                "Translated dubbing text is missing for one or more subtitle cues"
            )
        return translated
    if source_mode == DubbingTextSource.ORIGINAL:
        if not source:
            raise DubbingValidationError("Original dubbing text is empty")
        return source
    text = translated or source
    if not text:
        raise DubbingValidationError("Dubbing text is empty")
    return text


def calculate_report_summary(groups: Iterable[DubbingGroup], output_created: bool) -> dict[str, Any]:
    items = list(groups)
    ratios = sorted(group.fit_ratio for group in items if math.isfinite(group.fit_ratio))
    p95_index = max(0, math.ceil(len(ratios) * 0.95) - 1) if ratios else 0
    return {
        "total_groups": len(items),
        "cache_hits": sum("cache_hit" in group.action_taken for group in items),
        "rewritten_groups": sum("rewrite" in group.action_taken for group in items),
        "speed_adjusted_groups": sum(
            "speed_adjust_" in group.action_taken for group in items
        ),
        "fit_groups": sum(
            group.fit_status
            in {DubbingFitStatus.FIT, DubbingFitStatus.CACHED, DubbingFitStatus.REWRITTEN}
            for group in items
        ),
        "review_groups": sum(group.needs_review for group in items),
        "failed_groups": sum(group.fit_status == DubbingFitStatus.FAILED for group in items),
        "maximum_fit_ratio": round(max(ratios, default=0.0), 4),
        "p95_fit_ratio": round(ratios[p95_index], 4) if ratios else 0.0,
        "total_tts_attempts": sum(group.attempt_count for group in items),
        "output_created": output_created,
    }

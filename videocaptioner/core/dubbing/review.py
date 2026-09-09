"""Typed review documents; JSON supplies wording and evidence, never execution paths.

``DubbingReview.from_report(engine.last_report)`` captures a detached RAM copy.
Use ``with_group_text`` for edits, and ``save``/``load`` only on explicit user
request. Loading a legacy report permits inspection; ``engine.import_review``
is required to bind it to the user's currently selected sources and settings.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import tempfile
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit

from .cache import build_tts_cache_key
from .config import DubbingConfig, TTSProviderEnum, tts_provider_key
from .models import (
    DubbingFitStatus,
    DubbingGroup,
    DubbingPlan,
    DubbingReport,
    DubbingResumeMetadata,
    DubbingSourceFingerprint,
    DubbingTimingMode,
    DubbingValidationError,
)
from .planner import NORMALIZATION_VERSION, predict_spoken_duration

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_GROUP_BINDING = (
    "group_id", "cue_ids", "start_time", "subtitle_end_time", "available_end_time",
    "available_duration", "source_text", "subtitle_text",
)


class DubbingResumeError(DubbingValidationError):
    """A review could not be verified; keep it available for inspection/editing."""


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":")
    ).encode("utf-8")).hexdigest()


def synthesis_cache_key(text: str, config: DubbingConfig) -> str:
    """Preserve established keys, adding previously unrepresented voice options."""
    tts = config.tts_config
    if tts is None:
        raise DubbingResumeError("TTS configuration is required")
    key = build_tts_cache_key(
        text=text, provider=tts_provider_key(config.tts_provider), api_base=tts.base_url,
        model=tts.model, voice=tts.voice or "", speed=tts.speed, sample_rate=tts.sample_rate,
        runtime_identity=config.managed_tts_identity,
    )
    # Defaults retain established keys, including managed-provider WAV checkpoints.
    extra = {}
    if tts.custom_prompt or tts.gain or tts.stream:
        extra.update(custom_prompt=tts.custom_prompt or "", gain=tts.gain, stream=tts.stream)
    managed = config.tts_provider in (TTSProviderEnum.VIENEU_LOCAL, TTSProviderEnum.OMNIVOICE_LOCAL)
    default_format = "wav" if managed else "mp3"
    if tts.response_format != default_format:
        extra["response_format"] = tts.response_format
    if not managed:
        endpoint = urlsplit(tts.base_url)
        route = endpoint.path.rstrip("/")
        if route not in ("", "/v1") or endpoint.scheme not in ("", "https") or endpoint.query:
            extra["endpoint"] = [endpoint.scheme, route, endpoint.query]
    return _digest({"base_key": key, "options": extra}) if extra else key


def settings_fingerprint(config: DubbingConfig) -> str:
    """Bind synthesis/routing/timing; exclude credentials and operational controls.

    Cache enablement, concurrency, timeouts, mixing volumes and report paths may
    change without changing speech. Resume never invokes automatic rewriting.
    """
    return _digest({
        "synthesis_key": synthesis_cache_key("", config),
        "normalization_version": NORMALIZATION_VERSION,
        "text_source": config.text_source.value, "strip_cjk": config.strip_cjk,
        "target_language": config.target_language, "timing_mode": config.timing_mode.value,
        "borrow_gap_ms": config.borrow_gap_ms, "silence_guard_ms": config.silence_guard_ms,
        "max_group_duration": config.max_group_duration, "max_speed": config.max_speed,
        "natural_max_speed": config.natural_max_speed, "fit_ratio_limit": config.fit_ratio_limit,
        "unresolved_policy": config.unresolved_policy.value,
        "max_start_delay_ms": config.max_start_delay_ms,
        "response_format": config.tts_config.response_format if config.tts_config else "",
    })


def fingerprint_source(path: str, callback: Callable[[int, str], None]) -> DubbingSourceFingerprint:
    source = Path(path)
    digest = hashlib.sha256()
    try:
        before = source.stat()
        with source.open("rb") as handle:
            while chunk := handle.read(4 * 1024 * 1024):
                callback(8, "Đang xác minh nguồn lồng tiếng...")
                digest.update(chunk)
        after = source.stat()
    except OSError as exc:
        raise DubbingResumeError(f"Cannot read selected source: {source.name}") from exc
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise DubbingResumeError(f"Selected source changed while reading: {source.name}")
    return DubbingSourceFingerprint(source.name, after.st_size, digest.hexdigest())


def bind_sources(
    video_path: str, subtitle_path: str, display_subtitle_path: str | None,
    duration: float, config: DubbingConfig, callback: Callable[[int, str], None],
) -> DubbingResumeMetadata:
    return DubbingResumeMetadata(
        media=fingerprint_source(video_path, callback),
        subtitle=fingerprint_source(subtitle_path, callback),
        display_subtitle=fingerprint_source(display_subtitle_path, callback) if display_subtitle_path else None,
        video_duration=duration, settings_sha256=settings_fingerprint(config),
    )


def _object(value: Any, label: str) -> dict:
    if not isinstance(value, dict):
        raise DubbingResumeError(f"Invalid {label}: expected an object")
    return value


def _string(value: Any, label: str, *, nonempty: bool = False) -> str:
    if not isinstance(value, str) or (nonempty and not value.strip()):
        raise DubbingResumeError(f"Invalid {label}: expected {'nonempty ' if nonempty else ''}text")
    return value


def _number(value: Any, label: str, *, minimum: float = 0) -> float:
    if type(value) not in (int, float) or not math.isfinite(value) or value < minimum:
        raise DubbingResumeError(f"Invalid {label}: expected a finite number >= {minimum}")
    return float(value)


def _hash(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise DubbingResumeError(f"Invalid {label}: expected SHA-256")
    return value


def _source(value: Any, label: str) -> DubbingSourceFingerprint:
    data = _object(value, label)
    name = _string(data.get("name"), f"{label}.name", nonempty=True)
    if "/" in name or "\\" in name or name in (".", ".."):
        raise DubbingResumeError(f"Invalid {label}.name: expected a filename")
    size = data.get("size")
    if type(size) is not int or size < 0:
        raise DubbingResumeError(f"Invalid {label}.size")
    return DubbingSourceFingerprint(name, size, _hash(data.get("sha256"), f"{label}.sha256"))


def _metadata(value: Any) -> DubbingResumeMetadata | None:
    if value is None:
        return None
    data = _object(value, "resume_metadata")
    if data.get("schema_version") != "dubbing-resume-v1":
        raise DubbingResumeError("Unsupported dubbing resume metadata schema")
    provenance = data.get("provenance", "captured-at-run")
    if provenance not in ("captured-at-run", "legacy-user-bound"):
        raise DubbingResumeError("Unsupported review provenance")
    return DubbingResumeMetadata(
        media=_source(data.get("media"), "media"), subtitle=_source(data.get("subtitle"), "subtitle"),
        display_subtitle=_source(data["display_subtitle"], "display_subtitle") if data.get("display_subtitle") is not None else None,
        video_duration=_number(data.get("video_duration"), "video_duration", minimum=0.001),
        settings_sha256=_hash(data.get("settings_sha256"), "settings_sha256"), provenance=provenance,
    )


def _group(value: Any) -> DubbingGroup:
    data = _object(value, "group")
    group_id = _string(data.get("group_id"), "group_id", nonempty=True)
    cue_ids = data.get("cue_ids")
    if not isinstance(cue_ids, list) or not cue_ids or any(
        type(item) not in (int, str) or not str(item).strip() for item in cue_ids
    ):
        raise DubbingResumeError(f"Invalid cue membership: {group_id}")
    kwargs: dict[str, Any] = {"group_id": group_id, "cue_ids": list(cue_ids)}
    for name in ("source_text", "subtitle_text", "tts_text"):
        kwargs[name] = _string(data.get(name), f"{group_id}.{name}", nonempty=name == "tts_text")
    for name in ("start_time", "subtitle_end_time", "available_end_time", "available_duration"):
        kwargs[name] = _number(data.get(name), f"{group_id}.{name}")
    if (kwargs["subtitle_end_time"] <= kwargs["start_time"]
        or kwargs["available_end_time"] < kwargs["subtitle_end_time"]
        or not math.isclose(kwargs["available_duration"], kwargs["available_end_time"] - kwargs["start_time"], abs_tol=1e-6)):
        raise DubbingResumeError(f"Invalid timeline: {group_id}")
    # Parse diagnostics for display only. They never select audio or bypass fit.
    for name in ("predicted_duration", "measured_duration", "fit_ratio", "start_delay", "applied_speed"):
        if name in data:
            value = data[name]
            kwargs[name] = float("inf") if name == "fit_ratio" and value is None else _number(value, f"{group_id}.{name}")
    for name in ("playback_start_time", "playback_end_time"):
        if data.get(name) is not None:
            kwargs[name] = _number(data[name], f"{group_id}.{name}")
    for name in ("action_taken", "audio_path", "cache_key", "original_tts_text"):
        if name in data:
            kwargs[name] = _string(data[name], f"{group_id}.{name}")
    for name in ("attempt_count", "needs_review"):
        if name in data:
            expected_type = int if name == "attempt_count" else bool
            if type(data[name]) is not expected_type or (name == "attempt_count" and data[name] < 0):
                raise DubbingResumeError(f"Invalid {group_id}.{name}")
            kwargs[name] = data[name]
    if "warnings" in data:
        if not isinstance(data["warnings"], list) or any(not isinstance(item, str) for item in data["warnings"]):
            raise DubbingResumeError(f"Invalid {group_id}.warnings")
        kwargs["warnings"] = list(data["warnings"])
    try:
        kwargs["fit_status"] = DubbingFitStatus(data.get("fit_status", "pending"))
    except (ValueError, TypeError) as exc:
        raise DubbingResumeError(f"Invalid {group_id}.fit_status") from exc
    return DubbingGroup(**kwargs)


@dataclass(frozen=True)
class DubbingReview:
    """Detached typed snapshot. Use methods to edit; accessors return copies."""

    _plan: DubbingPlan

    @classmethod
    def from_report(cls, report: dict[str, Any]) -> DubbingReview:
        data = _object(deepcopy(report), "report")
        if data.get("schema_version") != "dubbing-report-v1" or data.get("plan_schema_version") != "dubbing-plan-v1":
            raise DubbingResumeError("Unsupported dubbing report/plan schema")
        raw_groups = data.get("groups")
        if not isinstance(raw_groups, list) or not raw_groups:
            raise DubbingResumeError("Review must contain groups")
        groups = [_group(item) for item in raw_groups]
        if len({group.group_id for group in groups}) != len(groups):
            raise DubbingResumeError("Duplicate group ID in review")
        cues = [str(cue) for group in groups for cue in group.cue_ids]
        if len(set(cues)) != len(cues):
            raise DubbingResumeError("Duplicate cue membership in review")
        values = {name: _string(data.get(name), name) for name in (
            "source_path", "target_language", "provider", "model", "voice", "created_at"
        )}
        try:
            timing = DubbingTimingMode(data.get("timing_mode"))
        except (ValueError, TypeError) as exc:
            raise DubbingResumeError("Invalid review timing_mode") from exc
        identity = _object(data.get("provider_identity", {}), "provider_identity")
        if any(not isinstance(key, str) or type(value) not in (str, int, float, bool)
               or (type(value) is float and not math.isfinite(value)) for key, value in identity.items()):
            raise DubbingResumeError("Invalid provider identity")
        return cls(DubbingPlan(**values, timing_mode=timing, groups=groups, provider_identity=identity,
                              summary=_object(data.get("summary", {}), "summary"),
                              resume_metadata=_metadata(data.get("resume_metadata"))))

    @property
    def plan(self) -> DubbingPlan:
        return deepcopy(self._plan)

    @property
    def groups(self) -> tuple[DubbingGroup, ...]:
        return tuple(deepcopy(self._plan.groups))

    @property
    def can_resume(self) -> bool:
        """Metadata exists; current source/config validation still runs at resume."""
        return self._plan.resume_metadata is not None

    @property
    def provenance_note(self) -> str:
        metadata = self._plan.resume_metadata
        if metadata is None:
            return "Legacy report has no source/settings fingerprints; explicit import with selected sources/config is required."
        if metadata.provenance == "legacy-user-bound":
            return "Fingerprints were captured at explicit import; historical media identity and unrecorded settings cannot be verified."
        return "Source/settings fingerprints captured for this job; revalidated on resume."

    def to_dict(self) -> dict[str, Any]:
        return DubbingReport(self._plan).to_dict()

    def with_group_text(self, group_id: str, tts_text: str) -> DubbingReview:
        text = _string(tts_text, "tts_text", nonempty=True)
        plan = self.plan
        group = next((item for item in plan.groups if item.group_id == group_id), None)
        if group is None:
            raise DubbingResumeError(f"Unknown review group: {group_id}")
        if group.tts_text == text:
            return DubbingReview(plan)
        group.tts_text = text
        group.audio_path = group.cache_key = ""
        group.measured_duration = group.fit_ratio = 0.0
        group.playback_start_time = group.playback_end_time = None
        group.start_delay, group.applied_speed = 0.0, 1.0
        group.predicted_duration = predict_spoken_duration(text, plan.target_language)
        group.fit_status, group.needs_review = DubbingFitStatus.PENDING, True
        group.action_taken = "review_text_edited"
        plan.summary = {**plan.summary, "output_created": False}
        return DubbingReview(plan)

    def save(self, path: str | Path) -> None:
        """Atomically save only to the path explicitly supplied by the caller."""
        data = DubbingReview.from_report(self.to_dict()).to_dict()
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(data, handle, ensure_ascii=False, indent=2, allow_nan=False)
            os.replace(temporary, target)
        finally:
            Path(temporary).unlink(missing_ok=True)

    @classmethod
    def load(cls, path: str | Path) -> DubbingReview:
        def unique_pairs(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise DubbingResumeError(f"Duplicate JSON field: {key}")
                result[key] = value
            return result
        try:
            with Path(path).open(encoding="utf-8") as handle:
                data = json.load(handle, object_pairs_hook=unique_pairs)
        except (OSError, ValueError, RecursionError) as exc:
            raise DubbingResumeError("Cannot load dubbing review JSON: " + str(exc)) from exc
        return cls.from_report(data)

    def restore_into(self, fresh: DubbingPlan, config: DubbingConfig, *, allow_config_change: bool = False,
                     legacy_import: bool = False) -> None:
        """Verify a fresh source-derived plan, then copy wording only."""
        saved = DubbingReview.from_report(self.to_dict())._plan
        old, new = saved.resume_metadata, fresh.resume_metadata
        if new is None:
            raise DubbingResumeError("Fresh plan has no source binding")
        if old is None and not legacy_import:
            raise DubbingResumeError(self.provenance_note)
        if old is not None:
            for name in ("media", "subtitle", "display_subtitle"):
                previous, current = getattr(old, name), getattr(new, name)
                # Relocation/renaming is safe when the complete content matches.
                if (previous is None) != (current is None) or (previous is not None and current is not None
                    and (previous.size, previous.sha256) != (current.size, current.sha256)):
                    raise DubbingResumeError(f"Review source mismatch: {name}")
            if not math.isclose(old.video_duration, new.video_duration, abs_tol=1e-6):
                raise DubbingResumeError("Review video duration mismatch")
            if not allow_config_change and old.settings_sha256 != new.settings_sha256:
                raise DubbingResumeError("Review settings mismatch; explicitly apply configuration changes to resume")
            new.provenance = old.provenance
        if not allow_config_change or legacy_import:
            for name in ("provider", "model", "voice", "provider_identity", "target_language", "timing_mode"):
                if getattr(saved, name) != getattr(fresh, name):
                    raise DubbingResumeError(f"Review provider/settings mismatch: {name}")
        if len(saved.groups) != len(fresh.groups):
            raise DubbingResumeError("Review group membership mismatch")
        for previous, current in zip(saved.groups, fresh.groups):
            for name in _GROUP_BINDING:
                a, b = getattr(previous, name), getattr(current, name)
                equal = math.isclose(a, b, abs_tol=1e-6) if isinstance(a, float) else a == b
                if not equal:
                    raise DubbingResumeError(f"Review group mismatch: {previous.group_id}.{name}")
            if previous.original_tts_text and previous.original_tts_text != current.original_tts_text:
                raise DubbingResumeError(f"Review group mismatch: {previous.group_id}.original_tts_text")
            if legacy_import:
                if previous.cache_key != synthesis_cache_key(previous.tts_text, config):
                    raise DubbingResumeError(f"Legacy TTS settings/cache key cannot be verified: {previous.group_id}")
            current.tts_text = previous.tts_text
            current.predicted_duration = predict_spoken_duration(current.tts_text, config.target_language)
            # Deliberately ignore all supplied cache paths, metrics and fit flags.
        if legacy_import:
            if not math.isclose(saved.groups[-1].available_end_time, new.video_duration, abs_tol=1e-6):
                raise DubbingResumeError("Legacy report cannot verify the selected video duration")
            new.provenance = "legacy-user-bound"

"""Pure deterministic grouping and duration prediction for dubbing cues."""

from __future__ import annotations

import re
from dataclasses import replace

from videocaptioner.core.dubbing.models import DubbingCue, DubbingGroup

NORMALIZATION_VERSION = "tts-normalization-v1"
_WS_RE = re.compile(r"\s+")
_TOKEN_RE = re.compile(r"[A-Za-zÀ-ỹА-Яа-я0-9]+|[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]")
_SPECIAL_RE = re.compile(
    r"(?:https?://\S+|www\.\S+|\b[A-Z]{2,}\b|\b[A-Za-z]+\d+[A-Za-z0-9-]*\b|\b\d+(?:[.,]\d+)?%?\b)"
)
_STRONG_END_RE = re.compile(r"[.!?。！？]\s*$")
_PUNCTUATION_RE = re.compile(r"[,;:，；：.!?。！？]")


def normalize_tts_text(text: str) -> str:
    return _WS_RE.sub(" ", text.replace("\n", " ")).strip()


def _join_text(parts: list[str]) -> str:
    return normalize_tts_text(" ".join(part for part in parts if part.strip()))


def _trim_spoken_prefix(text: str, token_count: int) -> str:
    matches = list(_TOKEN_RE.finditer(text))
    if token_count <= 0 or token_count >= len(matches):
        return text
    remainder = text[matches[token_count - 1].end():]
    return re.sub(r"^[\s,;:，；：.!?。！？\-–—]+", "", remainder).strip()


def _join_tts_text(parts: list[str]) -> tuple[str, list[str]]:
    """Join spoken cues while removing splitter overlap at merged boundaries."""
    normalized = [normalize_tts_text(part) for part in parts if part.strip()]
    if not normalized:
        return "", []
    result = normalized[0]
    removed: list[str] = []
    for part in normalized[1:]:
        previous_tokens = [match.group(0).casefold() for match in _TOKEN_RE.finditer(result)]
        next_tokens = [match.group(0).casefold() for match in _TOKEN_RE.finditer(part)]
        max_overlap = min(4, len(previous_tokens), len(next_tokens))
        overlap = next(
            (
                count
                for count in range(max_overlap, 0, -1)
                if previous_tokens[-count:] == next_tokens[:count]
            ),
            0,
        )
        trimmed = _trim_spoken_prefix(part, overlap)
        # Keep a fully repeated cue: dropping it would erase an intentional
        # subtitle rather than repair a split-boundary overlap.
        if overlap and trimmed != part:
            removed.append(" ".join(next_tokens[:overlap]))
        result = _join_text([result, trimmed])
    return result, removed


def predict_spoken_duration(text: str, target_language: str = "") -> float:
    """Conservative routing estimate; measured WAV duration remains authoritative."""
    normalized = normalize_tts_text(text)
    if not normalized:
        return 0.0
    tokens = _TOKEN_RE.findall(normalized)
    cjk_units = sum(bool(re.fullmatch(r"[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]", token)) for token in tokens)
    other_units = len(tokens) - cjk_units
    language = target_language.lower()
    rate = 4.2 if any(mark in language for mark in ("zh", "ja", "ko", "chinese", "japanese", "korean")) else 2.65
    base = (cjk_units + other_units) / max(rate, 0.1)
    punctuation_cost = 0.12 * len(_PUNCTUATION_RE.findall(normalized))
    special_cost = 0.18 * len(_SPECIAL_RE.findall(normalized))
    symbol_cost = 0.08 * len(re.findall(r"[$€£¥+&@#/]", normalized))
    return round(max(0.18, base + punctuation_cost + special_cost + symbol_cost), 4)


def plan_dubbing_groups(
    cues: list[DubbingCue],
    *,
    video_duration: float,
    borrow_gap_ms: int = 350,
    silence_guard_ms: int = 80,
    max_group_duration: float = 8.0,
    target_language: str = "",
) -> list[DubbingGroup]:
    """Group adjacent cues and assign real timeline capacity without side effects."""
    ordered = sorted((replace(cue) for cue in cues), key=lambda cue: (cue.start_time, cue.original_index))
    if not ordered:
        return []

    cue_groups: list[list[DubbingCue]] = []
    current: list[DubbingCue] = []
    for cue in ordered:
        if not current:
            current = [cue]
            continue
        previous = current[-1]
        gap = cue.start_time - previous.end_time
        combined_span = cue.end_time - current[0].start_time
        speaker_matches = previous.speaker == cue.speaker or (not previous.speaker and not cue.speaker)
        punctuation_boundary = bool(_STRONG_END_RE.search(previous.tts_text)) and gap > 0.12
        can_merge = (
            0.0 <= gap <= borrow_gap_ms / 1000.0
            and speaker_matches
            and combined_span <= max_group_duration
            and previous.end_time <= cue.start_time
            and not punctuation_boundary
        )
        if can_merge:
            current.append(cue)
        else:
            cue_groups.append(current)
            current = [cue]
    cue_groups.append(current)

    groups: list[DubbingGroup] = []
    for index, group_cues in enumerate(cue_groups):
        group_id = f"g-{index + 1:04d}"
        start_time = group_cues[0].start_time
        subtitle_end = group_cues[-1].end_time
        if index + 1 < len(cue_groups):
            next_start = cue_groups[index + 1][0].start_time
            available_end = max(subtitle_end, next_start - silence_guard_ms / 1000.0)
        else:
            available_end = max(subtitle_end, video_duration)
        for cue in group_cues:
            cue.group_id = group_id
        source_text = _join_text([cue.source_text for cue in group_cues])
        subtitle_text = _join_text([cue.subtitle_text for cue in group_cues])
        tts_text, removed_overlaps = _join_tts_text(
            [cue.tts_text for cue in group_cues]
        )
        predicted = predict_spoken_duration(tts_text, target_language)
        available_duration = max(0.0, available_end - start_time)
        groups.append(
            DubbingGroup(
                group_id=group_id,
                cue_ids=[cue.cue_id for cue in group_cues],
                start_time=start_time,
                subtitle_end_time=subtitle_end,
                available_end_time=available_end,
                available_duration=available_duration,
                source_text=source_text,
                subtitle_text=subtitle_text,
                tts_text=tts_text,
                predicted_duration=predicted,
                fit_ratio=predicted / available_duration if available_duration > 0 else float("inf"),
                warnings=[
                    f"Removed repeated TTS boundary overlap: {overlap}"
                    for overlap in removed_overlaps
                ],
            )
        )
    return groups

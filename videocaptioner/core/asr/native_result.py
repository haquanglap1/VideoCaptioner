"""Parse native token streams without inventing times, text, or speakers."""

from __future__ import annotations

import math
import re
from typing import Any

from .api_profiles import ASRAPIError
from .asr_data import ASRData, ASRDataSeg
from .metadata import ASRAudioEvent, ASRMetadata


def _timing(item: dict, start_key: str, end_key: str, scale: int, duration: int) -> tuple[int, int]:
    start, end = item.get(start_key), item.get(end_key)
    if (not isinstance(start, (int, float)) or not isinstance(end, (int, float))
            or isinstance(start, bool) or isinstance(end, bool)
            or not math.isfinite(start) or not math.isfinite(end)
            or not 0 <= start <= end or end * scale > duration):
        raise ASRAPIError("Missing or invalid native timestamp; review required.")
    return round(start * scale), round(end * scale)


def parse_native(value: Any, provider: str, duration_ms: int, scope: str, diarize: bool) -> ASRData:
    if provider not in ("soniox", "scribe") or not isinstance(value, dict):
        raise ASRAPIError("Malformed native transcription; review required.")
    text = value.get("text")
    items = value.get("tokens" if provider == "soniox" else "words")
    if not isinstance(text, str) or not isinstance(items, list):
        raise ASRAPIError("Missing native transcript or token list; review required.")
    segments: list[ASRDataSeg] = []
    events = []
    parts = []
    pending_space = ""
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get("text"), str):
            raise ASRAPIError("Malformed native token; review required.")
        part = item["text"]
        kind = item.get("type") if provider == "scribe" else "word"
        if kind not in ("word", "spacing", "audio_event"):
            raise ASRAPIError("Unknown native token type; review required.")
        if provider == "soniox" and item.get("translation_status") not in (None, "none", "original"):
            raise ASRAPIError("Unexpected translated token; review required.")
        parts.append(part)
        speaker = item.get("speaker" if provider == "soniox" else "speaker_id")
        if speaker is not None and not isinstance(speaker, str):
            raise ASRAPIError("Malformed anonymous speaker label; review required.")
        speaker = speaker.strip() or None if speaker is not None else None
        metadata = ASRMetadata(provider, scope, speaker if diarize else None)
        if kind == "spacing" or (part and part.isspace()):
            if part.strip():
                raise ASRAPIError("Non-spacing text in a spacing token; review required.")
            # Spacing carries no speech timing or identity. Keep it with adjacent text.
            if segments:
                segments[-1].text += part
            else:
                pending_space += part
            continue
        keys = ("start_ms", "end_ms", 1) if provider == "soniox" else ("start", "end", 1000)
        start, end = _timing(item, *keys, duration_ms)
        if kind == "audio_event":
            events.append(ASRAudioEvent(part, start, end, metadata))
            continue
        if not part:
            continue
        if start == end and any(char.isalnum() for char in part):
            raise ASRAPIError("Zero-duration speech token; review required.")
        segment = ASRDataSeg(pending_space + part, start, end, metadata=metadata)
        pending_space = ""
        # Join Latin subwords only when the provider supplied no word boundary.
        # CJK tokens already have usable measured character/subword spans.
        if (provider == "soniox" and segments and segments[-1].metadata == metadata
                and segments[-1].end_time <= start
                and re.search(r"[A-Za-z0-9]$", segments[-1].text)
                and re.match(r"[A-Za-z0-9]", part)):
            segments[-1].text += part
            segments[-1].end_time = end
        elif not any(char.isalnum() for char in part) and segments and segments[-1].metadata == metadata:
            segments[-1].text += part
            segments[-1].end_time = max(segments[-1].end_time, end)
        else:
            segments.append(segment)
    if "".join(parts) != text:
        raise ASRAPIError("Native transcript/token coverage mismatch; review required.")
    if any(seg.start_time == seg.end_time for seg in segments):
        raise ASRAPIError("Standalone zero-duration punctuation; review required.")
    # Sorting by ASRData permits interleaved overlapping speakers without discarding any tokens.
    return ASRData(segments, events)


def native_cues(data: ASRData, max_chars: int = 40) -> ASRData:
    """Group only measured, adjacent spans of one source; preserve overlapping speech."""
    cues: list[ASRDataSeg] = []
    for seg in data.segments:
        previous = cues[-1] if cues else None
        if (previous is not None and previous.metadata == seg.metadata
                and previous.end_time <= seg.start_time <= previous.end_time + 800
                and len(previous.text) + len(seg.text) <= max_chars
                and not re.search(r"[。！？.!?]\s*$", previous.text)):
            previous.text += seg.text
            previous.end_time = seg.end_time
        else:
            cues.append(seg.clone())
    return data.with_segments(cues)

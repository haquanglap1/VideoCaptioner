"""Strict audio/text alignment. Unmatched or suspect spans require review, never repair."""

from __future__ import annotations

import hashlib
import json
import math
import unicodedata
from dataclasses import dataclass, field
from typing import Any, cast

from ..api_profiles import MissingTimingError
from ..asr_data import ASRData, ASRDataSeg

MODEL_REPOSITORY = "Qwen/Qwen3-ForcedAligner-0.6B"
MODEL_REVISION = "c7cbfc2048c462b0d63a45797104fc9db3ad62b7"
POLICY = "strict-raw-v1"
MAX_AUDIO_MS = 300_000
CHUNK_MS = 240_000


class AlignmentError(MissingTimingError):
    """Safe error with a machine-readable state/reason, never input text or paths."""

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(f"Chinese alignment: {reason}. Review the audio/text or use a timestamp ASR model.")


def chinese_language(language: str) -> str:
    if language.strip().lower() not in ("zh", "zh-cn", "zh-tw", "zh-hans", "zh-hant", "chinese"):
        raise AlignmentError("select Chinese (zh); auto and other languages are unsupported in S2")
    return "Chinese"


def lexical(text: str) -> str:
    # Match upstream's retained characters. Keep numbers, case and script unchanged.
    return "".join(c for c in text if c == "'" or unicodedata.category(c)[0] in "LN")


@dataclass(frozen=True)
class AlignmentSpan:
    text: str = field(repr=False)
    start_ms: int
    end_ms: int


@dataclass(frozen=True)
class AlignmentResult:
    spans: tuple[AlignmentSpan, ...] = field(repr=False)
    duration_ms: int
    offset_ms: int = 0

    def asr_data(self, word_timing: bool = True) -> ASRData:
        segments: list[ASRDataSeg] = []
        for span in self.spans:
            if (not word_timing and segments and
                    not segments[-1].text.rstrip().endswith(tuple("。！？!?；;…")) and
                    span.start_ms + self.offset_ms - segments[-1].end_time < 800 and
                    span.end_ms + self.offset_ms - segments[-1].start_time <= 6000):
                segments[-1].text += span.text
                segments[-1].end_time = span.end_ms + self.offset_ms
            else:
                segments.append(ASRDataSeg(span.text, span.start_ms + self.offset_ms,
                                           span.end_ms + self.offset_ms))
        return ASRData(segments)


def validate_alignment(text: str, items: Any, duration_ms: int, offset_ms: int = 0) -> AlignmentResult:
    if (type(duration_ms) is not int or not 0 < duration_ms <= MAX_AUDIO_MS or
            type(offset_ms) is not int or offset_ms < 0):
        raise AlignmentError("invalid audio duration or chunk offset")
    if not isinstance(items, list):
        raise AlignmentError("malformed spans")
    source = lexical(text)
    if not source:
        if text.strip() or items:
            raise AlignmentError("punctuation-only or unmatched silence")
        return AlignmentResult((), duration_ms, offset_ms)
    if not items:
        raise AlignmentError("unmatched text")
    positions = [i for i, c in enumerate(text) if lexical(c)]
    spans = []
    cursor, original_cursor, previous_end = 0, 0, 0
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get("text"), str):
            raise AlignmentError("malformed spans")
        token = lexical(item["text"])
        if not token or source[cursor:cursor + len(token)] != token:
            raise AlignmentError("unmatched or duplicated text")
        times: list[Any] = [item.get("start_ms"), item.get("end_ms")]
        if any(type(t) not in (int, float) or not math.isfinite(t) for t in times):
            raise AlignmentError("nonfinite or missing timestamp")
        start, end = cast(tuple[float, float], tuple(times))
        if not (0 <= start < end <= duration_ms) or start < previous_end:
            raise AlignmentError("zero-length, overlapping or out-of-audio span")
        if int(start) != start or int(end) != end:
            raise AlignmentError("timestamp is not canonical milliseconds")
        cursor += len(token)
        # Attach punctuation/space to measured spans without changing any timestamp.
        stop = positions[cursor] if cursor < len(positions) else len(text)
        spans.append(AlignmentSpan(text[original_cursor:stop], int(start), int(end)))
        original_cursor, previous_end = stop, end
    if cursor != len(source) or "".join(s.text for s in spans) != text:
        raise AlignmentError("unmatched text")
    return AlignmentResult(tuple(spans), duration_ms, offset_ms)


def alignment_key(audio: bytes, text: str, language: str, *, revision: str = MODEL_REVISION,
                  policy: str = POLICY, config: str = "cuda-bfloat16-sdpa") -> str:
    payload = [hashlib.sha256(audio).hexdigest(), hashlib.sha256(text.encode()).hexdigest(),
               chinese_language(language), MODEL_REPOSITORY, revision, policy, config]
    return "alignment:v1-" + hashlib.sha256(json.dumps(payload).encode()).hexdigest()


def merge_chunks(chunks: list[AlignmentResult], total_ms: int, word_timing: bool) -> ASRData:
    segments = []
    boundary = 0
    for chunk in chunks:
        if chunk.offset_ms != boundary or chunk.offset_ms + chunk.duration_ms > total_ms:
            raise AlignmentError("overlapping or missing audio chunk")
        segments.extend(chunk.asr_data(word_timing).segments)
        boundary += chunk.duration_ms
    if boundary != total_ms:
        raise AlignmentError("incomplete audio coverage")
    return ASRData(segments)

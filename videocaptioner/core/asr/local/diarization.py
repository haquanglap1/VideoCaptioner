"""Whole-job anonymous speakers reconciled with existing timing, without changing words."""

import hashlib
import json
from dataclasses import dataclass, replace

from ..asr_data import ASRData
from ..metadata import ASRMetadata, SpeakerAssociation, StageProvenance
from .profiles import DIARIZATION_POLICY, MODELS


@dataclass(frozen=True)
class SpeakerSpan:
    start_ms: int
    end_ms: int
    speaker: str


def validate_spans(items: object, duration_ms: int) -> tuple[SpeakerSpan, ...]:
    if not isinstance(items, list) or type(duration_ms) is not int or duration_ms <= 0:
        raise ValueError("Invalid local diarization response.")
    spans = []
    for item in items:
        if not isinstance(item, dict) or set(item) != {"start_ms", "end_ms", "speaker"}:
            raise ValueError("Invalid local diarization span.")
        start, end, speaker = item["start_ms"], item["end_ms"], item["speaker"]
        if (type(start) is not int or type(end) is not int or not 0 <= start < end <= duration_ms or
                not isinstance(speaker, str) or not speaker or len(speaker) > 100):
            raise ValueError("Invalid local diarization timing or speaker.")
        spans.append(SpeakerSpan(start, end, speaker))
    return tuple(sorted(set(spans), key=lambda s: (s.start_ms, s.end_ms, s.speaker)))


def _coverage(intervals: list[tuple[int, int]]) -> int:
    end, covered = -1, 0
    for start, stop in sorted(intervals):
        covered += max(0, stop - max(start, end))
        end = max(end, stop)
    return covered


def associate(data: ASRData, spans: tuple[SpeakerSpan, ...], duration_ms: int, scope: str,
              recognition: StageProvenance) -> ASRData:
    model = MODELS["community-1"]
    stage = StageProvenance("pyannote", model.repository, model.revision, DIARIZATION_POLICY)
    result = []
    for seg in data.segments:
        if (type(seg.start_time) is not int or type(seg.end_time) is not int or
                not 0 <= seg.start_time < seg.end_time <= duration_ms):
            raise ValueError("Local diarization requires valid measured cue timing; align text first.")
        old = seg.metadata
        if old and (old.provider in ("soniox", "scribe") or old.speaker is not None or old.diarization is not None):
            raise ValueError("Existing diarization must be reviewed explicitly; local labels cannot replace it.")
        by_speaker: dict[str, list[tuple[int, int]]] = {}
        for span in spans:
            start, end = max(seg.start_time, span.start_ms), min(seg.end_time, span.end_ms)
            if start < end:
                by_speaker.setdefault(span.speaker, []).append((start, end))
        scores = {label: _coverage(parts) for label, parts in by_speaker.items()}
        labels = tuple(sorted(scores))
        duration = seg.end_time - seg.start_time
        coverage = max(scores.values(), default=0) * 1_000_000 // duration
        overlap = any(max(a, c) < min(b, d) for i, label in enumerate(labels) for other in labels[i + 1:]
                      for a, b in by_speaker[label] for c, d in by_speaker[other])
        # Conservative temporal confidence, not an acoustic probability: any second speaker
        # needs review, even if one dominates. Do not erase real overlap via exclusive output.
        status = "overlap" if overlap else "ambiguous" if len(labels) > 1 else "assigned" if coverage >= 800_000 else "unknown"
        speaker = labels[0] if status == "assigned" else None
        association = SpeakerAssociation(stage, scope, status, labels, coverage)
        metadata = old or ASRMetadata(recognition.provider, scope, recognition=recognition,
                                      timing="imported" if recognition.provider == "imported" else "native")
        copy = seg.clone()
        copy.metadata = replace(metadata, speaker=speaker, diarization=association)
        result.append(copy)
    return data.with_segments(result)


def diarization_key(audio_hash: str, data: ASRData) -> str:
    model = MODELS["community-1"]
    source = [[s.cue_id, s.text, s.start_time, s.end_time, s.metadata.to_dict() if s.metadata else None]
              for s in data.segments]
    payload = [audio_hash, model.repository, model.revision, DIARIZATION_POLICY, "cuda-float32", source]
    return "diarization:v1-" + hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()

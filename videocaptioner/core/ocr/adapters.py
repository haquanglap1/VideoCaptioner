"""Typed OCR handoff; two source lines remain one source cue throughout translation."""

from __future__ import annotations

from .document import OcrCue, OcrDocument
from .metadata import OcrMetadata, merged_cue_id
from .models import OcrError

MERGE_GAP_MS = 150


def merge_repeated_cues(cues: tuple[OcrCue, ...], gap_ms: int = MERGE_GAP_MS) -> list[tuple[OcrCue, ...]]:
    """Fade-in/out slivers read as the same text belong to one subtitle; timing spans the group."""
    groups: list[list[OcrCue]] = []
    for cue in cues:
        last = groups[-1][-1] if groups else None
        if last is not None and last.text == cue.text and cue.start_ms - last.end_ms <= gap_ms:
            groups[-1].append(cue)
        else:
            groups.append([cue])
    return [tuple(group) for group in groups]


def document_to_subtitles(document: OcrDocument):
    from videocaptioner.core.asr.asr_data import ASRData, ASRDataSeg

    if document.export_issues:
        raise OcrError("Incomplete or invalid OCR cannot become subtitles")
    groups = (merge_repeated_cues(document.cues) if document.config.vision is not None
              else [(cue,) for cue in document.cues])
    return ASRData([
        ASRDataSeg(group[0].text, group[0].start_ms, group[-1].end_ms,
                   cue_id=group[0].id if len(group) == 1 else merged_cue_id([cue.id for cue in group]),
                   ocr_metadata=OcrMetadata(document.id, document.visual_source.id, document.config, group))
        for group in groups
    ], visual_source=document.visual_source)

"""Typed OCR handoff; two source lines remain one source cue throughout translation."""

from __future__ import annotations

from .document import OcrDocument
from .metadata import OcrMetadata
from .models import OcrError


def document_to_subtitles(document: OcrDocument):
    from videocaptioner.core.asr.asr_data import ASRData, ASRDataSeg

    if document.pending_issues:
        raise OcrError("Unresolved OCR cannot become successful subtitles")
    return ASRData([
        ASRDataSeg(cue.text, cue.start_ms, cue.end_ms, cue_id=cue.id,
                   ocr_metadata=OcrMetadata(document.id, document.visual_source.id, document.config, (cue,)))
        for cue in document.cues
    ], visual_source=document.visual_source)

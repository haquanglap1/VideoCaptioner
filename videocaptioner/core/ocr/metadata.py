"""OCR lineage carried by subtitle/editor cues, separate from ASR timing and speakers."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from .codec import decode, digest, encode, sha256
from .document import OcrConfig, OcrCue, OcrDocument, document_id
from .identity import VisualSourceIdentity
from .models import OcrError


@dataclass(frozen=True)
class OcrMetadata:
    document_id: str
    source_id: str
    config: OcrConfig
    observations: tuple[OcrCue, ...]
    text_edited: bool = False
    timing_edited: bool = False

    def __post_init__(self) -> None:
        sha256(self.source_id)
        if not self.document_id.startswith("ocr-") or not self.observations:
            raise OcrError("Missing OCR lineage")
        if self.config.profile_snapshot is None:
            raise OcrError("Missing OCR profile snapshot")
        if len({c.id for c in self.observations}) != len(self.observations):
            raise OcrError("Duplicate OCR lineage")
        if any(c.pending_issues for c in self.observations):
            raise OcrError("Unresolved OCR belongs in a review document")

    def to_dict(self) -> dict:
        return encode(self)

    @classmethod
    def from_dict(cls, value: Any) -> OcrMetadata | None:
        return None if value is None else decode(cls, value)

    def verify_source(self, source: VisualSourceIdentity | None) -> None:
        if source is None or source.id != self.source_id or document_id(source, self.config) != self.document_id:
            raise OcrError("Missing or mismatched visual source for OCR subtitles")
        # Revalidate IDs, selection, raw references and timing without manufacturing new observations.
        OcrDocument(self.document_id, source, self.config, self.observations, True)

    def edited(self, *, text: bool = False, timing: bool = False) -> OcrMetadata:
        return replace(self, text_edited=self.text_edited or text, timing_edited=self.timing_edited or timing)


def merge_ocr_metadata(values: list[OcrMetadata | None]) -> OcrMetadata | None:
    if not any(value is not None for value in values):
        return None
    if any(value is None for value in values):
        raise OcrError("Cannot merge OCR and non-OCR sources")
    first = values[0]
    assert first is not None
    observations: dict[str, OcrCue] = {}
    for value in values:
        assert value is not None
        if (value.document_id, value.source_id, value.config) != (first.document_id, first.source_id, first.config):
            raise OcrError("Cannot merge different OCR sources or profiles")
        for cue in value.observations:
            if cue.id in observations and observations[cue.id] != cue:
                raise OcrError("Conflicting OCR review lineage")
            observations[cue.id] = cue
    return replace(first, observations=tuple(sorted(observations.values(), key=lambda c: c.exact_start_ms)),
                   text_edited=True, timing_edited=True)


def merged_cue_id(ids: list[str]) -> str:
    if any(not identifier for identifier in ids):
        raise OcrError("OCR merge requires stable input cue IDs")
    return "ocr-merge-" + digest(ids)[:32]

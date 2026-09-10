"""Whole snapshot identity for visual text, independent of audio and local paths."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from .codec import decode, digest, encode, sha256
from .models import Check, OcrError, Selection, VideoInfo
from .source import VideoSnapshot, video_snapshot


@dataclass(frozen=True)
class VisualSourceIdentity:
    snapshot_sha256: str
    size_bytes: int
    video: VideoInfo
    selection: Selection
    schema: Literal["visual-source-v1"] = "visual-source-v1"

    def __post_init__(self) -> None:
        sha256(self.snapshot_sha256)
        if type(self.size_bytes) is not int or self.size_bytes <= 0 or self.schema != "visual-source-v1":
            raise OcrError("Invalid visual source identity")

    @property
    def id(self) -> str:
        return digest(self)

    @classmethod
    def from_snapshot(cls, snapshot: VideoSnapshot, video: VideoInfo, selection: Selection) -> VisualSourceIdentity:
        return cls(snapshot.sha256, snapshot.size_bytes, video, selection)

    def to_dict(self) -> dict:
        return encode(self)

    @classmethod
    def from_dict(cls, value: Any) -> VisualSourceIdentity | None:
        return None if value is None else decode(cls, value)

    def require_match(self, actual: VisualSourceIdentity) -> None:
        if self != actual:
            raise OcrError("Visual source mismatch; select the original video and OCR selection")


def verify_visual_file(expected: VisualSourceIdentity, source: Path, jobs_root: Path,
                       *, ffprobe: str = "ffprobe", check: Check = lambda: None) -> VisualSourceIdentity:
    from .decoder import probe_video

    with video_snapshot(source, jobs_root, check) as snapshot:
        actual = VisualSourceIdentity.from_snapshot(snapshot, probe_video(snapshot.path, ffprobe, check),
                                                    expected.selection)
        expected.require_match(actual)
        return actual

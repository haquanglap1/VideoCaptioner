"""Typed timing and recognition observations for OCR-2, before document/export integration."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Callable

from .geometry import VideoGeometry

Check = Callable[[], None]


class OcrError(ValueError):
    pass


@dataclass(frozen=True)
class VisualDecision:
    present: bool
    changed: bool
    uncertain: bool
    quality: float

    def __post_init__(self) -> None:
        if (any(type(v) is not bool for v in (self.present, self.changed, self.uncertain))
                or type(self.quality) not in (int, float)
                or not math.isfinite(self.quality) or not 0 <= self.quality <= 1):
            raise OcrError("Invalid visual tracking decision")


@dataclass(frozen=True)
class Selection:
    start_ms: int
    end_ms: int

    def __post_init__(self) -> None:
        if (type(self.start_ms) is not int or type(self.end_ms) is not int
                or not 0 <= self.start_ms < self.end_ms):
            raise OcrError("Invalid OCR selection")


@dataclass(frozen=True)
class VideoInfo:
    stream_index: int
    geometry: VideoGeometry
    time_base: Fraction
    timeline_origin: Fraction

    def __post_init__(self) -> None:
        if self.stream_index < 0 or self.time_base <= 0:
            raise OcrError("Invalid video stream timing")


@dataclass(frozen=True)
class RoiFrame:
    index: int
    pts: int
    time_base: Fraction
    timeline_ms: Fraction
    width: int
    height: int
    rgb: bytes = field(repr=False)

    def __post_init__(self) -> None:
        if (min(self.width, self.height) <= 0 or self.time_base <= 0
                or len(self.rgb) != self.width * self.height * 3):
            raise OcrError("Invalid ROI frame")


@dataclass(frozen=True)
class FrameSpan:
    frame: RoiFrame
    start_ms: Fraction
    end_ms: Fraction
    clipped_start: bool = False
    clipped_end: bool = False
    uncertain_end: bool = False


@dataclass(frozen=True)
class ReadLine:
    text: str
    score: float
    box: tuple[tuple[float, float], ...]


@dataclass(frozen=True)
class GenerationRead:
    token_ids: tuple[int, ...]
    raw_decode: str
    crop_sha256: str
    crop_bounds: tuple[int, int, int, int]
    geometry_lines: tuple[ReadLine, ...]
    eos_token_id: int
    # This box comes from the input crop, not localization by the generator.
    geometry_kind: str = "anchor-union-pad-v1"

    def __post_init__(self):
        if (not self.token_ids or len(self.token_ids) > 96
                or any(type(t) is not int or not 0 <= t < 103424 for t in self.token_ids)
                or self.token_ids[-1] != self.eos_token_id
                or type(self.eos_token_id) is not int or self.eos_token_id != 2
                or self.geometry_kind != "anchor-union-pad-v1"
                or not isinstance(self.raw_decode, str) or len(self.raw_decode) > 8192
                or len(self.crop_sha256) != 64 or any(c not in "0123456789abcdef" for c in self.crop_sha256)
                or len(self.crop_bounds) != 4 or any(type(v) is not int for v in self.crop_bounds)
                or not 0 <= self.crop_bounds[0] < self.crop_bounds[2]
                or not 0 <= self.crop_bounds[1] < self.crop_bounds[3]):
            raise OcrError("Invalid OCR generation evidence")


@dataclass(frozen=True)
class EngineRead:
    lines: tuple[ReadLine, ...]
    revision: str
    generation: GenerationRead | None = field(default=None, metadata={"omit_none": True})

    @property
    def text(self) -> str:
        return "\n".join(line.text for line in self.lines)

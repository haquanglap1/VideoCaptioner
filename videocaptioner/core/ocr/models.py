"""Typed timing and recognition observations for OCR-2, before document/export integration."""

from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction
from typing import Callable

from .geometry import VideoGeometry

Check = Callable[[], None]


class OcrError(ValueError):
    pass


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
class EngineRead:
    lines: tuple[ReadLine, ...]
    revision: str

    @property
    def text(self) -> str:
        return "\n".join(line.text for line in self.lines)

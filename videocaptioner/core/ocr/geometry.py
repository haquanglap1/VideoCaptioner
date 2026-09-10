"""ROI coordinates on square-pixel video after display rotation, independent of Qt."""

from __future__ import annotations

import math
from dataclasses import dataclass
from fractions import Fraction


@dataclass(frozen=True)
class PixelRect:
    x: int
    y: int
    width: int
    height: int


@dataclass(frozen=True)
class Roi:
    x: float
    y: float
    width: float
    height: float

    def __post_init__(self) -> None:
        if (not all(math.isfinite(v) for v in (self.x, self.y, self.width, self.height))
                or min(self.x, self.y) < 0 or min(self.width, self.height) <= 0
                or self.x + self.width > 1.000000001 or self.y + self.height > 1.000000001):
            raise ValueError("ROI must be a nonempty rectangle inside the displayed video")

    def pixels(self, width: int, height: int) -> PixelRect:
        if min(width, height) <= 0:
            raise ValueError("Invalid display size")
        x, y = math.floor(self.x * width), math.floor(self.y * height)
        right = min(width, math.ceil((self.x + self.width) * width))
        bottom = min(height, math.ceil((self.y + self.height) * height))
        return PixelRect(x, y, right - x, bottom - y)


@dataclass(frozen=True)
class VideoGeometry:
    width: int
    height: int
    sar: Fraction = Fraction(1)
    rotation: int = 0  # Counterclockwise degrees, as reported by ffprobe displaymatrix.

    def __post_init__(self) -> None:
        if (min(self.width, self.height) <= 0 or self.sar <= 0
                or self.rotation not in (0, 90, 180, 270)):
            raise ValueError("Unsupported video geometry")
        if max(self.square_width, self.height) > 16384:
            raise ValueError("Video geometry exceeds the OCR size limit")

    @property
    def square_width(self) -> int:
        return max(1, round(self.width * self.sar))

    @property
    def display_size(self) -> tuple[int, int]:
        size = self.square_width, self.height
        return (size[1], size[0]) if self.rotation in (90, 270) else size

    def source_point(self, display_x: float, display_y: float) -> tuple[float, float]:
        """Inverse display transform, using pixel-edge coordinates (not pixel centers)."""
        w, h = self.square_width, self.height
        x, y = display_x, display_y
        if self.rotation == 90:
            x, y = w - display_y, display_x
        elif self.rotation == 180:
            x, y = w - display_x, h - display_y
        elif self.rotation == 270:
            x, y = display_y, h - display_x
        return x * self.width / w, y

    def filters(self, roi: Roi) -> list[str]:
        result = [f"scale={self.square_width}:{self.height}:flags=bilinear", "setsar=1"]
        result += {0: [], 90: ["transpose=cclock"], 180: ["hflip", "vflip"],
                   270: ["transpose=clock"]}[self.rotation]
        rect = roi.pixels(*self.display_size)
        # RGB before crop avoids chroma alignment rounding for narrow/odd ROIs.
        return result + ["format=rgb24", f"crop={rect.width}:{rect.height}:{rect.x}:{rect.y}:exact=1"]


def widget_roi(rect: tuple[float, float, float, float], widget_size: tuple[int, int],
               geometry: VideoGeometry) -> Roi:
    """Map a drag rectangle through centered aspect-fit letterboxing; clip to video."""
    x1, y1, x2, y2 = rect
    ww, wh = widget_size
    if min(ww, wh) <= 0 or not all(math.isfinite(v) for v in rect):
        raise ValueError("Invalid preview geometry")
    dw, dh = geometry.display_size
    scale = min(ww / dw, wh / dh)
    left, top = (ww - dw * scale) / 2, (wh - dh * scale) / 2
    x1, x2 = sorted((x1, x2))
    y1, y2 = sorted((y1, y2))
    x1, x2 = max(left, x1), min(left + dw * scale, x2)
    y1, y2 = max(top, y1), min(top + dh * scale, y2)
    return Roi((x1 - left) / (dw * scale), (y1 - top) / (dh * scale),
               (x2 - x1) / (dw * scale), (y2 - y1) / (dh * scale))

"""Explicit spatial selection of whole OCR lines; raw readings remain untouched."""

from __future__ import annotations

import math
import unicodedata
from dataclasses import dataclass
from typing import Literal

from .models import EngineRead, OcrError


@dataclass(frozen=True)
class LineSelectionPolicy:
    anchors: tuple[float, ...] = (0.5,)
    policy: Literal["horizontal-anchors-punctuation-v1"] = "horizontal-anchors-punctuation-v1"

    def __post_init__(self) -> None:
        if (self.policy != "horizontal-anchors-punctuation-v1" or not isinstance(self.anchors, tuple)
                or not 1 <= len(self.anchors) <= 2
                or any(type(y) not in (int, float) or not math.isfinite(y) or not 0 < y < 1 for y in self.anchors)
                or tuple(sorted(set(self.anchors))) != self.anchors):
            raise OcrError("Choose one or two increasing line positions strictly between 0 and 1")
        object.__setattr__(self, "anchors", tuple(float(y) for y in self.anchors))

    @classmethod
    def parse(cls, value: str) -> LineSelectionPolicy:
        return cls(tuple(float(y.strip()) for y in value.split(",")))

    def select(self, raw: EngineRead, height: int) -> tuple[int, ...]:
        if type(height) is not int or height <= 0:
            raise OcrError("Invalid OCR crop height for line selection")
        boxes = [(min(p[0] for p in line.box), min(p[1] for p in line.box),
                  max(p[0] for p in line.box), max(p[1] for p in line.box)) for line in raw.lines]
        if any(not all(math.isfinite(v) for v in b) or b[0] >= b[2] or b[1] >= b[3] for b in boxes):
            raise OcrError("Line selection needs nonempty OCR box geometry")
        selected = {i for i, b in enumerate(boxes) if any(b[1] <= y * height <= b[3] for y in self.anchors)}
        punctuation = {i for i, line in enumerate(raw.lines) if line.text.strip()
                       and all(c.isspace() or unicodedata.category(c).startswith("P") for c in line.text)}
        # Only attach to original text anchors; punctuation must not chain into UI rows.
        parents = selected - punctuation
        for i in punctuation - selected:
            x0, y0, x1, y1 = boxes[i]
            for parent in parents:
                left, top, right, bottom = boxes[parent]
                h = bottom - top
                if max(left - x1, x0 - right, 0) <= h / 2 and top - h / 4 <= (y0 + y1) / 2 <= bottom + h / 4:
                    selected.add(i)
                    break
        return tuple(sorted(selected))


def selected_text(raw: EngineRead, indices: tuple[int, ...] | None) -> str:
    if indices is None:
        return raw.text
    if (not isinstance(indices, tuple) or any(type(i) is not int or not 0 <= i < len(raw.lines) for i in indices)
            or tuple(sorted(set(indices))) != indices):
        raise OcrError("Invalid selected OCR line indices")
    return "\n".join(raw.lines[i].text for i in indices)

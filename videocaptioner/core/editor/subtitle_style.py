"""Project-local subtitle appearance, in units relative to a 720-line frame."""

from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass, fields
from typing import Any

SUBTITLE_REFERENCE_HEIGHT = 720


@dataclass(frozen=True)
class EditorSubtitleStyle:
    font_name: str = "Noto Sans SC"
    font_size: int = 42
    primary_color: str = "#ffffff"
    outline_color: str = "#000000"
    outline_width: float = 0.0
    bold: bool = True
    spacing: float = 0.0
    alignment: int = 2
    margin_left: int = 20
    margin_right: int = 20
    margin_bottom: int = 30

    def __post_init__(self) -> None:
        if (
            not isinstance(self.font_name, str)
            or not self.font_name.strip()
            or len(self.font_name) > 128
            or re.search(r"[\\,'\":;=\[\]\x00-\x1f]", self.font_name)
        ):
            raise ValueError("Font name is empty or contains unsupported characters")
        for name in ("primary_color", "outline_color"):
            value = getattr(self, name)
            if not isinstance(value, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", value):
                raise ValueError(f"{name} must be a #RRGGBB color")
            object.__setattr__(self, name, value.lower())
        for name, low, high in (
            ("font_size", 8, 200),
            ("alignment", 1, 9),
            ("margin_left", 0, 300),
            ("margin_right", 0, 300),
            ("margin_bottom", 0, 300),
        ):
            value = getattr(self, name)
            if type(value) is not int or not low <= value <= high:
                raise ValueError(f"{name} must be an integer between {low} and {high}")
        for name in ("outline_width", "spacing"):
            value = getattr(self, name)
            if type(value) not in (int, float) or not 0 <= value <= 20 or not math.isfinite(value):
                raise ValueError(f"{name} must be between 0 and 20")
        if type(self.bold) is not bool:
            raise ValueError("bold must be a boolean")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> EditorSubtitleStyle:
        if data is None:
            return cls()
        if not isinstance(data, dict):
            raise ValueError("subtitle_style must be an object")
        return cls(**{item.name: data[item.name] for item in fields(cls) if item.name in data})

    @staticmethod
    def reference_resolution(width: int, height: int) -> tuple[int, int]:
        if width <= 0 or height <= 0:
            return 1280, SUBTITLE_REFERENCE_HEIGHT
        return max(1, round(SUBTITLE_REFERENCE_HEIGHT * width / height)), SUBTITLE_REFERENCE_HEIGHT

    def _ass_fields(self) -> dict[str, str]:
        def color(value: str) -> str:
            return f"&H00{value[5:7]}{value[3:5]}{value[1:3]}".upper()

        return {
            "Fontname": self.font_name,
            "Fontsize": str(self.font_size),
            "PrimaryColour": color(self.primary_color),
            "SecondaryColour": color(self.primary_color),
            "OutlineColour": color(self.outline_color),
            "BackColour": "&H00000000",
            "Bold": "-1" if self.bold else "0",
            "Italic": "0",
            "Underline": "0",
            "StrikeOut": "0",
            "ScaleX": "100",
            "ScaleY": "100",
            "Spacing": str(self.spacing),
            "Angle": "0",
            "BorderStyle": "1",
            "Outline": str(self.outline_width),
            "Shadow": "0",
            "Alignment": str(self.alignment),
            "MarginL": str(self.margin_left),
            "MarginR": str(self.margin_right),
            "MarginV": str(self.margin_bottom),
            "Encoding": "1",
        }

    def to_ass_string(self) -> str:
        values = self._ass_fields()
        return (
            "[V4+ Styles]\nFormat: Name,"
            + ",".join(values)
            + "\nStyle: Default,"
            + ",".join(values.values())
        )

    def to_force_style(self, width: int, height: int) -> str:
        ref_width, ref_height = self.reference_resolution(width, height)
        values = {"PlayResX": str(ref_width), "PlayResY": str(ref_height), **self._ass_fields()}
        # libass overrides use internal scale/alignment, unlike ASS style lines.
        values.update(ScaleX="1", ScaleY="1")
        values["Alignment"] = str((1, 2, 3, 9, 10, 11, 5, 6, 7)[self.alignment - 1])
        return ",".join(f"{key}={value}" for key, value in values.items())

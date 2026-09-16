"""Project-local subtitle appearance, in units relative to a 720-line frame."""

from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass, fields, replace
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Sequence

from videocaptioner.config import FONTS_PATH
from videocaptioner.core.subtitle.style_manager import StyleMode, SubtitleStyle

SUBTITLE_REFERENCE_HEIGHT = 720
STYLE_REFERENCE_HEIGHT = SUBTITLE_REFERENCE_HEIGHT
DEFAULT_FRAME_WIDTH = 1920
DEFAULT_FRAME_HEIGHT = 1080
ALIGN_H_VALUES = ("left", "center", "right")
ALIGN_V_VALUES = ("top", "middle", "bottom")
_KAPPA = 0.5522847498


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


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
    background: bool = False
    bg_color: str = "#000000"
    bg_opacity: float = 0.55
    corner_radius: int = 12
    padding_h: int = 20
    padding_v: int = 10
    # Legacy projects store video pixels; current projects use a 720-line reference.
    reference_height: int = SUBTITLE_REFERENCE_HEIGHT
    layout_mode: str = "libass"

    def __post_init__(self) -> None:
        if type(self.reference_height) is not int or self.reference_height not in (0, 720):
            raise ValueError("reference_height must be 0 (video pixels) or 720")
        if self.layout_mode not in ("libass", "shared"):
            raise ValueError("layout_mode must be libass or shared")
        if (
            not isinstance(self.font_name, str)
            or not self.font_name.strip()
            or len(self.font_name) > 128
            or re.search(r"[\\,'\":;=\[\]\x00-\x1f]", self.font_name)
        ):
            raise ValueError("Font name is empty or contains unsupported characters")
        for name in ("primary_color", "outline_color", "bg_color"):
            value = getattr(self, name)
            if not isinstance(value, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", value):
                raise ValueError(f"{name} must be a #RRGGBB color")
            object.__setattr__(self, name, value.lower())
        for name, low, high in (
            (
                "font_size",
                1 if self.reference_height == 0 else 8,
                8000 if self.reference_height == 0 else 200,
            ),
            ("alignment", 1, 9),
            ("margin_left", 0, 16000 if self.reference_height == 0 else 300),
            ("margin_right", 0, 16000 if self.reference_height == 0 else 300),
            ("margin_bottom", 0, 16000 if self.reference_height == 0 else 300),
            ("corner_radius", 0, 8000 if self.reference_height == 0 else 400),
            ("padding_h", 0, 8000 if self.reference_height == 0 else 400),
            ("padding_v", 0, 8000 if self.reference_height == 0 else 400),
        ):
            value = getattr(self, name)
            if type(value) is not int or not low <= value <= high:
                raise ValueError(f"{name} must be an integer between {low} and {high}")
        for name in ("outline_width", "spacing"):
            value = getattr(self, name)
            high = 800 if self.reference_height == 0 else 20
            if (
                type(value) not in (int, float)
                or not 0 <= value <= high
                or not math.isfinite(value)
            ):
                raise ValueError(f"{name} must be between 0 and {high}")
        if type(self.bg_opacity) not in (int, float) or not 0 <= self.bg_opacity <= 1:
            raise ValueError("bg_opacity must be between 0 and 1")
        for name in ("bold", "background"):
            if type(getattr(self, name)) is not bool:
                raise ValueError(f"{name} must be a boolean")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> EditorSubtitleStyle:
        if data is None:
            return cls()
        if not isinstance(data, dict):
            raise ValueError("subtitle_style must be an object")
        payload = dict(data)
        aliases = {
            "margin_l": "margin_left",
            "margin_r": "margin_right",
            "margin_v": "margin_bottom",
        }
        legacy = any(name in payload for name in (*aliases, "align_h", "align_v"))
        if legacy and "reference_height" not in payload:
            payload = {
                "font_size": 40,
                "outline_width": 2.0,
                "margin_left": 40,
                "margin_right": 40,
                "reference_height": 0,
                "layout_mode": "shared",
                **payload,
            }
        for old, new in aliases.items():
            if old in payload:
                payload[new] = payload.pop(old)
        if "align_h" in payload or "align_v" in payload:
            alignment = payload.get("alignment", 2)
            if type(alignment) is not int or not 1 <= alignment <= 9:
                raise ValueError("alignment must be between 1 and 9")
            horizontal = payload.pop("align_h", ALIGN_H_VALUES[(alignment - 1) % 3])
            vertical = payload.pop("align_v", ("bottom", "middle", "top")[(alignment - 1) // 3])
            if horizontal not in ALIGN_H_VALUES or vertical not in ALIGN_V_VALUES:
                raise ValueError("Invalid subtitle alignment")
            payload["alignment"] = (
                ("bottom", "middle", "top").index(vertical) * 3
                + ALIGN_H_VALUES.index(horizontal)
                + 1
            )
        return cls(
            **{item.name: payload[item.name] for item in fields(cls) if item.name in payload}
        )

    @property
    def uses_shared_layout(self) -> bool:
        return self.background or self.layout_mode == "shared" or self.reference_height == 0

    @property
    def align_h(self) -> str:
        return ALIGN_H_VALUES[(self.alignment - 1) % 3]

    @property
    def align_v(self) -> str:
        return ("bottom", "middle", "top")[(self.alignment - 1) // 3]

    @property
    def ass_alignment(self) -> int:
        return self.alignment

    @property
    def margin_l(self) -> int:
        return self.margin_left

    @property
    def margin_r(self) -> int:
        return self.margin_right

    @property
    def margin_v(self) -> int:
        return self.margin_bottom

    def scaled_for_height(self, height: int) -> EditorSubtitleStyle:
        """Resolve reference units once; a pixel snapshot never scales twice."""
        if self.reference_height == 0:
            return self
        scale = (height or DEFAULT_FRAME_HEIGHT) / self.reference_height
        integers = (
            "font_size",
            "margin_left",
            "margin_right",
            "margin_bottom",
            "corner_radius",
            "padding_h",
            "padding_v",
        )
        values = {name: round(getattr(self, name) * scale) for name in integers}
        values["font_size"] = max(1, values["font_size"])
        return replace(
            self,
            **values,
            outline_width=self.outline_width * scale,
            spacing=self.spacing * scale,
            reference_height=0,
            layout_mode="shared",
        )

    @classmethod
    def default_for_height(cls, height: int) -> EditorSubtitleStyle:
        return cls().scaled_for_height(height)

    @classmethod
    def from_preset(cls, preset: SubtitleStyle) -> EditorSubtitleStyle:
        """Keep preset units at their authored 720p reference until rendering."""
        if preset.mode == StyleMode.ROUNDED:
            color = preset.bg_color
            opacity = int(color[7:9], 16) / 255 if len(color) == 9 else 1.0
            return cls(
                font_name=preset.font_name,
                font_size=int(preset.font_size),
                bold=False,
                primary_color=preset.text_color[:7],
                background=True,
                bg_color=color[:7],
                bg_opacity=opacity,
                corner_radius=int(preset.corner_radius),
                padding_h=int(preset.padding_h),
                padding_v=int(preset.padding_v),
                margin_bottom=int(preset.margin_bottom_rounded),
                layout_mode="shared",
            )
        return cls(
            font_name=preset.font_name,
            font_size=int(preset.font_size),
            bold=bool(preset.bold),
            primary_color=preset.primary_color[:7],
            outline_color=preset.outline_color[:7],
            outline_width=float(preset.outline_width),
            spacing=float(preset.spacing),
            margin_bottom=int(preset.margin_bottom),
        )

    @property
    def ass_font_size(self) -> int:
        return max(1, round(self.font_size / libass_size_factor(resolve_font_file(self.font_name))))

    def to_ass_style_block(self) -> str:
        """Shared layout uses measured pixel em sizes and a pinned bundled face."""
        values = self._ass_fields()
        font_file = resolve_font_file(self.font_name)
        values["Fontname"] = next(
            (family for family, path in bundled_font_files() if path == font_file), self.font_name
        )
        values["Fontsize"] = str(self.ass_font_size)
        return (
            "[V4+ Styles]\nFormat: Name,"
            + ",".join(values)
            + "\nStyle: Default,"
            + ",".join(values.values())
        )

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


@lru_cache(maxsize=1)
def bundled_font_files() -> tuple[tuple[str, str], ...]:
    """``(family, path)`` for every font shipped in ``resource/fonts/``."""
    from PIL import ImageFont

    directory = Path(FONTS_PATH)
    if not directory.is_dir():
        return ()
    items: list[tuple[str, str]] = []
    for candidate in sorted(directory.iterdir()):
        if candidate.suffix.lower() not in {".ttf", ".otf", ".ttc"}:
            continue
        try:
            family = ImageFont.truetype(str(candidate), 20).getname()[0]
        except Exception:
            continue
        items.append((str(family), str(candidate)))
    return tuple(items)


def bundled_font_families() -> list[str]:
    return sorted({family for family, _path in bundled_font_files()})


def resolve_font_file(font_name: str) -> str:
    """Pin the measured font to a bundled file; fontconfig differs per machine."""
    wanted = str(font_name or "").strip().casefold()
    items = bundled_font_files()
    for family, path in items:
        if family.casefold() == wanted:
            return path
    for family, path in items:
        if wanted and (wanted in family.casefold() or family.casefold() in wanted):
            return path
    return items[0][1] if items else ""


def _sfnt_tables(data: bytes) -> dict[bytes, tuple[int, int]]:
    if data[:4] == b"ttcf":  # collection: use the first font in it
        first = int.from_bytes(data[12:16], "big")
    else:
        first = 0
    count = int.from_bytes(data[first + 4 : first + 6], "big")
    tables: dict[bytes, tuple[int, int]] = {}
    for index in range(count):
        record = first + 12 + index * 16
        tag = data[record : record + 4]
        offset = int.from_bytes(data[record + 8 : record + 12], "big")
        length = int.from_bytes(data[record + 12 : record + 16], "big")
        tables[tag] = (offset, length)
    return tables


@lru_cache(maxsize=16)
def libass_size_factor(font_file: str) -> float:
    """Pixels per ASS ``Fontsize`` unit for this font file.

    libass sizes faces with ``FT_SIZE_REQUEST_TYPE_REAL_DIM`` after multiplying by
    ``hhea_height / (usWinAscent + usWinDescent)``, which works out to an em of
    ``Fontsize * unitsPerEm / (usWinAscent + usWinDescent)``. Without this, a CJK
    face whose win metrics run well past the em renders ~1.5x smaller than the
    number in the style block, and every measured box would be wrong.
    """
    try:
        data = Path(font_file).read_bytes()
        tables = _sfnt_tables(data)
        head_offset = tables[b"head"][0]
        os2_offset = tables[b"OS/2"][0]
        units_per_em = int.from_bytes(data[head_offset + 18 : head_offset + 20], "big")
        win_ascent = int.from_bytes(data[os2_offset + 74 : os2_offset + 76], "big")
        win_descent = int.from_bytes(data[os2_offset + 76 : os2_offset + 78], "big")
    except Exception:
        return 1.0
    total = win_ascent + win_descent
    if not units_per_em or not total:
        return 1.0
    return units_per_em / total


@lru_cache(maxsize=64)
def _pil_font(font_file: str, size: int) -> Any:
    from PIL import ImageFont

    if not font_file:
        return ImageFont.load_default()
    return ImageFont.truetype(font_file, max(1, int(size)))


@lru_cache(maxsize=4096)
def _measure(font_file: str, size: int, text: str, spacing: float = 0.0) -> float:
    """Advance width in pixels. Synthetic bold fattens outlines but not advances,
    so it deliberately plays no part here."""
    font = _pil_font(font_file, size)
    try:
        return float(font.getlength(text)) + max(0, len(text) - 1) * spacing
    except (AttributeError, TypeError):  # bitmap fallback font has no getlength
        return float(font.getbbox(text)[2]) + max(0, len(text) - 1) * spacing


@lru_cache(maxsize=64)
def _font_metrics(font_file: str, size: int) -> tuple[float, float]:
    font = _pil_font(font_file, size)
    try:
        ascent, descent = font.getmetrics()
    except AttributeError:
        ascent, descent = int(size * 0.8), int(size * 0.2)
    return float(ascent), float(descent)


# ------------------------------------------------------------------ #
# Layout
# ------------------------------------------------------------------ #


@dataclass(frozen=True)
class SubtitleLine:
    text: str
    left: float
    baseline: float
    width: float


@dataclass(frozen=True)
class SubtitleLayout:
    """Geometry in video pixels shared by the ASS writer and the Qt overlay."""

    lines: tuple[SubtitleLine, ...]
    block: tuple[float, float, float, float]
    box: tuple[float, float, float, float]
    font_file: str
    font_size: int
    ascent: float
    descent: float

    @property
    def is_empty(self) -> bool:
        return not self.lines

    @property
    def line_height(self) -> float:
        return self.ascent + self.descent

    def ass_text(self) -> str:
        return "\\N".join(escape_ass_text(line.text) for line in self.lines)


def escape_ass_text(text: str) -> str:
    r"""libass reads ``\{``/``\}`` as literal braces; bare ones open a tag block."""
    return str(text).replace("{", "\\{").replace("}", "\\}")


def wrap_subtitle_text(
    text: str,
    style: EditorSubtitleStyle,
    frame_width: int,
    *,
    font_file: str = "",
) -> list[str]:
    r"""Wrap to the usable width; events carry ``\q2`` so libass never rewraps."""
    font_file = font_file or resolve_font_file(style.font_name)
    usable = max(
        float(style.font_size),
        float(frame_width)
        - style.margin_l
        - style.margin_r
        - 2 * (style.padding_h + style.outline_width),
    )
    lines: list[str] = []
    for paragraph in str(text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        lines.extend(_wrap_paragraph(paragraph, style, font_file, usable))
    return lines


def _wrap_paragraph(
    paragraph: str, style: EditorSubtitleStyle, font_file: str, usable: float
) -> list[str]:
    if _measure(font_file, style.font_size, paragraph, style.spacing) <= usable:
        return [paragraph]
    lines: list[str] = []
    current = ""
    for token in _tokenize(paragraph):
        candidate = f"{current}{token}"
        if (
            current
            and _measure(font_file, style.font_size, candidate.rstrip(), style.spacing) > usable
        ):
            lines.append(current.rstrip())
            current = token.lstrip()
        else:
            current = candidate
    if current.strip():
        lines.append(current.rstrip())
    return lines or [paragraph]


def _tokenize(paragraph: str) -> list[str]:
    """Split on spaces, but break CJK per character since it carries no spaces."""
    tokens: list[str] = []
    buffer = ""
    for char in paragraph:
        if _is_cjk(char):
            if buffer:
                tokens.append(buffer)
                buffer = ""
            tokens.append(char)
            continue
        buffer += char
        if char == " ":
            tokens.append(buffer)
            buffer = ""
    if buffer:
        tokens.append(buffer)
    return tokens


def _is_cjk(char: str) -> bool:
    code = ord(char)
    return (
        0x3040 <= code <= 0x30FF
        or 0x3400 <= code <= 0x4DBF
        or 0x4E00 <= code <= 0x9FFF
        or 0xF900 <= code <= 0xFAFF
        or 0xAC00 <= code <= 0xD7AF
    )


def anchor_point(
    style: EditorSubtitleStyle, frame_width: int, frame_height: int
) -> tuple[float, float]:
    r"""The ``\pos`` point libass anchors the block to for this alignment."""
    if style.align_h == "left":
        x = float(style.margin_l)
    elif style.align_h == "right":
        x = float(frame_width - style.margin_r)
    else:
        x = (style.margin_l + (frame_width - style.margin_r)) / 2.0
    if style.align_v == "top":
        y = float(style.margin_v)
    elif style.align_v == "middle":
        y = frame_height / 2.0
    else:
        y = float(frame_height - style.margin_v)
    return x, y


def layout_subtitle(
    text: str,
    style: EditorSubtitleStyle,
    frame_width: int,
    frame_height: int,
) -> SubtitleLayout:
    """Place ``text`` exactly where libass puts it for the generated ASS event."""
    frame_width, frame_height = frame_size(frame_width, frame_height)
    style = style.scaled_for_height(frame_height)
    font_file = resolve_font_file(style.font_name)
    ascent, descent = _font_metrics(font_file, style.font_size)
    raw_lines = wrap_subtitle_text(text, style, frame_width, font_file=font_file)
    empty = (0.0, 0.0, 0.0, 0.0)
    if not raw_lines:
        return SubtitleLayout((), empty, empty, font_file, style.font_size, ascent, descent)

    widths = [_measure(font_file, style.font_size, line, style.spacing) for line in raw_lines]
    block_w = max(widths)
    line_height = ascent + descent
    block_h = line_height * len(raw_lines)

    anchor_x, anchor_y = anchor_point(style, frame_width, frame_height)
    if style.align_h == "left":
        block_x = anchor_x
    elif style.align_h == "right":
        block_x = anchor_x - block_w
    else:
        block_x = anchor_x - block_w / 2.0
    if style.align_v == "top":
        block_y = anchor_y
    elif style.align_v == "middle":
        block_y = anchor_y - block_h / 2.0
    else:
        block_y = anchor_y - block_h

    lines: list[SubtitleLine] = []
    for index, (line, width) in enumerate(zip(raw_lines, widths)):
        if style.align_h == "left":
            left = block_x
        elif style.align_h == "right":
            left = block_x + block_w - width
        else:
            left = block_x + (block_w - width) / 2.0
        lines.append(SubtitleLine(line, left, block_y + index * line_height + ascent, width))

    # The box must clear the glyph outline on top of the requested padding.
    inflate_x = style.padding_h + style.outline_width
    inflate_y = style.padding_v + style.outline_width
    box = (
        block_x - inflate_x,
        block_y - inflate_y,
        block_w + 2 * inflate_x,
        block_h + 2 * inflate_y,
    )
    return SubtitleLayout(
        tuple(lines),
        (block_x, block_y, block_w, block_h),
        box,
        font_file,
        style.font_size,
        ascent,
        descent,
    )


# ------------------------------------------------------------------ #
# ASS generation
# ------------------------------------------------------------------ #


def _ass_timestamp(ms: int) -> str:
    ms = max(0, int(ms))
    total_seconds, milliseconds = divmod(ms, 1000)
    minutes, seconds = divmod(total_seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:01}:{minutes:02}:{seconds:02}.{milliseconds // 10:02}"


def _ass_color(hex_color: str) -> str:
    raw = str(hex_color or "#000000").lstrip("#")
    if len(raw) != 6:
        raw = "000000"
    return f"&H00{raw[4:6]}{raw[2:4]}{raw[0:2]}".upper()


def _ass_alpha(opacity: float) -> str:
    return f"&H{255 - int(round(_clamp(float(opacity), 0.0, 1.0) * 255)):02X}&"


def rounded_rect_drawing(width: float, height: float, radius: float) -> str:
    r"""ASS ``\p1`` path for the background box, bezier corners included."""
    w, h = max(1.0, float(width)), max(1.0, float(height))
    r = _clamp(float(radius), 0.0, min(w, h) / 2.0)
    if r <= 0.5:
        return f"m 0 0 l {w:.0f} 0 l {w:.0f} {h:.0f} l 0 {h:.0f}"
    c = r * _KAPPA
    return (
        f"m {r:.0f} 0 "
        f"l {w - r:.0f} 0 "
        f"b {w - r + c:.0f} 0 {w:.0f} {r - c:.0f} {w:.0f} {r:.0f} "
        f"l {w:.0f} {h - r:.0f} "
        f"b {w:.0f} {h - r + c:.0f} {w - r + c:.0f} {h:.0f} {w - r:.0f} {h:.0f} "
        f"l {r:.0f} {h:.0f} "
        f"b {r - c:.0f} {h:.0f} 0 {h - r + c:.0f} 0 {h - r:.0f} "
        f"l 0 {r:.0f} "
        f"b 0 {r - c:.0f} {r - c:.0f} 0 {r:.0f} 0"
    )


def build_editor_ass(
    events: Iterable[Sequence[Any]],
    style: EditorSubtitleStyle,
    frame_width: int,
    frame_height: int,
) -> str:
    """Render ``(start_ms, end_ms, text)`` events into a fully positioned ASS script."""
    frame_width, frame_height = frame_size(frame_width, frame_height)
    style = style.scaled_for_height(frame_height)
    alignment = style.ass_alignment
    anchor_x, anchor_y = anchor_point(style, frame_width, frame_height)
    header = (
        "[Script Info]\n"
        "; Generated by VideoCaptioner Video Editor\n"
        "ScriptType: v4.00+\n"
        "WrapStyle: 2\n"
        "ScaledBorderAndShadow: yes\n"
        f"PlayResX: {frame_width}\n"
        f"PlayResY: {frame_height}\n\n"
        f"{style.to_ass_style_block()}\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )
    body: list[str] = []
    for event in events:
        start_ms, end_ms, text = int(event[0]), int(event[1]), str(event[2])
        layout = layout_subtitle(text, style, frame_width, frame_height)
        if layout.is_empty:
            continue
        start, end = _ass_timestamp(start_ms), _ass_timestamp(end_ms)
        if style.background:
            box_x, box_y, box_w, box_h = layout.box
            drawing = rounded_rect_drawing(box_w, box_h, style.corner_radius)
            body.append(
                f"Dialogue: 0,{start},{end},Default,,0,0,0,,"
                f"{{\\an7\\pos({box_x:.0f},{box_y:.0f})\\bord0\\shad0"
                f"\\1c{_ass_color(style.bg_color)}\\1a{_ass_alpha(style.bg_opacity)}\\p1}}"
                f"{drawing}{{\\p0}}\n"
            )
        body.append(
            f"Dialogue: 1,{start},{end},Default,,0,0,0,,"
            f"{{\\an{alignment}\\pos({anchor_x:.0f},{anchor_y:.0f})\\q2}}{layout.ass_text()}\n"
        )
    return header + "".join(body)


def frame_size(width: int, height: int) -> tuple[int, int]:
    """Fall back to 1080p so layout never depends on a probe that failed."""
    return int(width or DEFAULT_FRAME_WIDTH), int(height or DEFAULT_FRAME_HEIGHT)

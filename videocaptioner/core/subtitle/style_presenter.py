"""Qt-independent decisions behind the subtitle style tab.

The view owns widgets and ``cfg``; everything that can be reasoned about with
plain values (which text goes on top, which style files match the render mode,
how a colour is serialised, which renderer draws the preview) lives here so it
can be unit-tested without a QApplication.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from videocaptioner.core.entities import SubtitleLayoutEnum, SubtitleRenderModeEnum
from videocaptioner.core.subtitle.ass_renderer import render_ass_preview
from videocaptioner.core.subtitle.rounded_renderer import render_preview
from videocaptioner.core.subtitle.style_manager import (
    StyleMode,
    SubtitleStyle,
    style_id_from_filename,
)
from videocaptioner.core.subtitle.styles import RoundedBgStyle

# Combo labels are the dict keys; each value is (original, translation).
PREVIEW_TEXTS: Dict[str, Tuple[str, str]] = {
    "长文本": (
        "This is a long text for testing subtitle preview, text wrapping, and style settings.",
        "这是一段用于测试字幕预览、自动换行以及样式设置的较长文本内容。",
    ),
    "中文本": (
        "Welcome to apply for the prestigious South China Normal University!",
        "欢迎报考百年名校华南师范大学",
    ),
    "短文本": ("Elementary school students know this", "小学二年级的都知道"),
}

# Orientation combo entries; the first one is landscape.
PREVIEW_ORIENTATIONS: Tuple[str, str] = ("横屏", "竖屏")
LANDSCAPE_BACKGROUND = "default_bg_landscape.png"
PORTRAIT_BACKGROUND = "default_bg_portrait.png"

DEFAULT_STYLE_ID = "default"
IMAGE_SUFFIXES: Tuple[str, ...] = (".png", ".jpg", ".jpeg")
# Fallback when a stored rounded background colour cannot be parsed.
DEFAULT_ROUNDED_BG_RGBA: Tuple[int, int, int, int] = (25, 25, 25, 200)

_STYLE_FILE_PREFIX = {StyleMode.ASS: "ass-", StyleMode.ROUNDED: "rounded-"}


def style_mode_for(render_mode: SubtitleRenderModeEnum) -> StyleMode:
    """Map the GUI render mode onto the style-file mode."""
    if render_mode == SubtitleRenderModeEnum.ROUNDED_BG:
        return StyleMode.ROUNDED
    return StyleMode.ASS


def preview_text_pair(
    original: str, translation: str, layout: SubtitleLayoutEnum
) -> Tuple[str, Optional[str]]:
    """Order the two sample lines the way the chosen layout shows them.

    The renderers draw the first element with the primary style and the
    optional second element with the secondary style.
    """
    if layout == SubtitleLayoutEnum.TRANSLATE_ON_TOP:
        return translation, original
    if layout == SubtitleLayoutEnum.ONLY_TRANSLATE:
        return translation, None
    if layout == SubtitleLayoutEnum.ONLY_ORIGINAL:
        return original, None
    return original, translation


def default_background(assets_dir: Path, orientation: str) -> Path:
    """Bundled preview background for an orientation combo label."""
    if orientation == PREVIEW_ORIENTATIONS[0]:
        return Path(assets_dir) / LANDSCAPE_BACKGROUND
    return Path(assets_dir) / PORTRAIT_BACKGROUND


def preview_background(user_path: Optional[str], default: Path) -> Path:
    """Prefer the user's image when it still exists, else the bundled one."""
    if user_path and Path(user_path).exists():
        return Path(user_path)
    return Path(default)


def parse_rgba_hex(
    value: str, default: Tuple[int, int, int, int] = DEFAULT_ROUNDED_BG_RGBA
) -> Tuple[int, int, int, int]:
    """Parse ``#RRGGBBAA`` or ``#RRGGBB`` into an (r, g, b, a) tuple."""
    digits = (value or "").strip().lstrip("#")
    if len(digits) not in (6, 8):
        return default
    try:
        channels = [int(digits[i : i + 2], 16) for i in range(0, len(digits), 2)]
    except ValueError:
        return default
    if len(channels) == 3:
        channels.append(255)
    return channels[0], channels[1], channels[2], channels[3]


def format_rgba_hex(red: int, green: int, blue: int, alpha: int) -> str:
    """Serialise a colour as the ``#rrggbbaa`` form stored in style files."""
    return f"#{red:02x}{green:02x}{blue:02x}{alpha:02x}"


def font_choices(
    builtin_names: Sequence[str],
    system_families: Iterable[str],
    can_load: Callable[[str], bool],
) -> List[str]:
    """Bundled fonts first, then the system families the renderer can open.

    Private families (leading dot) and duplicates of bundled fonts are
    dropped; ``can_load`` filters out families Pillow cannot resolve, which
    would otherwise fall back to a default font in rounded mode.
    """
    builtin = list(builtin_names)
    known = set(builtin)
    system = sorted(
        name
        for name in system_families
        if name and not name.startswith(".") and name not in known and can_load(name)
    )
    return builtin + system


def pil_can_load_font(font_name: str, size: int = 12) -> bool:
    """Whether Pillow can open the family by name (lazy import keeps startup light)."""
    from PIL import ImageFont

    try:
        ImageFont.truetype(font_name, size)
    except OSError:
        return False
    return True


def style_file_path(styles_dir: Path, mode: StyleMode, style_id: str) -> Path:
    """Where a style of this mode is written: ``<prefix><id>.json``."""
    return Path(styles_dir) / f"{_STYLE_FILE_PREFIX[mode]}{style_id}.json"


def resolve_style_path(styles_dir: Path, mode: StyleMode, style_id: str) -> Path:
    """Prefer the mode-prefixed file, fall back to the bare ``<id>.json``."""
    prefixed = style_file_path(styles_dir, mode, style_id)
    if prefixed.exists():
        return prefixed
    return Path(styles_dir) / f"{style_id}.json"


def list_style_ids(styles_dir: Path, mode: StyleMode) -> List[str]:
    """IDs of the JSON styles whose ``mode`` matches, default first.

    Unreadable files are skipped rather than breaking the combo; a file
    without a ``mode`` key counts as an ASS style, matching ``SubtitleStyle``.
    """
    styles_dir = Path(styles_dir)
    if not styles_dir.is_dir():
        return []
    ids: List[str] = []
    for path in sorted(styles_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(data, dict):
            continue
        if data.get("mode", StyleMode.ASS.value) != mode.value:
            continue
        style_id = style_id_from_filename(path.name)
        if style_id not in ids:
            ids.append(style_id)
    if DEFAULT_STYLE_ID in ids:
        ids.remove(DEFAULT_STYLE_ID)
        ids.insert(0, DEFAULT_STYLE_ID)
    return ids


def choose_style_id(style_ids: Sequence[str], preferred: Optional[str]) -> str:
    """Keep the persisted choice when it still exists, else the first entry."""
    if preferred and preferred in style_ids:
        return preferred
    return style_ids[0] if style_ids else DEFAULT_STYLE_ID


def save_style(styles_dir: Path, style: SubtitleStyle) -> Path:
    """Write the style under its mode prefix and return the path."""
    path = style_file_path(styles_dir, style.mode, style.name)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(style.to_json_dict(), handle, ensure_ascii=False, indent=2)
    return path


def rounded_bg_style(style: SubtitleStyle) -> RoundedBgStyle:
    """Renderer-side dataclass for a rounded-mode style."""
    return RoundedBgStyle(**style.to_rounded_dict())


def render_style_preview(
    style: SubtitleStyle,
    preview_text: Tuple[str, Optional[str]],
    bg_image_path: str,
) -> str:
    """Render the preview image with the renderer matching the style mode."""
    if style.mode is StyleMode.ROUNDED:
        primary, secondary = preview_text
        return render_preview(
            primary_text=primary,
            secondary_text=secondary or "",
            style=rounded_bg_style(style),
            bg_image_path=bg_image_path,
        )
    return render_ass_preview(
        style_str=style.to_ass_string(),
        preview_text=preview_text,
        bg_image_path=bg_image_path,
    )


def first_image_path(paths: Iterable[str]) -> Optional[str]:
    """First dropped path that looks like a preview image, if any."""
    for path in paths:
        if path and path.lower().endswith(IMAGE_SUFFIXES):
            return path
    return None

"""Unit tests for the Qt-independent logic behind the subtitle style tab."""

import json
from pathlib import Path

import pytest

from videocaptioner.core.entities import SubtitleLayoutEnum, SubtitleRenderModeEnum
from videocaptioner.core.subtitle import style_presenter as presenter
from videocaptioner.core.subtitle.style_manager import (
    SecondaryStyle,
    StyleMode,
    SubtitleStyle,
)

# ----------------------------------------------------------------- preview text


@pytest.mark.parametrize(
    "layout, expected",
    [
        (SubtitleLayoutEnum.ORIGINAL_ON_TOP, ("orig", "trans")),
        (SubtitleLayoutEnum.TRANSLATE_ON_TOP, ("trans", "orig")),
        (SubtitleLayoutEnum.ONLY_ORIGINAL, ("orig", None)),
        (SubtitleLayoutEnum.ONLY_TRANSLATE, ("trans", None)),
    ],
)
def test_preview_text_pair_follows_layout(layout, expected):
    assert presenter.preview_text_pair("orig", "trans", layout) == expected


def test_every_preview_text_has_two_lines():
    for original, translation in presenter.PREVIEW_TEXTS.values():
        assert original and translation


def test_default_background_by_orientation(tmp_path):
    landscape, portrait = presenter.PREVIEW_ORIENTATIONS
    assert presenter.default_background(tmp_path, landscape).name == "default_bg_landscape.png"
    assert presenter.default_background(tmp_path, portrait).name == "default_bg_portrait.png"


def test_preview_background_prefers_existing_user_image(tmp_path):
    default = tmp_path / "default.png"
    user = tmp_path / "mine.png"
    user.write_bytes(b"png")
    assert presenter.preview_background(str(user), default) == user
    assert presenter.preview_background(str(tmp_path / "gone.png"), default) == default
    assert presenter.preview_background("", default) == default
    assert presenter.preview_background(None, default) == default


# ---------------------------------------------------------------------- colours


def test_parse_rgba_hex_accepts_both_lengths():
    assert presenter.parse_rgba_hex("#191919c8") == (25, 25, 25, 200)
    assert presenter.parse_rgba_hex("0DE3FFE5") == (13, 227, 255, 229)
    assert presenter.parse_rgba_hex("#ffffff") == (255, 255, 255, 255)


@pytest.mark.parametrize("value", ["", "#12345", "#zzzzzz", None, "#12345678901"])
def test_parse_rgba_hex_falls_back_on_garbage(value):
    assert presenter.parse_rgba_hex(value) == presenter.DEFAULT_ROUNDED_BG_RGBA
    assert presenter.parse_rgba_hex(value, default=(1, 2, 3, 4)) == (1, 2, 3, 4)


def test_format_rgba_hex_round_trips():
    text = presenter.format_rgba_hex(25, 25, 25, 200)
    assert text == "#191919c8"
    assert presenter.parse_rgba_hex(text) == (25, 25, 25, 200)


# ------------------------------------------------------------------------ fonts


def test_font_choices_keeps_builtin_first_and_filters_system():
    loadable = {"Arial", "Segoe UI"}
    fonts = presenter.font_choices(
        ["Noto Sans SC", "Noto Sans"],
        ["Segoe UI", ".HiddenFont", "Noto Sans", "Arial", "Broken", ""],
        loadable.__contains__,
    )
    assert fonts == ["Noto Sans SC", "Noto Sans", "Arial", "Segoe UI"]


def test_pil_can_load_font_reports_missing_family():
    assert presenter.pil_can_load_font("definitely-not-a-font-family-xyz") is False


# ------------------------------------------------------------------ style files


def _write(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data), encoding="utf-8")


def test_style_paths_use_mode_prefix(tmp_path):
    assert presenter.style_file_path(tmp_path, StyleMode.ASS, "anime") == tmp_path / "ass-anime.json"
    assert (
        presenter.style_file_path(tmp_path, StyleMode.ROUNDED, "dark")
        == tmp_path / "rounded-dark.json"
    )
    assert presenter.style_mode_for(SubtitleRenderModeEnum.ASS_STYLE) is StyleMode.ASS
    assert presenter.style_mode_for(SubtitleRenderModeEnum.ROUNDED_BG) is StyleMode.ROUNDED


def test_resolve_style_path_prefers_prefixed_file(tmp_path):
    _write(tmp_path / "ass-default.json", {"mode": "ass"})
    assert presenter.resolve_style_path(tmp_path, StyleMode.ASS, "default").name == "ass-default.json"
    # No rounded file yet: the bare name is returned even though it does not exist.
    bare = presenter.resolve_style_path(tmp_path, StyleMode.ROUNDED, "default")
    assert bare == tmp_path / "default.json"
    assert not bare.exists()


def test_list_style_ids_filters_by_mode_and_puts_default_first(tmp_path):
    _write(tmp_path / "ass-zeta.json", {"mode": "ass"})
    _write(tmp_path / "ass-default.json", {"mode": "ass"})
    _write(tmp_path / "legacy.json", {"font_name": "Arial"})  # no mode -> ass
    _write(tmp_path / "rounded-default.json", {"mode": "rounded"})
    _write(tmp_path / "rounded-night.json", {"mode": "rounded"})
    (tmp_path / "broken.json").write_text("{not json", encoding="utf-8")
    (tmp_path / "list.json").write_text("[1, 2]", encoding="utf-8")

    # Filename order (as the old view did), with "default" hoisted to the front.
    assert presenter.list_style_ids(tmp_path, StyleMode.ASS) == ["default", "zeta", "legacy"]
    assert presenter.list_style_ids(tmp_path, StyleMode.ROUNDED) == ["default", "night"]


def test_list_style_ids_handles_missing_dir(tmp_path):
    assert presenter.list_style_ids(tmp_path / "nope", StyleMode.ASS) == []


def test_choose_style_id_keeps_persisted_choice_when_present():
    assert presenter.choose_style_id(["default", "anime"], "anime") == "anime"
    assert presenter.choose_style_id(["default", "anime"], "gone") == "default"
    assert presenter.choose_style_id(["default", "anime"], None) == "default"
    assert presenter.choose_style_id([], "anything") == presenter.DEFAULT_STYLE_ID


def test_save_style_round_trips_ass_mode(tmp_path):
    style = SubtitleStyle(
        name="anime",
        mode=StyleMode.ASS,
        font_name="Noto Sans SC",
        font_size=48,
        primary_color="#ff00ff",
        outline_color="#101010",
        outline_width=1.5,
        bold=True,
        spacing=2.0,
        margin_bottom=44,
        secondary=SecondaryStyle(font_name="Arial", font_size=30, color="#eeeeee"),
    )
    path = presenter.save_style(tmp_path / "styles", style)
    assert path == tmp_path / "styles" / "ass-anime.json"
    loaded = SubtitleStyle.from_file(path)
    assert loaded == style
    assert loaded.to_ass_string() == style.to_ass_string()


def test_save_style_round_trips_rounded_mode(tmp_path):
    style = SubtitleStyle(
        name="night",
        mode=StyleMode.ROUNDED,
        font_name="Arial",
        font_size=36,
        text_color="#ffffff",
        bg_color="#191919c8",
        corner_radius=8,
        padding_h=20,
        padding_v=10,
        margin_bottom_rounded=55,
        line_spacing=6,
        letter_spacing=1,
    )
    path = presenter.save_style(tmp_path, style)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["mode"] == "rounded"
    assert data["margin_bottom"] == 55
    assert SubtitleStyle.from_file(path) == style


def test_rounded_bg_style_maps_every_field():
    style = SubtitleStyle(
        mode=StyleMode.ROUNDED,
        font_name="Arial",
        font_size=36,
        text_color="#ffffff",
        bg_color="#191919c8",
        corner_radius=8,
        padding_h=20,
        padding_v=10,
        margin_bottom_rounded=55,
        line_spacing=6,
        letter_spacing=1,
    )
    rounded = presenter.rounded_bg_style(style)
    assert rounded.font_name == "Arial"
    assert rounded.font_size == 36
    assert rounded.bg_color == "#191919c8"
    assert rounded.text_color == "#ffffff"
    assert rounded.margin_bottom == 55
    assert (rounded.corner_radius, rounded.padding_h, rounded.padding_v) == (8, 20, 10)
    assert (rounded.line_spacing, rounded.letter_spacing) == (6, 1)


def test_render_style_preview_dispatches_on_mode(monkeypatch):
    calls = []
    monkeypatch.setattr(
        presenter,
        "render_ass_preview",
        lambda **kwargs: calls.append(("ass", kwargs)) or "ass.png",
    )
    monkeypatch.setattr(
        presenter,
        "render_preview",
        lambda **kwargs: calls.append(("rounded", kwargs)) or "rounded.png",
    )
    ass = SubtitleStyle(mode=StyleMode.ASS, font_name="Arial")
    assert presenter.render_style_preview(ass, ("a", "b"), "bg.png") == "ass.png"
    rounded = SubtitleStyle(mode=StyleMode.ROUNDED, font_name="Arial")
    assert presenter.render_style_preview(rounded, ("a", None), "bg.png") == "rounded.png"

    kind, kwargs = calls[0]
    assert kind == "ass"
    assert kwargs["style_str"] == ass.to_ass_string()
    assert kwargs["preview_text"] == ("a", "b")
    kind, kwargs = calls[1]
    assert kind == "rounded"
    assert kwargs["primary_text"] == "a"
    assert kwargs["secondary_text"] == ""
    assert kwargs["style"].font_name == "Arial"


# ------------------------------------------------------------------- drag/drop


def test_first_image_path_picks_first_supported_file():
    assert presenter.first_image_path(["notes.txt", "C:/a/B.JPG", "c.png"]) == "C:/a/B.JPG"
    assert presenter.first_image_path(["notes.txt", ""]) is None
    assert presenter.first_image_path([]) is None

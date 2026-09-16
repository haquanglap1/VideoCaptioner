"""Both style generations survive persistence, editing and real render paths."""

import shutil
from dataclasses import replace
from pathlib import Path

import pytest
from PyQt5.QtWidgets import QApplication

from videocaptioner.config import FONTS_PATH
from videocaptioner.core.editor.commands import CommandStack, EditSubtitleStyleCommand
from videocaptioner.core.editor.media import (
    _escape_filter_path,
    export_editor_video,
    render_fast_preview,
)
from videocaptioner.core.editor.models import EditorCue, EditorProject
from videocaptioner.core.editor.project_store import EditorProjectStore
from videocaptioner.core.editor.subtitle_style import (
    EditorSubtitleStyle,
    build_editor_ass,
    layout_subtitle,
)
from videocaptioner.core.subtitle.style_manager import StyleMode, SubtitleStyle
from videocaptioner.ui.view.video_editor_interface import VideoEditorInterface

from .test_subtitle_style_render import _ffmpeg, _red_bounds


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.mark.parametrize("height", [720, 1080, 2160])
def test_stashed_pixel_style_is_migrated_once_without_changing_geometry(tmp_path, height):
    payload = EditorProject.empty("", 2000).to_dict()
    payload.update(width=height * 16 // 9, height=height)
    payload["subtitle_style"] = {
        "font_name": "Noto Sans SC",
        "font_size": 88,
        "bold": True,
        "primary_color": "#abcdef",
        "outline_color": "#000000",
        "outline_width": 2.25,
        "align_h": "right",
        "align_v": "top",
        "margin_l": 123,
        "margin_r": 80,
        "margin_v": 44,
        "background": True,
        "bg_color": "#123456",
        "bg_opacity": 0.375,
        "corner_radius": 27,
        "padding_h": 18,
        "padding_v": 11,
    }
    project = EditorProject.from_dict(payload)
    style = project.subtitle_style
    assert style.reference_height == 0 and style.layout_mode == "shared"
    assert style.font_size == 88 and style.alignment == 9
    assert style.scaled_for_height(height) == style
    before = layout_subtitle("Hello", style, project.width, project.height)
    saved, _ = EditorProjectStore().save(project, tmp_path / "legacy.vceditor.json")
    loaded = EditorProjectStore().load(saved)
    assert loaded.subtitle_style == style
    assert layout_subtitle("Hello", loaded.subtitle_style, loaded.width, loaded.height) == before
    assert not list(tmp_path.glob("*.ass"))
    assert loaded.schema_version == "editor-project-v1"


def test_current_style_defaults_and_reference_units_are_preserved():
    style = EditorSubtitleStyle.from_dict({"font_size": 61, "spacing": 1.5, "alignment": 8})
    assert style.reference_height == 720 and not style.uses_shared_layout
    assert style.scaled_for_height(1440).font_size == 122
    assert style.scaled_for_height(1440).spacing == 3.0
    assert style.scaled_for_height(1440).scaled_for_height(1440).font_size == 122
    assert EditorSubtitleStyle().outline_width == 0 and not EditorSubtitleStyle().background


@pytest.mark.parametrize(
    "bad",
    [
        {"background": "false"},
        {"bg_color": "red"},
        {"bg_opacity": float("nan")},
        {"bg_opacity": float("inf")},
        {"bg_opacity": True},
        {"corner_radius": -1},
        {"padding_h": 3.5},
        {"reference_height": 1080},
        {"reference_height": False},
        {"layout_mode": "unknown"},
        {"align_h": "middle"},
        {"align_v": "left"},
    ],
)
def test_restored_style_fields_fail_validation_before_mutation(bad):
    project = EditorProject.empty()
    original = project.to_dict()
    stack = CommandStack()
    with pytest.raises(ValueError):
        stack.execute(EditSubtitleStyleCommand(project, bad))
    assert project.to_dict() == original and not stack.can_undo


def test_partial_style_command_takes_a_snapshot_and_keeps_unedited_fields():
    project = EditorProject.empty()
    project.subtitle_style = EditorSubtitleStyle(spacing=2, font_name="Missing Font", alignment=9)
    changes = {"background": True, "padding_h": 42}
    command = EditSubtitleStyleCommand(project, changes)
    changes["padding_h"] = 100
    stack = CommandStack()
    stack.execute(command)
    assert project.subtitle_style.padding_h == 42
    assert (
        project.subtitle_style.spacing == 2 and project.subtitle_style.font_name == "Missing Font"
    )
    stack.undo()
    assert not project.subtitle_style.background
    stack.redo()
    assert project.subtitle_style.background


def test_rounded_preset_retains_rgba_and_plain_preset_retains_spacing():
    rounded = SubtitleStyle(
        name="round",
        mode=StyleMode.ROUNDED,
        font_size=56,
        bg_color="#12345680",
        text_color="#abcdef",
        padding_h=17,
    )
    restored = EditorSubtitleStyle.from_preset(rounded)
    assert restored.reference_height == 720 and restored.uses_shared_layout
    assert restored.bg_color == "#123456" and restored.bg_opacity == pytest.approx(128 / 255)
    assert restored.padding_h == 17 and restored.scaled_for_height(1440).padding_h == 34
    plain = EditorSubtitleStyle.from_preset(SubtitleStyle(name="plain", spacing=2.5))
    assert plain.spacing == 2.5 and not plain.uses_shared_layout


def test_preset_load_apply_noop_reset_and_undo_keep_both_styles(qapp, monkeypatch):
    from videocaptioner.core.subtitle import style_manager

    monkeypatch.setattr(
        style_manager,
        "load_style",
        lambda _: SubtitleStyle(
            name="rounded",
            mode=StyleMode.ROUNDED,
            font_size=55,
            padding_h=25,
        ),
    )
    page = VideoEditorInterface()
    monkeypatch.setattr(page, "_start_media", lambda *_args, **_kwargs: None)
    project = EditorProject.empty("", 2000)
    original = replace(project.subtitle_style, spacing=1.5)
    project.subtitle_style = original
    try:
        page._accept_project(project)
        panel = page.subtitle_style_panel
        panel.set_presets(["rounded-default"])
        panel.preset_button.click()
        assert project.subtitle_style == original and not page.command_stack.can_undo
        panel.apply_button.click()
        rounded = project.subtitle_style
        assert rounded.background and rounded.padding_h == 25
        panel.apply_button.click()
        page.undo()
        assert project.subtitle_style == original
        page.redo()
        assert project.subtitle_style == rounded
        panel.reset_button.click()
        assert project.subtitle_style == EditorSubtitleStyle()
        page.undo()
        assert project.subtitle_style == rounded
    finally:
        page.close()


def test_opening_pixel_project_and_editing_color_preserves_units_and_spacing(qapp, monkeypatch):
    page = VideoEditorInterface()
    monkeypatch.setattr(page, "_start_media", lambda *_args, **_kwargs: None)
    project = EditorProject.empty("", 2000)
    project.subtitle_style = EditorSubtitleStyle.from_dict(
        {
            "font_size": 400,
            "align_h": "left",
            "margin_v": 800,
            "outline_width": 2.25,
            "spacing": 1.125,
        }
    )
    try:
        page._accept_project(project)
        expected = replace(project.subtitle_style, primary_color="#123456")
        page.subtitle_style_panel.primary_color_edit.setText("#123456")
        page.subtitle_style_panel.apply_button.click()
        assert project.subtitle_style == expected
    finally:
        page.close()


def test_shared_layout_accounts_for_letter_spacing():
    style = EditorSubtitleStyle(background=True).scaled_for_height(720)
    plain = layout_subtitle("Spacing", style, 1280, 720)
    spaced = layout_subtitle("Spacing", replace(style, spacing=3), 1280, 720)
    assert spaced.block[2] - plain.block[2] == pytest.approx(18)
    ass = build_editor_ass([(0, 1000, "Spacing")], replace(style, spacing=3), 1280, 720)
    assert ",100,100,3," in ass


def test_real_reference_background_preview_export_and_explicit_ass_agree(tmp_path, monkeypatch):
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        pytest.skip("FFmpeg/ffprobe are required")
    import tempfile

    scratch = tmp_path / "scratch"
    scratch.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(scratch))
    source = tmp_path / "input.mp4"
    _ffmpeg(
        "-f",
        "lavfi",
        "-i",
        "color=c=black:s=320x180:r=24:d=2",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        source,
    )
    project = EditorProject.empty(str(source), 2000)
    project.cues = [EditorCue("cue", 0, 2000, "source", "Subtitle", "tts")]
    project.subtitle_style = EditorSubtitleStyle(
        background=True,
        bg_color="#ff0000",
        bg_opacity=1.0,
        spacing=2,
        font_size=56,
        alignment=8,
        margin_bottom=80,
    )
    project.selection_start_ms, project.selection_end_ms = 500, 1500
    preview = render_fast_preview(project, tmp_path / "preview.mp4")
    exported = export_editor_video(project, tmp_path / "export.mp4")
    bounds = _red_bounds(exported)
    assert bounds and _red_bounds(preview) == pytest.approx(bounds, abs=2)
    assert 0 <= bounds[1] < bounds[3] < 80
    assert not list(tmp_path.rglob("*.ass"))
    project.width, project.height = 320, 180
    ass = EditorProjectStore().save_as_ass(project, tmp_path / "explicit.ass")
    ass_video = tmp_path / "explicit.mp4"
    _ffmpeg(
        "-i",
        source,
        "-vf",
        f"ass='{_escape_filter_path(ass)}':fontsdir='{_escape_filter_path(str(FONTS_PATH))}'",
        "-c:v",
        "libx264",
        "-crf",
        "20",
        ass_video,
    )
    assert _red_bounds(ass_video) == pytest.approx(bounds, abs=2)
    project.track_by_id("track-ts1").visible = False
    hidden = export_editor_video(project, tmp_path / "hidden.mp4")
    assert _red_bounds(hidden) is None
    assert not list(scratch.iterdir())
    assert Path(source).is_file()

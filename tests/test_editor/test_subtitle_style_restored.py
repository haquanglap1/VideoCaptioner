# pyright: reportAttributeAccessIssue=false
"""Regressions for the editor subtitle style: model, ASS burn-in and preview parity."""

import subprocess
import sys
from pathlib import Path

import pytest
from PyQt5.QtGui import QColor, QImage, QPainter
from PyQt5.QtWidgets import QApplication

from videocaptioner.config import FONTS_PATH, TRANSLATIONS_PATH
from videocaptioner.core.editor.commands import CommandStack, EditSubtitleStyleCommand
from videocaptioner.core.editor.media import (
    EDITOR_SUBTITLE_FILE,
    _escape_filter_path,
    _tool_path,
    build_visual_filter_graph,
    write_editor_subtitle,
)
from videocaptioner.core.editor.models import EditorCue, EditorProject
from videocaptioner.core.editor.project_store import EditorProjectStore
from videocaptioner.core.editor.subtitle_style import (
    EditorSubtitleStyle,
    build_editor_ass,
    layout_subtitle,
    libass_size_factor,
    resolve_font_file,
    rounded_rect_drawing,
)
from videocaptioner.core.utils.subprocess_helper import child_environment
from videocaptioner.ui.components.editor.video_preview import EditorOverlay
from videocaptioner.ui.view.video_editor_interface import VideoEditorInterface

FRAME_W, FRAME_H = 1920, 1080


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication(sys.argv)
    yield app


def _project(style: EditorSubtitleStyle | None = None, text: str = "Xin chao cac ban") -> EditorProject:
    project = EditorProject.empty("", 60_000)
    project.width, project.height = FRAME_W, FRAME_H
    project.cues = [EditorCue("cue-a", 0, 2000, "source", text, "tts")]
    project.validate_all_cues()
    # create_from_media scales the default to the real height; mirror that here.
    project.subtitle_style = style or EditorSubtitleStyle.default_for_height(FRAME_H)
    return project


def _boxed_style(**overrides) -> EditorSubtitleStyle:
    base = EditorSubtitleStyle.default_for_height(FRAME_H).to_dict()
    base.update(
        {
            "background": True,
            "bg_color": "#ff0000",
            "bg_opacity": 1.0,
            "primary_color": "#0000ff",
            "outline_width": 0.0,
            "corner_radius": 24,
        }
    )
    base.update(overrides)
    return EditorSubtitleStyle.from_dict(base)


# --------------------------------------------------------------------- model


def test_project_without_a_style_field_keeps_current_plain_reference_defaults():
    payload = _project().to_dict()
    payload.pop("subtitle_style")
    restored = EditorProject.from_dict(payload)
    assert restored.subtitle_style == EditorSubtitleStyle()
    # Missing style follows current defaults, while explicit legacy styles keep pixels.
    assert restored.subtitle_style.font_size == 42


def test_style_survives_a_project_round_trip(tmp_path):
    project = _project(_boxed_style(margin_v=123, align_h="left"))
    project.video_path = str(tmp_path / "clip.mp4")
    Path(project.video_path).write_bytes(b"stub")
    store = EditorProjectStore()
    project_path, _srt = store.save(project, tmp_path / "demo.vceditor.json")
    reloaded = store.load(project_path)
    assert reloaded.subtitle_style == project.subtitle_style


def test_style_edits_go_through_the_command_stack_with_undo_and_redo():
    project = _project()
    stack = CommandStack()
    original = project.subtitle_style
    stack.execute(EditSubtitleStyleCommand(project, {"font_size": 88, "align_v": "top"}))
    assert project.subtitle_style.font_size == 88
    assert project.subtitle_style.align_v == "top"
    assert project.is_dirty
    stack.undo()
    assert project.subtitle_style == original
    stack.redo()
    assert project.subtitle_style.font_size == 88


@pytest.mark.parametrize(
    "changes",
    [{"unknown_field": 1}, {"align_h": "middle"}, {"align_v": "left"}],
)
def test_invalid_style_changes_are_rejected_before_they_mutate_the_project(changes):
    project = _project()
    original = project.subtitle_style
    with pytest.raises(ValueError):
        EditSubtitleStyleCommand(project, changes).execute()
    assert project.subtitle_style == original


def test_libass_size_factor_matches_the_os2_win_metrics_of_the_bundled_font():
    font_file = resolve_font_file("Noto Sans SC")
    assert Path(font_file).parent == Path(FONTS_PATH)
    # Noto Sans SC: unitsPerEm 1000, usWinAscent 1160, usWinDescent 288.
    assert libass_size_factor(font_file) == pytest.approx(1000 / 1448, rel=1e-6)
    style = EditorSubtitleStyle.from_dict({"font_size": 60})
    assert style.ass_font_size == 87  # 60 / 0.69061


# -------------------------------------------------------------------- layout


@pytest.mark.parametrize(
    "align_h,align_v",
    [("center", "bottom"), ("left", "top"), ("right", "middle")],
)
def test_layout_anchors_the_block_to_the_requested_alignment_and_margins(align_h, align_v):
    style = EditorSubtitleStyle.from_dict(
        {"align_h": align_h, "align_v": align_v, "margin_l": 100, "margin_r": 60, "margin_v": 80}
    )
    layout = layout_subtitle("Hello", style, FRAME_W, FRAME_H)
    block_x, block_y, block_w, block_h = layout.block
    if align_h == "left":
        assert block_x == pytest.approx(100)
    elif align_h == "right":
        assert block_x + block_w == pytest.approx(FRAME_W - 60)
    else:
        assert block_x + block_w / 2 == pytest.approx((100 + FRAME_W - 60) / 2)
    if align_v == "top":
        assert block_y == pytest.approx(80)
    elif align_v == "middle":
        assert block_y + block_h / 2 == pytest.approx(FRAME_H / 2)
    else:
        assert block_y + block_h == pytest.approx(FRAME_H - 80)


def test_box_adds_padding_and_outline_around_the_text_block():
    style = EditorSubtitleStyle.from_dict(
        {"reference_height": 0, "layout_mode": "shared", "background": True, "padding_h": 30, "padding_v": 12, "outline_width": 4}
    )
    layout = layout_subtitle("Hello", style, FRAME_W, FRAME_H)
    block_x, block_y, block_w, block_h = layout.block
    box_x, box_y, box_w, box_h = layout.box
    assert box_x == pytest.approx(block_x - 34)
    assert box_y == pytest.approx(block_y - 16)
    assert box_w == pytest.approx(block_w + 68)
    assert box_h == pytest.approx(block_h + 32)


def test_long_text_wraps_inside_the_usable_width_and_keeps_every_word():
    style = EditorSubtitleStyle.default_for_height(FRAME_H)
    text = " ".join(["word"] * 60)
    layout = layout_subtitle(text, style, FRAME_W, FRAME_H)
    assert len(layout.lines) > 1
    assert " ".join(line.text for line in layout.lines) == text
    usable = FRAME_W - style.margin_l - style.margin_r
    assert max(line.width for line in layout.lines) <= usable


def test_rounded_rect_drawing_degrades_to_a_plain_rectangle_without_radius():
    assert rounded_rect_drawing(100, 40, 0) == "m 0 0 l 100 0 l 100 40 l 0 40"
    assert rounded_rect_drawing(100, 40, 12).startswith("m 12 0 ")
    # The radius can never exceed half the shorter side, or the path self-intersects.
    assert rounded_rect_drawing(100, 40, 999).startswith("m 20 0 ")


# ----------------------------------------------------------------------- ASS


def test_ass_positions_every_event_and_only_draws_a_box_when_one_is_enabled():
    plain = build_editor_ass([(0, 1000, "Hello")], EditorSubtitleStyle(), FRAME_W, FRAME_H)
    assert "\\an2\\pos(" in plain and "\\q2" in plain
    assert "\\p1" not in plain
    assert "PlayResX: 1920" in plain and "PlayResY: 1080" in plain

    boxed = build_editor_ass([(0, 1000, "Hello")], _boxed_style(), FRAME_W, FRAME_H)
    assert "Dialogue: 0," in boxed and "\\p1}m " in boxed
    assert boxed.index("Dialogue: 0,") < boxed.index("Dialogue: 1,")  # box under the text


def test_ass_escapes_braces_and_joins_wrapped_lines_with_a_hard_break():
    content = build_editor_ass(
        [(0, 1000, "a {tag} b\nsecond")], EditorSubtitleStyle(), FRAME_W, FRAME_H
    )
    text_line = [line for line in content.splitlines() if line.startswith("Dialogue: 1,")][0]
    assert "a \\{tag\\} b\\Nsecond" in text_line


def test_alignment_maps_onto_the_numpad_ass_codes():
    codes = {
        ("bottom", "center"): 2,
        ("top", "left"): 7,
        ("middle", "right"): 6,
    }
    for (align_v, align_h), expected in codes.items():
        style = EditorSubtitleStyle.from_dict({"align_v": align_v, "align_h": align_h})
        assert style.ass_alignment == expected


def test_filter_graph_burns_the_generated_ass_with_a_pinned_fonts_dir(tmp_path):
    project = _project()
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    write_editor_subtitle(project, run_dir, 0, 2000)
    assert (run_dir / EDITOR_SUBTITLE_FILE).is_file()
    _extra, graph, _label = build_visual_filter_graph(project, run_dir)
    assert _escape_filter_path(str(run_dir / EDITOR_SUBTITLE_FILE)) in graph
    assert f"fontsdir='{_escape_filter_path(str(FONTS_PATH))}'" in graph


def test_written_ass_is_shifted_into_the_rendered_range(tmp_path):
    project = _project()
    project.cues = [
        EditorCue("cue-a", 0, 1000, "s", "first", "t"),
        EditorCue("cue-b", 5000, 6000, "s", "second", "t"),
    ]
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    content = write_editor_subtitle(project, run_dir, 4000, 7000).read_text(encoding="utf-8")
    assert "first" not in content
    assert "0:00:01.00,0:00:02.00" in content  # cue-b rebased to the clip clock


def test_save_as_ass_uses_the_project_style_and_normal_save_stays_srt_only(tmp_path):
    project = _project(_boxed_style())
    project.video_path = str(tmp_path / "clip.mp4")
    Path(project.video_path).write_bytes(b"stub")
    store = EditorProjectStore()
    project_path, srt_path = store.save(project, tmp_path / "demo.vceditor.json")
    assert Path(srt_path).suffix == ".srt"
    assert not list(Path(project_path).parent.glob("*.ass"))
    ass_path = store.save_as_ass(project, tmp_path / "demo.ass")
    content = Path(ass_path).read_text(encoding="utf-8")
    # Explicit export now preserves the same rounded shape as preview/export.
    assert "\\p1" in content and "Dialogue: 0," in content
    assert "PlayResY: 1080" in content


# ------------------------------------------------------- burn-in / preview parity


def _flat_render(tmp_path: Path, project: EditorProject, text: str) -> Path:
    run_dir = tmp_path / "run"
    run_dir.mkdir(exist_ok=True)
    write_editor_subtitle(project, run_dir, 0, 2000)
    frame = tmp_path / "frame.png"
    subprocess.run(
        [
            _tool_path("ffmpeg"), "-v", "error", "-y",
            "-f", "lavfi", "-i", f"color=c=green:s={FRAME_W}x{FRAME_H}:d=1",
            "-vf", (
                f"subtitles='{_escape_filter_path(str(run_dir / EDITOR_SUBTITLE_FILE))}'"
                f":fontsdir='{_escape_filter_path(str(FONTS_PATH))}'"
            ),
            "-frames:v", "1", str(frame),
        ],
        check=True,
        capture_output=True,
        env=child_environment(),
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    assert frame.is_file()
    return frame


def _ink_bounds(width: int, height: int, matches) -> tuple[int, int, int, int]:
    left, top, right, bottom = width, height, -1, -1
    for y in range(height):
        for x in range(width):
            if matches(x, y):
                left, top = min(left, x), min(top, y)
                right, bottom = max(right, x), max(bottom, y)
    return left, top, right, bottom


def test_real_ffmpeg_burns_the_box_where_the_shared_layout_says(tmp_path):
    """The layout drives both renderers, so libass must land on the same pixels."""
    from PIL import Image

    text = "Xin chao cac ban, day la phu de dai de kiem tra xuong dong tu dong"
    style = _boxed_style()
    project = _project(style, text)
    frame = _flat_render(tmp_path, project, text)
    image = Image.open(frame).convert("RGB")
    pixels = image.load()

    def is_box(x, y):
        r, g, b = pixels[x, y]
        return r > 150 and g < 100 and b < 100

    left, top, right, bottom = _ink_bounds(FRAME_W, FRAME_H, is_box)
    box_x, box_y, box_w, box_h = layout_subtitle(text, style, FRAME_W, FRAME_H).box
    assert left == pytest.approx(box_x, abs=4)
    assert top == pytest.approx(box_y, abs=4)
    assert right == pytest.approx(box_x + box_w, abs=4)
    assert bottom == pytest.approx(box_y + box_h, abs=4)

    def is_text(x, y):
        r, g, b = pixels[x, y]
        return b > 150 and r < 100 and g < 100

    text_left, text_top, text_right, text_bottom = _ink_bounds(FRAME_W, FRAME_H, is_text)
    # Glyph ink sits inside the box with at least the configured padding around it.
    assert text_left - left >= style.padding_h - 4
    assert right - text_right >= style.padding_h - 4
    assert text_top - top >= 0 and bottom - text_bottom >= 0


def test_preview_overlay_paints_the_same_box_as_the_burn_in(qapp):
    """EditorOverlay used to hardcode width//24 and 0.70 height and drew no box."""
    text = "Xin chao cac ban"
    style = _boxed_style()
    project = _project(style, text)
    overlay = EditorOverlay()
    overlay.resize(960, 540)  # exactly half the frame: scale is 0.5 in both axes
    overlay.set_state(project, 500)

    image = QImage(overlay.size(), QImage.Format_ARGB32)
    image.fill(QColor("green"))
    painter = QPainter(image)
    overlay.render(painter)
    painter.end()

    def is_box(x, y):
        color = QColor(image.pixel(x, y))
        return color.red() > 150 and color.green() < 100 and color.blue() < 100

    left, top, right, bottom = _ink_bounds(image.width(), image.height(), is_box)
    box_x, box_y, box_w, box_h = layout_subtitle(text, style, FRAME_W, FRAME_H).box
    assert left == pytest.approx(box_x / 2, abs=3)
    assert top == pytest.approx(box_y / 2, abs=3)
    assert right == pytest.approx((box_x + box_w) / 2, abs=3)
    assert bottom == pytest.approx((box_y + box_h) / 2, abs=3)


def test_overlay_skips_the_subtitle_when_the_ts1_track_is_hidden(qapp):
    project = _project(_boxed_style())
    project.track_by_id("track-ts1").visible = False
    overlay = EditorOverlay()
    overlay.resize(960, 540)
    overlay.set_state(project, 500)
    image = QImage(overlay.size(), QImage.Format_ARGB32)
    image.fill(QColor("green"))
    painter = QPainter(image)
    overlay.render(painter)
    painter.end()
    assert all(
        QColor(image.pixel(x, y)).red() < 150
        for y in range(0, 540, 7)
        for x in range(0, 960, 7)
    )


# ------------------------------------------------------------------------ UI


def test_style_panel_apply_routes_through_the_command_stack(qapp):
    page = VideoEditorInterface()
    try:
        project = _project()
        page.project = project
        page._set_actions_enabled(True)
        page.subtitle_style_panel.set_style(project.subtitle_style)
        page.subtitle_style_panel.font_size_spin.setValue(72)
        page.subtitle_style_panel.background_check.setChecked(True)
        page.subtitle_style_panel.corner_radius_spin.setValue(30)
        page.subtitle_style_panel.apply_button.click()
        assert project.subtitle_style.font_size == 72
        assert project.subtitle_style.background is True
        assert project.subtitle_style.corner_radius == 30
        assert page.command_stack.can_undo
        page.undo()
        assert project.subtitle_style.font_size == 63
    finally:
        page.close()


def test_context_tab_bar_fits_the_narrow_panel_with_vietnamese_labels(qapp):
    """A third tab was only safe once the tab metrics fit 700 px; verify in Vietnamese."""
    from videocaptioner.ui.common.json_translator import JsonTranslator

    translator = JsonTranslator(Path(TRANSLATIONS_PATH) / "VideoCaptioner_vi_VN.json")
    qapp.installTranslator(translator)
    try:
        page = VideoEditorInterface()
        page.resize(700, 800)
        page.show()
        qapp.processEvents()
        assert page.context_tabs.count() == 3
        assert page.context_tabs.tabText(2) == "Kiểu phụ đề"
        tab_bar = page.context_tabs.tabBar()
        assert tab_bar.sizeHint().width() <= page.context_tabs.width()
        page.close()
    finally:
        qapp.removeTranslator(translator)

# pyright: reportAttributeAccessIssue=false

from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace

import pytest
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QImage
from PyQt5.QtWidgets import QApplication

from videocaptioner.core.editor.models import EditorCue, EditorProject
from videocaptioner.core.editor.subtitle_style import EditorSubtitleStyle
from videocaptioner.ui.components.editor.video_preview import EditorOverlay
from videocaptioner.ui.view.video_editor_interface import VideoEditorInterface


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def page(qapp, monkeypatch):
    page = VideoEditorInterface()
    monkeypatch.setattr(page, "_start_media", lambda *_args, **_kwargs: None)
    project = EditorProject.empty("", 5000)
    project.cues = [EditorCue("cue", 0, 2000, "source", "Subtitle", "tts")]
    page._accept_project(project)
    yield page
    page.close()


def test_panel_apply_reset_undo_and_noop_are_project_local(page):
    panel = page.subtitle_style_panel
    original = page.project.subtitle_style
    panel.font_combo.setEditText("Unavailable Font Family")
    panel.font_size_spin.setValue(64)
    panel.primary_color_edit.setText("#ff0000")
    panel.alignment_combo.setCurrentIndex(panel.alignment_combo.findData(8))
    assert page.project.subtitle_style == original
    panel.apply_button.click()
    changed = page.project.subtitle_style
    assert changed.font_name == "Unavailable Font Family"
    assert changed.font_size == 64 and changed.alignment == 8
    panel.apply_button.click()  # Identical Apply must not create an extra undo step.
    page.undo()
    assert page.project.subtitle_style == original
    assert panel.font_size_spin.value() == original.font_size
    page.redo()
    assert page.project.subtitle_style == changed
    panel.reset_button.click()
    assert page.project.subtitle_style == EditorSubtitleStyle()
    page.undo()
    assert page.project.subtitle_style == changed


def test_invalid_panel_input_leaves_model_and_undo_history_untouched(page, monkeypatch):
    errors = []
    monkeypatch.setattr(page, "_show_error", errors.append)
    original = page.project.to_dict()
    page.subtitle_style_panel.primary_color_edit.setText("invalid")
    page.subtitle_style_panel.apply_button.click()
    assert errors and "#RRGGBB" in errors[0]
    assert page.project.to_dict() == original
    assert not page.command_stack.can_undo


def test_style_tab_delete_shortcut_does_not_remove_selected_cue(page):
    page.context_tabs.setCurrentWidget(page.subtitle_style_panel)
    page._delete_selection()
    assert len(page.project.cues) == 1
    assert not page.command_stack.can_undo


def _red_bounds(overlay):
    image = QImage(overlay.size(), QImage.Format_ARGB32)
    image.fill(Qt.transparent)
    overlay.render(image)
    points = [
        (x, y)
        for y in range(image.height())
        for x in range(image.width())
        if image.pixelColor(x, y).red() > 150
        and image.pixelColor(x, y).green() < 80
        and image.pixelColor(x, y).alpha() > 150
    ]
    assert points
    return (
        min(x for x, _ in points),
        min(y for _, y in points),
        max(x for x, _ in points),
        max(y for _, y in points),
    )


def test_overlay_uses_style_alignment_size_color_and_letterboxed_frame(qapp):
    project = EditorProject.empty("", 2000)
    project.width, project.height = 1280, 720
    project.cues = [EditorCue("cue", 0, 1000, "source", "Subtitle", "tts")]
    project.subtitle_style = EditorSubtitleStyle(primary_color="#ff0000", alignment=8, font_size=60)
    overlay = EditorOverlay()
    overlay.resize(640, 480)  # Actual video is y=60..420.
    overlay.set_state(project, 500)
    overlay.show()
    qapp.processEvents()
    top = _red_bounds(overlay)
    assert 60 <= top[1] < top[3] < 180
    project.subtitle_style = replace(project.subtitle_style, alignment=2, font_size=100)
    bottom = _red_bounds(overlay)
    assert 300 < bottom[1] < bottom[3] < 420
    assert bottom[2] - bottom[0] > top[2] - top[0]
    project.track_by_id("track-ts1").visible = False
    image = QImage(overlay.size(), QImage.Format_ARGB32)
    image.fill(Qt.transparent)
    overlay.render(image)
    assert all(
        image.pixelColor(x, y).alpha() == 0
        for y in range(image.height())
        for x in range(image.width())
    )
    overlay.close()


def test_rendered_preview_hides_overlay_and_style_edit_restores_it(page, monkeypatch):
    monkeypatch.setattr(page.preview.player, "setMedia", lambda *_: None)
    monkeypatch.setattr(page.preview.player, "play", lambda: None)
    page.preview.play_rendered_preview("preview.mp4", 0)
    assert page.preview.surface.overlay.isHidden()
    page.subtitle_style_panel.font_size_spin.setValue(55)
    page.subtitle_style_panel.apply_button.click()
    assert not page.preview.is_rendered_preview
    assert not page.preview.surface.overlay.isHidden()


def test_style_panel_loads_another_project_without_dirtying_it(page):
    other = EditorProject.empty("", 1000)
    other.subtitle_style = EditorSubtitleStyle(font_name="Another Missing Font", font_size=70)
    page._accept_project(other)
    assert page.subtitle_style_panel.font_combo.currentText() == "Another Missing Font"
    assert page.subtitle_style_panel.font_size_spin.value() == 70
    assert not other.is_dirty and not page.command_stack.can_undo


def test_style_change_cancels_pending_preview_and_discards_its_result(page, monkeypatch):
    cancelled, played = [], []
    page._render_thread = SimpleNamespace(
        action="preview",
        project=deepcopy(page.project),
        cancel=lambda: cancelled.append(True),
        isRunning=lambda: True,
    )
    page._signatures["preview"] = "old-style"
    monkeypatch.setattr(page.preview, "play_rendered_preview", lambda *args: played.append(args))
    try:
        page.subtitle_style_panel.font_size_spin.setValue(66)
        page.subtitle_style_panel.apply_button.click()
        assert cancelled
        page._on_render_completed("preview", "old-style", "stale.mp4")
        assert not played
    finally:
        page._render_thread = None

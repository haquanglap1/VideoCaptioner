# pyright: reportAttributeAccessIssue=false
"""Regressions for FX1 visual layers, render cancellation and preview isolation."""

import shutil
import sys
from pathlib import Path

import pytest
from PyQt5.QtGui import QColor, QPixmap
from PyQt5.QtWidgets import QApplication

from videocaptioner.core.editor.commands import AddLayerCommand, CommandStack
from videocaptioner.core.editor.media import (
    EditorRenderCancelled,
    _run,
    _tool_path,
    build_visual_filter_graph,
    cleanup_preview_files,
    editor_font_file,
)
from videocaptioner.core.editor.models import (
    EditorCue,
    EditorLayer,
    EditorLayerKind,
    EditorProject,
)
from videocaptioner.core.editor.project_store import EditorProjectStore
from videocaptioner.ui.thread.editor_media_thread import EditorRenderThread
from videocaptioner.ui.view.video_editor_interface import VideoEditorInterface


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication(sys.argv)
    yield app


def _project(duration_ms: int = 60_000) -> EditorProject:
    project = EditorProject.empty("", duration_ms)
    project.width, project.height = 1920, 1080
    project.cues = [
        EditorCue("cue-a", 0, 1000, "source", "display", "tts"),
        EditorCue("cue-b", 2000, 3000, "source 2", "display 2", "tts 2"),
    ]
    project.validate_all_cues()
    return project


def _graph(project: EditorProject, run_dir: Path, **kwargs) -> str:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "display.srt").write_text("", encoding="utf-8")
    return build_visual_filter_graph(project, run_dir, **kwargs)[1]


# --------------------------------------------------------------- filter graph


def test_text_layer_pins_a_bundled_font_and_centres_inside_its_box(tmp_path):
    project = _project()
    project.layers = [
        EditorLayer(
            "text-1",
            EditorLayerKind.TEXT,
            0,
            1000,
            x=0.1,
            y=0.2,
            width=0.4,
            height=0.3,
            properties={"text": "Xin chào", "font_size": 40},
        )
    ]
    graph = _graph(project, tmp_path / "run")
    assert f"fontfile='{editor_font_file()}'".replace("\\", "/").replace(":", r"\:") in graph
    assert "x='(w*0.100000)+(w*0.400000-text_w)/2'" in graph
    assert "y='(h*0.200000)+(h*0.300000-text_h)/2'" in graph


def test_logo_width_uses_the_real_frame_width_instead_of_a_1920_guess(tmp_path):
    from PIL import Image

    project = _project()
    project.width, project.height = 0, 0
    logo = tmp_path / "logo.png"
    Image.new("RGBA", (8, 4), (255, 0, 0, 255)).save(logo)
    project.layers = [
        EditorLayer("logo-1", EditorLayerKind.LOGO, 0, 1000, width=0.5, properties={"path": str(logo)})
    ]
    graph = _graph(project, tmp_path / "run", frame_width=640, frame_height=360)
    assert "scale=320:-1" in graph


def test_blur_radius_is_clamped_to_the_region_and_opacity_reaches_the_export(tmp_path):
    project = _project()
    project.layers = [
        EditorLayer(
            "blur-1",
            EditorLayerKind.BLUR,
            0,
            1000,
            width=0.02,
            height=0.02,
            opacity=0.5,
            properties={"strength": 50},
        )
    ]
    graph = _graph(project, tmp_path / "run")
    # 1080 * 0.02 = 21 px tall and 4:2:0 chroma halves that again, so radius 50 is impossible.
    assert "boxblur=4:1" in graph
    assert "colorchannelmixer=aa=0.500" in graph


def test_layer_box_is_clamped_so_crop_never_runs_past_the_frame(tmp_path):
    project = _project()
    project.layers = [
        EditorLayer("mask-1", EditorLayerKind.MASK, 0, 1000, x=0.8, width=0.9, properties={"mode": "solid"})
    ]
    graph = _graph(project, tmp_path / "run")
    assert "x='iw*0.800000'" in graph and "w='iw*0.200000'" in graph


def test_hiding_the_fx1_track_removes_every_visual_layer_from_the_graph(tmp_path):
    project = _project()
    project.layers = [
        EditorLayer("mask-1", EditorLayerKind.MASK, 0, 1000, properties={"mode": "solid"})
    ]
    project.track_by_id("track-fx1").visible = False
    graph = _graph(project, tmp_path / "run")
    assert "drawbox" not in graph


# --------------------------------------------------------------- cancellation


def test_running_ffmpeg_stops_when_the_caller_cancels():
    if not shutil.which("ffmpeg"):
        pytest.skip("FFmpeg is required")
    command = [
        _tool_path("ffmpeg"), "-v", "error",
        "-f", "lavfi", "-i", "testsrc2=s=640x360:r=30:d=600",
        "-f", "null", "-",
    ]
    with pytest.raises(EditorRenderCancelled):
        _run(command, timeout=60, should_cancel=lambda: True)


def test_render_thread_exposes_cancel_to_the_ui_thread(qapp, tmp_path):
    thread = EditorRenderThread("sig", "preview", _project(), str(tmp_path / "out.mp4"))
    assert thread._should_cancel() is False
    thread.cancel()
    assert thread._should_cancel() is True


def test_cleanup_preview_files_keeps_only_the_active_render(tmp_path):
    keep = tmp_path / "preview-new.mp4"
    for name in ("preview-old-1.mp4", "preview-old-2.mp4"):
        (tmp_path / name).write_bytes(b"x")
    keep.write_bytes(b"x")
    assert cleanup_preview_files(tmp_path, keep=str(keep)) == 2
    assert keep.is_file()
    assert list(tmp_path.glob("preview-*.mp4")) == [keep]


# --------------------------------------------------------------- persistence


def test_offdrive_layer_asset_keeps_the_project_saveable(tmp_path, monkeypatch):
    from PIL import Image

    project = _project()
    logo = tmp_path / "logo.png"
    Image.new("RGBA", (8, 4), (255, 0, 0, 255)).save(logo)
    project.video_path = str(tmp_path / "input.mp4")
    project.layers = [
        EditorLayer("logo-1", EditorLayerKind.LOGO, 0, 1000, properties={"path": str(logo)})
    ]
    real_relpath = EditorProjectStore._relative_path

    def fake_relpath(path, base_dir, *, required=True):
        if path and Path(path).name == "logo.png":
            if required:
                raise ValueError("cross drive")
            return Path(path).resolve().as_posix()
        return real_relpath(path, base_dir, required=required)

    monkeypatch.setattr(EditorProjectStore, "_relative_path", staticmethod(fake_relpath))
    project_file, _srt = EditorProjectStore().save(project, tmp_path / "project.vceditor.json")
    reopened = EditorProjectStore().load(project_file)
    assert Path(reopened.layer_by_id("logo-1").properties["path"]) == logo.resolve()


# --------------------------------------------------------------- UI wiring


def test_rendered_preview_position_maps_back_to_the_project_timeline(qapp):
    page = VideoEditorInterface()
    project = _project()
    page._accept_project(project)
    page.preview._rendered_offset_ms = 30_000
    page.preview._on_position_changed(1500)
    assert project.playhead_ms == 31_500
    assert page.timeline.playhead_ms == 31_500
    page.preview.exit_rendered_preview(resume_ms=31_500)
    assert page.preview.is_rendered_preview is False
    assert project.playhead_ms == 31_500
    page.close()


def test_late_thumbnail_does_not_hide_a_surface_that_already_played(qapp, tmp_path):
    page = VideoEditorInterface()
    poster = tmp_path / "poster.png"
    pixmap = QPixmap(320, 180)
    pixmap.fill(QColor("#234567"))
    assert pixmap.save(str(poster))
    page.preview._playback_started = True
    page.preview.set_poster(str(poster))
    current = page.preview.surface.placeholder.pixmap()
    assert current is None or current.isNull()
    page.close()


def test_layer_selection_survives_an_edit_and_keeps_the_buttons_live(qapp):
    page = VideoEditorInterface()
    project = _project()
    page._accept_project(project)
    layer = EditorLayer("layer-1", EditorLayerKind.MASK, 0, 2000, name="Mask", properties={"mode": "solid"})
    page.command_stack.execute(AddLayerCommand(project, layer))
    page.select_layer("layer-1")
    assert page.layer_inspector.layer_id == "layer-1"

    page.layer_inspector.x_spin.setValue(10.0)
    page.layer_inspector._emit_apply()
    assert project.layer_by_id("layer-1").x == pytest.approx(0.1)
    assert page._selected_layer() is not None
    assert page.layer_inspector.layer_id == "layer-1"
    assert page.layer_inspector.apply_button.isEnabled()
    assert page.layer_inspector.delete_button.isEnabled()

    page.command_stack.undo()
    assert project.layer_by_id("layer-1").x == pytest.approx(0.25)
    page.close()


def test_layer_timeline_drag_moves_the_layer_through_the_command_stack(qapp):
    page = VideoEditorInterface()
    project = _project()
    page._accept_project(project)
    layer = EditorLayer("layer-1", EditorLayerKind.BLUR, 1000, 3000, properties={"strength": 6})
    page.command_stack.execute(AddLayerCommand(project, layer))
    page._apply_layer_timeline_timing("layer-1", 4000, 6000, "move")
    assert (project.layer_by_id("layer-1").start_ms, project.layer_by_id("layer-1").end_ms) == (4000, 6000)
    page.command_stack.undo()
    assert (project.layer_by_id("layer-1").start_ms, project.layer_by_id("layer-1").end_ms) == (1000, 3000)
    page.close()


def test_opening_a_saved_project_keeps_saving_to_the_same_file(qapp, tmp_path):
    page = VideoEditorInterface()
    project_path = str(tmp_path / "project.vceditor.json")
    page._signatures["load-project"] = "sig"
    page._pending_project_path = project_path
    page._on_media_completed("load-project", "sig", _project())
    assert page.project_path == project_path
    page.close()


def test_visible_toggle_reaches_the_track_state_command(qapp):
    page = VideoEditorInterface()
    project = _project()
    page._accept_project(project)
    page._apply_track_state("track-fx1", "visible", False)
    assert project.track_by_id("track-fx1").visible is False
    page.command_stack.undo()
    assert project.track_by_id("track-fx1").visible is True
    page.close()


def test_dirty_flag_guards_are_wired_to_the_model(qapp):
    page = VideoEditorInterface()
    assert page._confirm_discard_changes() is True  # nothing open yet
    project = _project()
    page._accept_project(project)
    assert project.is_dirty is False
    assert page._confirm_discard_changes() is True
    stack = CommandStack()
    stack.execute(
        AddLayerCommand(project, EditorLayer("layer-x", EditorLayerKind.BLUR, 0, 1000))
    )
    assert project.is_dirty is True
    page.close()


def test_real_ffmpeg_accepts_translucent_blur_and_vietnamese_text(tmp_path):
    """The clamped/alpha filter chain has to survive a real FFmpeg run, not just a string check."""
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        pytest.skip("FFmpeg/ffprobe are required")
    from videocaptioner.core.editor.media import export_editor_video, probe_media

    video = tmp_path / "input.mp4"
    result = _ffmpeg_sample(video)
    assert result == 0
    subtitle = tmp_path / "input.srt"
    subtitle.write_text("1\n00:00:00,000 --> 00:00:01,000\nXin chào\n", encoding="utf-8")
    project = EditorProjectStore().create_from_media(
        str(video), str(subtitle), duration_ms=probe_media(video).duration_ms
    )
    project.width, project.height = 320, 180
    project.layers = [
        EditorLayer(
            "blur-1",
            EditorLayerKind.BLUR,
            0,
            1000,
            x=0.6,
            y=0.6,
            width=0.9,
            height=0.9,
            opacity=0.5,
            properties={"strength": 40},
        ),
        EditorLayer(
            "text-1",
            EditorLayerKind.TEXT,
            0,
            1000,
            properties={"text": "Tiếng Việt", "font_size": 20},
        ),
    ]
    output = Path(export_editor_video(project, tmp_path / "layers.mp4"))
    assert output.is_file() and output.stat().st_size > 0


def _ffmpeg_sample(video: Path) -> int:
    import subprocess

    return subprocess.run(
        [
            "ffmpeg", "-v", "error",
            "-f", "lavfi", "-i", "testsrc2=s=320x180:r=24:d=2",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-y", str(video),
        ],
        capture_output=True,
    ).returncode


def test_exit_rendered_preview_reloads_the_source_and_defers_the_seek(qapp):
    """Seeking immediately after setMedia made the packaged player report a failure."""
    from PyQt5.QtMultimedia import QMediaPlayer

    page = VideoEditorInterface()
    project = _project()
    page._accept_project(project)
    preview = page.preview
    preview._rendered_offset_ms = 0
    preview._playback_started = True

    preview.exit_rendered_preview(resume_ms=5_000)
    assert preview.is_rendered_preview is False
    assert preview._pending_seek_ms == 5_000  # not applied until the backend is ready
    assert project.playhead_ms == 5_000
    assert page.preview.slider.maximum() == project.duration_ms

    preview._on_media_status(QMediaPlayer.LoadedMedia)
    assert preview._pending_seek_ms is None
    page.close()


def test_status_label_stops_saying_loading_once_workers_finish(qapp):
    page = VideoEditorInterface()
    project = _project()
    page._accept_project(project)
    page._pending_media.clear()
    page.status_label.setText("Loading editor media...")
    page._restore_project_status()
    assert "Loading editor media" not in page.status_label.text()
    assert str(len(project.cues)) in page.status_label.text()
    page.close()

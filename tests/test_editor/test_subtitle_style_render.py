import shutil
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest
from PIL import Image

from videocaptioner.core.editor.media import export_editor_video, render_fast_preview
from videocaptioner.core.editor.models import EditorCue, EditorProject
from videocaptioner.core.editor.project_store import EditorProjectStore
from videocaptioner.core.editor.subtitle_style import EditorSubtitleStyle
from videocaptioner.core.utils.subprocess_helper import child_environment


def _ffmpeg(*args):
    result = subprocess.run(
        ["ffmpeg", "-v", "error", *map(str, args)],
        capture_output=True,
        env=child_environment(),
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    assert result.returncode == 0, result.stderr.decode(errors="replace")
    return result.stdout


def _red_bounds(path):
    raw = _ffmpeg("-i", path, "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1")
    image = Image.frombytes("RGB", (320, 180), raw)
    mask = Image.new("L", image.size)
    mask.putdata(
        [
            255 if red > 140 and green < 90 and blue < 90 else 0
            for red, green, blue in image.getdata()
        ]
    )
    return mask.getbbox()


def test_real_preview_export_and_reopened_project_render_the_same_style(tmp_path, monkeypatch):
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
    # Leave dimensions unset: render must probe before computing style coordinates.
    project.cues = [EditorCue("cue", 0, 2000, "source", "Subtitle", "tts")]
    project.subtitle_style = EditorSubtitleStyle(
        font_size=72,
        primary_color="#ff0000",
        alignment=8,
        margin_bottom=60,
    )
    project.selection_start_ms, project.selection_end_ms = 500, 1500
    project_file, _ = EditorProjectStore().save(project, tmp_path / "style.vceditor.json")
    loaded = EditorProjectStore().load(project_file)
    preview = render_fast_preview(loaded, tmp_path / "preview.mp4")
    exported = export_editor_video(loaded, tmp_path / "export.mp4")
    preview_bounds, export_bounds = _red_bounds(preview), _red_bounds(exported)
    assert preview_bounds and export_bounds
    assert preview_bounds == pytest.approx(export_bounds, abs=2)
    assert 10 <= export_bounds[1] < export_bounds[3] < 60
    assert 30 < export_bounds[2] - export_bounds[0] < 150

    loaded.subtitle_style = replace(loaded.subtitle_style, alignment=2, font_size=100)
    bottom = export_editor_video(loaded, tmp_path / "bottom.mp4")
    bottom_bounds = _red_bounds(bottom)
    assert bottom_bounds and bottom_bounds[1] > 110
    assert bottom_bounds[2] - bottom_bounds[0] > export_bounds[2] - export_bounds[0]

    loaded.track_by_id("track-ts1").visible = False
    hidden = export_editor_video(loaded, tmp_path / "hidden.mp4")
    assert _red_bounds(hidden) is None
    assert not list(tmp_path.rglob("*.ass"))
    loaded.track_by_id("track-ts1").visible = True
    loaded.width, loaded.height = 320, 180
    ass_path = EditorProjectStore().save_as_ass(loaded, tmp_path / "explicit.ass")
    # Save as ASS must produce the same geometry as SRT + libass overrides.
    from videocaptioner.config import FONTS_PATH
    from videocaptioner.core.editor.media import _escape_filter_path

    ass_video = tmp_path / "ass.mp4"
    _ffmpeg(
        "-i",
        source,
        "-vf",
        f"ass='{_escape_filter_path(ass_path)}':fontsdir='{_escape_filter_path(str(FONTS_PATH))}'",
        "-c:v",
        "libx264",
        "-crf",
        "20",
        ass_video,
    )
    assert _red_bounds(ass_video) == pytest.approx(bottom_bounds, abs=2)
    assert not list(scratch.iterdir())
    assert Path(project_file).is_file()

# pyright: reportAttributeAccessIssue=false

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest
from PyQt5.QtCore import QUrl
from PyQt5.QtGui import QColor, QPainter, QPalette, QPixmap
from PyQt5.QtMultimedia import QMediaContent, QMediaPlayer
from PyQt5.QtMultimediaWidgets import QVideoWidget
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QApplication

from videocaptioner.core.editor.models import EditorCue, EditorProject
from videocaptioner.ui.components.editor.timeline_view import EditorTimelineView
from videocaptioner.ui.view.video_editor_interface import VideoEditorInterface


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication(sys.argv)
    yield app


def long_project() -> EditorProject:
    project = EditorProject.empty("", 60 * 60 * 1000)
    project.cues = [
        EditorCue(
            f"cue-{index:04d}",
            index * 3600,
            index * 3600 + 1800,
            f"source {index}",
            f"display {index}",
            f"tts {index}",
        )
        for index in range(1000)
    ]
    project.validate_all_cues()
    return project


def test_timeline_paints_only_visible_cues_for_60_minute_1000_cue_project(qapp):
    timeline = EditorTimelineView()
    timeline.resize(900, 230)
    timeline.set_project(long_project())
    timeline.show()
    qapp.processEvents()
    timeline.horizontalScrollBar().setValue(timeline.horizontalScrollBar().maximum() // 2)
    image = QPixmap(timeline.size())
    started = time.perf_counter()
    painter = QPainter(image)
    try:
        for _ in range(30):
            timeline.render(painter)
    finally:
        painter.end()
    elapsed_ms = (time.perf_counter() - started) * 1000
    assert timeline.last_painted_cue_count < 10
    assert elapsed_ms < 1000
    timeline.close()


def test_preview_timeline_inspector_and_overlay_share_selection_and_playhead(qapp):
    page = VideoEditorInterface()
    project = EditorProject.empty("", 5000)
    project.cues = [
        EditorCue("cue-a", 0, 1000, "source", "display", "tts"),
        EditorCue("cue-b", 1500, 2500, "source 2", "display 2", "tts 2"),
    ]
    page._accept_project(project)
    page.preview.set_position(1600)
    qapp.processEvents()
    assert project.playhead_ms == 1600
    assert page.timeline.playhead_ms == 1600
    assert page.inspector.cue_id == "cue-b"
    assert project.active_cue_at(1600).display_text == "display 2"
    page.close()


def test_stale_media_result_is_discarded(qapp):
    page = VideoEditorInterface()
    page._signatures["waveform"] = "new"
    page.timeline.set_waveform([0.1], 1.0)
    page._on_media_completed("waveform", "old", ("fingerprint", [0.9], 9.0))
    assert page.timeline.waveform == [0.1]
    assert page.timeline.waveform_duration_s == 1.0
    page.close()


def test_editor_layout_remains_usable_at_700_pixel_page_width(qapp):
    page = VideoEditorInterface()
    project = EditorProject.empty("", 10_000)
    project.cues = [EditorCue("cue-a", 0, 1000, "source", "display", "tts")]
    project.validate_all_cues()
    page.project = project
    page.preview.set_project(project)
    page.timeline.set_project(project)
    page.track_header.set_project(project)
    page._set_actions_enabled(True)
    page.resize(700, 800)
    page.show()
    qapp.processEvents()
    assert page.width() == 700
    assert page.minimumSizeHint().width() <= 700
    assert page.preview.width() >= 320
    assert page.context_tabs.width() >= 290
    assert page.timeline.width() >= 300
    assert page.command_scroll.geometry().bottom() < page.vertical_splitter.geometry().top()
    page.close()


def test_editor_empty_state_uses_dark_native_and_context_surfaces(qapp):
    page = VideoEditorInterface()
    page.resize(1050, 800)
    page.show()
    qapp.processEvents()
    video_background = page.preview.surface.video.palette().color(QPalette.Window)
    assert video_background == QColor("#05080d")
    assert page.preview.surface.placeholder.isVisible()
    assert page.preview.surface.video.isHidden()
    assert page.command_scroll.height() >= 48
    assert "background: #08111f" in page.styleSheet()
    assert page.context_tabs.objectName() == "EditorContextTabs"
    assert page.inspector.widget().objectName() == "EditorInspectorContent"
    page.close()


def test_editor_preview_uses_poster_until_playback_starts(qapp, tmp_path):
    page = VideoEditorInterface()
    poster_path = tmp_path / "poster.png"
    poster = QPixmap(320, 180)
    poster.fill(QColor("#234567"))
    assert poster.save(str(poster_path))
    page.preview.set_poster(str(poster_path))
    assert page.preview.surface.video.isHidden()
    assert not page.preview.surface.placeholder.isHidden()
    assert not page.preview.surface.placeholder.pixmap().isNull()
    page.preview.surface.show_video()
    assert not page.preview.surface.video.isHidden()
    assert page.preview.surface.placeholder.isHidden()
    page.close()


def test_qtmultimedia_h264_preview_plays_and_seeks(qapp, tmp_path):
    if not shutil.which("ffmpeg"):
        pytest.skip("FFmpeg is required")
    if os.environ.get("QT_QPA_PLATFORM") == "offscreen":
        # Headless CI has no usable audio/video sink; the gstreamer backend can
        # abort the whole pytest process there. This test targets real backends.
        pytest.skip("QtMultimedia playback needs a real platform backend")
    video = Path(tmp_path) / "qt-preview.mp4"
    result = subprocess.run(
        [
            "ffmpeg", "-v", "error", "-f", "lavfi", "-i",
            "testsrc2=s=320x180:r=24:d=3", "-f", "lavfi", "-i",
            "sine=frequency=440:sample_rate=24000:duration=3", "-map", "0:v:0",
            "-map", "1:a:0", "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-shortest", "-movflags", "+faststart", "-y", str(video),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    player = QMediaPlayer(None, QMediaPlayer.VideoSurface)
    surface = QVideoWidget()
    surface.resize(320, 180)
    surface.show()
    player.setVideoOutput(surface)
    player.setVolume(0)
    player.setMedia(QMediaContent(QUrl.fromLocalFile(str(video))))
    player.play()
    deadline = time.monotonic() + 8.0
    while time.monotonic() < deadline and player.position() < 150:
        qapp.processEvents()
        QTest.qWait(25)
    assert player.error() == QMediaPlayer.NoError, player.errorString()
    assert player.position() >= 150
    player.setPosition(1700)
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline and abs(player.position() - 1700) > 350:
        qapp.processEvents()
        QTest.qWait(25)
    assert abs(player.position() - 1700) <= 350
    player.stop()
    surface.close()

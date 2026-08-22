# pyright: reportAttributeAccessIssue=false
"""QtMultimedia preview synchronized with editor cues and visual layers."""

from __future__ import annotations

from pathlib import Path

from PyQt5.QtCore import QRectF, Qt, QUrl, pyqtSignal
from PyQt5.QtGui import QColor, QPainter, QPalette, QPen, QPixmap
from PyQt5.QtMultimedia import QMediaContent, QMediaPlayer
from PyQt5.QtMultimediaWidgets import QVideoWidget
from PyQt5.QtWidgets import QHBoxLayout, QLabel, QSlider, QVBoxLayout, QWidget
from qfluentwidgets import FluentIcon as FIF
from qfluentwidgets import PushButton

from videocaptioner.core.editor.models import EditorLayerKind, EditorProject


class EditorOverlay(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.project: EditorProject | None = None
        self.position_ms = 0
        self.selected_layer_id = ""
        self._pixmaps: dict[str, QPixmap] = {}

    def set_state(self, project: EditorProject | None, position_ms: int) -> None:
        self.project = project
        self.position_ms = int(position_ms)
        self.update()

    def set_selected_layer(self, layer_id: str) -> None:
        self.selected_layer_id = str(layer_id or "")
        self.update()

    def video_rect(self) -> QRectF:
        """Letterboxed video area: layers are positioned against the frame, not the widget."""
        width, height = float(self.width()), float(self.height())
        project = self.project
        if not project or not (project.width and project.height):
            return QRectF(0, 0, width, height)
        scale = min(width / project.width, height / project.height)
        frame_width, frame_height = project.width * scale, project.height * scale
        return QRectF((width - frame_width) / 2, (height - frame_height) / 2, frame_width, frame_height)

    def _font_scale(self, frame: QRectF) -> float:
        """Map video pixels to widget pixels so preview text matches drawtext output."""
        if self.project and self.project.height:
            return frame.height() / float(self.project.height)
        return 1.0

    @staticmethod
    def _draw_outlined_text(
        painter: QPainter, rect: QRectF, text: str, flags: int, fill: QColor, outline: QColor, width: int
    ) -> None:
        if width > 0:
            painter.setPen(outline)
            for dx, dy in ((-width, 0), (width, 0), (0, -width), (0, width)):
                painter.drawText(rect.translated(dx, dy), flags, text)
        painter.setPen(fill)
        painter.drawText(rect, flags, text)

    def paintEvent(self, event) -> None:
        if not self.project:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        frame = self.video_rect()
        font_scale = self._font_scale(frame)
        visual_track = next(
            (track for track in self.project.tracks if track.id == "track-fx1"), None
        )
        layers = [] if visual_track is not None and not visual_track.visible else self.project.layers
        for layer in layers:
            if not layer.visible or not layer.start_ms <= self.position_ms < layer.end_ms:
                continue
            rect = QRectF(
                frame.x() + frame.width() * layer.x,
                frame.y() + frame.height() * layer.y,
                frame.width() * layer.width,
                frame.height() * layer.height,
            )
            if layer.kind == EditorLayerKind.TEXT:
                painter.setOpacity(layer.opacity)
                font = painter.font()
                font.setPixelSize(max(6, int(int(layer.properties.get("font_size", 42)) * font_scale)))
                font.setBold(bool(layer.properties.get("bold", False)))
                painter.setFont(font)
                self._draw_outlined_text(
                    painter,
                    rect,
                    str(layer.properties.get("text", "")),
                    Qt.AlignCenter | Qt.TextWordWrap,
                    QColor(str(layer.properties.get("font_color", "white"))),
                    QColor(str(layer.properties.get("outline_color", "black"))),
                    max(0, int(round(int(layer.properties.get("outline_width", 2)) * font_scale))),
                )
                painter.setOpacity(1.0)
            elif layer.kind == EditorLayerKind.LOGO:
                path = str(layer.properties.get("path", ""))
                pixmap = self._pixmaps.get(path)
                if pixmap is None:
                    pixmap = QPixmap(path)
                    self._pixmaps[path] = pixmap
                if not pixmap.isNull():
                    # Export scales the logo by width and keeps its aspect ratio.
                    target = QRectF(
                        rect.x(),
                        rect.y(),
                        rect.width(),
                        rect.width() * pixmap.height() / max(1, pixmap.width()),
                    )
                    painter.setOpacity(layer.opacity)
                    painter.drawPixmap(target, pixmap, QRectF(pixmap.rect()))
                    painter.setOpacity(1.0)
            elif layer.kind == EditorLayerKind.MASK:
                mode = str(layer.properties.get("mode", "solid"))
                if mode == "solid":
                    color = QColor(str(layer.properties.get("color", "black")))
                    color.setAlphaF(layer.opacity)
                    painter.fillRect(rect, color)
                else:
                    painter.fillRect(rect, QColor(30, 30, 30, int(150 * layer.opacity)))
                    painter.setPen(QPen(QColor("#e2e8f0"), 1, Qt.DashLine))
                    painter.drawText(rect, Qt.AlignCenter, mode.title())
            else:
                painter.fillRect(rect, QColor(130, 90, 180, int(90 * layer.opacity)))
                painter.setPen(QPen(QColor("#c4b5fd"), 1, Qt.DashLine))
                painter.drawText(rect, Qt.AlignCenter, "Blur")
            if layer.id == self.selected_layer_id:
                painter.setPen(QPen(QColor("#48d0b8"), 2, Qt.DashLine))
                painter.setBrush(Qt.NoBrush)
                painter.drawRect(rect)

        cue = self.project.active_cue_at(self.position_ms)
        subtitle_track = next(
            (track for track in self.project.tracks if track.id == "track-ts1"), None
        )
        if cue and (subtitle_track is None or subtitle_track.visible):
            subtitle_rect = QRectF(
                frame.x() + 20,
                frame.y() + frame.height() * 0.70,
                max(1.0, frame.width() - 40),
                frame.height() * 0.25,
            )
            font = painter.font()
            font.setPixelSize(max(12, min(42, int(frame.width() // 24))))
            font.setBold(True)
            painter.setFont(font)
            self._draw_outlined_text(
                painter,
                subtitle_rect,
                cue.display_text,
                Qt.AlignHCenter | Qt.AlignBottom | Qt.TextWordWrap,
                QColor(Qt.white),
                QColor(Qt.black),
                2,
            )
        painter.end()


class PreviewSurface(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("EditorPreviewSurface")
        self.video = QVideoWidget(self)
        self.video.setObjectName("EditorNativeVideoSurface")
        self.overlay = EditorOverlay(self)
        self.placeholder = QLabel(self.tr("Open a video to start previewing"), self)
        self.placeholder.setAlignment(Qt.AlignCenter)
        self.placeholder.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.placeholder.setStyleSheet(
            "color:#71829a; background:transparent; font-size:14px; font-weight:600;"
        )
        self._poster = QPixmap()
        self.setMinimumSize(320, 180)
        self.setStyleSheet(
            "QWidget#EditorPreviewSurface {"
            " background:#05080d; border:1px solid #1f3148; border-radius:8px; }"
            "QVideoWidget#EditorNativeVideoSurface { background:#05080d; }"
        )
        surface_palette = self.palette()
        surface_palette.setColor(QPalette.Window, QColor("#05080d"))
        self.setPalette(surface_palette)
        self.setAutoFillBackground(True)
        palette = self.video.palette()
        palette.setColor(QPalette.Window, QColor("#05080d"))
        self.video.setPalette(palette)
        self.video.setAutoFillBackground(True)
        self.set_empty(True)

    def set_empty(self, empty: bool) -> None:
        self._poster = QPixmap()
        self.placeholder.setPixmap(QPixmap())
        self.placeholder.setText(self.tr("Open a video to start previewing"))
        self.video.setVisible(not empty)
        self.placeholder.setVisible(bool(empty))
        if empty:
            self.placeholder.raise_()
            self.overlay.raise_()
        else:
            self.overlay.raise_()

    def set_loading(self) -> None:
        self._poster = QPixmap()
        self.video.hide()
        self.placeholder.setPixmap(QPixmap())
        self.placeholder.setText(self.tr("Loading preview..."))
        self.placeholder.show()
        self.placeholder.raise_()
        self.overlay.raise_()

    def set_poster(self, path: str) -> None:
        poster = QPixmap(str(path or ""))
        if poster.isNull():
            self.show_video()
            return
        self._poster = poster
        self.video.hide()
        self.placeholder.setText("")
        self.placeholder.show()
        self._scale_poster()
        self.placeholder.raise_()
        self.overlay.raise_()

    def show_video(self) -> None:
        self.placeholder.hide()
        self.video.show()
        self.overlay.raise_()

    def _scale_poster(self) -> None:
        if self._poster.isNull():
            return
        self.placeholder.setPixmap(
            self._poster.scaled(
                self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
        )

    def resizeEvent(self, event) -> None:
        self.video.setGeometry(self.rect())
        self.placeholder.setGeometry(self.rect())
        self._scale_poster()
        self.overlay.setGeometry(self.rect())
        self.placeholder.raise_()
        self.overlay.raise_()
        super().resizeEvent(event)


class EditorVideoPreview(QWidget):
    positionChanged = pyqtSignal(int)
    activeCueChanged = pyqtSignal(str)
    playbackError = pyqtSignal(str)
    renderedPreviewChanged = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("EditorVideoPreview")
        self.project: EditorProject | None = None
        # Non-None while a rendered Fast Preview clip is loaded; holds its timeline offset.
        self._rendered_offset_ms: int | None = None
        # Seeking right after setMedia fails on the Windows backend; wait for LoadedMedia.
        self._pending_seek_ms: int | None = None
        self._poster_path = ""
        self._playback_started = False
        self.surface = PreviewSurface(self)
        self.player = QMediaPlayer(self, QMediaPlayer.VideoSurface)
        self.player.setVideoOutput(self.surface.video)
        self.player.positionChanged.connect(self._on_position_changed)
        self.player.durationChanged.connect(self._on_duration_changed)
        self.player.stateChanged.connect(self._on_state_changed)
        self.player.mediaStatusChanged.connect(self._on_media_status)
        self.player.error.connect(self._on_error)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(self.surface, 1)
        transport = QHBoxLayout()
        self.play_button = PushButton(self.tr("Play"), self, icon=FIF.PLAY)
        self.play_button.clicked.connect(self.toggle_playback)
        self.slider = QSlider(Qt.Horizontal, self)
        self.slider.setRange(0, 0)
        self.slider.sliderMoved.connect(self.set_position)
        self.time_label = QLabel("00:00.000 / 00:00.000", self)
        transport.addWidget(self.play_button)
        transport.addWidget(self.slider, 1)
        transport.addWidget(self.time_label)
        layout.addLayout(transport)

    def set_project(self, project: EditorProject | None) -> None:
        self.project = project
        self._rendered_offset_ms = None
        self._pending_seek_ms = None
        self._poster_path = ""
        self._playback_started = False
        self.surface.overlay.set_state(project, 0)
        self.surface.overlay.set_selected_layer("")
        has_video = bool(project and project.video_path and Path(project.video_path).is_file())
        if not has_video:
            self.surface.set_empty(True)
            self.player.setMedia(QMediaContent())
            self.slider.setRange(0, 0)
            return
        self.surface.set_loading()
        self._load_source_media(seek_ms=project.playhead_ms)

    def _load_source_media(self, *, seek_ms: int) -> None:
        """Load the project video and defer the seek until the backend reports it ready."""
        if not self.project:
            return
        self.slider.setRange(0, max(0, self.project.duration_ms))
        position = max(0, min(int(seek_ms), self.project.duration_ms))
        self._pending_seek_ms = position
        self.project.playhead_ms = position
        self._sync_position(position)
        self.player.setMedia(QMediaContent(QUrl.fromLocalFile(self.project.video_path)))

    def _on_media_status(self, status: int) -> None:
        ready = (
            QMediaPlayer.LoadedMedia,
            QMediaPlayer.BufferingMedia,
            QMediaPlayer.BufferedMedia,
        )
        if self._pending_seek_ms is not None and status in ready:
            position = self._pending_seek_ms
            self._pending_seek_ms = None
            self.player.setPosition(position)
            self._sync_position(position)

    @property
    def is_rendered_preview(self) -> bool:
        return self._rendered_offset_ms is not None

    def play_rendered_preview(self, path: str, offset_ms: int) -> None:
        """Play a rendered clip without letting its local clock rewrite project state."""
        self._rendered_offset_ms = max(0, int(offset_ms))
        self.surface.show_video()
        self.player.setMedia(QMediaContent(QUrl.fromLocalFile(str(path))))
        self.player.play()
        self.renderedPreviewChanged.emit(True)

    def exit_rendered_preview(self, *, resume_ms: int | None = None) -> None:
        if self._rendered_offset_ms is None:
            return
        resume = (
            self._timeline_position(self.player.position()) if resume_ms is None else int(resume_ms)
        )
        self._rendered_offset_ms = None
        self.player.stop()
        self._playback_started = False
        # Show the poster again: a stopped QVideoWidget paints the native white surface.
        if self._poster_path:
            self.surface.set_poster(self._poster_path)
        else:
            self.surface.set_loading()
        self._load_source_media(seek_ms=resume)
        self.renderedPreviewChanged.emit(False)

    def _timeline_position(self, player_position_ms: int) -> int:
        return int(player_position_ms) + (self._rendered_offset_ms or 0)

    def toggle_playback(self) -> None:
        if self.player.state() == QMediaPlayer.PlayingState:
            self.player.pause()
        else:
            self.surface.show_video()
            self.player.play()

    def set_poster(self, path: str) -> None:
        self._poster_path = str(path or "")
        # A late thumbnail must never hide a surface the user already started playing.
        if self.is_rendered_preview or self._playback_started:
            return
        if self.player.state() == QMediaPlayer.PlayingState:
            return
        self.surface.set_poster(path)

    def set_position(self, position_ms: int) -> None:
        position_ms = int(position_ms)
        if self.project:
            position_ms = max(0, min(position_ms, self.project.duration_ms))
            self.project.playhead_ms = position_ms
        if self._rendered_offset_ms is not None:
            local = position_ms - self._rendered_offset_ms
            duration = self.player.duration()
            if local < 0 or (duration > 0 and local > duration):
                self.exit_rendered_preview(resume_ms=position_ms)
                return
            if abs(self.player.position() - local) > 5:
                self.player.setPosition(local)
            self._sync_position(position_ms)
            return
        if abs(self.player.position() - position_ms) > 5:
            self.player.setPosition(position_ms)
        self._sync_position(position_ms)

    def _on_position_changed(self, position_ms: int) -> None:
        if self._pending_seek_ms is not None:
            return  # setMedia resets the clock to 0; keep the requested position
        timeline_ms = self._timeline_position(position_ms)
        if self.project:
            timeline_ms = max(0, min(timeline_ms, self.project.duration_ms))
            self.project.playhead_ms = timeline_ms
        self._sync_position(timeline_ms)
        self.positionChanged.emit(timeline_ms)

    def _sync_position(self, position_ms: int) -> None:
        self.slider.blockSignals(True)
        self.slider.setValue(position_ms)
        self.slider.blockSignals(False)
        duration = self.project.duration_ms if self.project else self.player.duration()
        self.time_label.setText(f"{self._format_ms(position_ms)} / {self._format_ms(duration)}")
        self.surface.overlay.set_state(self.project, position_ms)
        if self.project:
            cue = self.project.active_cue_at(position_ms)
            self.activeCueChanged.emit(cue.id if cue else "")

    def _on_duration_changed(self, duration_ms: int) -> None:
        if self.project and self._rendered_offset_ms is not None:
            return  # keep the slider on the project timeline while a clip is previewing
        self.slider.setRange(0, max(0, int(duration_ms)))

    def _on_state_changed(self, state: int) -> None:
        if state == QMediaPlayer.PlayingState:
            self._playback_started = True
            self.surface.show_video()
        self.play_button.setText(
            self.tr("Pause") if state == QMediaPlayer.PlayingState else self.tr("Play")
        )

    def _on_error(self, *_args) -> None:
        message = self.player.errorString() or "QtMultimedia playback failed"
        self.playbackError.emit(message)

    @staticmethod
    def _format_ms(value: int) -> str:
        value = max(0, int(value))
        minutes, remainder = divmod(value, 60_000)
        seconds, milliseconds = divmod(remainder, 1000)
        return f"{minutes:02}:{seconds:02}.{milliseconds:03}"

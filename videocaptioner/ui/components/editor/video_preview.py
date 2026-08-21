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
        self._pixmaps: dict[str, QPixmap] = {}

    def set_state(self, project: EditorProject | None, position_ms: int) -> None:
        self.project = project
        self.position_ms = int(position_ms)
        self.update()

    def paintEvent(self, event) -> None:
        if not self.project:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        for layer in self.project.layers:
            if not layer.visible or not layer.start_ms <= self.position_ms < layer.end_ms:
                continue
            rect = QRectF(
                self.width() * layer.x,
                self.height() * layer.y,
                self.width() * layer.width,
                self.height() * layer.height,
            )
            if layer.kind == EditorLayerKind.TEXT:
                painter.setOpacity(layer.opacity)
                painter.setPen(QColor(str(layer.properties.get("font_color", "white"))))
                font = painter.font()
                font.setPixelSize(max(8, int(layer.properties.get("font_size", 32))))
                font.setBold(bool(layer.properties.get("bold", False)))
                painter.setFont(font)
                painter.drawText(rect, Qt.AlignCenter | Qt.TextWordWrap, str(layer.properties.get("text", "")))
                painter.setOpacity(1.0)
            elif layer.kind == EditorLayerKind.LOGO:
                path = str(layer.properties.get("path", ""))
                pixmap = self._pixmaps.get(path)
                if pixmap is None:
                    pixmap = QPixmap(path)
                    self._pixmaps[path] = pixmap
                if not pixmap.isNull():
                    painter.setOpacity(layer.opacity)
                    painter.drawPixmap(rect, pixmap, QRectF(pixmap.rect()))
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

        cue = self.project.active_cue_at(self.position_ms)
        subtitle_track = next(
            (track for track in self.project.tracks if track.id == "track-ts1"), None
        )
        if cue and (subtitle_track is None or subtitle_track.visible):
            subtitle_rect = QRectF(20, self.height() * 0.70, max(1, self.width() - 40), self.height() * 0.25)
            painter.setPen(QPen(Qt.black, 5))
            font = painter.font()
            font.setPixelSize(max(18, min(42, self.width() // 24)))
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(subtitle_rect, Qt.AlignHCenter | Qt.AlignBottom | Qt.TextWordWrap, cue.display_text)
            painter.setPen(Qt.white)
            painter.drawText(subtitle_rect, Qt.AlignHCenter | Qt.AlignBottom | Qt.TextWordWrap, cue.display_text)
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

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("EditorVideoPreview")
        self.project: EditorProject | None = None
        self.surface = PreviewSurface(self)
        self.player = QMediaPlayer(self, QMediaPlayer.VideoSurface)
        self.player.setVideoOutput(self.surface.video)
        self.player.positionChanged.connect(self._on_position_changed)
        self.player.durationChanged.connect(self._on_duration_changed)
        self.player.stateChanged.connect(self._on_state_changed)
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
        self.surface.overlay.set_state(project, 0)
        has_video = bool(project and project.video_path and Path(project.video_path).is_file())
        if not has_video:
            self.surface.set_empty(True)
            self.player.setMedia(QMediaContent())
            self.slider.setRange(0, 0)
            return
        self.surface.set_loading()
        self.player.setMedia(QMediaContent(QUrl.fromLocalFile(project.video_path)))
        self.slider.setRange(0, max(0, project.duration_ms))
        self.set_position(project.playhead_ms)

    def toggle_playback(self) -> None:
        if self.player.state() == QMediaPlayer.PlayingState:
            self.player.pause()
        else:
            self.surface.show_video()
            self.player.play()

    def set_poster(self, path: str) -> None:
        self.surface.set_poster(path)

    def set_position(self, position_ms: int) -> None:
        position_ms = int(position_ms)
        if self.project:
            position_ms = max(0, min(position_ms, self.project.duration_ms))
            self.project.playhead_ms = position_ms
        if abs(self.player.position() - position_ms) > 5:
            self.player.setPosition(position_ms)
        self._sync_position(position_ms)

    def _on_position_changed(self, position_ms: int) -> None:
        if self.project:
            self.project.playhead_ms = int(position_ms)
        self._sync_position(int(position_ms))
        self.positionChanged.emit(int(position_ms))

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
        self.slider.setRange(0, max(0, int(duration_ms)))

    def _on_state_changed(self, state: int) -> None:
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

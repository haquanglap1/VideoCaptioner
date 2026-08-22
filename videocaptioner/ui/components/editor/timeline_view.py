# pyright: reportAttributeAccessIssue=false
"""Virtualized V1/A1/TS1 timeline for projects with thousands of cues."""

from __future__ import annotations

from PyQt5.QtCore import QPoint, QRectF, Qt, pyqtSignal
from PyQt5.QtGui import QColor, QLinearGradient, QPainter, QPen, QPixmap
from PyQt5.QtWidgets import QAbstractScrollArea, QFrame, QGraphicsScene, QGraphicsView, QSizePolicy

from videocaptioner.core.editor.models import EditorProject, TimelineIndex


class EditorTimelineView(QGraphicsView):
    cueSelected = pyqtSignal(str)
    layerSelected = pyqtSignal(str)
    seekRequested = pyqtSignal(int)
    cueTimingRequested = pyqtSignal(str, int, int, str)
    layerTimingRequested = pyqtSignal(str, int, int, str)
    selectionRangeChanged = pyqtSignal(int, int)
    zoomChanged = pyqtSignal(int)

    RULER_HEIGHT = 30
    TRACK_HEIGHT = 54
    VISUAL_TRACK_HEIGHT = 44
    CONTENT_PAD = 8
    MIN_PPS = 8.0
    MAX_PPS = 800.0
    DEFAULT_PPS = 100.0
    HANDLE_WIDTH = 7

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.NoFrame)
        self.setMinimumWidth(0)
        self.setSizeAdjustPolicy(QAbstractScrollArea.AdjustIgnored)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Expanding)
        self.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.setMouseTracking(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)
        self.setScene(QGraphicsScene(self))
        self.project: EditorProject | None = None
        self._index = TimelineIndex([])
        self.pixels_per_second = self.DEFAULT_PPS
        self.playhead_ms = 0
        self.selected_cue_id = ""
        self.selected_layer_id = ""
        self.waveform: list[float] = []
        self.waveform_duration_s = 0.0
        self.thumbnails: list[tuple[float, QPixmap]] = []
        self.last_painted_cue_count = 0
        self._drag: dict | None = None
        self._selection_anchor_ms: int | None = None
        self._update_scene()

    def set_project(self, project: EditorProject | None) -> None:
        self.project = project
        self._rebuild_index()
        self.playhead_ms = project.playhead_ms if project else 0
        self.selected_cue_id = ""
        self.selected_layer_id = ""
        self._update_scene()
        self.viewport().update()

    def refresh_project(self) -> None:
        self._rebuild_index()
        self._update_scene()
        self.viewport().update()

    def _rebuild_index(self) -> None:
        self._index = TimelineIndex(self.project.cues if self.project else [])

    def _track_count(self) -> int:
        return 4 if self.project and self.project.layers else 3

    def content_height(self) -> int:
        base = self.RULER_HEIGHT + 3 * self.TRACK_HEIGHT
        return base + (self.VISUAL_TRACK_HEIGHT if self._track_count() == 4 else 0)

    def _update_scene(self) -> None:
        duration_s = (self.project.duration_ms / 1000.0) if self.project else 10.0
        width = max(self.viewport().width(), int(duration_s * self.pixels_per_second) + self.CONTENT_PAD * 2)
        self.scene().setSceneRect(0, 0, width, self.content_height())
        self.setMinimumHeight(self.content_height() + 20)

    def set_playhead(self, position_ms: int) -> None:
        if self.project:
            position_ms = max(0, min(int(position_ms), self.project.duration_ms))
        self.playhead_ms = max(0, int(position_ms))
        self.viewport().update()

    def select_cue(self, cue_id: str) -> None:
        self.selected_cue_id = str(cue_id or "")
        self.viewport().update()

    def select_layer(self, layer_id: str) -> None:
        self.selected_layer_id = str(layer_id or "")
        self.viewport().update()

    def _layer_row_rect(self, layer) -> QRectF:
        top = self.RULER_HEIGHT + 3 * self.TRACK_HEIGHT + 5
        x = self._x_for_ms(layer.start_ms)
        width = max(4.0, layer.duration_ms / 1000.0 * self.pixels_per_second)
        return QRectF(x, top, width, self.VISUAL_TRACK_HEIGHT - 10)

    def _layer_at(self, point: QPoint):
        if not self.project or self._track_count() != 4:
            return None
        top = self.RULER_HEIGHT + 3 * self.TRACK_HEIGHT
        if not top <= point.y() < top + self.VISUAL_TRACK_HEIGHT:
            return None
        for layer in reversed(self.project.layers):
            rect = self._layer_row_rect(layer)
            if rect.left() - 1 <= point.x() <= rect.right() + 1:
                return layer
        return None

    def set_waveform(self, samples: list[float], duration_s: float) -> None:
        self.waveform = [max(0.0, min(1.0, float(value))) for value in samples]
        self.waveform_duration_s = max(0.0, float(duration_s))
        self.viewport().update()

    def set_thumbnails(self, items: list[tuple[float, str]]) -> None:
        self.thumbnails = [
            (float(timestamp), QPixmap(path))
            for timestamp, path in items
            if path and not QPixmap(path).isNull()
        ]
        self.viewport().update()

    def set_zoom_percent(self, percent: int) -> None:
        self.pixels_per_second = max(
            self.MIN_PPS,
            min(self.MAX_PPS, self.DEFAULT_PPS * max(10, int(percent)) / 100.0),
        )
        self._update_scene()
        self.zoomChanged.emit(self.zoom_percent())
        self.viewport().update()

    def zoom_percent(self) -> int:
        return int(round(self.pixels_per_second / self.DEFAULT_PPS * 100))

    def zoom_in(self) -> None:
        self.set_zoom_percent(int(self.zoom_percent() * 1.25))

    def zoom_out(self) -> None:
        self.set_zoom_percent(int(self.zoom_percent() / 1.25))

    def fit_timeline(self) -> None:
        if not self.project or self.project.duration_ms <= 0:
            return
        available = max(1, self.viewport().width() - self.CONTENT_PAD * 2)
        self.pixels_per_second = max(
            self.MIN_PPS,
            min(self.MAX_PPS, available / (self.project.duration_ms / 1000.0)),
        )
        self._update_scene()
        self.zoomChanged.emit(self.zoom_percent())
        self.viewport().update()

    def _visible_range_ms(self) -> tuple[int, int]:
        scroll = self.horizontalScrollBar().value()
        start = max(0, int((scroll - self.CONTENT_PAD) / self.pixels_per_second * 1000))
        end = int((scroll + self.viewport().width()) / self.pixels_per_second * 1000) + 1
        return start, end

    def visible_cues(self):
        start, end = self._visible_range_ms()
        return self._index.visible(start, end)

    def _x_for_ms(self, value: int) -> float:
        return self.CONTENT_PAD + value / 1000.0 * self.pixels_per_second - self.horizontalScrollBar().value()

    def _ms_for_x(self, x: float) -> int:
        scroll = self.horizontalScrollBar().value()
        return max(0, int(round((x + scroll - self.CONTENT_PAD) / self.pixels_per_second * 1000)))

    def _cue_row_rect(self, cue) -> QRectF:
        top = self.RULER_HEIGHT + 2 * self.TRACK_HEIGHT + 6
        x = self._x_for_ms(cue.start_ms)
        width = max(4.0, (cue.end_ms - cue.start_ms) / 1000.0 * self.pixels_per_second)
        return QRectF(x, top, width, self.TRACK_HEIGHT - 12)

    def _cue_at(self, point: QPoint):
        if not self.project:
            return None
        ts_top = self.RULER_HEIGHT + 2 * self.TRACK_HEIGHT
        if not ts_top <= point.y() < ts_top + self.TRACK_HEIGHT:
            return None
        position = self._ms_for_x(point.x())
        matches = self._index.visible(position - 1, position + 2)
        return matches[0] if matches else None

    def _track_locked(self, track_id: str) -> bool:
        if not self.project:
            return True
        try:
            return self.project.track_by_id(track_id).locked
        except KeyError:
            return False

    def _clamp_timing(self, cue_id: str, start_ms: int, end_ms: int) -> tuple[int, int]:
        assert self.project is not None
        cue = self.project.cue_by_id(cue_id)
        duration = max(50, end_ms - start_ms)
        others = sorted(
            (item for item in self.project.cues if item.id != cue_id),
            key=lambda item: item.start_ms,
        )
        previous_end = max((item.end_ms for item in others if item.end_ms <= cue.start_ms), default=0)
        next_start = min(
            (item.start_ms for item in others if item.start_ms >= cue.end_ms),
            default=self.project.duration_ms,
        )
        start_ms = max(previous_end, start_ms)
        end_ms = min(next_start, end_ms)
        if end_ms - start_ms < 50:
            if self._drag and self._drag.get("mode") == "move":
                start_ms = max(previous_end, min(start_ms, next_start - duration))
                end_ms = start_ms + duration
            else:
                end_ms = min(next_start, start_ms + 50)
        return start_ms, end_ms

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        painter = QPainter(self.viewport())
        painter.setRenderHint(QPainter.Antialiasing, True)
        width = self.viewport().width()
        painter.fillRect(self.viewport().rect(), QColor("#10151f"))
        self._draw_tracks(painter, width)
        self._draw_ruler(painter, width)
        self._draw_playhead(painter)
        painter.end()

    def _draw_tracks(self, painter: QPainter, width: int) -> None:
        colors = (QColor("#182332"), QColor("#142923"), QColor("#2d2215"), QColor("#241b32"))
        heights = [self.TRACK_HEIGHT] * 3 + ([self.VISUAL_TRACK_HEIGHT] if self._track_count() == 4 else [])
        y = self.RULER_HEIGHT
        for index, height in enumerate(heights):
            painter.fillRect(0, y, width, height, colors[index])
            painter.setPen(QPen(QColor("#334155"), 1))
            painter.drawLine(0, y + height - 1, width, y + height - 1)
            self._draw_grid(painter, y, height, width)
            y += height
        self._draw_video_track(painter)
        self._draw_audio_track(painter)
        self._draw_subtitle_track(painter)
        if self._track_count() == 4:
            self._draw_visual_track(painter)

    def _draw_grid(self, painter: QPainter, y: int, height: int, width: int) -> None:
        start_ms, end_ms = self._visible_range_ms()
        interval_s = 10 if self.pixels_per_second < 25 else 5 if self.pixels_per_second < 60 else 1
        first = max(0, (start_ms // (interval_s * 1000)) * interval_s)
        painter.setPen(QPen(QColor(51, 65, 85, 100), 1))
        for second in range(first, end_ms // 1000 + interval_s, interval_s):
            x = int(self._x_for_ms(second * 1000))
            if 0 <= x <= width:
                painter.drawLine(x, y, x, y + height)

    def _draw_video_track(self, painter: QPainter) -> None:
        top = self.RULER_HEIGHT + 5
        bottom = top + self.TRACK_HEIGHT - 10
        if not self.thumbnails:
            painter.fillRect(0, top, self.viewport().width(), bottom - top, QColor("#26364b"))
            return
        for timestamp, pixmap in self.thumbnails:
            x = self._x_for_ms(int(timestamp * 1000))
            target = QRectF(x, top, 90, bottom - top)
            if target.right() < 0 or target.left() > self.viewport().width():
                continue
            painter.drawPixmap(target, pixmap, QRectF(pixmap.rect()))

    def _draw_audio_track(self, painter: QPainter) -> None:
        if not self.waveform:
            return
        y = self.RULER_HEIGHT + self.TRACK_HEIGHT + self.TRACK_HEIGHT / 2
        half = self.TRACK_HEIGHT / 2 - 7
        start_ms, end_ms = self._visible_range_ms()
        duration_ms = max(1, int(self.waveform_duration_s * 1000))
        first = max(0, int(start_ms / duration_ms * len(self.waveform)))
        last = min(len(self.waveform), int(end_ms / duration_ms * len(self.waveform)) + 2)
        gradient = QLinearGradient(0, y - half, 0, y + half)
        gradient.setColorAt(0, QColor("#47d7ac"))
        gradient.setColorAt(1, QColor("#147d6f"))
        painter.setPen(QPen(gradient, 1))
        for index in range(first, last):
            x = self._x_for_ms(int(index / max(1, len(self.waveform) - 1) * duration_ms))
            amplitude = self.waveform[index] * half
            painter.drawLine(int(x), int(y - amplitude), int(x), int(y + amplitude))

    def _draw_subtitle_track(self, painter: QPainter) -> None:
        visible = self.visible_cues()
        self.last_painted_cue_count = len(visible)
        for cue in visible:
            rect = self._cue_row_rect(cue)
            selected = cue.id == self.selected_cue_id
            painter.setPen(QPen(QColor("#ffd166") if selected else QColor("#d49438"), 2 if selected else 1))
            painter.setBrush(QColor("#9a641f") if selected else QColor("#65451e"))
            painter.drawRoundedRect(rect, 4, 4)
            painter.setPen(QColor("#fff7e3"))
            text_rect = rect.adjusted(5, 1, -5, -1)
            text = painter.fontMetrics().elidedText(cue.display_text.replace("\n", " "), Qt.ElideRight, int(text_rect.width()))
            painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, text)

    def _draw_visual_track(self, painter: QPainter) -> None:
        if not self.project:
            return
        for layer in self.project.layers:
            rect = self._layer_row_rect(layer)
            if rect.right() < 0 or rect.left() > self.viewport().width():
                continue
            selected = layer.id == self.selected_layer_id
            painter.setPen(QPen(QColor("#d9c6ff") if selected else QColor("#ae7ef5"), 2 if selected else 1))
            painter.setBrush(QColor("#6d4f96") if selected else QColor("#573f78"))
            painter.drawRoundedRect(rect, 3, 3)
            painter.setPen(Qt.white if layer.visible else QColor("#a5b4c8"))
            caption = layer.name or layer.kind.value
            if not layer.visible:
                caption = f"{caption} (hidden)"
            painter.drawText(rect.adjusted(4, 0, -4, 0), Qt.AlignVCenter, caption)

    def _draw_ruler(self, painter: QPainter, width: int) -> None:
        painter.fillRect(0, 0, width, self.RULER_HEIGHT, QColor("#0b1018"))
        start_ms, end_ms = self._visible_range_ms()
        interval_s = 10 if self.pixels_per_second < 25 else 5 if self.pixels_per_second < 60 else 1
        first = max(0, (start_ms // (interval_s * 1000)) * interval_s)
        painter.setPen(QColor("#94a3b8"))
        for second in range(first, end_ms // 1000 + interval_s, interval_s):
            x = int(self._x_for_ms(second * 1000))
            if 0 <= x <= width:
                painter.drawLine(x, self.RULER_HEIGHT - 7, x, self.RULER_HEIGHT)
                minutes, seconds = divmod(second, 60)
                painter.drawText(x + 3, 14, f"{minutes:02}:{seconds:02}")
        if self.project and self.project.selection_start_ms is not None and self.project.selection_end_ms is not None:
            left = self._x_for_ms(self.project.selection_start_ms)
            right = self._x_for_ms(self.project.selection_end_ms)
            painter.fillRect(QRectF(left, 0, right - left, self.content_height()), QColor(72, 149, 239, 45))

    def _draw_playhead(self, painter: QPainter) -> None:
        x = self._x_for_ms(self.playhead_ms)
        if -2 <= x <= self.viewport().width() + 2:
            painter.setPen(QPen(QColor("#ef4444"), 2))
            painter.drawLine(int(x), 0, int(x), self.content_height())

    def mousePressEvent(self, event) -> None:
        if not self.project or event.button() != Qt.LeftButton:
            return super().mousePressEvent(event)
        position_ms = min(self.project.duration_ms, self._ms_for_x(event.pos().x()))
        if event.modifiers() & Qt.ShiftModifier:
            self._selection_anchor_ms = position_ms
            self.project.selection_start_ms = position_ms
            self.project.selection_end_ms = position_ms
            self.viewport().update()
            return
        layer = self._layer_at(event.pos())
        if layer:
            self.selected_layer_id = layer.id
            self.layerSelected.emit(layer.id)
            if not self._track_locked("track-fx1"):
                rect = self._layer_row_rect(layer)
                if abs(event.pos().x() - rect.left()) <= self.HANDLE_WIDTH:
                    mode = "resize-left"
                elif abs(event.pos().x() - rect.right()) <= self.HANDLE_WIDTH:
                    mode = "resize-right"
                else:
                    mode = "move"
                self._drag = {
                    "target": "layer",
                    "cue_id": layer.id,
                    "mode": mode,
                    "anchor_ms": position_ms,
                    "start_ms": layer.start_ms,
                    "end_ms": layer.end_ms,
                }
            self.viewport().update()
            return
        cue = self._cue_at(event.pos())
        if cue:
            self.selected_cue_id = cue.id
            self.cueSelected.emit(cue.id)
            self.seekRequested.emit(cue.start_ms)
            if not self._track_locked("track-ts1"):
                rect = self._cue_row_rect(cue)
                if abs(event.pos().x() - rect.left()) <= self.HANDLE_WIDTH:
                    mode = "resize-left"
                elif abs(event.pos().x() - rect.right()) <= self.HANDLE_WIDTH:
                    mode = "resize-right"
                else:
                    mode = "move"
                self._drag = {
                    "target": "cue",
                    "cue_id": cue.id,
                    "mode": mode,
                    "anchor_ms": position_ms,
                    "start_ms": cue.start_ms,
                    "end_ms": cue.end_ms,
                }
        else:
            self.seekRequested.emit(position_ms)
        self.viewport().update()

    def mouseMoveEvent(self, event) -> None:
        if not self.project:
            return super().mouseMoveEvent(event)
        position_ms = min(self.project.duration_ms, self._ms_for_x(event.pos().x()))
        if self._selection_anchor_ms is not None:
            self.project.selection_start_ms = min(self._selection_anchor_ms, position_ms)
            self.project.selection_end_ms = max(self._selection_anchor_ms, position_ms)
            self.viewport().update()
            return
        if self._drag:
            delta = position_ms - int(self._drag["anchor_ms"])
            start, end = int(self._drag["start_ms"]), int(self._drag["end_ms"])
            if self._drag["mode"] == "move":
                duration = end - start
                start = max(0, start + delta)
                end = start + duration
            elif self._drag["mode"] == "resize-left":
                start = min(end - 50, max(0, start + delta))
            else:
                end = max(start + 50, min(self.project.duration_ms, end + delta))
            if self._drag.get("target") == "layer":
                # Visual layers may overlap each other, so only the media bounds apply.
                start = max(0, min(start, self.project.duration_ms - 50))
                end = max(start + 50, min(end, self.project.duration_ms))
            else:
                start, end = self._clamp_timing(str(self._drag["cue_id"]), start, end)
            self._drag["preview"] = (start, end)
            self.viewport().update()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if self._selection_anchor_ms is not None and self.project:
            start = int(self.project.selection_start_ms or 0)
            end = int(self.project.selection_end_ms or start)
            self._selection_anchor_ms = None
            if end > start:
                self.selectionRangeChanged.emit(start, end)
            return
        if self._drag:
            preview = self._drag.get("preview")
            if preview:
                signal = (
                    self.layerTimingRequested
                    if self._drag.get("target") == "layer"
                    else self.cueTimingRequested
                )
                signal.emit(
                    str(self._drag["cue_id"]),
                    int(preview[0]),
                    int(preview[1]),
                    str(self._drag["mode"]),
                )
            self._drag = None
            self.viewport().update()
            return
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event) -> None:
        if event.modifiers() & Qt.ControlModifier:
            if event.angleDelta().y() > 0:
                self.zoom_in()
            else:
                self.zoom_out()
            event.accept()
            return
        super().wheelEvent(event)

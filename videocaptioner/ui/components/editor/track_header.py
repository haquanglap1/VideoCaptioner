# pyright: reportAttributeAccessIssue=false
"""Fixed track labels synchronized with the scrollable timeline."""

from __future__ import annotations

from PyQt5.QtCore import QSize, Qt, pyqtSignal
from PyQt5.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget
from qfluentwidgets import PushButton

from videocaptioner.core.editor.models import EditorProject


class EditorTrackHeader(QFrame):
    trackStateRequested = pyqtSignal(str, str, bool)

    RULER_HEIGHT = 30
    TRACK_HEIGHT = 54
    VISUAL_TRACK_HEIGHT = 44

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(170)
        self.setFrameShape(QFrame.NoFrame)
        self.setStyleSheet("EditorTrackHeader { background:#111827; border-right:1px solid #334155; }")
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)
        ruler = QLabel(self.tr("Timeline"), self)
        ruler.setFixedHeight(self.RULER_HEIGHT)
        ruler.setAlignment(Qt.AlignCenter)
        ruler.setStyleSheet("color:#94a3b8; background:#0b1018; font-weight:600;")
        self._layout.addWidget(ruler)
        self._rows: dict[str, QWidget] = {}
        self._buttons: dict[tuple[str, str], PushButton] = {}
        self._project: EditorProject | None = None
        for track_id, label in (
            ("track-v1", "V1  Video"),
            ("track-a1", "A1  Original Audio"),
            ("track-ts1", "TS1  Subtitle + TTS"),
            ("track-fx1", "FX1  Visual Layers"),
        ):
            self._add_row(track_id, self.tr(label))
        self._rows["track-fx1"].hide()

    def _add_row(self, track_id: str, text: str) -> None:
        row = QWidget(self)
        row.setFixedHeight(
            self.VISUAL_TRACK_HEIGHT if track_id == "track-fx1" else self.TRACK_HEIGHT
        )
        row.setStyleSheet("background:#172033; border-bottom:1px solid #334155;")
        layout = QHBoxLayout(row)
        layout.setContentsMargins(8, 3, 5, 3)
        layout.setSpacing(4)
        label = QLabel(text, row)
        label.setStyleSheet("color:#e2e8f0; font-size:11px; font-weight:600;")
        layout.addWidget(label, 1)
        for field_name, caption in (("muted", "M"), ("locked", "L")):
            button = PushButton(caption, row)
            button.setCheckable(True)
            button.setFixedSize(27, 27)
            button.setToolTip("Mute" if field_name == "muted" else "Lock")
            button.toggled.connect(
                lambda checked, tid=track_id, field=field_name: self.trackStateRequested.emit(
                    tid, field, checked
                )
            )
            layout.addWidget(button)
            self._buttons[(track_id, field_name)] = button
        if track_id == "track-v1":
            self._buttons[(track_id, "muted")].setEnabled(False)
        self._rows[track_id] = row
        self._layout.addWidget(row)

    def set_project(self, project: EditorProject | None) -> None:
        self._project = project
        self._rows["track-fx1"].setVisible(bool(project and project.layers))
        if not project:
            return
        for track in project.tracks:
            for field_name in ("muted", "locked"):
                button = self._buttons.get((track.id, field_name))
                if button:
                    button.blockSignals(True)
                    button.setChecked(bool(getattr(track, field_name)))
                    button.blockSignals(False)

    def refresh(self) -> None:
        self.set_project(self._project)

    def minimumSizeHint(self) -> QSize:
        return QSize(self.width(), self.RULER_HEIGHT + 3 * self.TRACK_HEIGHT)

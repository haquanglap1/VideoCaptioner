# pyright: reportAttributeAccessIssue=false
"""Context inspector for independently editable source/display/TTS text."""

from __future__ import annotations

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import LineEdit, PrimaryPushButton, PushButton, StrongBodyLabel, TextEdit

from videocaptioner.core.editor.models import EditorCue


class SubtitleInspector(QScrollArea):
    applyRequested = pyqtSignal(str, object)
    regenerateRequested = pyqtSignal(str)
    splitRequested = pyqtSignal(str)
    deleteRequested = pyqtSignal(str)
    addRequested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("EditorSubtitleInspector")
        self.setWidgetResizable(True)
        self.setMinimumWidth(290)
        self.setFrameShape(QScrollArea.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._cue_id = ""
        self._duration_ms = 0
        content = QWidget(self)
        content.setObjectName("EditorInspectorContent")
        self.setWidget(content)
        self.viewport().setObjectName("EditorInspectorViewport")
        self.setStyleSheet(
            "QScrollArea#EditorSubtitleInspector, QWidget#EditorInspectorViewport,"
            " QWidget#EditorInspectorContent { background:#0d1726; border:none; }"
            "QWidget#EditorInspectorContent QLabel { color:#dbe7f5; }"
            "QWidget#EditorInspectorContent QDoubleSpinBox,"
            " QWidget#EditorInspectorContent QLineEdit,"
            " QWidget#EditorInspectorContent QTextEdit {"
            " color:#e8f0fa; background:#101d2e; border:1px solid #29405d;"
            " border-radius:6px; padding:5px; selection-background-color:#2a8f83; }"
            "QWidget#EditorInspectorContent QDoubleSpinBox:disabled,"
            " QWidget#EditorInspectorContent QLineEdit:disabled,"
            " QWidget#EditorInspectorContent QTextEdit:disabled {"
            " color:#64748b; background:#0b1421; border-color:#1d2c40; }"
            "QWidget#EditorInspectorContent QScrollBar:vertical {"
            " background:#0b1421; width:9px; margin:0; }"
            "QWidget#EditorInspectorContent QScrollBar::handle:vertical {"
            " background:#314967; min-height:28px; border-radius:4px; }"
            "QScrollArea#EditorSubtitleInspector QScrollBar:vertical {"
            " background:#0b1421; width:9px; margin:0; }"
            "QScrollArea#EditorSubtitleInspector QScrollBar::handle:vertical {"
            " background:#314967; min-height:28px; border-radius:4px; }"
            "QScrollArea#EditorSubtitleInspector QScrollBar::add-line:vertical,"
            " QScrollArea#EditorSubtitleInspector QScrollBar::sub-line:vertical {"
            " height:0; background:transparent; }"
        )
        layout = QVBoxLayout(content)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)
        layout.addWidget(StrongBodyLabel(self.tr("Context Inspector"), content))
        self.empty_label = QLabel(self.tr("Select a TS1 cue to edit"), content)
        self.empty_label.setStyleSheet("color:#71829a;")
        layout.addWidget(self.empty_label)

        self.form_widget = QWidget(content)
        form = QFormLayout(self.form_widget)
        form.setContentsMargins(0, 0, 0, 0)
        form.setSpacing(7)
        timing_row = QWidget(self.form_widget)
        timing_layout = QHBoxLayout(timing_row)
        timing_layout.setContentsMargins(0, 0, 0, 0)
        self.start_spin = QDoubleSpinBox(timing_row)
        self.end_spin = QDoubleSpinBox(timing_row)
        for spin in (self.start_spin, self.end_spin):
            spin.setRange(0, 24 * 60 * 60)
            spin.setDecimals(3)
            spin.setSuffix(" s")
        timing_layout.addWidget(self.start_spin)
        timing_layout.addWidget(self.end_spin)
        form.addRow(self.tr("Start / End"), timing_row)

        self.source_edit = TextEdit(self.form_widget)
        self.display_edit = TextEdit(self.form_widget)
        self.tts_edit = TextEdit(self.form_widget)
        for editor in (self.source_edit, self.display_edit, self.tts_edit):
            editor.setMinimumHeight(68)
            editor.setMaximumHeight(110)
        form.addRow(self.tr("Source text"), self.source_edit)
        form.addRow(self.tr("Display subtitle"), self.display_edit)
        form.addRow(self.tr("TTS text"), self.tts_edit)

        self.speaker_edit = LineEdit(self.form_widget)
        self.voice_edit = LineEdit(self.form_widget)
        self.voice_speed = QDoubleSpinBox(self.form_widget)
        self.voice_speed.setRange(0.25, 4.0)
        self.voice_speed.setSingleStep(0.05)
        self.voice_speed.setDecimals(2)
        self.voice_speed.setSuffix("x")
        form.addRow(self.tr("Speaker"), self.speaker_edit)
        form.addRow(self.tr("Voice"), self.voice_edit)
        form.addRow(self.tr("Voice speed"), self.voice_speed)

        self.fit_label = QLabel("pending", self.form_widget)
        self.warnings_edit = TextEdit(self.form_widget)
        self.warnings_edit.setReadOnly(True)
        self.warnings_edit.setMaximumHeight(85)
        form.addRow(self.tr("Fit status"), self.fit_label)
        form.addRow(self.tr("Warnings"), self.warnings_edit)
        layout.addWidget(self.form_widget)

        self.apply_button = PrimaryPushButton(self.tr("Apply changes"), content)
        self.regenerate_button = PushButton(self.tr("Regenerate voice"), content)
        self.apply_button.clicked.connect(self._emit_apply)
        self.regenerate_button.clicked.connect(
            lambda: self.regenerateRequested.emit(self._cue_id) if self._cue_id else None
        )
        layout.addWidget(self.apply_button)
        layout.addWidget(self.regenerate_button)

        edit_row = QHBoxLayout()
        self.add_button = PushButton(self.tr("Add"), content)
        self.split_button = PushButton(self.tr("Split"), content)
        self.delete_button = PushButton(self.tr("Delete"), content)
        self.add_button.clicked.connect(self.addRequested.emit)
        self.split_button.clicked.connect(
            lambda: self.splitRequested.emit(self._cue_id) if self._cue_id else None
        )
        self.delete_button.clicked.connect(
            lambda: self.deleteRequested.emit(self._cue_id) if self._cue_id else None
        )
        for button in (self.add_button, self.split_button, self.delete_button):
            edit_row.addWidget(button)
        layout.addLayout(edit_row)
        layout.addStretch()
        self.set_cue(None, 0)

    @property
    def cue_id(self) -> str:
        return self._cue_id

    def set_cue(self, cue: EditorCue | None, duration_ms: int) -> None:
        self._duration_ms = int(duration_ms)
        self._cue_id = cue.id if cue else ""
        self.empty_label.setVisible(cue is None)
        self.form_widget.setVisible(cue is not None)
        for button in (
            self.apply_button,
            self.regenerate_button,
            self.split_button,
            self.delete_button,
        ):
            button.setEnabled(cue is not None)
        if not cue:
            return
        self.start_spin.setMaximum(max(0.0, duration_ms / 1000.0))
        self.end_spin.setMaximum(max(0.0, duration_ms / 1000.0))
        self.start_spin.setValue(cue.start_ms / 1000.0)
        self.end_spin.setValue(cue.end_ms / 1000.0)
        self.source_edit.setPlainText(cue.source_text)
        self.display_edit.setPlainText(cue.display_text)
        self.tts_edit.setPlainText(cue.tts_text)
        self.speaker_edit.setText(cue.speaker)
        self.voice_edit.setText(cue.voice)
        self.voice_speed.setValue(cue.voice_speed)
        self.fit_label.setText(
            f"{cue.fit_status} ({cue.fit_ratio:.2f}x)" if cue.fit_ratio else cue.fit_status
        )
        self.warnings_edit.setPlainText("\n".join(cue.warnings))

    def _emit_apply(self) -> None:
        if not self._cue_id:
            return
        self.applyRequested.emit(
            self._cue_id,
            {
                "start_ms": int(round(self.start_spin.value() * 1000)),
                "end_ms": int(round(self.end_spin.value() * 1000)),
                "source_text": self.source_edit.toPlainText(),
                "display_text": self.display_edit.toPlainText(),
                "tts_text": self.tts_edit.toPlainText(),
                "speaker": self.speaker_edit.text(),
                "voice": self.voice_edit.text(),
                "voice_speed": self.voice_speed.value(),
            },
        )

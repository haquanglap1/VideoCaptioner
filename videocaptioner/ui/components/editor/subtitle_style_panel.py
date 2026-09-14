# pyright: reportAttributeAccessIssue=false
"""Subtitle appearance controls; Apply emits one project command snapshot."""

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFontComboBox,
    QFormLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import LineEdit, PrimaryPushButton, PushButton, StrongBodyLabel

from videocaptioner.core.editor.subtitle_style import EditorSubtitleStyle

from .fonts import load_editor_fonts


class SubtitleStylePanel(QScrollArea):
    applyRequested = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        load_editor_fonts()
        self.setObjectName("EditorSubtitleStylePanel")
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setFrameShape(QScrollArea.NoFrame)
        content = QWidget(self)
        content.setObjectName("EditorSubtitleStyleContent")
        self.setWidget(content)
        self.setStyleSheet(
            "QScrollArea#EditorSubtitleStylePanel, QWidget#EditorSubtitleStyleContent {"
            " background:#0d1726; border:none; }"
            "QWidget#EditorSubtitleStyleContent QLabel, QWidget#EditorSubtitleStyleContent QCheckBox {"
            " color:#dbe7f5; }"
            "QWidget#EditorSubtitleStyleContent QSpinBox, QWidget#EditorSubtitleStyleContent QDoubleSpinBox,"
            " QWidget#EditorSubtitleStyleContent QComboBox, QWidget#EditorSubtitleStyleContent QLineEdit {"
            " color:#e8f0fa; background:#101d2e; border:1px solid #29405d; border-radius:6px; padding:4px; }"
            "QScrollArea#EditorSubtitleStylePanel QScrollBar:vertical {"
            " background:#0b1421; width:9px; margin:0; }"
            "QScrollArea#EditorSubtitleStylePanel QScrollBar::handle:vertical {"
            " background:#29405d; min-height:24px; border-radius:4px; }"
            "QScrollArea#EditorSubtitleStylePanel QScrollBar::add-line:vertical,"
            " QScrollArea#EditorSubtitleStylePanel QScrollBar::sub-line:vertical { height:0; }"
        )
        layout = QVBoxLayout(content)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.addWidget(StrongBodyLabel(self.tr("Subtitle Style"), content))
        hint = QLabel(self.tr("Applies to all subtitles in this project."), content)
        hint.setWordWrap(True)
        layout.addWidget(hint)
        form = QFormLayout()
        form.setRowWrapPolicy(QFormLayout.WrapLongRows)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.font_combo = QFontComboBox(content)
        self.font_combo.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.font_combo.setMinimumWidth(0)
        form.addRow(self.tr("Font"), self.font_combo)
        self.font_size_spin = QSpinBox(content)
        self.font_size_spin.setRange(8, 200)
        form.addRow(self.tr("Font size"), self.font_size_spin)
        self.bold_check = QCheckBox(self.tr("Bold"), content)
        form.addRow(self.bold_check)
        self.primary_color_edit = LineEdit(content)
        self.outline_color_edit = LineEdit(content)
        for edit in (self.primary_color_edit, self.outline_color_edit):
            edit.setPlaceholderText("#RRGGBB")
        form.addRow(self.tr("Text color"), self.primary_color_edit)
        form.addRow(self.tr("Outline color"), self.outline_color_edit)
        self.outline_width_spin = QDoubleSpinBox(content)
        self.spacing_spin = QDoubleSpinBox(content)
        for spin in (self.outline_width_spin, self.spacing_spin):
            spin.setRange(0, 20)
            spin.setDecimals(1)
            spin.setSingleStep(0.5)
        form.addRow(self.tr("Outline width"), self.outline_width_spin)
        form.addRow(self.tr("Letter spacing"), self.spacing_spin)
        self.alignment_combo = QComboBox(content)
        for alignment, label in enumerate(
            (
                self.tr("Bottom left"),
                self.tr("Bottom center"),
                self.tr("Bottom right"),
                self.tr("Middle left"),
                self.tr("Middle center"),
                self.tr("Middle right"),
                self.tr("Top left"),
                self.tr("Top center"),
                self.tr("Top right"),
            ),
            start=1,
        ):
            self.alignment_combo.addItem(label, alignment)
        form.addRow(self.tr("Alignment"), self.alignment_combo)
        self.margin_spins: dict[str, QSpinBox] = {}
        for name, label in (
            ("margin_left", self.tr("Left margin")),
            ("margin_right", self.tr("Right margin")),
            ("margin_bottom", self.tr("Vertical margin")),
        ):
            spin = QSpinBox(content)
            spin.setRange(0, 300)
            self.margin_spins[name] = spin
            form.addRow(label, spin)
        layout.addLayout(form)
        self.apply_button = PrimaryPushButton(self.tr("Apply"), content)
        self.apply_button.clicked.connect(lambda: self.applyRequested.emit(self.values()))
        layout.addWidget(self.apply_button)
        self.reset_button = PushButton(self.tr("Reset style"), content)
        self.reset_button.clicked.connect(
            lambda: self.applyRequested.emit(EditorSubtitleStyle().to_dict())
        )
        layout.addWidget(self.reset_button)
        layout.addStretch(1)
        self.set_style(EditorSubtitleStyle())
        self.setEnabled(False)

    def set_style(self, style: EditorSubtitleStyle) -> None:
        # Keep unavailable font names intact when loading a project from another machine.
        self.font_combo.setEditText(style.font_name)
        self.font_combo.lineEdit().setCursorPosition(0)
        self.font_size_spin.setValue(style.font_size)
        self.bold_check.setChecked(style.bold)
        self.primary_color_edit.setText(style.primary_color)
        self.outline_color_edit.setText(style.outline_color)
        self.outline_width_spin.setValue(style.outline_width)
        self.spacing_spin.setValue(style.spacing)
        self.alignment_combo.setCurrentIndex(self.alignment_combo.findData(style.alignment))
        for name, spin in self.margin_spins.items():
            spin.setValue(getattr(style, name))

    def values(self) -> dict:
        return {
            "font_name": self.font_combo.currentText(),
            "font_size": self.font_size_spin.value(),
            "bold": self.bold_check.isChecked(),
            "primary_color": self.primary_color_edit.text(),
            "outline_color": self.outline_color_edit.text(),
            "outline_width": self.outline_width_spin.value(),
            "spacing": self.spacing_spin.value(),
            "alignment": self.alignment_combo.currentData(),
            **{name: spin.value() for name, spin in self.margin_spins.items()},
        }

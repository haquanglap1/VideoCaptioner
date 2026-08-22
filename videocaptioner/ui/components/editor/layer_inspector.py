# pyright: reportAttributeAccessIssue=false
"""Inspector for FX1 visual layers: geometry, timing and per-kind properties."""

from __future__ import annotations

from typing import Any

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import LineEdit, PrimaryPushButton, PushButton, StrongBodyLabel, TextEdit

from videocaptioner.core.editor.models import EditorLayer, EditorLayerKind

LAYER_INSPECTOR_STYLE = (
    "QScrollArea#EditorLayerInspector, QWidget#EditorLayerViewport,"
    " QWidget#EditorLayerContent { background:#0d1726; border:none; }"
    "QWidget#EditorLayerContent QLabel { color:#dbe7f5; }"
    "QWidget#EditorLayerContent QDoubleSpinBox,"
    " QWidget#EditorLayerContent QSpinBox,"
    " QWidget#EditorLayerContent QComboBox,"
    " QWidget#EditorLayerContent QLineEdit,"
    " QWidget#EditorLayerContent QTextEdit {"
    " color:#e8f0fa; background:#101d2e; border:1px solid #29405d;"
    " border-radius:6px; padding:4px; selection-background-color:#2a8f83; }"
    "QWidget#EditorLayerContent QCheckBox { color:#dbe7f5; }"
    "QScrollArea#EditorLayerInspector QScrollBar:vertical {"
    " background:#0b1421; width:9px; margin:0; }"
    "QScrollArea#EditorLayerInspector QScrollBar::handle:vertical {"
    " background:#314967; min-height:28px; border-radius:4px; }"
    "QScrollArea#EditorLayerInspector QScrollBar::add-line:vertical,"
    " QScrollArea#EditorLayerInspector QScrollBar::sub-line:vertical {"
    " height:0; background:transparent; }"
)


class LayerInspector(QScrollArea):
    """Edits one :class:`EditorLayer`; the page turns the payload into one command."""

    applyRequested = pyqtSignal(str, object)
    deleteRequested = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("EditorLayerInspector")
        self.setWidgetResizable(True)
        self.setMinimumWidth(0)
        self.setFrameShape(QScrollArea.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._layer_id = ""
        self._kind: EditorLayerKind | None = None
        self._duration_ms = 0
        self._rows: dict[str, tuple[QWidget, QWidget]] = {}

        content = QWidget(self)
        content.setObjectName("EditorLayerContent")
        self.setWidget(content)
        self.viewport().setObjectName("EditorLayerViewport")
        self.setStyleSheet(LAYER_INSPECTOR_STYLE)

        layout = QVBoxLayout(content)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)
        layout.addWidget(StrongBodyLabel(self.tr("Layer properties"), content))
        self.empty_label = QLabel(self.tr("Select a layer to edit"), content)
        self.empty_label.setStyleSheet("color:#71829a;")
        layout.addWidget(self.empty_label)

        self.form_widget = QWidget(content)
        form = QFormLayout(self.form_widget)
        form.setContentsMargins(0, 0, 0, 0)
        form.setSpacing(6)
        form.setLabelAlignment(Qt.AlignLeft)
        # The context panel can be ~300 px wide; wrap instead of clipping the editors.
        form.setRowWrapPolicy(QFormLayout.WrapLongRows)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)

        self.kind_label = QLabel("", self.form_widget)
        self._add_row(form, "kind", self.tr("Type"), self.kind_label)

        self.name_edit = LineEdit(self.form_widget)
        self._add_row(form, "name", self.tr("Name"), self.name_edit)

        self.start_spin, self.end_spin = QDoubleSpinBox(), QDoubleSpinBox()
        for spin in (self.start_spin, self.end_spin):
            spin.setParent(self.form_widget)
            spin.setRange(0, 24 * 60 * 60)
            spin.setDecimals(3)
            spin.setSuffix(" s")
            spin.setMinimumWidth(78)
        self._add_row(form, "timing", self.tr("Start / End"), self._pair(self.start_spin, self.end_spin))

        self.x_spin, self.y_spin = self._percent_spin(), self._percent_spin()
        self._add_row(form, "position", self.tr("X / Y (%)"), self._pair(self.x_spin, self.y_spin))
        self.width_spin, self.height_spin = self._percent_spin(minimum=0.1), self._percent_spin(minimum=0.1)
        self._add_row(form, "size", self.tr("W / H (%)"), self._pair(self.width_spin, self.height_spin))

        self.opacity_spin = QDoubleSpinBox(self.form_widget)
        self.opacity_spin.setRange(0.0, 1.0)
        self.opacity_spin.setSingleStep(0.05)
        self.opacity_spin.setDecimals(2)
        self._add_row(form, "opacity", self.tr("Opacity"), self.opacity_spin)

        self.visible_check = QCheckBox(self.tr("Visible"), self.form_widget)
        self.locked_check = QCheckBox(self.tr("Locked"), self.form_widget)
        self._add_row(form, "flags", self.tr("State"), self._pair(self.visible_check, self.locked_check))

        self.text_edit = TextEdit(self.form_widget)
        self.text_edit.setMaximumHeight(90)
        self._add_row(form, "text", self.tr("Text"), self.text_edit)

        self.font_size_spin = QSpinBox(self.form_widget)
        self.font_size_spin.setRange(8, 400)
        self.font_size_spin.setSuffix(" px")
        self._add_row(form, "font_size", self.tr("Font size"), self.font_size_spin)

        self.font_color_edit = LineEdit(self.form_widget)
        self._add_row(form, "font_color", self.tr("Text color"), self.font_color_edit)
        self.outline_color_edit = LineEdit(self.form_widget)
        self._add_row(form, "outline_color", self.tr("Outline color"), self.outline_color_edit)
        self.outline_width_spin = QSpinBox(self.form_widget)
        self.outline_width_spin.setRange(0, 20)
        self._add_row(form, "outline_width", self.tr("Outline width"), self.outline_width_spin)

        self.image_edit = LineEdit(self.form_widget)
        self.image_edit.setReadOnly(True)
        self.browse_button = PushButton(self.tr("Browse"), self.form_widget)
        self.browse_button.clicked.connect(self._browse_image)
        self._add_row(form, "image", self.tr("Image"), self._pair(self.image_edit, self.browse_button))

        self.mode_combo = QComboBox(self.form_widget)
        self.mode_combo.addItems(["solid", "pixelate", "blur"])
        self._add_row(form, "mode", self.tr("Mask mode"), self.mode_combo)
        self.color_edit = LineEdit(self.form_widget)
        self._add_row(form, "color", self.tr("Fill color"), self.color_edit)

        self.strength_spin = QSpinBox(self.form_widget)
        self.strength_spin.setRange(1, 50)
        self._add_row(form, "strength", self.tr("Strength"), self.strength_spin)

        layout.addWidget(self.form_widget)
        self.apply_button = PrimaryPushButton(self.tr("Apply changes"), content)
        self.delete_button = PushButton(self.tr("Delete layer"), content)
        self.apply_button.clicked.connect(self._emit_apply)
        self.delete_button.clicked.connect(
            lambda: self.deleteRequested.emit(self._layer_id) if self._layer_id else None
        )
        layout.addWidget(self.apply_button)
        layout.addWidget(self.delete_button)
        layout.addStretch()
        self.set_layer(None, 0)

    def _percent_spin(self, *, minimum: float = 0.0) -> QDoubleSpinBox:
        spin = QDoubleSpinBox(self.form_widget)
        spin.setRange(minimum, 100.0)
        spin.setDecimals(1)
        spin.setSingleStep(1.0)
        spin.setMinimumWidth(64)
        return spin

    def _pair(self, first: QWidget, second: QWidget) -> QWidget:
        holder = QWidget(self.form_widget)
        row = QHBoxLayout(holder)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        first.setParent(holder)
        second.setParent(holder)
        row.addWidget(first)
        row.addWidget(second)
        return holder

    def _add_row(self, form: QFormLayout, key: str, text: str, field: QWidget) -> None:
        label = QLabel(text, self.form_widget)
        form.addRow(label, field)
        self._rows[key] = (label, field)

    def _set_rows_visible(self, keys: set[str]) -> None:
        # Qt5 has no QFormLayout.setRowVisible, so both halves are toggled by hand.
        for key, (label, field) in self._rows.items():
            visible = key in keys
            label.setVisible(visible)
            field.setVisible(visible)

    @property
    def layer_id(self) -> str:
        return self._layer_id

    def _browse_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, self.tr("Add Logo"), "", self.tr("Image (*.png *.jpg *.jpeg *.webp)")
        )
        if path:
            self.image_edit.setText(path)

    def set_layer(self, layer: EditorLayer | None, duration_ms: int) -> None:
        self._duration_ms = max(0, int(duration_ms))
        self._layer_id = layer.id if layer else ""
        self._kind = layer.kind if layer else None
        self.empty_label.setVisible(layer is None)
        self.form_widget.setVisible(layer is not None)
        self.apply_button.setEnabled(layer is not None)
        self.delete_button.setEnabled(layer is not None)
        if not layer:
            return
        common = {"kind", "name", "timing", "position", "size", "opacity", "flags"}
        per_kind = {
            EditorLayerKind.TEXT: {"text", "font_size", "font_color", "outline_color", "outline_width"},
            EditorLayerKind.LOGO: {"image"},
            EditorLayerKind.MASK: {"mode", "color", "strength"},
            EditorLayerKind.BLUR: {"strength"},
        }
        self._set_rows_visible(common | per_kind.get(layer.kind, set()))

        maximum = max(0.001, self._duration_ms / 1000.0)
        for spin in (self.start_spin, self.end_spin):
            spin.setMaximum(maximum)
        self.kind_label.setText(layer.kind.value.upper())
        self.name_edit.setText(layer.name)
        self.start_spin.setValue(layer.start_ms / 1000.0)
        self.end_spin.setValue(layer.end_ms / 1000.0)
        self.x_spin.setValue(layer.x * 100.0)
        self.y_spin.setValue(layer.y * 100.0)
        self.width_spin.setValue(layer.width * 100.0)
        self.height_spin.setValue(layer.height * 100.0)
        self.opacity_spin.setValue(layer.opacity)
        self.visible_check.setChecked(layer.visible)
        self.locked_check.setChecked(layer.locked)

        properties = layer.properties
        self.text_edit.setPlainText(str(properties.get("text", "")))
        self.font_size_spin.setValue(max(8, int(properties.get("font_size", 42))))
        self.font_color_edit.setText(str(properties.get("font_color", "white")))
        self.outline_color_edit.setText(str(properties.get("outline_color", "black")))
        self.outline_width_spin.setValue(max(0, int(properties.get("outline_width", 2))))
        self.image_edit.setText(str(properties.get("path", "")))
        mode = str(properties.get("mode", "solid"))
        self.mode_combo.setCurrentIndex(max(0, self.mode_combo.findText(mode)))
        self.color_edit.setText(str(properties.get("color", "black")))
        self.strength_spin.setValue(max(1, min(50, int(properties.get("strength", 12)))))

    def pending_changes(self) -> dict[str, Any]:
        """Editor values as an :class:`EditLayerCommand` payload."""
        x = min(max(self.x_spin.value() / 100.0, 0.0), 0.999)
        y = min(max(self.y_spin.value() / 100.0, 0.0), 0.999)
        width = max(0.001, min(self.width_spin.value() / 100.0, 1.0 - x))
        height = max(0.001, min(self.height_spin.value() / 100.0, 1.0 - y))
        changes: dict[str, Any] = {
            "name": self.name_edit.text().strip(),
            "start_ms": int(round(self.start_spin.value() * 1000)),
            "end_ms": int(round(self.end_spin.value() * 1000)),
            "x": x,
            "y": y,
            "width": width,
            "height": height,
            "opacity": round(self.opacity_spin.value(), 3),
            "visible": self.visible_check.isChecked(),
            "locked": self.locked_check.isChecked(),
        }
        properties: dict[str, Any] = {}
        if self._kind == EditorLayerKind.TEXT:
            properties = {
                "text": self.text_edit.toPlainText(),
                "font_size": self.font_size_spin.value(),
                "font_color": self.font_color_edit.text().strip() or "white",
                "outline_color": self.outline_color_edit.text().strip() or "black",
                "outline_width": self.outline_width_spin.value(),
            }
        elif self._kind == EditorLayerKind.LOGO:
            properties = {"path": self.image_edit.text().strip()}
        elif self._kind == EditorLayerKind.MASK:
            properties = {
                "mode": self.mode_combo.currentText(),
                "color": self.color_edit.text().strip() or "black",
                "strength": self.strength_spin.value(),
            }
        elif self._kind == EditorLayerKind.BLUR:
            properties = {"strength": self.strength_spin.value()}
        if properties:
            changes["properties"] = properties
        return changes

    def _emit_apply(self) -> None:
        if self._layer_id:
            self.applyRequested.emit(self._layer_id, self.pending_changes())

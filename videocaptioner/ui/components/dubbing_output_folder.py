"""Shared optional destination control for Batch and manual dubbing."""

from PyQt5.QtWidgets import QFileDialog, QHBoxLayout, QWidget
from qfluentwidgets import BodyLabel, LineEdit, PushButton

from videocaptioner.ui.common.config import cfg


class DubbingOutputFolder(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(BodyLabel(self.tr("Dubbed video folder:")))
        self.edit = LineEdit()
        self.edit.setPlaceholderText(self.tr("Leave empty to save beside each source video"))
        self.edit.setText(cfg.dubbing_output_dir.value)
        layout.addWidget(self.edit, 1)
        self.browse_btn = PushButton(self.tr("Browse"))
        self.clear_btn = PushButton(self.tr("Use source folder"))
        layout.addWidget(self.browse_btn)
        layout.addWidget(self.clear_btn)
        self.edit.textChanged.connect(self._save)
        cfg.dubbing_output_dir.valueChanged.connect(self._sync)
        self.browse_btn.clicked.connect(self._browse)
        self.clear_btn.clicked.connect(self.edit.clear)

    def _save(self, text):
        if cfg.dubbing_output_dir.value != text:
            cfg.set(cfg.dubbing_output_dir, text)

    def _sync(self, text):
        if self.edit.text() != text:
            self.edit.setText(text)

    def _browse(self):
        directory = QFileDialog.getExistingDirectory(self, self.tr("Choose dubbed video folder"), self.edit.text())
        if directory:
            self.edit.setText(directory)

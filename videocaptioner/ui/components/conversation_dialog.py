"""Explicit local context editing; opening the dialog never starts inference."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, cast
from uuid import uuid4

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from videocaptioner.core.translate.conversation import (
    ConversationContext,
    SourceCue,
    prepare_snapshot,
)


class ConversationDialog(QDialog):
    """Tables expose stable IDs, evidence and scope without hiding unknown associations."""

    COLUMNS = {
        "characters": ("id", "label"),
        "scenes": ("id", "label", "cue_ids"),
        "mappings": ("id", "speaker_id", "character_id", "scene_id", "cue_ids"),
        "assignments": ("id", "speaker_id", "addressee_ids", "mentioned_ids", "mode", "scene_id", "cue_ids"),
        "rules": ("id", "speaker_id", "addressee_ids", "self_term", "address_term", "scene_id", "cue_ids"),
    }

    def __init__(self, context: ConversationContext, cues: tuple[SourceCue, ...], parent=None):
        super().__init__(parent)
        self.context = context
        self.cues = cues
        self.tables: dict[str, QTableWidget] = {}
        self.setWindowTitle(self.tr("Conversation context"))
        self.resize(1080, 700)
        layout = QVBoxLayout(self)
        help_text = QLabel(self.tr(
            "LLM translation uses these rules; Google/Bing/DeepLX preserve data but do not apply them. "
            "Blank listener means unknown; comma-separated character IDs mean a group. "
            "Rules are speaker → listener. Cue IDs limit a turn; scene IDs limit a scene; blank scope means document. "
            "Only confirmed/locked evidence applies. Apply is an explicit user edit, including unlocking. "
            "Save JSON to retain context; SRT loses it."
        ), self)
        help_text.setWordWrap(True)
        layout.addWidget(help_text)
        self.tabs = QTabWidget(self)
        layout.addWidget(self.tabs, 1)
        labels = (self.tr("Characters"), self.tr("Scenes"), self.tr("Speaker mappings"),
                  self.tr("Speakers and listeners"), self.tr("Directed rules"))
        for (name, columns), label in zip(self.COLUMNS.items(), labels):
            page = QWidget(self.tabs)
            page_layout = QVBoxLayout(page)
            table = QTableWidget(0, len(columns) + 3, page)
            headers = (*columns, "source", "status", "evidence_cue_ids")
            table.setHorizontalHeaderLabels([self.tr(h) for h in headers])
            table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
            table.horizontalHeader().setDefaultSectionSize(155)
            table.setHorizontalScrollMode(QTableWidget.ScrollPerPixel)
            self.tables[name] = table
            page_layout.addWidget(table)
            buttons = QHBoxLayout()
            add = QPushButton(self.tr("Add"), page)
            remove = QPushButton(self.tr("Remove selected"), page)
            add.clicked.connect(lambda _=False, n=name: self.add_row(n))
            remove.clicked.connect(lambda _=False, n=name: self.remove_rows(n))
            buttons.addWidget(add)
            buttons.addWidget(remove)
            buttons.addStretch()
            page_layout.addLayout(buttons)
            self.tabs.addTab(page, label)
            for item in getattr(context, name):
                self.add_row(name, asdict(item))
        sources = QTextEdit(self)
        sources.setReadOnly(True)
        sources.setPlainText("\n".join(f"{i}. {c.id} | {c.speaker or 'unknown'} | {c.text}"
                                       for i, c in enumerate(cues, 1)))
        self.tabs.addTab(sources, self.tr("Source cues (IDs and evidence)"))
        self.review = QTextEdit(self)
        self.review.setReadOnly(True)
        self.review.setMaximumHeight(145)
        layout.addWidget(self.review)
        controls = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        controls.button(QDialogButtonBox.Ok).setText(self.tr("Apply"))
        check = controls.addButton(self.tr("Review context"), QDialogButtonBox.ActionRole)
        check.clicked.connect(self.review_context)
        controls.accepted.connect(self.apply)
        controls.rejected.connect(self.reject)
        layout.addWidget(controls)
        self.validate_context()

    def add_row(self, name: str, data: dict | None = None) -> None:
        raw: dict[str, Any] = dict(data or {"id": uuid4().hex[:12]})
        raw.update(raw.pop("scope", {}))
        evidence = raw.pop("evidence", {})
        raw.update(source=evidence.get("source", "user"), status=evidence.get("status", "confirmed"),
                   evidence_cue_ids=evidence.get("cue_ids", []))
        table = self.tables[name]
        row = table.rowCount()
        table.insertRow(row)
        for col, field in enumerate((*self.COLUMNS[name], "source", "status", "evidence_cue_ids")):
            value = raw.get(field, "unknown" if field == "mode" else "")
            if isinstance(value, (tuple, list)):
                value = ", ".join(value)
            options = {"source": ("user", "text"), "status": ("unknown", "proposed", "confirmed", "locked"),
                       "mode": ("unknown", "dialogue", "narration", "quotation")}.get(field)
            references = []
            if field in ("character_id", "speaker_id", "scene_id"):
                if name == "mappings" and field == "speaker_id":
                    references = [(s, s) for s in sorted({c.speaker for c in self.cues if c.speaker})]
                else:
                    reference_table = self.tables.get("scenes" if field == "scene_id" else "characters")
                    if reference_table is not None:
                        references = [(reference_table.item(r, 1).text(), reference_table.item(r, 0).text())
                                      for r in range(reference_table.rowCount())]
            if references:
                combo = QComboBox(table)
                combo.addItem(self.tr("Unknown / document"), "")
                for label, identity in references:
                    combo.addItem(f"{label} [{identity}]", identity)
                index = combo.findData(str(value))
                if index >= 0:
                    combo.setCurrentIndex(index)
                else:
                    combo.addItem(str(value), str(value))
                    combo.setCurrentIndex(combo.count() - 1)
                table.setCellWidget(row, col, combo)
            elif options:
                combo = QComboBox(table)
                for option in options:
                    combo.addItem(self.tr(option), option)
                combo.setCurrentIndex(max(0, combo.findData(str(value))))
                table.setCellWidget(row, col, combo)
            else:
                item = QTableWidgetItem(str(value))
                if field == "id":
                    item.setFlags(cast(Qt.ItemFlags, item.flags() & ~Qt.ItemFlag.ItemIsEditable))
                table.setItem(row, col, item)

    def remove_rows(self, name: str) -> None:
        table = self.tables[name]
        for row in sorted({i.row() for i in table.selectedIndexes()}, reverse=True):
            table.removeRow(row)

    def read_context(self) -> ConversationContext:
        payload = {}
        for name, columns in self.COLUMNS.items():
            table = self.tables[name]
            rows = []
            for row in range(table.rowCount()):
                raw = {}
                for col, key in enumerate((*columns, "source", "status", "evidence_cue_ids")):
                    widget = table.cellWidget(row, col)
                    item = table.item(row, col)
                    if isinstance(widget, QComboBox):
                        value = widget.currentData() if widget.currentData() is not None else widget.currentText()
                    else:
                        value = item.text() if item else ""
                    raw[key] = [i.strip() for i in value.split(",") if i.strip()] if key.endswith("_ids") else value
                raw["evidence"] = {"source": raw.pop("source"), "status": raw.pop("status"),
                                   "cue_ids": raw.pop("evidence_cue_ids")}
                if name in ("mappings", "assignments", "rules"):
                    raw["scope"] = {"scene_id": raw.pop("scene_id"), "cue_ids": raw.pop("cue_ids")}
                rows.append(raw)
            payload[name] = rows
        return ConversationContext.from_dict(payload)

    def validate_context(self) -> bool:
        try:
            context = self.read_context()
            snapshot = prepare_snapshot(self.cues, context)
            issues = [self.tr(issue) for issue in snapshot.review]
            issues.extend(f"{cue.id}: {', '.join(self.tr(issue) for issue in cue.review)}"
                          for cue in snapshot.resolved if cue.review)
            self.review.setPlainText("\n".join(issues) or self.tr("No unresolved context entries."))
            return True
        except ValueError as exc:
            self.review.setPlainText(str(exc))
            return False

    def review_context(self) -> None:
        self.validate_context()

    def apply(self) -> None:
        if self.validate_context():
            self.context = self.read_context()
            self.accept()

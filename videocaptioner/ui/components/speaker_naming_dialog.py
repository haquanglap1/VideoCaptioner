"""Review table for LLM-proposed speaker names; opening it never sends a request."""

from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)
from qfluentwidgets import isDarkTheme

from videocaptioner.core.asr.asr_data import ASRData
from videocaptioner.core.asr.local.speaker_naming import speaker_clusters

SAMPLE_LINES = 3


class SpeakerNamingDialog(QDialog):
    """One row per cluster: proposal, confidence and sample lines; the name cell is editable."""

    COLUMNS = ("Cluster", "Lines", "Name", "Role", "Gender", "Age", "Confidence", "Status", "Sample lines")

    def __init__(self, document: ASRData, parent=None):
        super().__init__(parent)
        self.document = document
        self.decisions: dict[str, str] = {}
        naming = document.speaker_naming
        self.profiles = tuple(sorted(naming.profiles, key=lambda p: (p.status != "proposed", p.label))) if naming else ()
        self.setWindowTitle(self.tr("Speaker names (AI)"))
        self.resize(1080, 560)
        if isDarkTheme():
            self.setStyleSheet("QDialog { background: #202733; color: #e6edf6; } QLabel { color: #e6edf6; }")
        layout = QVBoxLayout(self)
        guide = QLabel(self.tr(
            "The LLM proposed a name for each diarized cluster from the dialogue and your series notes. "
            "Confident names are already applied to the conversation context; rows marked 'proposed' need you. "
            "Edit the Name cell, clear it to leave a cluster unknown, then Apply. Names stay in JSON only; "
            "SRT never prints them."))
        guide.setWordWrap(True)
        layout.addWidget(guide)
        if naming is not None:
            summary = self.tr("Model: {0}. {1} cluster(s), {2} to confirm.").format(
                naming.model, len(naming.profiles), len(naming.pending))
            if naming.sampled:
                summary += " " + self.tr("The transcript was sampled (head, middle, tail).")
            label = QLabel(summary)
            label.setWordWrap(True)
            layout.addWidget(label)
        self.table = QTableWidget(len(self.profiles), len(self.COLUMNS), self)
        self.table.setHorizontalHeaderLabels([self.tr(column) for column in self.COLUMNS])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setWordWrap(True)
        samples = self._samples()
        for row, profile in enumerate(self.profiles):
            values = (profile.label, str(len(samples.get(profile.speaker_id, ())[1])), profile.name, profile.role,
                      self.tr(profile.gender), self.tr(profile.age_group), f"{profile.confidence:.2f}",
                      self.tr(profile.status), "\n".join(samples.get(profile.speaker_id, ("", ()))[0]))
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setToolTip(value)
                if column != 2:
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)  # type: ignore[operator]
                self.table.setItem(row, column, item)
        self.table.resizeColumnsToContents()
        self.table.resizeRowsToContents()
        layout.addWidget(self.table, 1)
        controls = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        controls.button(QDialogButtonBox.Ok).setText(self.tr("Apply names"))
        controls.button(QDialogButtonBox.Cancel).setText(self.tr("Later"))
        controls.accepted.connect(self.apply)
        controls.rejected.connect(self.reject)
        layout.addWidget(controls)

    def _samples(self) -> dict[str, tuple[list[str], tuple[str, ...]]]:
        texts = {seg.cue_id: seg.text for seg in self.document.segments}
        result = {}
        for cluster in speaker_clusters(self.document):
            lines = [texts[c] for c in cluster.cue_ids[:SAMPLE_LINES] if c in texts]
            result[cluster.speaker_id] = (lines, cluster.cue_ids)
        return result

    def read_decisions(self) -> dict[str, str]:
        """Only rows the user changed, plus every pending row, become decisions."""
        decisions = {}
        for row, profile in enumerate(self.profiles):
            item = self.table.item(row, 2)
            name = " ".join((item.text() if item else "").split())
            if name != profile.name or profile.status == "proposed":
                decisions[profile.speaker_id] = name
        return decisions

    def apply(self) -> None:
        self.decisions = self.read_decisions()
        self.accept()

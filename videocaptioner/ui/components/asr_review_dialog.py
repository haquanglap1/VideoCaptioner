"""Explicit local timing review. Opening, editing and resuming never call a provider."""

from pathlib import Path

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from videocaptioner.core.asr.review import (
    EditReviewTimingCommand,
    NativeReview,
    ReviewSession,
)
from videocaptioner.core.editor.commands import CommandStack


class ASRReviewDialog(QDialog):
    def __init__(self, review: NativeReview, parent=None, *, review_path: Path | None = None):
        super().__init__(parent)
        self.session = ReviewSession(review)
        self.review_path = review_path
        self.stack = CommandStack()
        self.stack.add_changed_callback(self.refresh)
        self.setWindowTitle(self.tr("ASR timing review"))
        self.resize(1080, 720)
        layout = QVBoxLayout(self)
        notice = QLabel(self.tr("Local review: no upload. Select a token, enter measured milliseconds, then Apply. Edited timing is marked as a user override."))
        notice.setWordWrap(True)
        layout.addWidget(notice)
        if getattr(review, "pending_diarization", False):
            pending = QLabel(self.tr("Local diarization is still pending. This review exports timing only; run local-diarize with the saved JSON and original audio."))
            pending.setWordWrap(True)
            layout.addWidget(pending)
        self.transcript = QPlainTextEdit(review.text)
        self.transcript.setReadOnly(True)
        self.transcript.setMaximumHeight(110)
        layout.addWidget(self.transcript)
        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels([self.tr(s) for s in
            ("Token ID", "Speaker", "Text", "Original start", "Original end", "Start (ms)", "End (ms)", "Review / provenance")])
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.itemSelectionChanged.connect(self.select_token)
        layout.addWidget(self.table)
        edit_row = QHBoxLayout()
        self.start_ms, self.end_ms = QSpinBox(), QSpinBox()
        for label, spin in (("Start (ms)", self.start_ms), ("End (ms)", self.end_ms)):
            spin.setRange(0, min(review.duration_ms, 2_147_483_647))
            edit_row.addWidget(QLabel(self.tr(label)))
            edit_row.addWidget(spin)
        for label, callback in (("Apply timing override", self.apply_timing), ("Undo", self.stack.undo), ("Redo", self.stack.redo)):
            button = QPushButton(self.tr(label))
            def invoke(_checked=False, action=callback):
                action()
            button.clicked.connect(invoke)
            edit_row.addWidget(button)
        layout.addLayout(edit_row)
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.status)
        actions = QHBoxLayout()
        for label, callback in (("Save review as…", self.save_review), ("Validate and export…", self.export_result), ("Close", self.reject)):
            button = QPushButton(self.tr(label))
            button.clicked.connect(callback)
            actions.addWidget(button)
        layout.addLayout(actions)
        self.refresh()
        issues = review.issues()
        if issues:
            self.table.selectRow(issues[0].index)

    def refresh(self):
        review = self.session.review
        selected = self.table.currentRow()
        issues = {i.token_id: i.reason for i in review.issues()}
        edits = {o.token_id for o in review.overrides}
        self.table.blockSignals(True)
        self.table.setRowCount(len(review.tokens))
        for row, token in enumerate(review.tokens):
            times = review.timing_ms(token)
            values = (token.id, token.speaker or self.tr("Unknown"), token.text,
                      str(token.start), str(token.end), str(times[0]) if times else "?",
                      str(times[1]) if times else "?",
                      self.tr(issues[token.id]) if token.id in issues else
                      self.tr("Edited by user") if token.id in edits else
                      self.tr("Aligned") if review.provider not in ("soniox", "scribe") else self.tr("Native"))
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setToolTip(value)
                self.table.setItem(row, col, item)
        self.table.resizeColumnsToContents()
        self.table.blockSignals(False)
        if selected >= 0:
            self.table.selectRow(selected)
            self.select_token()
        units = "s" if review.provider == "scribe" else "ms"
        self.status.setText(self.tr("{0} token timing issue(s). Original units: {1}. Full validation is required before export.").format(len(issues), units))

    def select_token(self):
        row = self.table.currentRow()
        if 0 <= row < len(self.session.review.tokens):
            times = self.session.review.timing_ms(self.session.review.tokens[row])
            self.start_ms.setValue(times[0] if times else 0)
            self.end_ms.setValue(times[1] if times else 0)

    def apply_timing(self):
        row = self.table.currentRow()
        if row < 0:
            return
        try:
            self.stack.execute(EditReviewTimingCommand(self.session, self.session.review.tokens[row].id,
                                                      self.start_ms.value(), self.end_ms.value()))
        except ValueError as exc:
            self.status.setText(str(exc))

    def save_review(self):
        path, _ = QFileDialog.getSaveFileName(self, self.tr("Save ASR review"), "recognition.asr-review.json", "JSON (*.json)")
        if path:
            try:
                self.session.review.save(path)
                self.review_path = Path(path)
                self.status.setText(self.tr("Review saved. Reopen this JSON to continue without uploading."))
            except OSError:
                self.status.setText(self.tr("Cannot save review file."))

    def export_result(self):
        try:
            data = self.session.review.resume()
        except ValueError as exc:
            self.status.setText(str(exc))
            return
        path, _ = QFileDialog.getSaveFileName(self, self.tr("Export validated subtitles"), "reviewed-subtitles.json",
                                             "JSON (*.json);;SRT (*.srt)")
        if not path:
            return
        try:
            if self.review_path is not None and Path(path).resolve() == self.review_path.resolve():
                raise ValueError(self.tr("Subtitle output must not replace the review file."))
            if Path(path).suffix.lower() not in (".json", ".srt"):
                raise ValueError(self.tr("Choose JSON or SRT."))
            data.save(path)
            self.status.setText(self.tr("Full result exported. JSON retains cue IDs and edited provenance; SRT does not."))
        except (OSError, ValueError) as exc:
            self.status.setText(str(exc))

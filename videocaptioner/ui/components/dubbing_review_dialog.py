"""Edit spoken group wording while keeping cue and display text intact."""

from PyQt5.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from videocaptioner.core.dubbing.review import DubbingReview


class DubbingReviewDialog(QDialog):
    def __init__(self, review: DubbingReview, parent=None):
        super().__init__(parent)
        self.review = review
        self.plan = review.plan
        plan = self.plan
        self._row = -1
        self.setWindowTitle(self.tr("Duyệt lời đọc lồng tiếng"))
        self.resize(1040, 680)
        layout = QVBoxLayout(self)
        hint = QLabel(self.tr(
            "Sửa lời đọc riêng cho từng nhóm. Phụ đề hiển thị, cue và nhóm được giữ nguyên. "
            "Áp dụng chỉ giữ trong RAM; chọn Lưu kế hoạch ở tab Lồng tiếng để lưu ra file."
        ))
        hint.setWordWrap(True)
        layout.addWidget(hint)
        identity = QLabel(f"{plan.provider} | {plan.model} | {plan.voice} | {plan.timing_mode.value}")
        identity.setWordWrap(True)
        layout.addWidget(identity)
        splitter = QSplitter(self)
        self.table = QTableWidget(len(plan.groups), 3)
        self.table.setHorizontalHeaderLabels([self.tr("Nhóm / cue"), self.tr("Thời gian"), self.tr("Trạng thái")])
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.verticalHeader().hide()
        for row, group in enumerate(plan.groups):
            values = [
                f"{group.group_id} ({', '.join(map(str, group.cue_ids))})",
                f"{group.start_time:.2f}–{group.subtitle_end_time:.2f}s",
                group.fit_status.value,
            ]
            for column, value in enumerate(values):
                self.table.setItem(row, column, QTableWidgetItem(value))
        self.table.resizeColumnsToContents()
        splitter.addWidget(self.table)
        details = QWidget()
        fields = QVBoxLayout(details)
        self.source_text = self._text_field(fields, self.tr("Nguyên văn nguồn"))
        self.subtitle_text = self._text_field(fields, self.tr("Nội dung phụ đề của nhóm"))
        self.original_tts_text = self._text_field(fields, self.tr("Lời đọc trước rewrite"))
        self.issue_label = QLabel()
        self.issue_label.setWordWrap(True)
        fields.addWidget(self.issue_label)
        self.tts_text = self._text_field(fields, self.tr("Lời đọc đã duyệt (có thể sửa)"), editable=True)
        splitter.addWidget(details)
        splitter.setSizes([400, 600])
        layout.addWidget(splitter)
        self.error_label = QLabel()
        self.error_label.setWordWrap(True)
        layout.addWidget(self.error_label)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText(self.tr("Áp dụng lời đọc"))
        buttons.button(QDialogButtonBox.Cancel).setText(self.tr("Hủy thay đổi"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        row_layout = QHBoxLayout()
        row_layout.addStretch()
        row_layout.addWidget(buttons)
        layout.addLayout(row_layout)
        self.table.currentCellChanged.connect(self._select_group)
        if plan.groups:
            self.table.selectRow(next((i for i, g in enumerate(plan.groups) if g.needs_review), 0))

    @staticmethod
    def _text_field(layout, label: str, *, editable: bool = False) -> QPlainTextEdit:
        layout.addWidget(QLabel(label))
        editor = QPlainTextEdit()
        editor.setReadOnly(not editable)
        editor.setMinimumHeight(65)
        layout.addWidget(editor)
        return editor

    def _store_wording(self) -> None:
        if self._row >= 0:
            self.plan.groups[self._row].tts_text = self.tts_text.toPlainText()

    def _select_group(self, row: int, _column: int, _old_row: int, _old_column: int) -> None:
        self._store_wording()
        self._row = row
        if row < 0:
            return
        group = self.plan.groups[row]
        self.source_text.setPlainText(group.source_text)
        self.subtitle_text.setPlainText(group.subtitle_text)
        self.original_tts_text.setPlainText(group.original_tts_text or self.tr("Checkpoint không có lời trước rewrite."))
        self.tts_text.setPlainText(group.tts_text)
        self.issue_label.setText(self.tr(
            "Khung: {available:.2f}s | Audio đã đo: {measured:.2f}s | Trễ: {delay:.2f}s | "
            "Tốc độ: {speed:.2f}×\n{issues}\nTiming sẽ được đo lại khi tiếp tục."
        ).format(available=group.available_duration, measured=group.measured_duration,
                 delay=group.start_delay, speed=group.applied_speed,
                 issues=" | ".join([group.action_taken, *group.warnings])))

    def accept(self) -> None:
        self._store_wording()
        empty = next((g.group_id for g in self.plan.groups if not g.tts_text.strip()), "")
        if empty:
            self.error_label.setText(self.tr("Lời đọc không được để trống: ") + empty)
            return
        review = self.review
        for original, edited in zip(review.groups, self.plan.groups):
            if original.tts_text != edited.tts_text:
                review = review.with_group_text(edited.group_id, edited.tts_text)
        self.review = review
        super().accept()

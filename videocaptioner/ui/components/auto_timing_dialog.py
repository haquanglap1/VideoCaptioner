"""Review predicted tradeoffs separately from the measured candidate."""

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QTableWidgetItem,
    QVBoxLayout,
)
from qfluentwidgets import (
    BodyLabel,
    PrimaryPushButton,
    PushButton,
    StrongBodyLabel,
    TableWidget,
    isDarkTheme,
)

from videocaptioner.core.dubbing.auto_timing import AutoTimingPlan, TimingCandidate

DECISION_LABELS = {
    "llm": "LLM chọn trong các phương án hợp lệ của solver",
    "solver": "Solver tất định (không dùng LLM)",
    "solver-fallback": "Solver (LLM tắt, lỗi, timeout hoặc thiếu cấu hình)",
}
REFINED_SUFFIX = "+refined"
COLUMNS = ("Trạng thái", "Giọng ×", "Video ×", "Video (s)", "Trễ max (ms)", "Trễ p95 (ms)",
           "Vượt cuối (ms)", "Vượt biên (ms)", "Nhóm cần review")
MEASURED, PREDICTED = "Đã đo / chọn", "Dự báo"


def decision_label(source: str) -> str:
    """Vietnamese wording for the core's decision_source token, keeping unknown tokens visible."""
    refined = source.endswith(REFINED_SUFFIX)
    base = source[: -len(REFINED_SUFFIX)] if refined else source
    text = DECISION_LABELS.get(base, base)
    if refined:
        text += " + solver giảm thêm tốc độ video sau khi đo media thật"
    return text


def headline(proposal: AutoTimingPlan) -> str:
    selected = proposal.selected
    if proposal.can_apply and selected is not None:
        return (f"Đã đo: giọng {selected.voice_tempo:.2f}× · video {selected.video_speed:.2f}× · "
                f"trễ tối đa {selected.max_delay_ms} ms · không vượt biên/cuối video. Có thể áp dụng.")
    if selected is not None:
        return (f"Phương án đã đo (giọng {selected.voice_tempo:.2f}× / video {selected.video_speed:.2f}×) "
                f"vẫn còn {selected.review_groups} nhóm cần review; chưa áp dụng được.")
    return "Chưa có phương án đo được trong giới hạn; giữ nguyên WAV và lời đã duyệt."


class AutoTimingDialog(QDialog):
    def __init__(self, proposal: AutoTimingPlan, parent=None):
        super().__init__(parent)
        self.proposal = proposal
        self.preview_requested = False
        self.setObjectName("AutoTimingDialog")
        self.setWindowTitle("Tự căn timing/tốc độ")
        self.resize(1000, 560)
        self._apply_theme()
        layout = QVBoxLayout(self)
        summary = StrongBodyLabel(headline(proposal))
        summary.setWordWrap(True)
        layout.addWidget(summary)
        explanation = BodyLabel(f"Nguồn quyết định: {decision_label(proposal.decision_source)}\n{proposal.reason}")
        explanation.setTextFormat(Qt.TextFormat.PlainText)
        explanation.setWordWrap(True)
        layout.addWidget(explanation)
        self.table = TableWidget(self)
        self.table.setColumnCount(len(COLUMNS))
        self.table.setHorizontalHeaderLabels(list(COLUMNS))
        self.table.verticalHeader().hide()
        self.table.setWordWrap(False)
        rows = ([proposal.selected] if proposal.selected else []) + list(proposal.candidates)
        self.table.setRowCount(len(rows))
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        for row, candidate in enumerate(rows):
            self._fill_row(row, candidate)
        layout.addWidget(self.table, 1)
        note = BodyLabel("Dự báo tính từ WAV nguồn và tempo, chưa đo media. Áp dụng chỉ dùng dòng đã đo. "
                         "Có thể chỉnh tay tempo/video ở tab Lồng tiếng; chỉnh tay sẽ bỏ nhãn Auto và kiểm lại "
                         "khi xuất. Chưa nghiệm thu chất lượng nghe.")
        note.setWordWrap(True)
        layout.addWidget(note)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.apply_button = PrimaryPushButton("Áp dụng")
        self.preview_button = PushButton("Áp dụng / Xem trước")
        close = PushButton("Đóng")
        for button in (self.apply_button, self.preview_button):
            button.setEnabled(proposal.can_apply)
            buttons.addWidget(button)
        buttons.addWidget(close)
        self.apply_button.clicked.connect(self.accept)
        self.preview_button.clicked.connect(self._preview)
        close.clicked.connect(self.reject)
        layout.addLayout(buttons)

    def _apply_theme(self):
        # A bare QDialog keeps the native light palette while Fluent labels/tables draw
        # white text for the forced dark theme; pin the dialog colors to the active theme.
        background, foreground = ("#202020", "#f0f0f0") if isDarkTheme() else ("#fafafa", "#202020")
        self.setStyleSheet(f"QDialog#AutoTimingDialog {{ background-color: {background}; color: {foreground}; }}")

    def _fill_row(self, row: int, candidate: TimingCandidate):
        values = [MEASURED if candidate.measured else PREDICTED, f"{candidate.voice_tempo:.2f}",
                  f"{candidate.video_speed:.2f}", f"{candidate.video_duration:.3f}", candidate.max_delay_ms,
                  candidate.p95_delay_ms, candidate.end_overrun_ms, candidate.boundary_overrun_ms,
                  candidate.review_groups]
        tooltip = ("Đã render tempo và đo video/WAV thật." if candidate.measured
                   else "Dự báo từ WAV nguồn chia tempo; chỉ dòng đã đo mới áp dụng được.")
        font = QFont()
        font.setBold(candidate.measured)
        for column, value in enumerate(values):
            item = QTableWidgetItem(str(value))
            item.setToolTip(tooltip)
            item.setFont(font)
            if column:
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, column, item)

    def _preview(self):
        self.preview_requested = True
        self.accept()

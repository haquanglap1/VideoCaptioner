"""Review predicted tradeoffs separately from the measured candidate."""

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QTableWidgetItem,
    QVBoxLayout,
)
from qfluentwidgets import BodyLabel, PushButton, TableWidget

from videocaptioner.core.dubbing.auto_timing import AutoTimingPlan


class AutoTimingDialog(QDialog):
    def __init__(self, proposal: AutoTimingPlan, parent=None):
        super().__init__(parent)
        self.proposal = proposal
        self.preview_requested = False
        self.setWindowTitle("Tự căn timing/tốc độ")
        self.resize(1000, 560)
        layout = QVBoxLayout(self)
        explanation = BodyLabel(f"Nguồn quyết định: {proposal.decision_source}\n{proposal.reason}")
        explanation.setTextFormat(Qt.TextFormat.PlainText)
        explanation.setWordWrap(True)
        layout.addWidget(explanation)
        self.table = TableWidget(self)
        self.table.setColumnCount(9)
        self.table.setHorizontalHeaderLabels(["Trạng thái", "Giọng ×", "Video ×", "Video (s)",
            "Trễ max (ms)", "Trễ p95 (ms)", "Vượt cuối (ms)", "Vượt biên (ms)", "Review"])
        rows = ([proposal.selected] if proposal.selected else []) + list(proposal.candidates)
        self.table.setRowCount(len(rows))
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        for row, candidate in enumerate(rows):
            values = ["Đã đo / chọn" if candidate.measured else "Dự báo", f"{candidate.voice_tempo:.2f}",
                f"{candidate.video_speed:.2f}", f"{candidate.video_duration:.3f}", candidate.max_delay_ms,
                candidate.p95_delay_ms, candidate.end_overrun_ms, candidate.boundary_overrun_ms, candidate.review_groups]
            for column, value in enumerate(values):
                self.table.setItem(row, column, QTableWidgetItem(str(value)))
        layout.addWidget(self.table)
        note = BodyLabel("Áp dụng dùng dòng đã đo. Có thể chỉnh tay tempo/video ở tab Lồng tiếng; "
                         "chỉnh tay sẽ bỏ nhãn Auto và kiểm lại khi xuất. Chưa nghiệm thu chất lượng nghe.")
        note.setWordWrap(True)
        layout.addWidget(note)
        buttons = QHBoxLayout()
        self.apply_button = PushButton("Áp dụng")
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

    def _preview(self):
        self.preview_requested = True
        self.accept()

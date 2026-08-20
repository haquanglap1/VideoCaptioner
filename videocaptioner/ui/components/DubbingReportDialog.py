"""Read-only Natural Dubbing in-memory report viewer."""

from PyQt5.QtWidgets import QHeaderView, QTableWidget, QTableWidgetItem
from qfluentwidgets import BodyLabel, MessageBoxBase, StrongBodyLabel, TableWidget


class DubbingReportDialog(MessageBoxBase):
    def __init__(self, data: dict, parent=None):
        super().__init__(parent)
        summary = data.get("summary", {})

        self.titleLabel = StrongBodyLabel(self.tr("Báo cáo lồng tiếng"), self)
        counters = self.tr(
            "Tổng: {total} | Phù hợp: {fit} | Cache: {cache} | Viết lại: {rewrite} | "
            "Cần xem lại: {review} | Lỗi: {failed}"
        ).format(
            total=summary.get("total_groups", 0),
            fit=summary.get("fit_groups", 0),
            cache=summary.get("cache_hits", 0),
            rewrite=summary.get("rewritten_groups", 0),
            review=summary.get("review_groups", 0),
            failed=summary.get("failed_groups", 0),
        )
        self.summaryLabel = BodyLabel(counters, self)

        columns = [
            self.tr("Group"),
            self.tr("Thời gian"),
            self.tr("Subtitle"),
            self.tr("TTS text"),
            self.tr("Khả dụng"),
            self.tr("Đã đo"),
            self.tr("Tỷ lệ"),
            self.tr("Lần thử"),
            self.tr("Hành động"),
            self.tr("Trạng thái / cảnh báo"),
        ]
        groups = data.get("groups", [])
        self.table = TableWidget(self)
        self.table.setColumnCount(len(columns))
        self.table.setHorizontalHeaderLabels(columns)
        self.table.setRowCount(len(groups))
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.verticalHeader().hide()
        self.table.setMinimumSize(980, 420)
        for row, group in enumerate(groups):
            ratio = group.get("fit_ratio")
            values = [
                group.get("group_id", ""),
                f"{float(group.get('start_time', 0)):.2f}-{float(group.get('subtitle_end_time', 0)):.2f}s",
                group.get("subtitle_text", ""),
                group.get("tts_text", ""),
                f"{float(group.get('available_duration', 0)):.2f}s",
                f"{float(group.get('measured_duration', 0)):.2f}s",
                f"{float(ratio):.3f}" if ratio is not None else "n/a",
                str(group.get("attempt_count", 0)),
                group.get("action_taken", ""),
                " | ".join(
                    [group.get("fit_status", ""), *group.get("warnings", [])]
                ),
            ]
            for column, value in enumerate(values):
                self.table.setItem(row, column, QTableWidgetItem(str(value)))
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.Stretch)

        self.viewLayout.addWidget(self.titleLabel)
        self.viewLayout.addWidget(self.summaryLabel)
        self.viewLayout.addWidget(self.table)
        self.yesButton.hide()
        self.cancelButton.setText(self.tr("Đóng"))
        self.widget.setMinimumWidth(1040)

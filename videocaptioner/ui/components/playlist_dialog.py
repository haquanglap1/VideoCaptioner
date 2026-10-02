"""Inspect, select and download playlist entries before explicitly handing off local videos."""

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QTableWidgetItem,
    QVBoxLayout,
)
from qfluentwidgets import (
    BodyLabel,
    ComboBox,
    LineEdit,
    PushButton,
    TableWidget,
    isDarkTheme,
    qconfig,
)

from videocaptioner.core.playlist import PlaylistInfo, PlaylistItemResult, PlaylistResult
from videocaptioner.ui.thread.playlist_thread import PlaylistThread
from videocaptioner.ui.thread.worker_lifecycle import retain_worker


class PlaylistDialog(QDialog):
    files_ready = pyqtSignal(list)

    def __init__(self, url: str, output: str, cookies: str, parent=None):
        super().__init__(parent)
        self.setObjectName("PlaylistDialog")
        self._apply_theme()
        qconfig.themeChangedFinished.connect(self._apply_theme)
        self.setWindowTitle("Tải playlist /合集 Bilibili")
        self.resize(1000, 650)
        self.cookies = cookies
        self.info: PlaylistInfo | None = None
        self._worker: PlaylistThread | None = None
        self._closing = False
        self._result = None
        self._error = ""
        self.completed: dict[int, str] = {}
        layout = QVBoxLayout(self)
        self.url_edit = LineEdit()
        self.url_edit.setPlaceholderText("Link video trong合集, link danh sách hoặc video nhiều phần P")
        self.url_edit.setText(url)
        layout.addWidget(self.url_edit)
        options = QHBoxLayout()
        self.scope_combo = ComboBox()
        self.scope_combo.addItems(["Tự nhận diện合集 / playlist", "Các phần P của video Bilibili"])
        self.scan_btn = PushButton("Đọc danh sách")
        self.scan_btn.clicked.connect(self._discover)
        options.addWidget(self.scope_combo)
        options.addWidget(self.scan_btn)
        layout.addLayout(options)
        destination = QHBoxLayout()
        self.output_edit = LineEdit()
        self.output_edit.setText(output)
        self.browse_btn = PushButton("Thư mục tải")
        self.browse_btn.clicked.connect(self._browse)
        destination.addWidget(self.output_edit)
        destination.addWidget(self.browse_btn)
        layout.addLayout(destination)
        self.label = BodyLabel("Đọc danh sách trước, chọn tập rồi tải. Chưa chạy ASR/dịch/TTS.")
        self.label.setTextFormat(Qt.TextFormat.PlainText)
        self.label.setWordWrap(True)
        layout.addWidget(self.label)
        self.table = TableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Chọn / STT", "Video", "Thời lượng", "Trạng thái"])
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.setColumnWidth(0, 90)
        self.table.setColumnWidth(2, 100)
        self.table.setColumnWidth(3, 240)
        layout.addWidget(self.table)
        actions = QHBoxLayout()
        self.all_btn, self.none_btn = PushButton("Chọn tất cả"), PushButton("Bỏ chọn")
        self.all_btn.clicked.connect(lambda: self._select(True))
        self.none_btn.clicked.connect(lambda: self._select(False))
        self.download_btn = PushButton("Tải / Tiếp tục các tập đã chọn")
        self.download_btn.clicked.connect(self._download)
        self.cancel_btn = PushButton("Dừng tải")
        self.cancel_btn.clicked.connect(self._cancel)
        for button in (self.all_btn, self.none_btn, self.download_btn, self.cancel_btn):
            actions.addWidget(button)
        layout.addLayout(actions)
        self.handoff_btn = PushButton("Đưa video đã tải sang Xử lý hàng loạt")
        self.handoff_btn.clicked.connect(self._handoff)
        layout.addWidget(self.handoff_btn)
        note = BodyLabel("Tải lần lượt; tập lỗi được giữ trong bảng và có thể thử lại. File hoàn tất được kiểm SHA "
                         "để dùng lại. Đóng/Dừng giữ các file đã tải; lỗi truy cập không được tính là thành công.")
        note.setWordWrap(True)
        layout.addWidget(note)
        self.url_edit.textEdited.connect(self._invalidate_list)
        self.scope_combo.currentIndexChanged.connect(self._invalidate_list)
        self._set_busy(False)

    def _apply_theme(self):
        background, foreground = ("#202020", "#f0f0f0") if isDarkTheme() else ("#fafafa", "#202020")
        self.setStyleSheet(f"QDialog#PlaylistDialog {{ background-color: {background}; color: {foreground}; }}")

    def _invalidate_list(self, *_):
        self.info = None
        self.completed.clear()
        self.table.setRowCount(0)
        self.label.setText("URL/phạm vi đã đổi. Bấm Đọc danh sách trước khi tải.")
        self._set_busy(False)

    def _set_busy(self, busy):
        for control in (self.url_edit, self.scope_combo, self.output_edit, self.browse_btn, self.scan_btn, self.all_btn, self.none_btn, self.table):
            control.setEnabled(not busy)
        self.download_btn.setEnabled(not busy and self.info is not None)
        self.cancel_btn.setEnabled(busy)
        self.handoff_btn.setEnabled(not busy and bool(self.completed))

    def _browse(self):
        folder = QFileDialog.getExistingDirectory(self, "Chọn thư mục tải", self.output_edit.text())
        if folder:
            self.output_edit.setText(folder)

    def _select(self, checked):
        if self.info:
            for row, entry in enumerate(self.info.entries):
                if not entry.unavailable_reason:
                    self.table.item(row, 0).setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)

    def _discover(self):
        if self._worker and self._worker.isRunning():
            return
        self.info = None
        self.completed.clear()
        self.table.setRowCount(0)
        self.label.setText("Đang đọc danh sách, chưa tải media...")
        self._start(PlaylistThread(url=self.url_edit.text().strip(),
            scope="parts" if self.scope_combo.currentIndex() else "auto", cookies=self.cookies))

    def _download(self):
        if self.info is None or (self._worker and self._worker.isRunning()):
            return
        entries = tuple(entry for row, entry in enumerate(self.info.entries)
                        if self.table.item(row, 0).checkState() == Qt.CheckState.Checked)
        if not entries or not self.output_edit.text().strip():
            self.label.setText("Chọn ít nhất một tập và thư mục đích.")
            return
        self.label.setText(f"Đang tải {len(entries)} tập đã chọn...")
        self._start(PlaylistThread(info=self.info, selected=entries,
            output=self.output_edit.text().strip(), cookies=self.cookies))

    def _start(self, worker):
        self._result, self._error = None, ""
        self._worker = retain_worker(worker)
        worker.result.connect(self._receive)
        worker.error.connect(self._failed)
        worker.progress.connect(self._progress)
        worker.cancelled.connect(lambda: self._failed("Đã dừng đọc danh sách."))
        worker.finished.connect(self._stopped)
        self._set_busy(True)
        worker.start()

    def _receive(self, result):
        self._result = result

    def _failed(self, error):
        self._error = error

    def _progress(self, item: PlaylistItemResult, percent: int):
        if self._closing or self.info is None:
            return
        labels = {"pending": "Chờ", "downloading": f"Đang tải {percent}%", "downloaded": "Đã tải",
                  "existing": "Đã có (SHA khớp)", "failed": "Lỗi: " + item.error, "cancelled": "Đã dừng"}
        cell = self.table.item(item.index - 1, 3)
        cell.setText(labels.get(item.status, item.status))
        cell.setToolTip(item.error or item.path)
        if item.path and item.status in ("downloaded", "existing"):
            self.completed[item.index] = item.path

    def _stopped(self):
        if self._worker:
            self._worker.wait()
        if self._closing:
            return
        result = self._result
        if self._error:
            self.label.setText(self._error)
        elif isinstance(result, PlaylistInfo):
            self.info = result
            self.label.setText(f"{result.title} — {len(result.entries)} mục ({result.kind})")
            self.table.setRowCount(len(result.entries))
            for row, entry in enumerate(result.entries):
                item = QTableWidgetItem(str(entry.index))
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Unchecked if entry.unavailable_reason else Qt.CheckState.Checked)
                if entry.unavailable_reason:
                    item.setFlags(Qt.ItemFlag.ItemIsSelectable)
                self.table.setItem(row, 0, item)
                self.table.setItem(row, 1, QTableWidgetItem(entry.title))
                duration = f"{int(entry.duration) // 60}:{int(entry.duration) % 60:02d}" if entry.duration is not None else "—"
                self.table.setItem(row, 2, QTableWidgetItem(duration))
                self.table.setItem(row, 3, QTableWidgetItem(entry.unavailable_reason or "Chờ"))
        elif isinstance(result, PlaylistResult):
            for item in result.items:
                self._progress(item, 100 if item.path else 0)
            failures = sum(item.status == "failed" for item in result.items)
            pending = sum(item.status in ("pending", "cancelled") for item in result.items)
            self.label.setText(f"{'Đã dừng' if result.cancelled else 'Kết thúc lượt tải'}: "
                               f"{len(result.paths)} hoàn tất/đã có, {failures} lỗi, {pending} chưa tải.")
        self._set_busy(False)

    def _cancel(self):
        if self._worker and self._worker.isRunning():
            self._worker.requestInterruption()
            self.label.setText("Đang dừng sau thao tác mạng/ghép media hiện tại; giữ file đã tải...")

    def _handoff(self):
        paths = [self.completed[index] for index in sorted(self.completed)]
        if paths:
            self.files_ready.emit(paths)
            self.hide()
        self._set_busy(False)

    def reject(self):
        self._closing = True
        self._cancel()
        super().reject()

    def closeEvent(self, event):
        self._closing = True
        self._cancel()
        super().closeEvent(event)

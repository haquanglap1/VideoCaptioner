"""Edit the series/video background sent with every LLM translation; fetching runs off the GUI thread."""

from pathlib import Path

from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)
from qfluentwidgets import isDarkTheme

from videocaptioner.config import APPDATA_PATH
from videocaptioner.core.translate.series_context import (
    MAX_NOTES,
    VideoContext,
    fetch_video_context,
)
from videocaptioner.ui.common.config import cfg
from videocaptioner.ui.thread.worker_lifecycle import connect_current, retain_worker, retire_worker


class SeriesContextFetchThread(QThread):
    fetched = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, url: str):
        super().__init__()
        self.url = url

    def run(self):
        try:
            cookies = Path(APPDATA_PATH) / "cookies.txt"
            self.fetched.emit(fetch_video_context(self.url, cookies=cookies if cookies.is_file() else None))
        except ValueError as exc:
            self.failed.emit(str(exc))
        except Exception:  # noqa: BLE001 - extractor/network errors can carry private details
            self.failed.emit("Không lấy được thông tin video; kiểm tra đường dẫn, mạng hoặc cookies.")


class SeriesContextDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.worker: SeriesContextFetchThread | None = None
        self.setWindowTitle("Ngữ cảnh bộ phim cho LLM dịch")
        self.resize(760, 560)
        if isDarkTheme():
            self.setStyleSheet("QDialog { background: #202733; color: #e6edf6; } QLabel { color: #e6edf6; }")
        layout = QVBoxLayout(self)
        guide = QLabel("Đoạn mô tả này được gửi kèm mọi lần dịch bằng LLM (cả phụ đề ASR lẫn OCR): nhân vật, quan hệ, "
                       "cách xưng hô, thuật ngữ, giọng điệu. Dán link Bilibili/YouTube rồi bấm Lấy từ link để điền tiêu đề, "
                       "mô tả và danh sách phần, sau đó sửa lại cho đúng ý. Video tải bằng app còn có thêm metadata riêng "
                       "của từng video.")
        guide.setWordWrap(True)
        layout.addWidget(guide)
        row = QHBoxLayout()
        self.url = QLineEdit()
        self.url.setPlaceholderText("https://www.bilibili.com/video/BV… hoặc https://www.youtube.com/watch?v=…")
        row.addWidget(self.url, 1)
        self.fetch_button = QPushButton("Lấy từ link")
        self.fetch_button.clicked.connect(self.fetch)
        row.addWidget(self.fetch_button)
        layout.addLayout(row)
        self.notes = QPlainTextEdit()
        self.notes.setPlaceholderText("Ví dụ:\nThể loại: PV game, tiên hiệp, trang trọng nhưng ấm áp.\n"
                                      "Nhân vật: 清宵 = Thanh Tiêu, sư phụ; 卜灵 = Bốc Linh, đồ đệ.\n"
                                      "Xưng hô: sư phụ gọi đồ đệ là \"đồ nhi\", tự xưng \"ta\".\n"
                                      "Thuật ngữ: 共鸣者 = Cộng Minh Giả.")
        self.notes.setPlainText(str(cfg.translate_series_context.value or ""))
        layout.addWidget(self.notes, 1)
        self.status = QLabel("")
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        row = QHBoxLayout()
        row.addStretch(1)
        self.clear_button = QPushButton("Xóa")
        self.clear_button.clicked.connect(self.notes.clear)
        row.addWidget(self.clear_button)
        self.save_button = QPushButton("Lưu")
        self.save_button.clicked.connect(self.save)
        row.addWidget(self.save_button)
        close = QPushButton("Đóng")
        close.clicked.connect(self.reject)
        row.addWidget(close)
        layout.addLayout(row)
        self.finished.connect(self.shutdown)

    def fetch(self):
        url = self.url.text().strip()
        if not url or self.worker is not None:
            return
        self.worker = retain_worker(SeriesContextFetchThread(url))
        self.fetch_button.setEnabled(False)
        self.status.setText("Đang lấy tiêu đề, mô tả và danh sách phần…")
        connect_current(self, "worker", self.worker, self.worker.fetched, self.apply_fetched)
        connect_current(self, "worker", self.worker, self.worker.failed, self.status.setText)
        worker = self.worker

        def finished():
            if self.worker is worker:
                self.worker = None
            self.fetch_button.setEnabled(True)

        worker.finished.connect(finished)
        worker.start()

    def apply_fetched(self, context: VideoContext):
        block = "## Video\n" + context.brief()
        current = self.notes.toPlainText().strip()
        text = block if not current else block + "\n\n" + current
        self.notes.setPlainText(text[:MAX_NOTES])
        self.status.setText("Đã điền thông tin từ link; sửa lại nhân vật, xưng hô và thuật ngữ rồi bấm Lưu.")

    def save(self):
        text = self.notes.toPlainText().strip()
        if len(text) > MAX_NOTES:
            self.status.setText(f"Ngữ cảnh dài quá {MAX_NOTES} ký tự; rút gọn trước khi lưu.")
            return
        cfg.set(cfg.translate_series_context, text)
        self.status.setText("Đã lưu. Mọi lần dịch bằng LLM từ giờ sẽ nhận ngữ cảnh này.")

    def shutdown(self, *_):
        if self.worker is not None:
            retire_worker(self.worker)
            self.worker = None

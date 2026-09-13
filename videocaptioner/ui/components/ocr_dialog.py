"""Local OCR acquisition and direct subtitle export; IO/model work runs in workers."""

from pathlib import Path

from PyQt5 import sip
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from videocaptioner.core.ocr.assistance import OcrVietnameseDraft, comparison_note
from videocaptioner.core.ocr.cache import DEFAULT_CACHE_MIB, MAX_CACHE_MIB, manage_cache
from videocaptioner.core.ocr.codec import atomic_json, atomic_text
from videocaptioner.core.ocr.document import OcrDocument
from videocaptioner.core.ocr.geometry import Roi
from videocaptioner.core.ocr.identity import verify_visual_file
from videocaptioner.core.ocr.installation import inspect_installation
from videocaptioner.core.ocr.models import OcrError, Selection
from videocaptioner.core.ocr.preview import preview_candidate, preview_video
from videocaptioner.core.ocr.review import OcrReviewSession, issue_labels
from videocaptioner.core.ocr.service import jobs_directory
from videocaptioner.ui.task_factory import TaskFactory
from videocaptioner.ui.thread.ocr_thread import (
    OcrDraftThread,
    OcrThread,
    OcrWorker,
    capture_draft_settings,
)
from videocaptioner.ui.thread.worker_lifecycle import connect_current, retain_worker, retire_worker

from .ocr_region_canvas import OcrRegionCanvas


class OcrDialog(QDialog):
    subtitles_ready = pyqtSignal(object, str, str)

    def __init__(self, parent=None, *, source: str = ""):
        super().__init__(parent)
        self.worker: OcrWorker | None = None
        self.session: OcrReviewSession | None = None
        self.review_path: Path | None = None
        self.source_preview = None
        self._drafts: dict[tuple[str, str], OcrVietnameseDraft] = {}
        self._draft_configs: dict[tuple[str, str], tuple[str, str, int]] = {}
        self._closed = False
        self.setWindowTitle("OCR — Phụ đề trong hình")
        self.resize(1120, 900)
        self.setStyleSheet("QDialog { background: #202733; color: #e6edf6; } QLabel { color: #e6edf6; }")
        self.finished.connect(self.shutdown)
        layout = QVBoxLayout(self)
        notice = QLabel("Đọc phụ đề ngang trong một vùng cố định, một hoặc hai dòng. "
                        "CPU chạy tại máy; không tự tải model hoặc gọi dịch vụ đọc ảnh.")
        notice.setWordWrap(True)
        layout.addWidget(notice)
        self.controls = QWidget()
        controls = QVBoxLayout(self.controls)
        controls.setContentsMargins(0, 0, 0, 0)
        row = QHBoxLayout()
        self.source = QLineEdit(source)
        self.source.setReadOnly(True)
        row.addWidget(self.source, 1)
        self._button(row, "Chọn video…", self.choose_source)
        self._button(row, "Mở dữ liệu OCR…", self.load_review)
        controls.addLayout(row)
        row = QHBoxLayout()
        self.runtime = QLineEdit()
        self.runtime.setPlaceholderText("Tự tìm runtime OCR cạnh ứng dụng; hoặc chọn bộ đã cài")
        row.addWidget(self.runtime, 1)
        self._button(row, "Chọn runtime…", self.choose_runtime)
        self._button(row, "Kiểm tra model đã cài", self.check_runtime)
        controls.addLayout(row)
        row = QHBoxLayout()
        self.start_ms, self.end_ms, self.position_ms = QSpinBox(), QSpinBox(), QSpinBox()
        for label, spin, value in (("Đầu (ms)", self.start_ms, 0), ("Cuối (ms)", self.end_ms, 60000),
                                    ("Xem tại (ms)", self.position_ms, 0)):
            spin.setRange(0, 2_147_483_647)
            spin.setValue(value)
            row.addWidget(QLabel(label))
            row.addWidget(spin)
        self._button(row, "Tải ảnh chọn ROI", self.load_preview)
        self.scan_button = self._button(row, "Đọc phụ đề bằng CPU", self.scan)
        controls.addLayout(row)
        row = QHBoxLayout()
        self.roi_values = []
        for label, value in (("X", 0), ("Y", 0), ("Rộng", 1), ("Cao", 1)):
            spin = QDoubleSpinBox()
            spin.setRange(0, 1)
            spin.setDecimals(6)
            spin.setSingleStep(.01)
            spin.setValue(value)
            self.roi_values.append(spin)
            row.addWidget(QLabel(label))
            row.addWidget(spin)
        self._button(row, "Dùng ROI số", self.apply_roi)
        controls.addLayout(row)
        row = QHBoxLayout()
        row.addWidget(QLabel("Cache chữ OCR (MiB; 0 = tắt)"))
        self.cache_mib = QSpinBox()
        self.cache_mib.setRange(0, MAX_CACHE_MIB)
        self.cache_mib.setValue(DEFAULT_CACHE_MIB)
        self.cache_mib.setToolTip("Hạn mức dữ liệu bản đọc dùng chung giữa các lần quét, chưa gồm metadata. "
                                 "Cache không giữ ảnh/video hoặc chỉnh sửa phụ đề.")
        row.addWidget(self.cache_mib)
        self._button(row, "Dung lượng cache", self.show_cache)
        self._button(row, "Xóa cache OCR", lambda: self.show_cache(clear=True))
        row.addStretch(1)
        controls.addLayout(row)
        layout.addWidget(self.controls)
        splitter = QSplitter(Qt.Orientation.Vertical)
        self.canvas = OcrRegionCanvas()
        self.canvas.roi_changed.connect(self.roi_changed)
        splitter.addWidget(self.canvas)
        self.result_controls = QWidget()
        results = QVBoxLayout(self.result_controls)
        results.setContentsMargins(0, 0, 0, 0)
        self.table = QTableWidget(0, 3)
        self.table.setMinimumHeight(150)
        self.table.setHorizontalHeaderLabels(["Câu", "Đầu / cuối (ms)", "Chữ đã đọc"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.itemSelectionChanged.connect(self.select_cue)
        self.table.horizontalHeader().setStretchLastSection(True)
        results.addWidget(self.table)
        details_button = QPushButton("Chi tiết bản đọc")
        details_button.setCheckable(True)
        results.addWidget(details_button)
        self.details = QWidget()
        details = QVBoxLayout(self.details)
        details.setContentsMargins(0, 0, 0, 0)
        details_button.toggled.connect(self.details.setVisible)
        self.details.hide()
        results.addWidget(self.details)
        row = QHBoxLayout()
        self.candidate = QComboBox()
        self.candidate.currentIndexChanged.connect(self.refresh_draft)
        row.addWidget(self.candidate, 1)
        self._button(row, "Xem crop gốc", self.load_crop)
        self._button(row, "Xem video tại đầu câu", self.preview_cue_start)
        details.addLayout(row)
        self.readings = QPlainTextEdit()
        self.readings.setReadOnly(True)
        self.readings.setMaximumHeight(120)
        self.draft_text = QPlainTextEdit()
        self.draft_text.setReadOnly(True)
        self.draft_text.setMaximumHeight(120)
        self.draft_text.setPlaceholderText("Bản Việt tham khảo từ chữ OCR. AI chưa nhìn ảnh nên không xác minh chữ đúng/sai. "
                                          "Bản tham khảo chỉ giữ trong phiên này.")
        row = QHBoxLayout()
        row.addWidget(self.readings)
        row.addWidget(self.draft_text)
        details.addLayout(row)
        row = QHBoxLayout()
        self.draft_button = self._button(row, "Dịch bản đọc đang chọn sang Việt", self.translate_current_draft)
        draft_notice = QLabel("Chỉ gửi chữ của bản đọc đang chọn tới LLM trong Cài đặt khi bấm nút; "
                              "bản dịch tham khảo chỉ giữ trong phiên.")
        draft_notice.setWordWrap(True)
        row.addWidget(draft_notice, 1)
        details.addLayout(row)
        splitter.addWidget(self.result_controls)
        splitter.setSizes([260, 300])
        layout.addWidget(splitter, 1)
        self.status = QLabel("Chọn video, tải ảnh và kéo vùng phụ đề. Quét xong có thể xuất hoặc chuyển sang dịch ngay.")
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.progress = QProgressBar()
        layout.addWidget(self.progress)
        self.actions_panel = QWidget()
        row = QHBoxLayout(self.actions_panel)
        self._button(row, "Lưu dữ liệu OCR…", self.save_review)
        self.resume_button = self._button(row, "Tiếp tục quét", self.resume_scan)
        self.resume_button.setToolTip("Giữ các câu đã lưu; tiếp tục quét theo vùng và đoạn của dữ liệu OCR.")
        self.export_button = self._button(row, "Xuất phụ đề…", self.export)
        self.handoff_button = self._button(row, "Mở bảng phụ đề / dịch…", lambda: self.export(handoff=True))
        layout.addWidget(self.actions_panel)
        row = QHBoxLayout()
        self.cancel_button = self._button(row, "Hủy tác vụ", self.cancel)
        self._button(row, "Đóng", self.reject)
        layout.addLayout(row)
        self.refresh()

    @staticmethod
    def _button(row, text, callback):
        button = QPushButton(text)
        button.clicked.connect(lambda _checked=False: callback())
        row.addWidget(button)
        return button

    def _start(self, worker, accept):
        if self.worker is not None or self._closed:
            return
        self.worker = retain_worker(worker)
        self.refresh_enabled()
        self.progress.setRange(0, 0)
        self.progress.setValue(0)
        connect_current(self, "worker", worker, worker.result_ready, accept)
        connect_current(self, "worker", worker, worker.failed, self.status.setText)
        connect_current(self, "worker", worker, worker.progress, self.show_progress)
        def finished():
            if sip.isdeleted(self) or self._closed or self.worker is not worker:
                return
            if isinstance(worker, OcrThread) and worker.partial_document is not None:
                self.accept_document(worker.partial_document)
            self.worker = None
            self.progress.setRange(0, 100)
            if worker.cancelled.is_set():
                self.status.setText("Đã hủy. Có thể lưu dữ liệu OCR để tiếp tục quét sau.")
            elif worker.error_message:
                self.status.setText(worker.error_message + " Dữ liệu OCR đã có được giữ lại.")
            else:
                self.progress.setValue(100)
            self.refresh_enabled()
        worker.finished.connect(finished)
        worker.start()

    def show_progress(self, value, text):
        self.progress.setRange(0, 100 if value else 0)
        self.progress.setValue(value)
        self.status.setText(text)

    def refresh_enabled(self):
        busy = self.worker is not None
        self.controls.setEnabled(not busy)
        self.result_controls.setEnabled(not busy and self.session is not None)
        self.actions_panel.setEnabled(not busy and self.session is not None)
        self.cancel_button.setEnabled(busy)
        self.scan_button.setEnabled(self.source_preview is not None and self.canvas.roi is not None)
        self.resume_button.setEnabled(bool(not busy and self.source.text() and self.session
                                           and not self.session.document.complete))
        exportable = not busy and self.session is not None and not self.session.document.export_issues
        self.export_button.setEnabled(exportable)
        self.handoff_button.setEnabled(exportable)
        cue = self.current_cue()
        self.draft_button.setEnabled(bool(not busy and cue and self.candidate.currentData()
                                          and cue.candidate(self.candidate.currentData()).raw.text.strip()))

    def choose_source(self):
        path, _ = QFileDialog.getOpenFileName(self, "Chọn video nguồn", "", "Video (*)")
        if path:
            self.source.setText(path)
            self.source_preview = None
            self.canvas.roi = None
            self.refresh_enabled()

    def choose_runtime(self):
        path = QFileDialog.getExistingDirectory(self, "Chọn runtime OCR đã cài")
        if path:
            self.runtime.setText(path)

    def check_runtime(self):
        root = Path(self.runtime.text()) if self.runtime.text().strip() else None
        self.status.setText("Đang kiểm tra file/model đã cài; không nạp engine…")
        self._start(OcrWorker(lambda check: inspect_installation(root, check)),
                    lambda installation: self.status.setText(
                        f"{installation.profile.id}: model/profile khớp SHA. "
                        "Engine chỉ nạp khi bạn bấm đọc phụ đề."))

    def show_cache(self, *, clear=False):
        def show(info):
            if clear:
                self.status.setText(f"Đã xóa {info.entries} bản đọc trong cache OCR. "
                                    "Dữ liệu OCR đã lưu và model được giữ nguyên.")
            else:
                self.status.setText(f"Cache OCR: {info.entries} bản đọc, "
                                    f"{info.payload_bytes / (1024 * 1024):.2f} MiB dữ liệu; "
                                    f"{info.database_bytes / (1024 * 1024):.2f} MiB gồm metadata.")
        self._start(OcrWorker(lambda check: manage_cache(clear=clear, check=check)), show)

    def load_preview(self):
        if not self.source.text():
            self.status.setText("Chọn video trước khi tải ảnh.")
            return
        source, position = Path(self.source.text()), self.position_ms.value()
        self._start(OcrWorker(lambda check: preview_video(source, position, jobs_directory(), check=check)), self.accept_preview)

    def accept_preview(self, preview):
        self.source_preview = preview
        self.canvas.editable = True
        self.canvas.set_image(preview.png)
        self.status.setText("Kéo đúng vùng phụ đề trên ảnh, hoặc nhập ROI số. Ảnh xem trước không xác nhận biên câu.")

    def roi_changed(self, roi):
        for spin, value in zip(self.roi_values, (roi.x, roi.y, roi.width, roi.height)):
            spin.setValue(value)
        self.refresh_enabled()

    def apply_roi(self):
        try:
            self.canvas.roi = Roi(*(spin.value() for spin in self.roi_values))
            self.canvas.update()
            self.refresh_enabled()
        except ValueError:
            self.status.setText("ROI phải là vùng không rỗng nằm trong ảnh.")

    def scan(self):
        if self.source_preview is None or self.canvas.roi is None:
            return
        try:
            task = TaskFactory.create_ocr_task(self.source.text(), self.canvas.roi,
                Selection(self.start_ms.value(), self.end_ms.value()), self.runtime.text(),
                expected_source_sha256=self.source_preview.source_sha256, cache_mib=self.cache_mib.value())
            self._start(OcrThread(task), self.accept_document)
        except ValueError:
            self.status.setText("Đoạn video không hợp lệ; đầu phải nhỏ hơn cuối.")

    def resume_scan(self):
        if self.worker is not None or self.session is None or not self.source.text():
            return
        document = self.session.document
        if document.complete:
            return
        task = TaskFactory.create_ocr_task(self.source.text(), document.config.roi,
            document.config.selection, self.runtime.text(),
            expected_source_sha256=document.visual_source.snapshot_sha256,
            cache_mib=self.cache_mib.value(), resume_document=document)
        self._start(OcrThread(task), self.accept_document)

    def accept_document(self, document):
        self.session = OcrReviewSession(document)
        self.review_path = None
        self.refresh()

    def load_review(self):
        path, _ = QFileDialog.getOpenFileName(self, "Mở dữ liệu OCR", "", "JSON (*.json)")
        if not path:
            return
        if not self.source.text():
            self.choose_source()
        if not self.source.text():
            return
        source = Path(self.source.text())
        def load(check):
            doc = OcrDocument.load(path)
            verify_visual_file(doc.visual_source, source, jobs_directory(), check=check)
            return doc
        def accept(doc):
            self.accept_document(doc)
            self.review_path = Path(path)
        self._start(OcrWorker(load), accept)

    def refresh(self):
        if self.session:
            selected = self.table.currentRow()
            doc = self.session.document
            self.table.blockSignals(True)
            self.table.setRowCount(len(doc.cues))
            for row, cue in enumerate(doc.cues):
                for col, value in enumerate((str(row + 1), f"{cue.start_ms} / {cue.end_ms}", cue.text)):
                    item = QTableWidgetItem(value)
                    item.setToolTip(value)
                    self.table.setItem(row, col, item)
                self.table.setRowHeight(row, 48)
            self.table.blockSignals(False)
            self.table.setColumnWidth(2, 300)
            self.table.selectRow(max(0, selected))
            self.select_cue()
            if not doc.complete:
                message = "Có thể lưu dữ liệu OCR hoặc tiếp tục quét phần còn lại."
            elif doc.export_issues:
                message = "Chưa xuất được: thiếu chữ hoặc thời gian không hợp lệ. Kiểm tra vùng và đoạn video."
            else:
                message = "Sẵn sàng xuất phụ đề hoặc mở bảng phụ đề để dịch, chỉnh sửa."
            self.status.setText(f"{len(doc.cues)} câu. {message}")
        self.refresh_enabled()

    def current_cue(self):
        row = self.table.currentRow()
        return self.session.document.cues[row] if self.session and 0 <= row < len(self.session.document.cues) else None

    def select_cue(self):
        self.candidate.clear()
        cue = self.current_cue()
        if cue:
            for index, candidate in enumerate(cue.candidates, 1):
                label = " / ".join(candidate.raw.text.splitlines())
                self.candidate.addItem(f"Ảnh {index} — {label}", candidate.id)
                self.candidate.setItemData(index - 1, candidate.raw.text, Qt.ItemDataRole.ToolTipRole)
            self.readings.setPlainText("Gốc: " + cue.raw_text + "\nHiện tại: " + cue.text + "\n"
                                       + comparison_note(cue) + "\n" + issue_labels(cue))
        self.refresh_draft()

    def refresh_draft(self, *_):
        if not hasattr(self, "draft_text"):
            return
        cue = self.current_cue()
        candidate_id = self.candidate.currentData()
        if hasattr(self, "draft_button"):
            self.draft_button.setEnabled(bool(not self.worker and cue and candidate_id
                                              and cue.candidate(candidate_id).raw.text.strip()))
        draft = self._drafts.get((self.session.document.id, candidate_id)) if self.session and candidate_id else None
        if cue and draft and cue.candidate(candidate_id).raw.text == draft.source_text:
            text = f"Bản Việt tham khảo ({draft.model}) — AI chưa nhìn ảnh:\n{draft.translation_vi}"
            if draft.uncertainties_vi:
                text += "\nAI lưu ý (chưa xác minh): " + " / ".join(draft.uncertainties_vi)
            text += "\nBản dịch tham khảo chỉ giữ trong phiên này."
            self.draft_text.setPlainText(text)
        else:
            self.draft_text.clear()

    def translate_current_draft(self):
        cue = self.current_cue()
        candidate_id = self.candidate.currentData()
        if self.worker or not self.session or not cue or not candidate_id:
            return
        document, candidate = self.session.document, cue.candidate(candidate_id)
        try:
            settings = capture_draft_settings()
        except (KeyError, ValueError, OcrError):
            self.status.setText("Kiểm tra cấu hình dịch vụ LLM, model, API key và thời gian chờ trong Cài đặt.")
            return
        key = (document.id, candidate.id)
        config = (settings.credentials.base_url, settings.model, settings.timeout)
        if (key in self._drafts and self._drafts[key].source_text == candidate.raw.text
                and self._draft_configs.get(key) == config):
            self.refresh_draft()
            self.status.setText("Dùng bản Việt tham khảo đã có trong phiên; không gửi lại yêu cầu.")
            return

        def accept(draft):
            if not self.session or self.session.document.id != document.id:
                return
            # Bound private text held in RAM; the OCR document and saved review stay untouched.
            if key not in self._drafts and len(self._drafts) >= 64:
                oldest = next(iter(self._drafts))
                del self._drafts[oldest]
                self._draft_configs.pop(oldest, None)
            self._drafts[key] = draft
            self._draft_configs[key] = config
            self.refresh_draft()
            usage = (f"Token dịch vụ báo: {draft.prompt_tokens} vào / {draft.completion_tokens} ra."
                     if draft.prompt_tokens is not None and draft.completion_tokens is not None
                     else "Dịch vụ không cung cấp đủ số liệu token.")
            self.status.setText("Đã nhận bản Việt tham khảo từ chữ OCR; chưa kiểm chứng ảnh. " + usage)

        self.status.setText("Đang dịch bản đọc đang chọn sang Việt…")
        self._start(OcrDraftThread(document, candidate, settings), accept)

    def load_crop(self):
        cue = self.current_cue()
        if cue is None or not self.session or not self.candidate.currentData():
            return
        candidate, doc, source = cue.candidate(self.candidate.currentData()), self.session.document, Path(self.source.text())
        def accept(preview):
            self.canvas.editable = False
            self.canvas.set_image(preview.png)
            self.status.setText("Đang xem ảnh gốc của bản đọc OCR đã chọn.")
        self._start(OcrWorker(lambda check: preview_candidate(source, doc, candidate, jobs_directory(), check=check)), accept)

    def preview_cue_start(self):
        cue = self.current_cue()
        if cue:
            self.position_ms.setValue(cue.start_ms)
            self.load_preview()

    def _destination(self, path, export=False):
        target = Path(path).resolve()
        protected = [Path(self.source.text()).resolve()]
        if export and self.review_path:
            protected.append(self.review_path.resolve())
        if any(target == p or (target.exists() and p.exists() and target.samefile(p)) for p in protected):
            raise OcrError("Không ghi đè video hoặc dữ liệu OCR bằng phụ đề xuất.")
        return target

    def save_review(self):
        if not self.session:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Lưu dữ liệu OCR", "scan.ocr.json", "JSON (*.json)")
        if path:
            try:
                target, doc = self._destination(path), self.session.document
                def save(check):
                    check()
                    doc.save(target)
                    return target
                self._start(OcrWorker(save), lambda result: self.saved_review(result))
            except ValueError as exc:
                self.status.setText(str(exc))

    def saved_review(self, path):
        self.review_path = path
        self.status.setText("Đã lưu dữ liệu OCR; mở lại cùng video để xuất phụ đề hoặc tiếp tục quét.")

    def export(self, handoff=False):
        if self.worker is not None or not self.session or self.session.document.export_issues:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Xuất phụ đề OCR", "captions.ocr.json",
                                              "JSON (*.json)" if handoff else "JSON (*.json);;SRT (*.srt)")
        if not path:
            return
        try:
            target, doc, source = self._destination(path, True), self.session.document, Path(self.source.text())
            if target.suffix.lower() not in ((".json",) if handoff else (".json", ".srt")):
                raise OcrError("Chọn JSON để giữ metadata hoặc SRT để chỉ giữ chữ và giờ.")
            def save(check):
                actual = verify_visual_file(doc.visual_source, source, jobs_directory(), check=check)
                data = doc.resume(actual)
                check()
                if target.suffix.lower() == ".json":
                    atomic_json(target, data.to_document())
                else:
                    atomic_text(target, data.to_srt())
                return data
            def accept(data):
                self.status.setText("Đã xuất phụ đề OCR. JSON giữ nguồn OCR; SRT chỉ giữ chữ/giờ.")
                if handoff:
                    self.subtitles_ready.emit(data, str(target), str(source))
                    self.accept()
            self._start(OcrWorker(save), accept)
        except ValueError as exc:
            self.status.setText(str(exc))

    def cancel(self):
        if self.worker:
            self.worker.stop()
            self.status.setText("Đang hủy và đóng process OCR…")

    def shutdown(self, *_):
        self._closed = True
        self._drafts.clear()
        self._draft_configs.clear()
        if self.worker:
            retire_worker(self.worker)
            self.worker = None

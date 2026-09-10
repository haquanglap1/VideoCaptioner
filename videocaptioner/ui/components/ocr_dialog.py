"""Local OCR acquisition and evidence review; all IO/model work belongs to workers."""

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

from videocaptioner.core.editor.commands import CommandStack
from videocaptioner.core.ocr.codec import atomic_json, atomic_text
from videocaptioner.core.ocr.document import OcrDocument
from videocaptioner.core.ocr.geometry import Roi
from videocaptioner.core.ocr.identity import verify_visual_file
from videocaptioner.core.ocr.installation import inspect_installation
from videocaptioner.core.ocr.models import OcrError, Selection
from videocaptioner.core.ocr.preview import preview_candidate, preview_video
from videocaptioner.core.ocr.review import OcrReviewSession, ReviewOcrCueCommand, issue_labels
from videocaptioner.core.ocr.service import jobs_directory
from videocaptioner.ui.task_factory import TaskFactory
from videocaptioner.ui.thread.ocr_thread import OcrThread, OcrWorker
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
        self.verified_candidate_id = ""
        self.stack = CommandStack()
        self.stack.add_changed_callback(self.refresh)
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
        self._button(row, "Mở review…", self.load_review)
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
        layout.addWidget(self.controls)
        splitter = QSplitter(Qt.Orientation.Vertical)
        self.canvas = OcrRegionCanvas()
        self.canvas.roi_changed.connect(self.roi_changed)
        splitter.addWidget(self.canvas)
        self.review_controls = QWidget()
        review = QVBoxLayout(self.review_controls)
        review.setContentsMargins(0, 0, 0, 0)
        self.table = QTableWidget(0, 4)
        self.table.setMinimumHeight(150)
        self.table.setHorizontalHeaderLabels(["Câu", "Đầu / cuối (ms)", "Chữ đã đọc", "Cần xem lại"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.itemSelectionChanged.connect(self.select_cue)
        self.table.horizontalHeader().setStretchLastSection(True)
        review.addWidget(self.table)
        row = QHBoxLayout()
        self.candidate = QComboBox()
        self.candidate.currentIndexChanged.connect(self.clear_candidate_evidence)
        row.addWidget(self.candidate, 1)
        self._button(row, "Xem crop gốc", self.load_crop)
        self._button(row, "Xem video tại đầu câu", self.preview_cue_start)
        review.addLayout(row)
        self.readings = QPlainTextEdit()
        self.readings.setReadOnly(True)
        self.readings.setMaximumHeight(90)
        review.addWidget(self.readings)
        self.note = QLineEdit()
        self.note.setPlaceholderText("Lý do/bằng chứng cho quyết định duyệt; không tự duyệt khi chưa chắc chữ")
        review.addWidget(self.note)
        row = QHBoxLayout()
        self.approve_button = self._button(row, "Dùng nguyên bản đọc đã xem", self.approve)
        self.cue_start, self.cue_end = QSpinBox(), QSpinBox()
        self.cue_start.setToolTip("Thời điểm bắt đầu đã kiểm (ms)")
        self.cue_end.setToolTip("Thời điểm kết thúc đã kiểm (ms)")
        for spin in (self.cue_start, self.cue_end):
            spin.setRange(0, 2_147_483_647)
            row.addWidget(spin)
        self._button(row, "Duyệt giờ đã kiểm", self.review_timing)
        self._button(row, "Hoàn tác", self.stack.undo)
        self._button(row, "Làm lại", self.stack.redo)
        review.addLayout(row)
        splitter.addWidget(self.review_controls)
        splitter.setSizes([260, 300])
        layout.addWidget(splitter, 1)
        self.status = QLabel("Chọn video, tải ảnh và kéo vùng phụ đề. Review chưa giải quyết sẽ được giữ lại.")
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.progress = QProgressBar()
        layout.addWidget(self.progress)
        self.actions_panel = QWidget()
        row = QHBoxLayout(self.actions_panel)
        self._button(row, "Lưu review…", self.save_review)
        self.export_button = self._button(row, "Xuất phụ đề đã duyệt…", self.export)
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
                self.status.setText("Đã hủy. Phần review đã có được giữ; chưa phải kết quả hoàn chỉnh.")
            elif worker.error_message:
                self.status.setText(worker.error_message + " Review đã có được giữ lại.")
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
        self.review_controls.setEnabled(not busy and self.session is not None)
        self.actions_panel.setEnabled(not busy and self.session is not None)
        self.cancel_button.setEnabled(busy)
        self.scan_button.setEnabled(self.source_preview is not None and self.canvas.roi is not None)
        accepted = self.session is not None and not self.session.document.pending_issues
        self.export_button.setEnabled(accepted)
        self.handoff_button.setEnabled(accepted)
        self.approve_button.setEnabled(bool(self.verified_candidate_id))

    def choose_source(self):
        path, _ = QFileDialog.getOpenFileName(self, "Chọn video nguồn", "", "Video (*)")
        if path:
            self.source.setText(path)
            self.source_preview = None
            self.canvas.roi = None
            self.clear_candidate_evidence()
            self.refresh_enabled()

    def choose_runtime(self):
        path = QFileDialog.getExistingDirectory(self, "Chọn runtime OCR đã cài")
        if path:
            self.runtime.setText(path)

    def check_runtime(self):
        root = Path(self.runtime.text()) if self.runtime.text().strip() else None
        self.status.setText("Đang kiểm tra file/model đã cài; không nạp engine…")
        self._start(OcrWorker(lambda check: inspect_installation(root, check)),
                    lambda _: self.status.setText("Model/profile khớp SHA. Engine chỉ nạp khi bạn bấm đọc phụ đề."))

    def load_preview(self):
        if not self.source.text():
            self.status.setText("Chọn video trước khi tải ảnh.")
            return
        source, position = Path(self.source.text()), self.position_ms.value()
        self.clear_candidate_evidence()
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
                expected_source_sha256=self.source_preview.source_sha256)
            self._start(OcrThread(task), self.accept_document)
        except ValueError:
            self.status.setText("Đoạn video không hợp lệ; đầu phải nhỏ hơn cuối.")

    def accept_document(self, document):
        self.session = OcrReviewSession(document)
        self.stack.clear()
        self.review_path = None
        self.clear_candidate_evidence()
        self.refresh()

    def load_review(self):
        path, _ = QFileDialog.getOpenFileName(self, "Mở review OCR", "", "JSON (*.json)")
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
                for col, value in enumerate((str(row + 1), f"{cue.start_ms} / {cue.end_ms}", cue.text, issue_labels(cue) or "Đã duyệt")):
                    item = QTableWidgetItem(value)
                    item.setToolTip(value)
                    self.table.setItem(row, col, item)
                self.table.setRowHeight(row, 48)
            self.table.blockSignals(False)
            self.table.setColumnWidth(2, 300)
            self.table.selectRow(max(0, selected))
            self.select_cue()
            self.status.setText(f"{len(doc.cues)} câu; {len(doc.pending_issues)} vấn đề còn mở. "
                                "Chưa chắc chữ thì giữ review; không cần đoán để xuất.")
        self.refresh_enabled()

    def current_cue(self):
        row = self.table.currentRow()
        return self.session.document.cues[row] if self.session and 0 <= row < len(self.session.document.cues) else None

    def select_cue(self):
        self.clear_candidate_evidence()
        self.candidate.clear()
        cue = self.current_cue()
        if cue:
            for index, candidate in enumerate(cue.candidates, 1):
                self.candidate.addItem(f"Ảnh {index} — {candidate.raw.text}", candidate.id)
            self.cue_start.setValue(cue.start_ms)
            self.cue_end.setValue(cue.end_ms)
            self.readings.setPlainText("Gốc: " + cue.raw_text + "\nHiện tại: " + cue.text + "\n" + issue_labels(cue))

    def clear_candidate_evidence(self, *_):
        self.verified_candidate_id = ""
        if hasattr(self, "approve_button"):
            self.approve_button.setEnabled(False)

    def load_crop(self):
        cue = self.current_cue()
        if cue is None or not self.session or not self.candidate.currentData():
            return
        candidate, doc, source = cue.candidate(self.candidate.currentData()), self.session.document, Path(self.source.text())
        self.clear_candidate_evidence()
        def accept(preview):
            self.canvas.editable = False
            self.canvas.set_image(preview.png)
            self.verified_candidate_id = candidate.id
            self.status.setText("Crop khớp SHA của ảnh engine đã đọc. Giữ review nếu chữ vẫn chưa chắc chắn.")
        self._start(OcrWorker(lambda check: preview_candidate(source, doc, candidate, jobs_directory(), check=check)), accept)

    def preview_cue_start(self):
        cue = self.current_cue()
        if cue:
            self.position_ms.setValue(cue.start_ms)
            self.load_preview()

    def approve(self):
        cue = self.current_cue()
        if cue and self.session and self.verified_candidate_id == self.candidate.currentData():
            try:
                self.stack.execute(ReviewOcrCueCommand(self.session, cue.select_candidate(self.verified_candidate_id, self.note.text())))
            except ValueError:
                self.status.setText("Chọn bản đọc không rỗng và ghi lý do/bằng chứng trước khi duyệt.")

    def review_timing(self):
        cue = self.current_cue()
        if cue and self.session:
            try:
                self.stack.execute(ReviewOcrCueCommand(self.session, cue.review_timing(
                    self.cue_start.value(), self.cue_end.value(), self.note.text())))
            except ValueError:
                self.status.setText("Giờ hoặc lý do duyệt không hợp lệ; giờ đo gốc vẫn được giữ.")

    def _destination(self, path, export=False):
        target = Path(path).resolve()
        protected = [Path(self.source.text()).resolve()]
        if export and self.review_path:
            protected.append(self.review_path.resolve())
        if any(target == p or (target.exists() and p.exists() and target.samefile(p)) for p in protected):
            raise OcrError("Không ghi đè video hoặc file review bằng phụ đề xuất.")
        return target

    def save_review(self):
        if not self.session:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Lưu review OCR", "pending.ocr.json", "JSON (*.json)")
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
        self.status.setText("Đã lưu review; mở lại cùng video để tiếp tục tại máy.")

    def export(self, handoff=False):
        if not self.session or self.session.document.pending_issues:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Xuất phụ đề đã duyệt", "captions.ocr.json",
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
                self.status.setText("Đã xuất toàn bộ phụ đề đã duyệt. JSON giữ nguồn OCR; SRT chỉ giữ chữ/giờ.")
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
        if self.worker:
            retire_worker(self.worker)
            self.worker = None

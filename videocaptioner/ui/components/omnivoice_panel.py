"""OmniVoice setup and optional reference controls; long work stays in a QThread."""

from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5.QtWidgets import QFileDialog, QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import BodyLabel, LineEdit, PushButton

from videocaptioner.core.tts.omnivoice.config import runtime_root, status
from videocaptioner.core.tts.omnivoice.prepare import prepare_runtime
from videocaptioner.ui.common.config import cfg
from videocaptioner.ui.thread.worker_lifecycle import connect_current, retain_worker, retire_worker


class OmniVoicePrepareThread(QThread):
    progress = pyqtSignal(str)
    prepared = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, root):
        super().__init__()
        self.root = root

    def run(self):
        def check():
            if self.isInterruptionRequested():
                raise RuntimeError("OmniVoice preparation cancelled; resume to continue")
        try:
            root = prepare_runtime(self.root, check=check, progress=self.progress.emit)
            check()
            self.prepared.emit(str(root))
        except Exception as exc:
            if not self.isInterruptionRequested():
                self.failed.emit(str(exc))


class OmniVoicePanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.worker = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.status_label = BodyLabel()
        layout.addWidget(self.status_label)
        row = QHBoxLayout()
        self.runtime_edit = LineEdit()
        self.runtime_edit.setPlaceholderText(str(runtime_root()))
        self.runtime_edit.setText(cfg.omnivoice_runtime.value)
        browse = PushButton(self.tr("Chọn runtime"))
        browse.clicked.connect(self.browse_runtime)
        self.prepare_button = PushButton(self.tr("Chuẩn bị / tiếp tục OmniVoice"))
        self.prepare_button.clicked.connect(self.prepare)
        row.addWidget(self.runtime_edit)
        row.addWidget(browse)
        row.addWidget(self.prepare_button)
        layout.addLayout(row)
        row = QHBoxLayout()
        self.reference_audio = LineEdit()
        self.reference_audio.setPlaceholderText(self.tr("Audio giọng mẫu 3–10 giây (tùy chọn)"))
        self.reference_audio.setText(cfg.omnivoice_reference_audio.value)
        browse = PushButton(self.tr("Chọn giọng mẫu"))
        browse.clicked.connect(self.browse_reference)
        row.addWidget(self.reference_audio)
        row.addWidget(browse)
        layout.addLayout(row)
        self.reference_text = LineEdit()
        self.reference_text.setPlaceholderText(self.tr("Chép đúng lời nói trong audio giọng mẫu; để trống cả hai để dùng giọng tự sinh"))
        self.reference_text.setText(cfg.omnivoice_reference_text.value)
        layout.addWidget(self.reference_text)
        row = QHBoxLayout()
        row.addWidget(BodyLabel(self.tr("Ngôn ngữ OmniVoice:")))
        self.language = LineEdit()
        self.language.setText(cfg.omnivoice_language.value)
        self.language.setFixedWidth(100)
        row.addWidget(self.language)
        row.addWidget(BodyLabel(self.tr("vi = tiếng Việt; en = tiếng Anh; zh = tiếng Trung")))
        row.addStretch()
        layout.addLayout(row)
        self.refresh()

    def refresh(self):
        self.status_label.setText("OmniVoice: " + status(self.runtime_edit.text().strip()))

    def browse_runtime(self):
        root = QFileDialog.getExistingDirectory(self, self.tr("Chọn thư mục runtime OmniVoice"))
        if root:
            self.runtime_edit.setText(root)
            self.refresh()

    def browse_reference(self):
        path, _ = QFileDialog.getOpenFileName(self, self.tr("Chọn audio giọng mẫu"), "", "Audio (*.wav *.flac *.mp3 *.m4a)")
        if path:
            self.reference_audio.setText(path)

    def save(self):
        cfg.set(cfg.omnivoice_runtime, self.runtime_edit.text().strip())
        cfg.set(cfg.omnivoice_reference_audio, self.reference_audio.text().strip())
        cfg.set(cfg.omnivoice_reference_text, self.reference_text.text().strip())
        cfg.set(cfg.omnivoice_language, self.language.text().strip() or "vi")

    def prepare(self):
        if self.worker and self.worker.isRunning():
            retire_worker(self.worker)
            self.prepare_button.setEnabled(False)
            self.status_label.setText(self.tr("Đang dừng; có thể tiếp tục tải sau…"))
            return
        self.save()
        worker = OmniVoicePrepareThread(self.runtime_edit.text().strip())
        self.worker = retain_worker(worker)
        connect_current(self, "worker", worker, worker.progress, self.status_label.setText)
        connect_current(self, "worker", worker, worker.prepared, self.ready)
        connect_current(self, "worker", worker, worker.failed, self.status_label.setText)
        worker.finished.connect(self.finished)
        self.prepare_button.setText(self.tr("Hủy chuẩn bị"))
        worker.start()

    def ready(self, root):
        self.runtime_edit.setText(root)
        cfg.set(cfg.omnivoice_runtime, root)
        self.refresh()

    def finished(self):
        worker = self.sender()
        if not isinstance(worker, QThread) or worker is not self.worker:
            return
        worker.wait()
        self.prepare_button.setEnabled(True)
        self.prepare_button.setText(self.tr("Chuẩn bị / tiếp tục OmniVoice"))

    def stop(self):
        if self.worker and self.worker.isRunning():
            retire_worker(self.worker)

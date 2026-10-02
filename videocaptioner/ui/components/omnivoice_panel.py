"""OmniVoice setup and optional reference controls; long work stays in a QThread."""

from pathlib import Path

from PyQt5.QtCore import QThread, QUrl, pyqtSignal
from PyQt5.QtMultimedia import QMediaContent, QMediaPlayer
from PyQt5.QtWidgets import QApplication, QFileDialog, QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import BodyLabel, ComboBox, LineEdit, PushButton

from videocaptioner.core.tts.omnivoice.config import runtime_root, status
from videocaptioner.core.tts.omnivoice.prepare import prepare_runtime
from videocaptioner.core.tts.omnivoice.voices import ALIASES, list_voices, resolve_voice
from videocaptioner.ui.common.config import cfg
from videocaptioner.ui.thread.omnivoice_voice_thread import OmniVoiceImportThread
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
        self.voice_worker = None
        self.player = QMediaPlayer(self)
        self.player.error.connect(lambda: self.voice_status.setText(self.tr("Không phát được audio giọng mẫu.")))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.status_label = BodyLabel()
        layout.addWidget(self.status_label)
        row = QHBoxLayout()
        self.runtime_edit = LineEdit()
        self.runtime_edit.setPlaceholderText(str(runtime_root()))
        self.runtime_edit.setText(cfg.omnivoice_runtime.value)
        self.browse_runtime_button = PushButton(self.tr("Chọn runtime"))
        self.browse_runtime_button.clicked.connect(self.browse_runtime)
        self.prepare_button = PushButton(self.tr("Chuẩn bị / tiếp tục OmniVoice"))
        self.prepare_button.clicked.connect(self.prepare)
        row.addWidget(self.runtime_edit)
        row.addWidget(self.browse_runtime_button)
        row.addWidget(self.prepare_button)
        layout.addLayout(row)
        row = QHBoxLayout()
        row.addWidget(BodyLabel(self.tr("Giọng OmniVoice:")))
        self.voice_list = ComboBox()
        self.voice_list.setMinimumWidth(230)
        self.preview_button = PushButton(self.tr("Nghe mẫu"))
        self.preview_button.clicked.connect(self.preview_voice)
        self.stop_preview_button = PushButton(self.tr("Dừng nghe"))
        self.stop_preview_button.clicked.connect(self.player.stop)
        row.addWidget(self.voice_list)
        row.addWidget(self.preview_button)
        row.addWidget(self.stop_preview_button)
        row.addStretch()
        layout.addLayout(row)
        self.voice_status = BodyLabel()
        self.voice_status.setWordWrap(True)
        layout.addWidget(self.voice_status)
        self.reference_widget = QWidget(self)
        reference_layout = QVBoxLayout(self.reference_widget)
        reference_layout.setContentsMargins(0, 0, 0, 0)
        row = QHBoxLayout()
        self.reference_audio = LineEdit()
        self.reference_audio.setPlaceholderText(self.tr("Audio giọng mẫu 3–10 giây"))
        self.reference_audio.setText(cfg.omnivoice_reference_audio.value)
        browse = PushButton(self.tr("Chọn giọng mẫu"))
        browse.clicked.connect(self.browse_reference)
        row.addWidget(self.reference_audio)
        row.addWidget(browse)
        reference_layout.addLayout(row)
        self.reference_text = LineEdit()
        self.reference_text.setPlaceholderText(self.tr("Chép đúng lời nói trong audio giọng mẫu; tự đọc file .txt cùng tên nếu có"))
        self.reference_text.setText(cfg.omnivoice_reference_text.value)
        reference_layout.addWidget(self.reference_text)
        row = QHBoxLayout()
        self.voice_name = LineEdit()
        self.voice_name.setPlaceholderText(self.tr("Đặt tên để lưu giọng vào danh sách"))
        self.save_voice_button = PushButton(self.tr("Lưu giọng riêng"))
        self.save_voice_button.clicked.connect(self.import_voice)
        row.addWidget(self.voice_name)
        row.addWidget(self.save_voice_button)
        reference_layout.addLayout(row)
        layout.addWidget(self.reference_widget)
        row = QHBoxLayout()
        row.addWidget(BodyLabel(self.tr("Ngôn ngữ OmniVoice:")))
        self.language = LineEdit()
        self.language.setText(cfg.omnivoice_language.value)
        self.language.setFixedWidth(100)
        row.addWidget(self.language)
        row.addWidget(BodyLabel(self.tr("vi = tiếng Việt; en = tiếng Anh; zh = tiếng Trung")))
        row.addStretch()
        layout.addLayout(row)
        selected = cfg.omnivoice_voice_id.value
        if not selected:
            selected = "reference" if cfg.omnivoice_reference_audio.value else (
                cfg.dubbing_tts_voice.value if cfg.dubbing_tts_provider.value == "omnivoice-local" else "vi-female-1")
            selected = ALIASES.get(selected, selected)
        self.refresh_voices(selected)
        self.voice_list.currentIndexChanged.connect(self.voice_changed)
        app = QApplication.instance()
        if app:
            app.aboutToQuit.connect(self.stop)
        self.refresh()

    def selected_voice(self) -> str:
        return self.voice_list.currentData() or "vi-female-1"

    def refresh_voices(self, selected=None):
        selected = selected or self.selected_voice()
        self.voice_list.blockSignals(True)
        self.voice_list.clear()
        try:
            for profile in list_voices():
                suffix = " · AI cố định" if profile.builtin else " · giọng đã lưu"
                self.voice_list.addItem(profile.name + suffix, userData=profile.voice_id)
        except (OSError, ValueError, KeyError, TypeError):
            self.voice_status.setText(self.tr("Không đọc được thư viện giọng OmniVoice."))
        self.voice_list.addItem(self.tr("Dùng / thêm audio giọng mẫu riêng"), userData="reference")
        self.voice_list.addItem(self.tr("Tự chọn từng câu — có thể đổi giọng"), userData="auto")
        index = self.voice_list.findData(selected)
        if index < 0:
            self.voice_list.addItem(self.tr("Giọng đã chọn không còn trong thư viện"), userData=selected)
            index = self.voice_list.count() - 1
        self.voice_list.setCurrentIndex(index)
        self.voice_list.blockSignals(False)
        self.voice_changed()

    def voice_changed(self, *_):
        self.player.stop()
        selected = self.selected_voice()
        self.reference_widget.setVisible(selected == "reference")
        self.preview_button.setEnabled(selected != "auto")
        if selected == "auto":
            message = self.tr("Tự sinh giọng cho từng câu; chọn giọng AI cố định để giữ cùng người đọc.")
        elif selected == "reference":
            message = self.tr("Chọn audio sạch 3–10 giây của một người và nhập đúng lời mẫu. Lưu giọng để dùng lại ở video khác.")
        else:
            message = self.tr("Dùng cùng một mẫu giọng cho mọi câu. Nghe mẫu để chọn chất giọng phù hợp.")
        self.voice_status.setText(message)

    def preview_voice(self):
        try:
            if self.selected_voice() == "reference":
                path = Path(self.reference_audio.text().strip())
            else:
                profile = resolve_voice(self.selected_voice())
                if profile is None:
                    return
                path = profile.audio_path
            if not path.is_file():
                raise ValueError(self.tr("Chọn audio giọng mẫu trước khi nghe."))
            self.player.setMedia(QMediaContent(QUrl.fromLocalFile(str(path.resolve()))))
            self.player.play()
        except (OSError, ValueError) as exc:
            self.voice_status.setText(str(exc))

    def import_voice(self):
        if self.voice_worker is not None:
            return
        worker = OmniVoiceImportThread(self.voice_name.text(), self.reference_audio.text().strip(),
            self.reference_text.text(), self.language.text())
        self.voice_worker = retain_worker(worker)
        connect_current(self, "voice_worker", worker, worker.saved, self.voice_saved)
        connect_current(self, "voice_worker", worker, worker.failed, self.voice_status.setText)
        worker.finished.connect(self.voice_import_finished)
        self.save_voice_button.setEnabled(False)
        self.voice_status.setText(self.tr("Đang kiểm tra và lưu giọng mẫu…"))
        worker.start()

    def voice_saved(self, voice_id):
        self.refresh_voices(voice_id)
        self.save()
        self.voice_status.setText(self.tr("Đã lưu giọng riêng; bản sao audio sẽ được giữ để dùng lại."))

    def voice_import_finished(self):
        worker = self.sender()
        if isinstance(worker, QThread) and worker is self.voice_worker:
            worker.wait()
            self.voice_worker = None
            self.save_voice_button.setEnabled(True)

    def refresh(self):
        if self.worker is not None:
            return
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
            self.reference_text.clear()
            transcript = Path(path).with_suffix(".txt")
            if transcript.is_file() and transcript.stat().st_size <= 16000:
                try:
                    self.reference_text.setText(transcript.read_text(encoding="utf-8-sig").strip())
                except (OSError, UnicodeError):
                    self.voice_status.setText(self.tr("Không đọc được file .txt cùng tên; nhập lời mẫu thủ công."))

    def save(self):
        if self.worker is None:
            cfg.set(cfg.omnivoice_runtime, self.runtime_edit.text().strip())
        cfg.set(cfg.omnivoice_reference_audio, self.reference_audio.text().strip())
        cfg.set(cfg.omnivoice_reference_text, self.reference_text.text().strip())
        cfg.set(cfg.omnivoice_language, self.language.text().strip() or "vi")
        cfg.set(cfg.omnivoice_voice_id, self.selected_voice())

    def prepare(self):
        if self.worker is not None:
            if self.worker.isRunning():
                retire_worker(self.worker)
                self.prepare_button.setEnabled(False)
                self.status_label.setText(self.tr("Đang dừng; có thể tiếp tục tải sau…"))
            return
        worker = OmniVoicePrepareThread(self.runtime_edit.text().strip())
        self.worker = retain_worker(worker)
        connect_current(self, "worker", worker, worker.progress, self.status_label.setText)
        connect_current(self, "worker", worker, worker.prepared, self.ready)
        connect_current(self, "worker", worker, worker.failed, self.status_label.setText)
        worker.finished.connect(self.finished)
        self.runtime_edit.setEnabled(False)
        self.browse_runtime_button.setEnabled(False)
        self.prepare_button.setText(self.tr("Hủy chuẩn bị"))
        self.status_label.setText(self.tr("Đang chuẩn bị OmniVoice…"))
        worker.start()

    def ready(self, root):
        self.runtime_edit.setText(root)
        cfg.set(cfg.omnivoice_runtime, root)
        self.status_label.setText("OmniVoice: Ready")

    def finished(self):
        worker = self.sender()
        if not isinstance(worker, QThread) or worker is not self.worker:
            return
        worker.wait()
        if getattr(worker, "_vc_cancel_requested", False):
            self.status_label.setText(self.tr("Đã hủy chuẩn bị OmniVoice; có thể tiếp tục tải."))
        self.worker = None
        self.runtime_edit.setEnabled(True)
        self.browse_runtime_button.setEnabled(True)
        self.prepare_button.setEnabled(True)
        self.prepare_button.setText(self.tr("Chuẩn bị / tiếp tục OmniVoice"))

    def stop(self):
        self.player.stop()
        if self.voice_worker and self.voice_worker.isRunning():
            retire_worker(self.voice_worker)
        if self.worker and self.worker.isRunning():
            retire_worker(self.worker)

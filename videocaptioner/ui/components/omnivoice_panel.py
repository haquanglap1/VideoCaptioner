"""OmniVoice setup and optional reference controls; long work stays in a QThread."""

from pathlib import Path

from PyQt5.QtCore import QThread, QUrl, pyqtSignal
from PyQt5.QtMultimedia import QMediaContent, QMediaPlayer
from PyQt5.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import BodyLabel, ComboBox, DoubleSpinBox, LineEdit, PushButton, SpinBox

from videocaptioner.core.tts.omnivoice.config import runtime_root, status
from videocaptioner.core.tts.omnivoice.prepare import prepare_runtime
from videocaptioner.core.tts.omnivoice.voices import ALIASES, list_voices, resolve_voice
from videocaptioner.ui.common.config import cfg
from videocaptioner.ui.components.omnivoice_recorder import ReferenceRecorder
from videocaptioner.ui.thread.omnivoice_tools_thread import OmniVoiceToolsThread
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
        self.tools_worker = None
        self.recorder = ReferenceRecorder(self)
        self.recorder.recorded.connect(self._recorded)
        self.recorder.failed.connect(self._record_failed)
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
        self.record_button = PushButton(self.tr("Thu mẫu microphone (3–10s)"))
        self.record_button.clicked.connect(self._record_reference)
        self.transcribe_button = PushButton(self.tr("Chép lời mẫu bằng ASR đã cài"))
        self.transcribe_button.clicked.connect(self._transcribe_reference)
        row.addWidget(self.record_button)
        row.addWidget(self.transcribe_button)
        reference_layout.addLayout(row)
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
        row = QHBoxLayout()
        row.addWidget(BodyLabel(self.tr("Cấu hình chất lượng:")))
        self.quality_preset = ComboBox()
        self.quality_preset.addItem(self.tr("Cân bằng · 32 bước / FP16"), userData="balanced")
        self.quality_preset.addItem(self.tr("Thử nghiệm · 64 bước / FP16"), userData="more-steps")
        self.quality_preset.setCurrentIndex(self.quality_preset.findData(cfg.omnivoice_quality_preset.value))
        row.addWidget(self.quality_preset)
        row.addStretch()
        layout.addLayout(row)
        hint = BodyLabel(self.tr("64 bước cần nhiều thời gian hơn; cần nghe so sánh. Tốc độ đọc không đổi."))
        hint.setWordWrap(True)
        layout.addWidget(hint)
        row = QHBoxLayout()
        row.addWidget(BodyLabel(self.tr("Pitch (semitone):")))
        self.pitch = DoubleSpinBox()
        self.pitch.setRange(-6, 6)
        self.pitch.setSingleStep(0.5)
        self.pitch.setDecimals(1)
        self.pitch.setValue(cfg.omnivoice_pitch.value)
        row.addWidget(self.pitch)
        row.addWidget(BodyLabel(self.tr("Nghỉ thêm cuối nhóm (ms):")))
        self.pause_ms = SpinBox()
        self.pause_ms.setRange(0, 500)
        self.pause_ms.setValue(cfg.omnivoice_pause_ms.value)
        row.addWidget(self.pause_ms)
        row.addStretch()
        layout.addLayout(row)
        hint = BodyLabel(self.tr("0 giữ nguyên. Dấu , ; : nghỉ thêm 1×; dấu . ? ! nghỉ thêm 2× giá trị trên. "
            "Pitch không đổi tốc độ đọc; audio vượt khung vẫn cần duyệt."))
        hint.setWordWrap(True)
        layout.addWidget(hint)
        row = QHBoxLayout()
        row.addWidget(BodyLabel(self.tr("Số câu trong một batch GPU:")))
        self.batch_size = ComboBox()
        for size in (1, 2, 4):
            self.batch_size.addItem(str(size), userData=size)
        self.batch_size.setCurrentIndex(self.batch_size.findData(cfg.omnivoice_batch_size.value))
        row.addWidget(self.batch_size)
        row.addStretch()
        layout.addLayout(row)
        hint = BodyLabel(self.tr("OmniVoice dùng một worker. Câu dài hoặc thiếu VRAM sẽ chạy batch nhỏ hơn. "
            "Batch GPU khác số luồng gửi request; cần nghe kiểm tra khi đổi batch."))
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.voice_list.currentIndexChanged.connect(self.voice_changed)
        row = QHBoxLayout()
        self.text_audio_button = PushButton(self.tr("Văn bản → WAV + SRT"))
        self.text_audio_button.clicked.connect(self._text_audio_dialog)
        self.cancel_tools_button = PushButton(self.tr("Hủy tiện ích"))
        self.cancel_tools_button.clicked.connect(self._cancel_tools)
        self.cancel_tools_button.hide()
        row.addWidget(self.text_audio_button)
        row.addWidget(self.cancel_tools_button)
        row.addStretch()
        layout.addLayout(row)
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
        cfg.set(cfg.omnivoice_quality_preset, self.quality_preset.currentData())
        cfg.set(cfg.omnivoice_batch_size, self.batch_size.currentData())
        cfg.set(cfg.omnivoice_pitch, self.pitch.value())
        cfg.set(cfg.omnivoice_pause_ms, self.pause_ms.value())

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
        self.recorder.cancel()
        if self.tools_worker and self.tools_worker.isRunning():
            retire_worker(self.tools_worker)
        if self.voice_worker and self.voice_worker.isRunning():
            retire_worker(self.voice_worker)
        if self.worker and self.worker.isRunning():
            retire_worker(self.worker)

    def _set_tools_busy(self, busy, *, recording=False):
        for widget in (self.voice_list, self.reference_audio, self.reference_text,
                       self.save_voice_button, self.transcribe_button, self.text_audio_button):
            widget.setEnabled(not busy)
        self.record_button.setEnabled(not busy or recording)
        self.cancel_tools_button.setVisible(busy and not recording)

    def _record_reference(self):
        if self.recorder.active:
            self.recorder.stop()
        elif self.tools_worker is None:
            self.recorder.start()
            if self.recorder.active:
                self._set_tools_busy(True, recording=True)
                self.record_button.setText(self.tr("Dừng thu mẫu"))
                self.voice_status.setText(self.tr("Đang thu microphone; tự dừng sau 10 giây. Đọc trọn câu trong 3–10 giây."))

    def _recorded(self, path):
        self._set_tools_busy(False)
        self.record_button.setText(self.tr("Thu mẫu microphone (3–10s)"))
        self.reference_audio.setText(path)
        self.reference_text.clear()
        self.voice_status.setText(self.tr("Đã thu mẫu. Nhập hoặc chép lời, duyệt/sửa cho đúng rồi Lưu giọng riêng."))

    def _record_failed(self, message):
        self._set_tools_busy(False)
        self.record_button.setText(self.tr("Thu mẫu microphone (3–10s)"))
        self.voice_status.setText(message)

    def _transcribe_reference(self):
        from videocaptioner.core.tts.omnivoice.reference import ReferenceASROptions

        if self.tools_worker is not None or not self.reference_audio.text().strip():
            return
        options = ReferenceASROptions(program=cfg.faster_whisper_program.value,
            model_dir=cfg.faster_whisper_model_dir.value, model=cfg.faster_whisper_model.value.value,
            device=cfg.faster_whisper_device.value, language=self.language.text().strip() or "vi")
        self._start_tools(OmniVoiceToolsThread("transcribe", audio=self.reference_audio.text().strip(), asr_options=options))

    def _speech_config(self):
        from videocaptioner.core.dubbing.config import DubbingConfig, TTSProviderEnum
        from videocaptioner.core.tts import TTSConfig
        from videocaptioner.core.tts.omnivoice.config import OmniVoiceOptions

        reference = self.selected_voice() == "reference"
        return DubbingConfig(tts_provider=TTSProviderEnum.OMNIVOICE_LOCAL,
            tts_config=TTSConfig("", "", "", voice=self.selected_voice(), speed=1, sample_rate=24000),
            omnivoice=OmniVoiceOptions(runtime=self.runtime_edit.text().strip(),
                reference_audio=self.reference_audio.text().strip() if reference else "",
                reference_text=self.reference_text.text().strip() if reference else "",
                language=self.language.text().strip() or "vi", quality_preset=str(self.quality_preset.currentData() or "balanced"),
                batch_size=int(self.batch_size.currentData() or 1), pitch_semitones=self.pitch.value(),
                punctuation_pause_ms=self.pause_ms.value()))

    def _text_audio_dialog(self):
        from videocaptioner.core.dubbing.vietnamese_text import suggest_vietnamese

        if self.tools_worker is not None:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle(self.tr("Văn bản → WAV + SRT"))
        dialog.resize(720, 500)
        layout = QVBoxLayout(dialog)
        label = BodyLabel(self.tr("Mỗi dòng là một đoạn. Đọc đủ ở 1×, nghỉ 80ms giữa các đoạn; SRT theo WAV đã đo."))
        label.setWordWrap(True)
        layout.addWidget(label)
        editor = QPlainTextEdit()
        editor.setPlaceholderText(self.tr("Nhập và duyệt lời sẽ đọc…"))
        layout.addWidget(editor)
        suggest = PushButton(self.tr("Gợi ý lời đọc tiếng Việt"))
        def propose():
            result = suggest_vietnamese(editor.toPlainText())
            editor.setPlainText(result.text)
            label.setText("\n".join(result.warnings) or self.tr("Duyệt/sửa lời đọc trước khi xuất."))
        suggest.clicked.connect(propose)
        layout.addWidget(suggest)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText(self.tr("Chọn nơi xuất WAV + SRT"))
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec_() != QDialog.Accepted or not editor.toPlainText().strip():
            return
        output, _ = QFileDialog.getSaveFileName(self, self.tr("Xuất WAV + SRT bằng tên mới"), "", "WAV (*.wav)")
        if not output:
            return
        try:
            config = self._speech_config()
        except ValueError as exc:
            self.voice_status.setText(str(exc))
            return
        self._start_tools(OmniVoiceToolsThread("text_audio", text=editor.toPlainText(), output=output, config=config))

    def _start_tools(self, worker):
        if self.tools_worker is not None:
            return
        self.tools_worker = retain_worker(worker)
        self._set_tools_busy(True)
        connect_current(self, "tools_worker", worker, worker.progress, self.voice_status.setText)
        connect_current(self, "tools_worker", worker, worker.failed, self.voice_status.setText)
        connect_current(self, "tools_worker", worker, worker.completed, self._tools_result)
        worker.finished.connect(self._tools_finished)
        worker.start()

    def _tools_result(self, result):
        from videocaptioner.core.tts.omnivoice.reference import ReferenceTranscript

        if isinstance(result, ReferenceTranscript):
            try:
                selected = Path(self.reference_audio.text()).resolve()
                stamp = selected.stat()
                if str(selected) != result.audio_path or (stamp.st_size, stamp.st_mtime_ns) != result.source_stamp:
                    raise ValueError("Audio mẫu đã đổi; không áp dụng transcript cũ.")
            except (OSError, ValueError) as exc:
                self.voice_status.setText(str(exc))
                return
            self.reference_text.setText(result.text)
            self.voice_status.setText(self.tr("Bản chép ASR là gợi ý. Hãy duyệt/sửa đúng lời mẫu trước khi Lưu giọng riêng."))
        else:
            self.voice_status.setText(self.tr("Đã xuất WAV + SRT: ") + result.audio_path)

    def _tools_finished(self):
        worker = self.sender()
        if not isinstance(worker, QThread) or worker is not self.tools_worker:
            return
        worker.wait()
        if getattr(worker, "_vc_cancel_requested", False):
            self.voice_status.setText(self.tr("Đã hủy chép lời mẫu.") if getattr(worker, "operation", "") == "transcribe"
                else self.tr("Đã hủy tiện ích; các đoạn audio đã tạo được giữ để kiểm tra."))
        self.tools_worker = None
        self._set_tools_busy(False)

    def _cancel_tools(self):
        if self.tools_worker is not None:
            retire_worker(self.tools_worker)

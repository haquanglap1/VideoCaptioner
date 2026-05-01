"""Dubbing interface — tab lồng tiếng video.

Hỗ trợ 2 chế độ:
- Pipeline tự động: nhận task từ HomeInterface (subtitle → dub → synthesis)
- Thủ công: người dùng chọn video + SRT rồi bấm "Lồng tiếng"
"""

from pathlib import Path

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    BodyLabel,
    ComboBox,
    InfoBar,
    InfoBarPosition,
    LineEdit,
    PrimaryPushButton,
    ProgressBar,
    PushButton,
    Slider,
    StrongBodyLabel,
    SwitchButton,
)

from videocaptioner.core.entities import DubbingTask
from videocaptioner.core.utils.logger import setup_logger
from videocaptioner.ui.common.config import cfg
from videocaptioner.ui.task_factory import TaskFactory
from videocaptioner.ui.thread.dubbing_thread import DubbingThread

logger = setup_logger("dubbing_interface")


class DubbingInterface(QWidget):
    """Tab lồng tiếng — cho phép lồng tiếng video bằng TTS.

    Khi chạy trong pipeline (set_task + process), dubbing tự động skip nếu tắt.
    Khi chạy thủ công (bấm nút), user chọn file video + SRT.
    """

    finished = pyqtSignal(str, str)  # (video_path, subtitle_path) cho next step

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("DubbingInterface")
        self._task: DubbingTask | None = None
        self._thread: DubbingThread | None = None
        self._is_pipeline_mode = False
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(12)

        # --- Enable switch ---
        enable_row = QHBoxLayout()
        enable_label = StrongBodyLabel(self.tr("Bật lồng tiếng"))
        self.enable_switch = SwitchButton()
        self.enable_switch.setChecked(cfg.dubbing_enabled.value)
        self.enable_switch.checkedChanged.connect(self._on_enable_changed)
        enable_row.addWidget(enable_label)
        enable_row.addStretch()
        enable_row.addWidget(self.enable_switch)
        layout.addLayout(enable_row)

        # --- Settings container (disabled when dubbing is off) ---
        self.settings_widget = QWidget()
        settings_layout = QVBoxLayout(self.settings_widget)
        settings_layout.setContentsMargins(0, 0, 0, 0)
        settings_layout.setSpacing(8)

        # TTS Provider
        row1 = QHBoxLayout()
        row1.addWidget(BodyLabel(self.tr("TTS Provider:")))
        self.provider_combo = ComboBox()
        self.provider_combo.addItems(["OpenAI", "SiliconFlow", "OpenAI.fm"])
        _provider_map = {"openai": 0, "siliconflow": 1, "openai_fm": 2}
        self.provider_combo.setCurrentIndex(
            _provider_map.get(cfg.dubbing_tts_provider.value, 0)
        )
        self.provider_combo.currentIndexChanged.connect(self._on_provider_changed)
        row1.addWidget(self.provider_combo)
        row1.addStretch()
        settings_layout.addLayout(row1)

        # Voice
        row2 = QHBoxLayout()
        row2.addWidget(BodyLabel(self.tr("Giọng nói:")))
        self.voice_edit = LineEdit()
        self.voice_edit.setPlaceholderText("alloy, echo, fable, onyx, nova, shimmer")
        self.voice_edit.setText(cfg.dubbing_tts_voice.value)
        self.voice_edit.setFixedWidth(200)
        row2.addWidget(self.voice_edit)
        row2.addStretch()
        settings_layout.addLayout(row2)

        # API Key
        row3 = QHBoxLayout()
        row3.addWidget(BodyLabel(self.tr("API Key:")))
        self.api_key_edit = LineEdit()
        self.api_key_edit.setPlaceholderText("sk-...")
        self.api_key_edit.setText(cfg.dubbing_tts_api_key.value)
        self.api_key_edit.setEchoMode(LineEdit.Password)
        self.api_key_edit.setFixedWidth(300)
        row3.addWidget(self.api_key_edit)
        row3.addStretch()
        settings_layout.addLayout(row3)

        # API Base
        row4 = QHBoxLayout()
        row4.addWidget(BodyLabel(self.tr("API Base:")))
        self.api_base_edit = LineEdit()
        self.api_base_edit.setText(cfg.dubbing_tts_api_base.value)
        self.api_base_edit.setFixedWidth(300)
        row4.addWidget(self.api_base_edit)
        row4.addStretch()
        settings_layout.addLayout(row4)

        # Model
        row5 = QHBoxLayout()
        row5.addWidget(BodyLabel(self.tr("Model:")))
        self.model_edit = LineEdit()
        self.model_edit.setText(cfg.dubbing_tts_model.value)
        self.model_edit.setFixedWidth(200)
        row5.addWidget(self.model_edit)
        row5.addStretch()
        settings_layout.addLayout(row5)

        # Mix Mode
        row6 = QHBoxLayout()
        row6.addWidget(BodyLabel(self.tr("Chế độ audio gốc:")))
        self.mix_combo = ComboBox()
        self.mix_combo.addItems([
            self.tr("Giữ nguyên"),
            self.tr("Giảm âm lượng nền"),
            self.tr("Tắt audio gốc"),
        ])
        _mix_map = {"keep": 0, "reduce": 1, "mute": 2}
        self.mix_combo.setCurrentIndex(
            _mix_map.get(cfg.dubbing_mix_mode.value, 1)
        )
        row6.addWidget(self.mix_combo)
        row6.addStretch()
        settings_layout.addLayout(row6)

        # Volume slider
        row7 = QHBoxLayout()
        row7.addWidget(BodyLabel(self.tr("Âm lượng nền:")))
        self.volume_slider = Slider(Qt.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(cfg.dubbing_original_volume.value)
        self.volume_slider.setFixedWidth(200)
        self.volume_label = BodyLabel(f"{cfg.dubbing_original_volume.value}%")
        self.volume_slider.valueChanged.connect(
            lambda v: self.volume_label.setText(f"{v}%")
        )
        row7.addWidget(self.volume_slider)
        row7.addWidget(self.volume_label)
        row7.addStretch()
        settings_layout.addLayout(row7)

        # --- Separator ---
        settings_layout.addSpacing(10)

        # --- Manual mode: file selectors ---
        manual_label = StrongBodyLabel(self.tr("Lồng tiếng thủ công"))
        settings_layout.addWidget(manual_label)

        # Video file
        row_video = QHBoxLayout()
        row_video.addWidget(BodyLabel(self.tr("📁 File video:")))
        self.video_path_edit = LineEdit()
        self.video_path_edit.setPlaceholderText(
            self.tr("Chọn file video (.mp4, .mkv, ...)")
        )
        self.video_path_edit.setFixedWidth(350)
        row_video.addWidget(self.video_path_edit)
        self.browse_video_btn = PushButton(self.tr("Duyệt"))
        self.browse_video_btn.setFixedWidth(60)
        self.browse_video_btn.clicked.connect(self._browse_video)
        row_video.addWidget(self.browse_video_btn)
        row_video.addStretch()
        settings_layout.addLayout(row_video)

        # Subtitle file
        row_sub = QHBoxLayout()
        row_sub.addWidget(BodyLabel(self.tr("📁 File phụ đề:")))
        self.subtitle_path_edit = LineEdit()
        self.subtitle_path_edit.setPlaceholderText(
            self.tr("Chọn file phụ đề (.srt, .ass, .vtt)")
        )
        self.subtitle_path_edit.setFixedWidth(350)
        row_sub.addWidget(self.subtitle_path_edit)
        self.browse_sub_btn = PushButton(self.tr("Duyệt"))
        self.browse_sub_btn.setFixedWidth(60)
        self.browse_sub_btn.clicked.connect(self._browse_subtitle)
        row_sub.addWidget(self.browse_sub_btn)
        row_sub.addStretch()
        settings_layout.addLayout(row_sub)

        # Manual dub button
        self.manual_dub_btn = PrimaryPushButton(self.tr("▶ Lồng tiếng"))
        self.manual_dub_btn.setFixedWidth(160)
        self.manual_dub_btn.clicked.connect(self._start_manual_dub)
        settings_layout.addWidget(self.manual_dub_btn, alignment=Qt.AlignCenter)

        layout.addWidget(self.settings_widget)
        self.settings_widget.setEnabled(cfg.dubbing_enabled.value)

        # Spacer
        layout.addStretch()

        # --- Progress ---
        self.progress_bar = ProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        self.status_label = BodyLabel("")
        self.status_label.setVisible(False)
        layout.addWidget(self.status_label)

    # ==== Public API (called by HomeInterface pipeline) ====

    def set_task(self, task: DubbingTask):
        """Đặt task trước khi bắt đầu xử lý (pipeline mode)."""
        self._task = task
        self._is_pipeline_mode = True

    def process(self):
        """Bắt đầu dubbing (pipeline mode)."""
        if not self._task:
            return

        config = self._task.dubbing_config
        if not config or not config.enabled:
            # Dubbing tắt — emit finished ngay để chuyển sang synthesis
            logger.info("Dubbing tắt, bỏ qua")
            self.finished.emit(
                self._task.video_path or "",
                self._task.subtitle_path or "",
            )
            return

        self._run_dubbing(self._task)

    # ==== Manual mode ====

    def _browse_video(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            self.tr("Chọn file video"),
            "",
            self.tr("Video Files (*.mp4 *.mkv *.avi *.mov *.webm *.flv *.ts)"),
        )
        if path:
            self.video_path_edit.setText(path)

    def _browse_subtitle(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            self.tr("Chọn file phụ đề"),
            "",
            self.tr("Subtitle Files (*.srt *.ass *.vtt)"),
        )
        if path:
            self.subtitle_path_edit.setText(path)

    def _start_manual_dub(self):
        """Bắt đầu lồng tiếng thủ công."""
        video_path = self.video_path_edit.text().strip()
        subtitle_path = self.subtitle_path_edit.text().strip()

        if not video_path or not Path(video_path).is_file():
            InfoBar.warning(
                self.tr("Thiếu file"),
                self.tr("Vui lòng chọn file video hợp lệ"),
                duration=3000,
                position=InfoBarPosition.BOTTOM,
                parent=self.window(),
            )
            return

        if not subtitle_path or not Path(subtitle_path).is_file():
            InfoBar.warning(
                self.tr("Thiếu file"),
                self.tr("Vui lòng chọn file phụ đề hợp lệ"),
                duration=3000,
                position=InfoBarPosition.BOTTOM,
                parent=self.window(),
            )
            return

        # Save settings first
        self._save_settings()

        # Create task
        self._is_pipeline_mode = False
        task = TaskFactory.create_dubbing_task(video_path, subtitle_path)
        self._task = task
        self._run_dubbing(task)

    # ==== Shared execution ====

    def _run_dubbing(self, task: DubbingTask):
        """Thực thi dubbing task."""
        # Save current settings to config
        self._save_settings()

        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)
        self.status_label.setVisible(True)
        self.status_label.setText(self.tr("Đang bắt đầu lồng tiếng..."))
        self.manual_dub_btn.setEnabled(False)

        self._thread = DubbingThread(task)
        self._thread.progress.connect(self._on_progress)
        self._thread.error.connect(self._on_error)
        self._thread.finished.connect(self._on_finished)
        self._thread.start()

    # ==== Slots ====

    def _on_enable_changed(self, checked: bool):
        self.settings_widget.setEnabled(checked)
        cfg.set(cfg.dubbing_enabled, checked)

    def _on_provider_changed(self, index: int):
        provider_keys = ["openai", "siliconflow", "openai_fm"]
        if 0 <= index < len(provider_keys):
            cfg.set(cfg.dubbing_tts_provider, provider_keys[index])

    def _on_progress(self, value: int, message: str):
        self.progress_bar.setValue(value)
        self.status_label.setText(message)

    def _on_error(self, error_msg: str):
        self.progress_bar.setVisible(False)
        self.status_label.setText(self.tr("Lồng tiếng thất bại"))
        self.manual_dub_btn.setEnabled(True)
        InfoBar.error(
            self.tr("Lỗi lồng tiếng"),
            error_msg,
            duration=5000,
            position=InfoBarPosition.BOTTOM,
            parent=self.window(),
        )
        # In pipeline mode: emit finished with original video (non-fatal)
        if self._is_pipeline_mode and self._task:
            self.finished.emit(
                self._task.video_path or "",
                self._task.subtitle_path or "",
            )

    def _on_finished(self, task: DubbingTask):
        self.progress_bar.setValue(100)
        self.status_label.setText(self.tr("Lồng tiếng hoàn tất!"))
        self.manual_dub_btn.setEnabled(True)

        InfoBar.success(
            self.tr("Thành công"),
            self.tr("Đã lồng tiếng: ") + str(task.output_path or ""),
            duration=5000,
            position=InfoBarPosition.BOTTOM,
            parent=self.window(),
        )

        # In pipeline mode: emit dubbed video for synthesis
        if self._is_pipeline_mode:
            self.finished.emit(
                task.output_path or task.video_path or "",
                task.subtitle_path or "",
            )

    def _save_settings(self):
        """Lưu settings hiện tại vào persistent config."""
        cfg.set(cfg.dubbing_tts_voice, self.voice_edit.text())
        cfg.set(cfg.dubbing_tts_api_key, self.api_key_edit.text())
        cfg.set(cfg.dubbing_tts_api_base, self.api_base_edit.text())
        cfg.set(cfg.dubbing_tts_model, self.model_edit.text())

        mix_keys = ["keep", "reduce", "mute"]
        idx = self.mix_combo.currentIndex()
        if 0 <= idx < len(mix_keys):
            cfg.set(cfg.dubbing_mix_mode, mix_keys[idx])
        cfg.set(cfg.dubbing_original_volume, self.volume_slider.value())

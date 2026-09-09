"""Dubbing interface — tab lồng tiếng video.

Hỗ trợ 2 chế độ:
- Pipeline tự động: nhận task từ HomeInterface (subtitle → dub → synthesis)
- Thủ công: người dùng chọn video + SRT rồi bấm "Lồng tiếng"
"""

from dataclasses import replace
from pathlib import Path
from typing import Literal

from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    BodyLabel,
    ComboBox,
    EditableComboBox,
    FlowLayout,
    InfoBar,
    InfoBarPosition,
    LineEdit,
    PrimaryPushButton,
    ProgressBar,
    PushButton,
    ScrollArea,
    Slider,
    SpinBox,
    StrongBodyLabel,
    SwitchButton,
)

from videocaptioner.config import MODEL_PATH
from videocaptioner.core.dubbing import presets
from videocaptioner.core.dubbing.review import DubbingReview
from videocaptioner.core.entities import DubbingTask
from videocaptioner.core.tts.vieneu.model_updater import VieNeuUpdateCheck
from videocaptioner.core.utils.logger import setup_logger
from videocaptioner.core.utils.platform_utils import open_folder
from videocaptioner.ui.common.config import cfg
from videocaptioner.ui.components.dubbing_review_dialog import DubbingReviewDialog
from videocaptioner.ui.components.DubbingReportDialog import DubbingReportDialog
from videocaptioner.ui.components.omnivoice_panel import OmniVoicePanel
from videocaptioner.ui.task_factory import TaskFactory
from videocaptioner.ui.thread.audio_merge_thread import AudioMergeThread
from videocaptioner.ui.thread.dubbing_thread import DubbingReviewFileThread, DubbingThread
from videocaptioner.ui.thread.vieneu_runtime_thread import VieNeuRuntimeThread

logger = setup_logger("dubbing_interface")


class VoiceFetchThread(QThread):
    """Luồng phụ để tải danh sách model/giọng nói từ API (Local AI)."""
    finished_fetch = pyqtSignal(list, str)  # (models, error_msg)

    def __init__(self, api_base: str, api_key: str):
        super().__init__()
        self.api_base = api_base
        self.api_key = api_key

    def run(self):
        import requests
        try:
            base_url = self.api_base.rstrip("/")
            if not base_url:
                self.finished_fetch.emit([], "Thiếu API Base")
                return

            headers = {}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"

            models_url = f"{base_url}/models"
            response = requests.get(models_url, headers=headers, timeout=10)
            if response.status_code != 200:
                self.finished_fetch.emit(
                    [], f"HTTP {response.status_code}: {response.text[:200]}"
                )
                return

            try:
                data = response.json()
            except ValueError:
                # Response không phải JSON — thường do API Base sai endpoint
                self.finished_fetch.emit(
                    [],
                    f"API không trả về JSON hợp lệ tại {models_url}. "
                    "Kiểm tra lại API Base (endpoint tương thích OpenAI /models). "
                    "Nếu dùng MiniMax, hãy chọn provider MiniMax thay vì Local AI.",
                )
                return

            models = []
            # Handle standard OpenAI /v1/models response
            if isinstance(data, dict) and isinstance(data.get("data"), list):
                for m in data["data"]:
                    if isinstance(m, dict) and "id" in m:
                        models.append(m["id"])
            self.finished_fetch.emit(models, "")
        except Exception as e:
            self.finished_fetch.emit([], str(e))


class DubbingInterface(QWidget):
    """Tab lồng tiếng — cho phép lồng tiếng video bằng TTS.

    Khi chạy trong pipeline (set_task + process), dubbing tự động skip nếu tắt.
    Khi chạy thủ công (bấm nút), user chọn file video + SRT.
    """

    finished = pyqtSignal(str, str)  # (video_path, subtitle_path) cho next step
    openInVideoEditorRequested = pyqtSignal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("DubbingInterface")
        self._task: DubbingTask | None = None
        self._thread: DubbingThread | None = None
        self._review_thread: DubbingReviewFileThread | None = None
        self._job_busy = False
        self._closing = False
        self._job_result: DubbingTask | None = None
        self._job_error = ""
        self._job_cancelled = False
        self._file_result: DubbingReview | None = None
        self._is_pipeline_mode = False
        self._pending_report_data: dict = {}
        self._vieneu_threads: set[VieNeuRuntimeThread] = set()
        self._vieneu_pending_action = ""
        self._vieneu_launch_check = False
        self._vieneu_offered_revision = ""
        self._init_ui()

    def _init_ui(self):
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        self.scroll_area = ScrollArea(self)
        self.scroll_content = QWidget()
        self.scroll_area.setWidget(self.scroll_content)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.enableTransparentBackground()
        self.scroll_area.viewport().setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.scroll_content.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        outer_layout.addWidget(self.scroll_area)
        layout = QVBoxLayout(self.scroll_content)
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
        self.provider_combo.addItems(["OpenAI", "MiniMax", "Local AI", "VieNeu Local", "OmniVoice Local"])
        _provider_map = {key: i for i, key in enumerate(presets.TTS_PROVIDER_KEYS)}
        self.provider_combo.setCurrentIndex(
            _provider_map.get(cfg.dubbing_tts_provider.value, 0)
        )
        self.provider_combo.currentIndexChanged.connect(self._on_provider_changed)
        row1.addWidget(self.provider_combo)
        row1.addStretch()
        settings_layout.addLayout(row1)

        self.vieneu_widget = QWidget(self.settings_widget)
        vieneu_layout = QHBoxLayout(self.vieneu_widget)
        vieneu_layout.setContentsMargins(0, 0, 0, 0)
        self.vieneu_status_label = BodyLabel(self.tr("VieNeu: Stopped"))
        self.vieneu_start_stop_btn = PushButton(self.tr("Start"))
        self.vieneu_update_btn = PushButton(self.tr("Check for model update"))
        self.vieneu_rollback_btn = PushButton(self.tr("Rollback"))
        self.vieneu_folder_btn = PushButton(self.tr("Open model folder"))
        self.vieneu_auto_update_switch = SwitchButton()
        self.vieneu_auto_update_switch.setChecked(cfg.vieneu_auto_update.value)
        self.vieneu_auto_update_switch.checkedChanged.connect(
            lambda checked: cfg.set(cfg.vieneu_auto_update, checked)
        )
        self.vieneu_start_stop_btn.clicked.connect(self._toggle_vieneu_runtime)
        self.vieneu_update_btn.clicked.connect(
            lambda: self._start_vieneu_action("check")
        )
        self.vieneu_rollback_btn.clicked.connect(
            lambda: self._start_vieneu_action("rollback")
        )
        self.vieneu_folder_btn.clicked.connect(
            lambda: open_folder(str(MODEL_PATH / "vieneu"))
        )
        vieneu_layout.addWidget(self.vieneu_status_label)
        vieneu_layout.addWidget(self.vieneu_start_stop_btn)
        vieneu_layout.addWidget(self.vieneu_update_btn)
        vieneu_layout.addWidget(self.vieneu_rollback_btn)
        vieneu_layout.addWidget(self.vieneu_folder_btn)
        vieneu_layout.addWidget(BodyLabel(self.tr("Auto update")))
        vieneu_layout.addWidget(self.vieneu_auto_update_switch)
        vieneu_layout.addStretch()
        settings_layout.addWidget(self.vieneu_widget)
        self.omnivoice_panel = OmniVoicePanel(self.settings_widget)
        settings_layout.addWidget(self.omnivoice_panel)

        # Voice
        row2 = QHBoxLayout()
        row2.addWidget(BodyLabel(self.tr("Giọng nói:")))
        self.voice_combo = EditableComboBox()
        self.voice_combo.setPlaceholderText(self.tr("Chọn hoặc nhập tên giọng nói..."))
        self.voice_combo.setFixedWidth(200)

        # Load saved voice if any
        saved_voice = cfg.dubbing_tts_voice.value
        self.voice_combo.setText(saved_voice)

        self.fetch_voice_btn = PushButton(self.tr("Tải danh sách"))
        self.fetch_voice_btn.setFixedWidth(120)
        self.fetch_voice_btn.clicked.connect(self._fetch_voices)

        row2.addWidget(self.voice_combo)
        row2.addWidget(self.fetch_voice_btn)
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

        # Spoken text routing
        row5a = QHBoxLayout()
        row5a.addWidget(BodyLabel(self.tr("Nguồn văn bản TTS:")))
        self.text_source_combo = ComboBox()
        self.text_source_combo.addItems(
            [self.tr("Tự động"), self.tr("Bản dịch"), self.tr("Bản gốc")]
        )
        source_keys = ["auto", "translated", "original"]
        self.text_source_combo.setCurrentIndex(
            source_keys.index(cfg.dubbing_text_source.value)
        )
        row5a.addWidget(self.text_source_combo)
        row5a.addStretch()
        settings_layout.addLayout(row5a)

        # Timing policy
        row5b = QHBoxLayout()
        row5b.addWidget(BodyLabel(self.tr("Chế độ timing:")))
        self.timing_mode_combo = ComboBox()
        self.timing_mode_combo.addItems([self.tr("Tự nhiên"), self.tr("Legacy")])
        self.timing_mode_combo.setCurrentIndex(
            0 if cfg.dubbing_timing_mode.value == "natural" else 1
        )
        self.timing_mode_combo.currentIndexChanged.connect(
            self._update_timing_controls
        )
        row5b.addWidget(self.timing_mode_combo)
        row5b.addStretch()
        settings_layout.addLayout(row5b)

        row5c = QHBoxLayout()
        row5c.addWidget(BodyLabel(self.tr("Tốc độ Natural tối đa:")))
        self.natural_speed_slider = Slider(Qt.Orientation.Horizontal)
        self.natural_speed_slider.setRange(100, 150)
        self.natural_speed_slider.setValue(cfg.dubbing_natural_max_speed.value)
        self.natural_speed_slider.setFixedWidth(200)
        self.natural_speed_label = BodyLabel(
            f"{cfg.dubbing_natural_max_speed.value / 100.0:.2f}x"
        )
        self.natural_speed_slider.valueChanged.connect(
            lambda v: self.natural_speed_label.setText(f"{v / 100.0:.2f}x")
        )
        row5c.addWidget(self.natural_speed_slider)
        row5c.addWidget(self.natural_speed_label)
        row5c.addStretch()
        settings_layout.addLayout(row5c)

        row5d = QHBoxLayout()
        row5d.addWidget(BodyLabel(self.tr("LLM rút gọn riêng lời đọc vượt khung:")))
        self.rewrite_switch = SwitchButton()
        self.rewrite_switch.setChecked(cfg.dubbing_timing_rewrite.value)
        row5d.addWidget(self.rewrite_switch)
        row5d.addWidget(BodyLabel(self.tr("Cache TTS:")))
        self.tts_cache_switch = SwitchButton()
        self.tts_cache_switch.setChecked(cfg.dubbing_tts_cache.value)
        row5d.addWidget(self.tts_cache_switch)
        row5d.addStretch()
        settings_layout.addLayout(row5d)

        row5e = QHBoxLayout()
        row5e.addWidget(BodyLabel(self.tr("Khi vẫn vượt timing:")))
        self.unresolved_combo = ComboBox()
        self.unresolved_combo.addItems(
            [self.tr("Yêu cầu xem lại"), self.tr("Cho phép chồng lấn"), self.tr("Nhịp đọc đều, không chồng lời")]
        )
        self.unresolved_combo.setCurrentIndex(
            presets.UNRESOLVED_POLICY_KEYS.index(cfg.dubbing_unresolved_policy.value)
        )
        self.unresolved_combo.currentIndexChanged.connect(self._update_timing_controls)
        row5e.addWidget(self.unresolved_combo)
        row5e.addStretch()
        settings_layout.addLayout(row5e)
        row5f = QHBoxLayout()
        row5f.addWidget(BodyLabel(self.tr("Độ trễ bắt đầu tối đa (ms):")))
        self.start_delay_spinbox = SpinBox()
        self.start_delay_spinbox.setRange(0, 10000)
        self.start_delay_spinbox.setSingleStep(100)
        self.start_delay_spinbox.setValue(cfg.dubbing_max_start_delay_ms.value)
        row5f.addWidget(self.start_delay_spinbox)
        start_delay_hint = BodyLabel(self.tr("Gợi ý: 2500 ms, tốc độ 1.00–1.05×; ưu tiên LLM rút lời dài"))
        start_delay_hint.setWordWrap(True)
        row5f.addWidget(start_delay_hint)
        row5f.addStretch()
        settings_layout.addLayout(row5f)

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
        self.volume_slider = Slider(Qt.Orientation.Horizontal)
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

        # Speed slider (giá trị lưu dạng 10x: 10 = 1.0x)
        row8 = QHBoxLayout()
        row8.addWidget(BodyLabel(self.tr("Tốc độ giọng:")))
        self.speed_slider = Slider(Qt.Orientation.Horizontal)
        self.speed_slider.setRange(5, 20)  # 0.5x - 2.0x
        self.speed_slider.setValue(cfg.dubbing_tts_speed.value)
        self.speed_slider.setFixedWidth(200)
        self.speed_label = BodyLabel(f"{cfg.dubbing_tts_speed.value / 10.0:.1f}x")
        self.speed_slider.valueChanged.connect(
            lambda v: self.speed_label.setText(f"{v / 10.0:.1f}x")
        )
        row8.addWidget(self.speed_slider)
        row8.addWidget(self.speed_label)
        row8.addStretch()
        settings_layout.addLayout(row8)

        # Max speed slider — trần tăng tốc khi căn timeline (10 = 1.0x .. 30 = 3.0x)
        row8b = QHBoxLayout()
        row8b.addWidget(BodyLabel(self.tr("Tốc độ tối đa:")))
        self.max_speed_slider = Slider(Qt.Orientation.Horizontal)
        self.max_speed_slider.setRange(10, 30)
        self.max_speed_slider.setValue(cfg.dubbing_max_speed.value)
        self.max_speed_slider.setFixedWidth(200)
        self.max_speed_label = BodyLabel(f"{cfg.dubbing_max_speed.value / 10.0:.1f}x")
        self.max_speed_slider.valueChanged.connect(
            lambda v: self.max_speed_label.setText(f"{v / 10.0:.1f}x")
        )
        row8b.addWidget(self.max_speed_slider)
        row8b.addWidget(self.max_speed_label)
        row8b.addStretch()
        settings_layout.addLayout(row8b)

        # Sample rate (chất lượng audio)
        row9 = QHBoxLayout()
        row9.addWidget(BodyLabel(self.tr("Chất lượng (Hz):")))
        self.sample_rate_combo = ComboBox()
        self._sample_rates = list(presets.SAMPLE_RATES)
        self.sample_rate_combo.addItems([str(r) for r in self._sample_rates])
        try:
            self.sample_rate_combo.setCurrentIndex(
                self._sample_rates.index(cfg.dubbing_tts_sample_rate.value)
            )
        except ValueError:
            self.sample_rate_combo.setCurrentIndex(2)  # 32000
        row9.addWidget(self.sample_rate_combo)
        row9.addStretch()
        settings_layout.addLayout(row9)

        # Voice volume slider (giá trị lưu dạng %: 100 = 1.0x)
        row10 = QHBoxLayout()
        row10.addWidget(BodyLabel(self.tr("Âm lượng giọng:")))
        self.voice_volume_slider = Slider(Qt.Orientation.Horizontal)
        self.voice_volume_slider.setRange(50, 300)
        self.voice_volume_slider.setValue(cfg.dubbing_voice_volume.value)
        self.voice_volume_slider.setFixedWidth(200)
        self.voice_volume_label = BodyLabel(f"{cfg.dubbing_voice_volume.value}%")
        self.voice_volume_slider.valueChanged.connect(
            lambda v: self.voice_volume_label.setText(f"{v}%")
        )
        row10.addWidget(self.voice_volume_slider)
        row10.addWidget(self.voice_volume_label)
        row10.addStretch()
        settings_layout.addLayout(row10)

        # TTS concurrency (số luồng chạy song song) — nhập trực tiếp
        row11 = QHBoxLayout()
        row11.addWidget(BodyLabel(self.tr("Số luồng TTS:")))
        self.concurrency_spinbox = SpinBox()
        self.concurrency_spinbox.setRange(1, 48)
        self.concurrency_spinbox.setValue(cfg.dubbing_tts_concurrency.value)
        self.concurrency_spinbox.setFixedWidth(120)
        row11.addWidget(self.concurrency_spinbox)
        row11.addStretch()
        settings_layout.addLayout(row11)

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

        row_display = QHBoxLayout()
        row_display.addWidget(BodyLabel(self.tr("SRT hiển thị (tùy chọn):")))
        self.display_subtitle_path_edit = LineEdit()
        self.display_subtitle_path_edit.setPlaceholderText(self.tr("Để trống để dùng file phụ đề phía trên"))
        self.display_subtitle_path_edit.setFixedWidth(350)
        row_display.addWidget(self.display_subtitle_path_edit)
        self.browse_display_btn = PushButton(self.tr("Duyệt"))
        self.browse_display_btn.setFixedWidth(60)
        self.browse_display_btn.clicked.connect(self._browse_display_subtitle)
        row_display.addWidget(self.browse_display_btn)
        row_display.addStretch()
        settings_layout.addLayout(row_display)

        row_cache = QHBoxLayout()
        row_cache.addWidget(BodyLabel(self.tr("Thư mục WAV cache (tùy chọn):")))
        self.cache_root_edit = LineEdit()
        self.cache_root_edit.setPlaceholderText(self.tr("Để trống để dùng cache mặc định của ứng dụng"))
        self.cache_root_edit.setFixedWidth(350)
        row_cache.addWidget(self.cache_root_edit)
        self.browse_cache_btn = PushButton(self.tr("Duyệt"))
        self.browse_cache_btn.setFixedWidth(60)
        self.browse_cache_btn.clicked.connect(self._browse_cache_root)
        row_cache.addWidget(self.browse_cache_btn)
        row_cache.addStretch()
        settings_layout.addLayout(row_cache)
        cache_hint = BodyLabel(self.tr(
            "Chọn thư mục chứa trực tiếp các file WAV/JSON cache (v1). "
            "Đường dẫn cache không lưu trong kế hoạch; chọn lại khi mở kế hoạch ở phiên mới."
        ))
        cache_hint.setWordWrap(True)
        settings_layout.addWidget(cache_hint)

        # Manual dub button
        self.manual_dub_btn = PrimaryPushButton(self.tr("▶ Lồng tiếng"))
        self.manual_dub_btn.setFixedWidth(160)
        self.manual_dub_btn.clicked.connect(self._start_manual_dub)
        settings_layout.addWidget(self.manual_dub_btn, alignment=Qt.AlignmentFlag.AlignCenter)
        self.open_editor_btn = PushButton(self.tr("Open in Video Editor"))
        self.open_editor_btn.setFixedWidth(180)
        self.open_editor_btn.clicked.connect(self._open_in_video_editor)
        settings_layout.addWidget(self.open_editor_btn, alignment=Qt.AlignmentFlag.AlignCenter)
        self.editor_scope_label = BodyLabel(self.tr(
            "Video Editor mở video và phụ đề. Duyệt lời đọc và tiếp tục kế hoạch ở tab Lồng tiếng."
        ))
        self.editor_scope_label.setWordWrap(True)
        settings_layout.addWidget(self.editor_scope_label)

        # --- Separator ---
        settings_layout.addSpacing(10)

        # --- Manual mode: ghép audio ngoài vào video (không qua TTS) ---
        merge_label = StrongBodyLabel(self.tr("Ghép audio thủ công"))
        settings_layout.addWidget(merge_label)

        # Video file
        row_mvideo = QHBoxLayout()
        row_mvideo.addWidget(BodyLabel(self.tr("📁 File video:")))
        self.merge_video_path_edit = LineEdit()
        self.merge_video_path_edit.setPlaceholderText(
            self.tr("Chọn file video (.mp4, .mkv, ...)")
        )
        self.merge_video_path_edit.setFixedWidth(350)
        row_mvideo.addWidget(self.merge_video_path_edit)
        self.browse_merge_video_btn = PushButton(self.tr("Duyệt"))
        self.browse_merge_video_btn.setFixedWidth(60)
        self.browse_merge_video_btn.clicked.connect(self._browse_merge_video)
        row_mvideo.addWidget(self.browse_merge_video_btn)
        row_mvideo.addStretch()
        settings_layout.addLayout(row_mvideo)

        # Audio file
        row_maudio = QHBoxLayout()
        row_maudio.addWidget(BodyLabel(self.tr("📁 File audio:")))
        self.merge_audio_path_edit = LineEdit()
        self.merge_audio_path_edit.setPlaceholderText(
            self.tr("Chọn file audio (.mp3, .wav, .m4a, ...)")
        )
        self.merge_audio_path_edit.setFixedWidth(350)
        row_maudio.addWidget(self.merge_audio_path_edit)
        self.browse_merge_audio_btn = PushButton(self.tr("Duyệt"))
        self.browse_merge_audio_btn.setFixedWidth(60)
        self.browse_merge_audio_btn.clicked.connect(self._browse_merge_audio)
        row_maudio.addWidget(self.browse_merge_audio_btn)
        row_maudio.addStretch()
        settings_layout.addLayout(row_maudio)

        # Merge button
        self.merge_audio_btn = PrimaryPushButton(self.tr("▶ Ghép audio"))
        self.merge_audio_btn.setFixedWidth(160)
        self.merge_audio_btn.clicked.connect(self._start_merge_audio)
        settings_layout.addWidget(self.merge_audio_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        layout.addWidget(self.settings_widget)
        self.settings_widget.setEnabled(cfg.dubbing_enabled.value)

        review_row = FlowLayout()
        self.review_btn = PushButton(self.tr("Duyệt / sửa lời đọc"))
        self.review_btn.clicked.connect(self._edit_review)
        self.save_review_btn = PushButton(self.tr("Lưu kế hoạch"))
        self.save_review_btn.clicked.connect(self._save_review)
        self.open_review_btn = PushButton(self.tr("Mở kế hoạch"))
        self.open_review_btn.clicked.connect(self._open_review)
        self.import_review_btn = PushButton(self.tr("Nhập checkpoint cũ"))
        self.import_review_btn.clicked.connect(self._import_review)
        self.resume_btn = PrimaryPushButton(self.tr("Tiếp tục lời đã duyệt"))
        self.resume_btn.clicked.connect(self._resume_review)
        for button in (self.review_btn, self.save_review_btn, self.open_review_btn, self.import_review_btn, self.resume_btn):
            review_row.addWidget(button)
        layout.addLayout(review_row)
        self.review_label = BodyLabel(self.tr("Chưa có kế hoạch lời đọc."))
        self.review_label.setWordWrap(True)
        layout.addWidget(self.review_label)
        self.cancel_job_btn = PushButton(self.tr("Hủy thao tác"))
        self.cancel_job_btn.clicked.connect(self.request_stop)
        self.cancel_job_btn.setVisible(False)
        layout.addWidget(self.cancel_job_btn)
        self._refresh_review_actions()

        # Spacer
        layout.addStretch()

        # --- Progress ---
        self.progress_bar = ProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        self.status_label = BodyLabel("")
        self.status_label.setWordWrap(True)
        self.status_label.setVisible(False)
        layout.addWidget(self.status_label)
        self._update_timing_controls()
        self._update_provider_visibility()

    # ==== Public API (called by HomeInterface pipeline) ====

    def set_task(self, task: DubbingTask):
        """Đặt task trước khi bắt đầu xử lý (pipeline mode)."""
        if self._job_busy:
            raise RuntimeError("Lồng tiếng đang bận; chờ worker kết thúc trước khi đổi task")
        self._task = task
        if task.cache_root is None:
            task.cache_root = self.cache_root_edit.text().strip() or None
        self.cache_root_edit.setText(task.cache_root or "")
        self._is_pipeline_mode = True
        self._pending_report_data = task.dubbing_report or {}
        self._refresh_review_actions()

    def process(self):
        """Bắt đầu dubbing (pipeline mode)."""
        if self._job_busy or not self._task:
            return

        config = self._task.dubbing_config
        if not config or not config.enabled:
            # Synthesis must keep the display layout even when speech is skipped.
            logger.info("Dubbing tắt, bỏ qua")
            self.finished.emit(
                self._task.video_path or "",
                self._task.display_subtitle_path or self._task.subtitle_path or "",
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

    def _browse_display_subtitle(self):
        path, _ = QFileDialog.getOpenFileName(
            self, self.tr("Chọn phụ đề hiển thị"), "", self.tr("Subtitle Files (*.srt *.ass *.vtt)")
        )
        if path:
            self.display_subtitle_path_edit.setText(path)

    def _browse_cache_root(self):
        path = QFileDialog.getExistingDirectory(
            self, self.tr("Chọn thư mục chứa WAV và JSON cache (v1)"), self.cache_root_edit.text().strip()
        )
        if path:
            self.cache_root_edit.setText(path)

    def _start_manual_dub(self):
        """Bắt đầu lồng tiếng thủ công."""
        if self._job_busy:
            return
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
        try:
            task = TaskFactory.create_dubbing_task(
                video_path, subtitle_path,
                display_subtitle_path=self.display_subtitle_path_edit.text().strip() or None,
                cache_root=self.cache_root_edit.text().strip() or None,
            )
        except ValueError as exc:
            InfoBar.warning(self.tr("Kiểm tra cấu hình lồng tiếng"), str(exc), duration=5000,
                            position=InfoBarPosition.BOTTOM, parent=self.window())
            return
        self._task = task
        self._run_dubbing(task)

    # ==== Manual audio merge ====

    def _browse_merge_video(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            self.tr("Chọn file video"),
            "",
            self.tr("Video Files (*.mp4 *.mkv *.avi *.mov *.webm *.flv *.ts)"),
        )
        if path:
            self.merge_video_path_edit.setText(path)

    def _browse_merge_audio(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            self.tr("Chọn file audio"),
            "",
            self.tr("Audio Files (*.mp3 *.wav *.m4a *.aac *.flac *.ogg *.opus)"),
        )
        if path:
            self.merge_audio_path_edit.setText(path)

    def _start_merge_audio(self):
        """Ghép audio ngoài vào video bằng các tuỳ chọn âm thanh phía trên."""
        if self._job_busy:
            return
        video_path = self.merge_video_path_edit.text().strip()
        audio_path = self.merge_audio_path_edit.text().strip()

        if not video_path or not Path(video_path).is_file():
            InfoBar.warning(
                self.tr("Thiếu file"),
                self.tr("Vui lòng chọn file video hợp lệ"),
                duration=3000,
                position=InfoBarPosition.BOTTOM,
                parent=self.window(),
            )
            return
        if not audio_path or not Path(audio_path).is_file():
            InfoBar.warning(
                self.tr("Thiếu file"),
                self.tr("Vui lòng chọn file audio hợp lệ"),
                duration=3000,
                position=InfoBarPosition.BOTTOM,
                parent=self.window(),
            )
            return

        # Lưu cài đặt (dùng chung các slider âm thanh phía trên)
        self._save_settings()

        mix_mode = presets.mix_mode_from_key(cfg.dubbing_mix_mode.value)
        original_volume = cfg.dubbing_original_volume.value / 100.0
        voice_volume = cfg.dubbing_voice_volume.value / 100.0
        output_path = presets.merged_output_path(video_path)

        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)
        self.status_label.setVisible(True)
        self.status_label.setText(self.tr("Đang ghép audio..."))
        self._set_job_busy(True)

        self._merge_thread = AudioMergeThread(
            video_path,
            audio_path,
            output_path,
            mix_mode,
            original_volume,
            voice_volume,
        )
        self._merge_thread.progress.connect(self._on_progress)
        self._merge_thread.error.connect(self._on_merge_error)
        self._merge_thread.finished.connect(self._on_merge_finished)
        QThread.finished.__get__(self._merge_thread).connect(self._on_merge_stopped)
        self._merge_thread.start()

    def _on_merge_stopped(self):
        self._merge_thread.wait()
        self._set_job_busy(False)

    def _on_merge_error(self, error_msg: str):
        self.progress_bar.setVisible(False)
        self.status_label.setText(self.tr("Ghép audio thất bại"))
        InfoBar.error(
            self.tr("Lỗi ghép audio"),
            error_msg,
            duration=5000,
            position=InfoBarPosition.BOTTOM,
            parent=self.window(),
        )

    def _on_merge_finished(self, output_path: str):
        self.progress_bar.setValue(100)
        self.status_label.setText(self.tr("Ghép audio hoàn tất!"))
        InfoBar.success(
            self.tr("Thành công"),
            self.tr("Đã ghép audio: ") + str(output_path),
            duration=5000,
            position=InfoBarPosition.BOTTOM,
            parent=self.window(),
        )

    # ==== Shared execution ====

    def _run_dubbing(self, task: DubbingTask, *, resume: bool = False):
        """Thực thi dubbing task."""
        if self._job_busy:
            return

        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)
        self.status_label.setVisible(True)
        self.status_label.setText(self.tr("Đang bắt đầu lồng tiếng..."))
        self._set_job_busy(True)
        self._job_result = None
        self._job_error = ""
        self._job_cancelled = False
        if not resume:
            self._pending_report_data = {}
            task.dubbing_review = None

        self._thread = DubbingThread(task, resume=resume)
        self._thread.progress.connect(self._on_progress)
        self._thread.report_ready.connect(self._on_report_ready)
        self._thread.plan_ready.connect(self._on_review_ready)
        self._thread.error.connect(self._on_error)
        self._thread.finished.connect(self._on_finished)
        self._thread.cancelled.connect(self._on_cancelled)
        self._thread.lifecycle_finished.connect(self._on_dubbing_stopped)
        self._thread.start()

    def _set_job_busy(self, busy: bool):
        self._job_busy = busy
        self.enable_switch.setEnabled(not busy)
        self.settings_widget.setEnabled(not busy and self.enable_switch.isChecked())
        self.manual_dub_btn.setEnabled(not busy)
        self.merge_audio_btn.setEnabled(not busy)
        self.cancel_job_btn.setVisible(busy)
        self.cancel_job_btn.setEnabled(busy)
        self._refresh_review_actions()

    def _refresh_review_actions(self):
        review = self._task.dubbing_review if self._task else None
        self.review_btn.setEnabled(bool(review) and not self._job_busy)
        self.save_review_btn.setEnabled(bool(review) and not self._job_busy)
        self.resume_btn.setEnabled(bool(review and review.can_resume) and not self._job_busy)
        self.open_review_btn.setEnabled(not self._job_busy)
        self.import_review_btn.setEnabled(not self._job_busy)
        if review:
            plan = review.plan
            task = self._task
            self.review_label.setText(self.tr(
                "{groups} nhóm | {review} cần review | {provider} / {model} / {voice}\n"
                "Nguồn: {video} + {subtitle}. Tiếp tục dùng cấu hình đã chụp của job; "
                "kiểm tra nguồn và giọng trước khi tạo audio.\nCache của job: {cache}\n{provenance}"
            ).format(groups=len(plan.groups), review=sum(g.needs_review for g in plan.groups),
                     provider=plan.provider, model=plan.model, voice=plan.voice,
                     video=Path(task.video_path or "").name if task else "",
                     subtitle=Path(task.subtitle_path or "").name if task else "",
                     cache=task.cache_root if task and task.cache_root else self.tr("Mặc định của ứng dụng"),
                     provenance=review.provenance_note))
        else:
            self.review_label.setText(self.tr("Chưa có kế hoạch lời đọc."))

    def _on_review_ready(self, review: DubbingReview):
        if self._task:
            self._task.dubbing_review = review
        self._refresh_review_actions()

    def _edit_review(self):
        if self._job_busy or not self._task or not self._task.dubbing_review:
            return
        dialog = DubbingReviewDialog(self._task.dubbing_review, self.window())
        if dialog.exec_() == QDialog.Accepted:
            self._task.dubbing_review = dialog.review
            self._refresh_review_actions()

    def _resume_review(self):
        if self._job_busy or not self._task or not self._task.dubbing_review:
            return
        self._run_dubbing(self._task, resume=True)

    def _save_review(self):
        if self._job_busy or not self._task or not self._task.dubbing_review:
            return
        path, _ = QFileDialog.getSaveFileName(self, self.tr("Lưu kế hoạch lời đọc"), "", "JSON (*.json)")
        if path:
            self._start_review_file("save", path)

    def _open_review(self):
        self._choose_review_file("open")

    def _import_review(self):
        self._choose_review_file("import")

    def _choose_review_file(self, operation: Literal["open", "import"]):
        if self._job_busy:
            return
        title = self.tr("Mở kế hoạch lời đọc") if operation == "open" else self.tr(
            "Nhập checkpoint cũ — liên kết với nguồn đã chọn, không xác minh được media lịch sử"
        )
        path, _ = QFileDialog.getOpenFileName(self, title, "", "JSON (*.json)")
        if path:
            self._start_review_file(operation, path)

    def _start_review_file(self, operation: Literal["open", "save", "import"], path: str):
        if self._job_busy:
            return
        task = self._task
        if task is None or (operation != "save" and not self._is_pipeline_mode):
            self._save_settings()
            try:
                task = TaskFactory.create_dubbing_task(
                    self.video_path_edit.text().strip(), self.subtitle_path_edit.text().strip(),
                    display_subtitle_path=self.display_subtitle_path_edit.text().strip() or None,
                    cache_root=self.cache_root_edit.text().strip() or None,
                )
            except ValueError as exc:
                self._show_job_error(str(exc))
                return
        elif operation != "save":
            task = replace(task, cache_root=self.cache_root_edit.text().strip() or None)
        self._file_result = None
        self._job_error = ""
        self._job_cancelled = False
        self._set_job_busy(True)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)
        self.status_label.setVisible(True)
        worker = DubbingReviewFileThread(operation, path, task, self)
        self._review_thread = worker
        worker.result.connect(self._on_file_result)
        worker.error.connect(self._on_error)
        worker.cancelled.connect(self._on_cancelled)
        worker.progress.connect(self._on_progress)
        worker.finished.connect(self._on_review_file_stopped)
        worker.start()

    def _on_file_result(self, review: DubbingReview):
        self._file_result = review

    def _on_review_file_stopped(self):
        worker = self._review_thread
        if worker is None:
            return
        worker.wait()
        self._set_job_busy(False)
        self.progress_bar.setVisible(False)
        if self._closing:
            return
        if self._job_cancelled:
            self.status_label.setText(self.tr("Đã hủy thao tác. Kế hoạch trước đó vẫn được giữ."))
        elif self._job_error:
            self._show_job_error(self._job_error)
        elif self._file_result:
            if worker.operation != "save":
                self._task = worker.task
                self._on_review_ready(self._file_result)
            self.status_label.setText(self.tr("Đã lưu kế hoạch.") if worker.operation == "save" else self.tr(
                "Đã mở kế hoạch trong RAM. Duyệt lời đọc rồi chọn Tiếp tục; nguồn/cấu hình sẽ được xác minh."
            ))

    # ==== Slots ====

    def _on_enable_changed(self, checked: bool):
        self.settings_widget.setEnabled(checked and not self._job_busy)
        cfg.set(cfg.dubbing_enabled, checked)

    def _on_provider_changed(self, index: int):
        if not (0 <= index < len(presets.TTS_PROVIDER_KEYS)):
            return
        provider = presets.TTS_PROVIDER_KEYS[index]
        cfg.set(cfg.dubbing_tts_provider, provider)

        # Suggest voices and endpoint defaults for the provider; only blank
        # fields are filled so nothing the user typed is overwritten.
        preset = presets.TTS_PROVIDER_PRESETS[provider]
        voice, api_base, model = presets.fill_provider_defaults(
            preset,
            self.voice_combo.text(),
            self.api_base_edit.text(),
            self.model_edit.text(),
        )
        if provider == "omnivoice-local":
            voice = "auto"
        self.voice_combo.clear()
        if preset.voices:
            self.voice_combo.addItems(list(preset.voices))
        if voice:
            self.voice_combo.setText(voice)
        if api_base:
            self.api_base_edit.setText(api_base)
        if model:
            self.model_edit.setText(model)
        self._update_provider_visibility()

    def _update_provider_visibility(self):
        index = self.provider_combo.currentIndex()
        managed = 0 <= index < len(presets.TTS_PROVIDER_KEYS) and presets.TTS_PROVIDER_KEYS[index] == "vieneu-local"
        self.vieneu_widget.setVisible(managed)
        omni = 0 <= index < len(presets.TTS_PROVIDER_KEYS) and presets.TTS_PROVIDER_KEYS[index] == "omnivoice-local"
        self.omnivoice_panel.setVisible(omni)
        for editor in (self.api_key_edit, self.api_base_edit, self.model_edit):
            editor.setEnabled(not (managed or omni))
        self.sample_rate_combo.setEnabled(not (managed or omni))
        if not managed:
            self.fetch_voice_btn.setEnabled(not omni)
        if managed:
            from videocaptioner.core.tts.vieneu.service import get_vieneu_service

            service = get_vieneu_service()
            runtime_error = service.update_prerequisite_error()
            state = service.manager.state.value.title()
            model = service.model_state().active_revision[:12]
            if runtime_error:
                self.vieneu_status_label.setText(
                    self.tr("VieNeu: Runtime not installed — use the VieNeu One-App package")
                )
            else:
                suffix = f" • {model}" if model else " • no active model"
                if self._vieneu_offered_revision:
                    suffix += " • " + self.tr("update {0} available").format(
                        self._vieneu_offered_revision[:12]
                    )
                self.vieneu_status_label.setText(f"VieNeu: {state}{suffix}")
            self.vieneu_start_stop_btn.setText(
                self.tr("Stop") if service.manager.process_id else self.tr("Start")
            )
            self.vieneu_start_stop_btn.setEnabled(
                not runtime_error and bool(model or service.manager.process_id)
            )
            self.vieneu_update_btn.setEnabled(not runtime_error)
            self.vieneu_rollback_btn.setEnabled(
                not runtime_error and bool(service.model_state().previous_revision)
            )
            self.fetch_voice_btn.setEnabled(not runtime_error and bool(model))
            for button in (
                self.vieneu_start_stop_btn,
                self.vieneu_update_btn,
                self.fetch_voice_btn,
            ):
                button.setToolTip(runtime_error)

    def _toggle_vieneu_runtime(self):
        from videocaptioner.core.tts.vieneu.service import get_vieneu_service

        action = "stop" if get_vieneu_service().manager.process_id else "start"
        self._start_vieneu_action(action)

    def start_launch_update_check(self) -> None:
        """Startup path: ask the hub for a newer model and offer it, never download."""
        self._vieneu_launch_check = True
        self._start_vieneu_action("check")

    def _start_vieneu_action(self, action: str):
        from videocaptioner.core.tts.vieneu.service import get_vieneu_service

        runtime_error = get_vieneu_service().update_prerequisite_error()
        if runtime_error and action in {"start", "voices", "check", "update"}:
            self._on_vieneu_error(action, runtime_error)
            return
        if any(thread.isRunning() for thread in self._vieneu_threads):
            # One managed operation at a time. Remember the latest request and run
            # it when the current thread finishes; dropping it used to leave the
            # voice button stuck on "Đang tải..." while auto-update was running.
            self._vieneu_pending_action = action
            self.vieneu_status_label.setText(
                self.tr("VieNeu: busy, {0} queued").format(action)
            )
            return
        self._vieneu_pending_action = ""
        if action in {"start", "update", "rollback"}:
            # Model load, a 1.7 GB download and GPU validation take minutes;
            # report them through the tab's progress bar like a dubbing job.
            self.progress_bar.setValue(0)
            self.progress_bar.setVisible(True)
            self.status_label.setVisible(True)
        thread = VieNeuRuntimeThread(action, parent=self)
        self._vieneu_threads.add(thread)
        thread.runtime_state.connect(self._on_vieneu_state)
        thread.progress.connect(self._on_progress)
        thread.result.connect(self._on_vieneu_result)
        thread.error.connect(self._on_vieneu_error)
        thread.finished.connect(
            lambda current=thread: self._on_vieneu_thread_finished(current)
        )
        thread.start()

    def _on_vieneu_thread_finished(self, thread) -> None:
        self._vieneu_threads.discard(thread)
        pending, self._vieneu_pending_action = self._vieneu_pending_action, ""
        if pending:
            self._start_vieneu_action(pending)

    def shutdown_vieneu_threads(self, timeout_ms: int = 10_000) -> None:
        """Cancel and wait for managed VieNeu work; used on close and app quit."""
        self._vieneu_pending_action = ""
        try:
            from videocaptioner.core.tts.vieneu.service import get_vieneu_service

            get_vieneu_service().cancel_pending()
        except Exception:
            pass
        for thread in tuple(self._vieneu_threads):
            if thread.isRunning():
                thread.requestInterruption()
                thread.wait(timeout_ms)

    def request_stop(self) -> None:
        """Ask a running dubbing job to stop at its next progress report."""
        self.omnivoice_panel.stop()
        for thread in (self._thread, self._review_thread, getattr(self, "_merge_thread", None)):
            if thread is not None and thread.isRunning():
                thread.requestInterruption()
        if self._job_busy:
            self._job_cancelled = True
            self.cancel_job_btn.setEnabled(False)
            self.status_label.setText(self.tr("Đang hủy; chờ worker kết thúc..."))

    def wait_for_dubbing_job(self, timeout_ms: int = 10_000) -> bool:
        """Interrupt the dubbing job and block until its thread exits.

        Interpreter shutdown tears down ThreadPoolExecutor workers under a
        QThread that is still running, so a job left behind at exit ends with
        "cannot schedule new futures" or a Qt abort instead of a clean stop.
        """
        stopped = True
        for thread in (self._thread, self._review_thread, getattr(self, "_merge_thread", None)):
            if thread is not None:
                if thread.isRunning():
                    thread.requestInterruption()
                stopped = thread.wait(timeout_ms) and stopped
        return stopped

    def _on_vieneu_state(self, state: str, message: str):
        suffix = f" • {message}" if message else ""
        self.vieneu_status_label.setText(f"VieNeu: {state.title()}{suffix}")

    def _on_vieneu_result(self, action: str, result):
        if action == "voices":
            models = [str(item.get("id", "")) for item in result if item.get("id")]
            self._on_fetch_voices_finished(models, "")
            # Fetching voices starts the runtime, so Start/Stop must reflect it.
            self._update_provider_visibility()
            return
        if action == "check":
            quiet, self._vieneu_launch_check = self._vieneu_launch_check, False
            self._show_update_check(result, quiet=quiet)
            self._update_provider_visibility()
            return
        if action == "update":
            self._vieneu_offered_revision = ""
            self._show_update_outcome(result)
        self._update_provider_visibility()
        self.progress_bar.setValue(100)
        self.status_label.setVisible(True)
        self.status_label.setText(self.tr("VieNeu operation completed"))
        if action == "start" and self._managed_provider_selected():
            # A freshly started runtime should offer its voices right away.
            self._fetch_voices()

    def _show_update_check(self, check: VieNeuUpdateCheck, *, quiet: bool) -> None:
        if check.status == "available":
            self._offer_vieneu_update(check)
            return
        if quiet:
            return
        if check.status == "current":
            InfoBar.success(
                self.tr("VieNeu model is up to date"),
                check.active_revision[:12],
                duration=4000,
                position=InfoBarPosition.BOTTOM,
                parent=self.window(),
            )
            return
        InfoBar.warning(
            self.tr("VieNeu update unavailable"),
            check.message,
            duration=5000,
            position=InfoBarPosition.BOTTOM,
            parent=self.window(),
        )

    def _offer_vieneu_update(self, check: VieNeuUpdateCheck) -> None:
        """Ask before pulling about 1.7 GB and validating it on the GPU."""
        self._vieneu_offered_revision = check.remote_revision
        bar = InfoBar.info(
            self.tr("VieNeu model update available"),
            self.tr("Revision {0} can replace {1}. Download it now?").format(
                check.remote_revision[:12], check.active_revision[:12] or "-"
            ),
            duration=-1,
            position=InfoBarPosition.BOTTOM,
            parent=self.window(),
        )
        button = PushButton(self.tr("Download and activate"), bar)

        def accept() -> None:
            bar.close()
            self._start_vieneu_action("update")

        button.clicked.connect(accept)
        bar.addWidget(button)

    def _show_update_outcome(self, result) -> None:
        if isinstance(result, VieNeuUpdateCheck):
            self._show_update_check(result, quiet=False)
            return
        if result == "deferred":
            InfoBar.info(
                self.tr("VieNeu update staged"),
                self.tr("The new model activates once the current dubbing job finishes."),
                duration=6000,
                position=InfoBarPosition.BOTTOM,
                parent=self.window(),
            )
            return
        InfoBar.success(
            self.tr("VieNeu model updated"),
            self.tr("Revision {0} is active.").format(
                str(getattr(result, "model_revision", ""))[:12]
            ),
            duration=6000,
            position=InfoBarPosition.BOTTOM,
            parent=self.window(),
        )

    def _managed_provider_selected(self) -> bool:
        index = self.provider_combo.currentIndex()
        return 0 <= index < len(presets.TTS_PROVIDER_KEYS) and presets.TTS_PROVIDER_KEYS[index] == "vieneu-local"

    def _on_vieneu_error(self, action: str, error: str):
        logger.warning("VieNeu %s failed: %s", action, error)
        quiet, self._vieneu_launch_check = self._vieneu_launch_check, False
        self.fetch_voice_btn.setEnabled(True)
        self.fetch_voice_btn.setText(self.tr("Tải danh sách"))
        self._update_provider_visibility()
        from videocaptioner.core.tts.vieneu.service import get_vieneu_service

        has_active = bool(get_vieneu_service().model_state().active_revision)
        if action == "check" and has_active:
            # The active model keeps working offline; the startup check stays
            # silent, a manual check gets a notice.
            if not quiet:
                InfoBar.warning(
                    self.tr("VieNeu update unavailable"),
                    error,
                    duration=5000,
                    position=InfoBarPosition.BOTTOM,
                    parent=self.window(),
                )
            return
        self.status_label.setVisible(True)
        self.status_label.setText(self.tr("VieNeu failed") + ": " + error)
        InfoBar.error(
            self.tr("VieNeu Local error"),
            error,
            duration=-1,
            position=InfoBarPosition.BOTTOM,
            parent=self.window(),
        )

    def _fetch_voices(self):
        if self.provider_combo.currentIndex() == presets.TTS_PROVIDER_KEYS.index("omnivoice-local"):
            return
        """Tải danh sách giọng nói từ API."""
        api_base = self.api_base_edit.text().strip()
        api_key = self.api_key_edit.text().strip()

        provider_idx = self.provider_combo.currentIndex()
        if provider_idx in [0, 1]:  # OpenAI or MiniMax -> Hardcoded usually
            InfoBar.info(
                self.tr("Thông báo"),
                self.tr("Provider này sử dụng danh sách giọng nói mặc định."),
                duration=3000,
                position=InfoBarPosition.BOTTOM,
                parent=self.window(),
            )
            # Re-trigger the default list
            self._on_provider_changed(provider_idx)
            return

        if provider_idx == 3:
            self.fetch_voice_btn.setEnabled(False)
            self.fetch_voice_btn.setText(self.tr("Đang tải..."))
            self._start_vieneu_action("voices")
            return

        self.fetch_voice_btn.setEnabled(False)
        self.fetch_voice_btn.setText(self.tr("Đang tải..."))

        self.fetch_thread = VoiceFetchThread(api_base, api_key)
        self.fetch_thread.finished_fetch.connect(self._on_fetch_voices_finished)
        self.fetch_thread.start()

    def _on_fetch_voices_finished(self, models: list, error_msg: str):
        self.fetch_voice_btn.setEnabled(True)
        self.fetch_voice_btn.setText(self.tr("Tải danh sách"))

        if error_msg:
            InfoBar.error(
                self.tr("Lỗi tải danh sách"),
                error_msg,
                duration=4000,
                position=InfoBarPosition.BOTTOM,
                parent=self.window(),
            )
            return

        if models:
            current_text = self.voice_combo.text()
            self.voice_combo.clear()
            self.voice_combo.addItems(models)
            if current_text in models:
                self.voice_combo.setText(current_text)
            else:
                self.voice_combo.setText(models[0])
            InfoBar.success(
                self.tr("Thành công"),
                self.tr("Đã tải {0} giọng nói.").format(len(models)),
                duration=3000,
                position=InfoBarPosition.BOTTOM,
                parent=self.window(),
            )
        else:
            InfoBar.warning(
                self.tr("Không có dữ liệu"),
                self.tr("Không tìm thấy model nào từ API."),
                duration=3000,
                position=InfoBarPosition.BOTTOM,
                parent=self.window(),
            )

    def _on_progress(self, value: int, message: str):
        self.progress_bar.setValue(value)
        self.status_label.setText(message)

    def _on_report_ready(self, report_data: dict):
        self._pending_report_data = report_data

    def _show_report(self, *, editable: bool = True):
        if editable and self._task and self._task.dubbing_review:
            self._edit_review()
        elif self._pending_report_data:
            DubbingReportDialog(self._pending_report_data, self.window()).exec_()

    def _on_error(self, error_msg: str):
        self._job_error = error_msg

    def _on_cancelled(self):
        self._job_cancelled = True

    def _on_finished(self, task: DubbingTask):
        self._job_result = task

    def _on_dubbing_stopped(self):
        if self._thread is None:
            return
        self._thread.wait()
        self._set_job_busy(False)
        if self._closing:
            return
        if self._job_cancelled:
            self.progress_bar.setVisible(False)
            self.status_label.setText(self.tr("Lồng tiếng đã bị hủy. Kế hoạch lời đọc vẫn được giữ."))
        elif self._job_error:
            self._show_job_error(self._job_error)
            self._show_report()
        elif self._job_result:
            self._complete_dubbing(self._job_result)

    def _show_job_error(self, error_msg: str):
        self.progress_bar.setVisible(False)
        self.status_label.setVisible(True)
        self.status_label.setText(self.tr("Lồng tiếng thất bại") + ": " + error_msg)
        review_required = (
            "timing review" in error_msg.lower()
            or "chưa khớp thời gian" in error_msg.lower()
        )
        InfoBar.error(
            self.tr("Cần xem lại timing") if review_required else self.tr("Lỗi lồng tiếng"),
            error_msg,
            duration=-1,
            position=InfoBarPosition.BOTTOM,
            parent=self.window(),
        )

    def _complete_dubbing(self, task: DubbingTask):
        self.progress_bar.setValue(100)
        self.status_label.setText(self.tr("Lồng tiếng hoàn tất!"))

        InfoBar.success(
            self.tr("Thành công"),
            self.tr("Đã lồng tiếng: ") + str(task.output_path or ""),
            duration=5000,
            position=InfoBarPosition.BOTTOM,
            parent=self.window(),
        )
        self._show_report(editable=False)

        # In pipeline mode: emit dubbed video for synthesis
        if self._is_pipeline_mode:
            self.finished.emit(
                task.output_path or task.video_path or "",
                task.display_subtitle_path or task.subtitle_path or "",
            )

    def _open_in_video_editor(self):
        task = self._task
        if task:
            video_path = task.output_path if task.output_path and Path(task.output_path).is_file() else task.video_path
            subtitle_path = task.display_subtitle_path or task.subtitle_path
        else:
            video_path = self.video_path_edit.text().strip()
            subtitle_path = self.display_subtitle_path_edit.text().strip() or self.subtitle_path_edit.text().strip()
        if not video_path or not Path(video_path).is_file() or not subtitle_path or not Path(subtitle_path).is_file():
            InfoBar.warning(
                self.tr("Chưa thể mở Video Editor"),
                self.tr("Cần video và file phụ đề hợp lệ."),
                duration=4000,
                position=InfoBarPosition.BOTTOM,
                parent=self.window(),
            )
            return

        self.openInVideoEditorRequested.emit(str(video_path), str(subtitle_path))

    def _save_settings(self):
        """Lưu settings hiện tại vào persistent config."""
        self.omnivoice_panel.save()
        cfg.set(cfg.dubbing_tts_voice, self.voice_combo.text())
        cfg.set(cfg.dubbing_tts_api_key, self.api_key_edit.text())
        cfg.set(cfg.dubbing_tts_api_base, self.api_base_edit.text())
        cfg.set(cfg.dubbing_tts_model, self.model_edit.text())

        idx = self.mix_combo.currentIndex()
        if 0 <= idx < len(presets.MIX_MODE_KEYS):
            cfg.set(cfg.dubbing_mix_mode, presets.MIX_MODE_KEYS[idx])
        cfg.set(cfg.dubbing_original_volume, self.volume_slider.value())
        cfg.set(cfg.dubbing_tts_speed, self.speed_slider.value())
        cfg.set(cfg.dubbing_max_speed, self.max_speed_slider.value())
        cfg.set(
            cfg.dubbing_text_source,
            presets.TEXT_SOURCE_KEYS[self.text_source_combo.currentIndex()],
        )
        cfg.set(
            cfg.dubbing_timing_mode,
            presets.TIMING_MODE_KEYS[0 if self.timing_mode_combo.currentIndex() == 0 else 1],
        )
        cfg.set(cfg.dubbing_natural_max_speed, self.natural_speed_slider.value())
        cfg.set(cfg.dubbing_timing_rewrite, self.rewrite_switch.isChecked())
        cfg.set(cfg.dubbing_tts_cache, self.tts_cache_switch.isChecked())
        cfg.set(
            cfg.dubbing_unresolved_policy,
            presets.UNRESOLVED_POLICY_KEYS[self.unresolved_combo.currentIndex()],
        )
        cfg.set(cfg.dubbing_max_start_delay_ms, self.start_delay_spinbox.value())

        sr_idx = self.sample_rate_combo.currentIndex()
        if 0 <= sr_idx < len(self._sample_rates):
            cfg.set(cfg.dubbing_tts_sample_rate, self._sample_rates[sr_idx])

        cfg.set(cfg.dubbing_voice_volume, self.voice_volume_slider.value())
        cfg.set(cfg.dubbing_tts_concurrency, self.concurrency_spinbox.value())

    def _update_timing_controls(self):
        natural = self.timing_mode_combo.currentIndex() == 0
        self.natural_speed_slider.setEnabled(natural)
        self.natural_speed_label.setEnabled(natural)
        self.max_speed_slider.setEnabled(not natural)
        self.max_speed_label.setEnabled(not natural)
        self.rewrite_switch.setEnabled(natural)
        self.unresolved_combo.setEnabled(natural)
        self.start_delay_spinbox.setEnabled(natural and self.unresolved_combo.currentIndex() == 2)

    def closeEvent(self, event):
        self._closing = True
        self.request_stop()
        self.shutdown_vieneu_threads()
        if not self.wait_for_dubbing_job():
            self._closing = False
            event.ignore()
            return
        super().closeEvent(event)

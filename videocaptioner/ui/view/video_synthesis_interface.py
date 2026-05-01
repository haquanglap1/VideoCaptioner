# -*- coding: utf-8 -*-

import os
import sys
from pathlib import Path

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QDropEvent
from PyQt5.QtWidgets import QApplication, QFileDialog, QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import (
    Action,
    BodyLabel,
    CardWidget,
    CommandBar,
    InfoBar,
    InfoBarPosition,
    LineEdit,
    PrimaryPushButton,
    ProgressBar,
    PushButton,
    RoundMenu,
    ToolTipFilter,
    ToolTipPosition,
    TransparentDropDownPushButton,
)
from qfluentwidgets import FluentIcon as FIF

from videocaptioner.core.constant import (
    INFOBAR_DURATION_ERROR,
    INFOBAR_DURATION_SUCCESS,
    INFOBAR_DURATION_WARNING,
)
from videocaptioner.core.entities import (
    SubtitleRenderModeEnum,
    SupportedSubtitleFormats,
    SupportedVideoFormats,
    SynthesisTask,
    VideoQualityEnum,
)
from videocaptioner.core.utils.platform_utils import open_folder
from videocaptioner.ui.common.config import cfg
from videocaptioner.ui.common.signal_bus import signalBus
from videocaptioner.ui.task_factory import TaskFactory
from videocaptioner.ui.thread.video_synthesis_thread import VideoSynthesisThread


class VideoSynthesisInterface(QWidget):
    finished = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("VideoSynthesisInterface")
        self.setAttribute(Qt.WA_StyledBackground, True)  # type: ignore
        self.setAcceptDrops(True)
        self._quality_display_to_enum = {
            self.tr(e.value): e for e in VideoQualityEnum
        }
        self._render_mode_display_to_enum = {
            self.tr(e.value): e for e in SubtitleRenderModeEnum
        }
        self.setup_ui()
        self.setup_style()
        self.set_value()
        self.setup_signals()
        self.task = None

        self.installEventFilter(ToolTipFilter(self, 100, ToolTipPosition.BOTTOM))

    def setup_ui(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setSpacing(20)

        top_layout = QHBoxLayout()

        self.command_bar = CommandBar(self)
        self.command_bar.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)  # type: ignore
        top_layout.addWidget(self.command_bar, 1)

        self._setup_command_bar()

        self.synthesize_button = PrimaryPushButton(
            self.tr("Bắt đầu ghép"), self, icon=FIF.PLAY
        )
        self.synthesize_button.setFixedHeight(34)
        top_layout.addWidget(self.synthesize_button)

        self.main_layout.addLayout(top_layout)

        self.config_card = CardWidget(self)
        self.config_layout = QVBoxLayout(self.config_card)
        self.config_layout.setContentsMargins(20, 20, 20, 20)
        self.config_layout.setSpacing(20)

        self.subtitle_layout = QHBoxLayout()
        self.subtitle_layout.setSpacing(15)
        self.subtitle_label = BodyLabel(self.tr("File phụ đề"), self)
        self.subtitle_input = LineEdit(self)
        self.subtitle_input.setPlaceholderText(self.tr("Chọn hoặc kéo thả file phụ đề"))
        self.subtitle_input.setAcceptDrops(True)
        self.subtitle_button = PushButton(self.tr("Duyệt"))
        self.subtitle_layout.addWidget(self.subtitle_label)
        self.subtitle_layout.addWidget(self.subtitle_input)
        self.subtitle_layout.addWidget(self.subtitle_button)
        self.config_layout.addLayout(self.subtitle_layout)

        self.video_layout = QHBoxLayout()
        self.video_layout.setSpacing(15)
        self.video_label = BodyLabel(self.tr("File video"), self)
        self.video_input = LineEdit(self)
        self.video_input.setPlaceholderText(self.tr("Chọn hoặc kéo thả file video"))
        self.video_input.setAcceptDrops(True)
        self.video_button = PushButton(self.tr("Duyệt"))
        self.video_layout.addWidget(self.video_label)
        self.video_layout.addWidget(self.video_input)
        self.video_layout.addWidget(self.video_button)
        self.config_layout.addLayout(self.video_layout)

        self.main_layout.addWidget(self.config_card)
        self.main_layout.addStretch(1)

        self.bottom_layout = QHBoxLayout()
        self.progress_bar = ProgressBar(self)
        self.status_label = BodyLabel(self.tr("Sẵn sàng"), self)
        self.status_label.setMinimumWidth(100)
        self.status_label.setAlignment(Qt.AlignCenter)  # type: ignore
        self.bottom_layout.addWidget(self.progress_bar, 1)
        self.bottom_layout.addWidget(self.status_label)
        self.main_layout.addLayout(self.bottom_layout)

    def _setup_command_bar(self):
        self.soft_subtitle_action = Action(
            FIF.FONT,
            self.tr("Phụ đề mềm"),
            triggered=self.on_soft_subtitle_action_triggered,
            checkable=True,
        )
        self.soft_subtitle_action.setToolTip(self.tr("Nhúng phụ đề như một track riêng"))
        self.command_bar.addAction(self.soft_subtitle_action)

        self.command_bar.addSeparator()

        self.use_style_action = Action(
            FIF.PALETTE,
            self.tr("Dùng kiểu phụ đề"),
            triggered=self.on_use_style_action_triggered,
            checkable=True,
        )
        self.use_style_action.setToolTip(self.tr("Bật render phụ đề theo kiểu đã chọn"))
        self.command_bar.addAction(self.use_style_action)

        self.command_bar.addSeparator()

        self.render_mode_button = TransparentDropDownPushButton(
            self.tr("Chế độ render"), self, FIF.FONT_SIZE
        )
        self.render_mode_button.setFixedHeight(34)
        self.render_mode_button.setMinimumWidth(140)
        self.render_mode_menu = RoundMenu(parent=self)
        for mode in SubtitleRenderModeEnum:
            action = Action(text=self._display_for_render_mode(mode))
            action.triggered.connect(
                lambda checked, m=mode: self.on_render_mode_changed(m)
            )
            self.render_mode_menu.addAction(action)
        self.render_mode_button.setMenu(self.render_mode_menu)
        self.command_bar.addWidget(self.render_mode_button)

        self.command_bar.addSeparator()

        self.video_quality_button = TransparentDropDownPushButton(
            self.tr("Chất lượng video"), self, FIF.SPEED_HIGH
        )
        self.video_quality_button.setFixedHeight(34)
        self.video_quality_button.setMinimumWidth(125)
        self.video_quality_menu = RoundMenu(parent=self)
        for quality in VideoQualityEnum:
            action = Action(text=self._display_for_quality(quality))
            action.triggered.connect(
                lambda checked, q=quality: self.on_video_quality_action_changed(q)
            )
            self.video_quality_menu.addAction(action)
        self.video_quality_button.setMenu(self.video_quality_menu)
        self.command_bar.addWidget(self.video_quality_button)

        self.command_bar.addSeparator()

        self.need_video_action = Action(
            FIF.VIDEO,
            self.tr("Ghép video"),
            triggered=self.on_need_video_action_triggered,
            checkable=True,
        )
        self.need_video_action.setToolTip(self.tr("Tạo file video mới sau khi xử lý"))
        self.command_bar.addAction(self.need_video_action)

        self.command_bar.addSeparator()

        folder_action = Action(FIF.FOLDER, "", triggered=self.open_video_folder)
        folder_action.setToolTip(self.tr("Mở thư mục đầu ra"))
        self.command_bar.addAction(folder_action)

    def setup_style(self):
        self.subtitle_input.focusOutEvent = lambda e: super(
            LineEdit, self.subtitle_input
        ).focusOutEvent(e)
        self.subtitle_input.paintEvent = lambda e: super(
            LineEdit, self.subtitle_input
        ).paintEvent(e)
        self.subtitle_input.setStyleSheet(
            self.subtitle_input.styleSheet()
            + """
            QLineEdit {
                border-radius: 15px;
                padding: 0 20px;
                background-color: transparent;
                border: 1px solid rgba(255,255, 255, 0.08);
            }
            QLineEdit:focus[transparent=true] {
                border: 1px solid rgba(47,141, 99, 0.48);
            }
        """
        )

        self.video_input.focusOutEvent = lambda e: super(
            LineEdit, self.video_input
        ).focusOutEvent(e)
        self.video_input.paintEvent = lambda e: super(
            LineEdit, self.video_input
        ).paintEvent(e)
        self.video_input.setStyleSheet(
            self.video_input.styleSheet()
            + """
            QLineEdit {
                border-radius: 15px;
                padding: 0 20px;
                background-color: transparent;
                border: 1px solid rgba(255,255, 255, 0.08);
            }
            QLineEdit:focus[transparent=true] {
                border: 1px solid rgba(47,141, 99, 0.48);
            }
        """
        )

    def setup_signals(self):
        self.subtitle_button.clicked.connect(self.choose_subtitle_file)
        self.video_button.clicked.connect(self.choose_video_file)
        self.synthesize_button.clicked.connect(
            lambda: self.start_video_synthesis(need_create_task=True)
        )

        signalBus.soft_subtitle_changed.connect(self.on_soft_subtitle_changed)
        signalBus.need_video_changed.connect(self.on_need_video_changed)
        signalBus.video_quality_changed.connect(self.on_video_quality_changed)
        signalBus.use_subtitle_style_changed.connect(self.on_use_style_changed)
        signalBus.subtitle_render_mode_changed.connect(self.on_render_mode_changed_external)

    def set_value(self):
        self.soft_subtitle_action.setChecked(cfg.soft_subtitle.value)
        self.need_video_action.setChecked(cfg.need_video.value)
        self.video_quality_button.setText(self._display_for_quality(cfg.video_quality.value))

        self.use_style_action.setChecked(cfg.use_subtitle_style.value)
        self.render_mode_button.setText(
            self._display_for_render_mode(cfg.subtitle_render_mode.value)
        )
        self._update_synthesis_controls_state()

    def on_soft_subtitle_action_triggered(self, checked: bool):
        cfg.set(cfg.soft_subtitle, checked)

        if checked:
            if self.use_style_action.isChecked():
                self.use_style_action.setChecked(False)
                cfg.set(cfg.use_subtitle_style, False)
                self._update_style_controls_state()
            InfoBar.info(
                self.tr("Đã bật phụ đề mềm"),
                self.tr("Phụ đề được nhúng thành track riêng và không kèm kiểu hiển thị."),
                duration=3000,
                position=InfoBarPosition.BOTTOM,
                parent=self,
            )
        else:
            InfoBar.info(
                self.tr("Đã bật phụ đề cứng"),
                self.tr("Phụ đề sẽ được ghi trực tiếp lên khung hình video."),
                duration=3000,
                position=InfoBarPosition.BOTTOM,
                parent=self,
            )

    def on_soft_subtitle_changed(self, checked: bool):
        self.soft_subtitle_action.setChecked(checked)

    def on_need_video_action_triggered(self, checked: bool):
        cfg.set(cfg.need_video, checked)
        self._update_synthesis_controls_state()

        if checked:
            InfoBar.info(
                self.tr("Đã bật ghép video"),
                self.tr("Video và phụ đề sẽ được ghép thành file mới."),
                duration=3000,
                position=InfoBarPosition.BOTTOM,
                parent=self,
            )
        else:
            InfoBar.info(
                self.tr("Đã tắt ghép video"),
                self.tr("Chỉ tạo file phụ đề, không tạo video mới."),
                duration=3000,
                position=InfoBarPosition.BOTTOM,
                parent=self,
            )

    def on_need_video_changed(self, checked: bool):
        self.need_video_action.setChecked(checked)
        self._update_synthesis_controls_state()

    def on_video_quality_action_changed(self, quality: VideoQualityEnum | str):
        quality_enum = (
            quality if isinstance(quality, VideoQualityEnum) else self._quality_from_text(quality)
        )
        if not quality_enum:
            return

        cfg.set(cfg.video_quality, quality_enum)
        self.video_quality_button.setText(self._display_for_quality(quality_enum))

    def on_video_quality_changed(self, quality_text: str):
        quality = self._quality_from_text(quality_text)
        self.video_quality_button.setText(
            self._display_for_quality(quality) if quality else quality_text
        )

    def on_use_style_action_triggered(self, checked: bool):
        cfg.set(cfg.use_subtitle_style, checked)
        self._update_style_controls_state()

        if checked:
            if self.soft_subtitle_action.isChecked():
                self.soft_subtitle_action.setChecked(False)
                cfg.set(cfg.soft_subtitle, False)
            InfoBar.info(
                self.tr("Đã bật kiểu phụ đề"),
                self.tr("Tự động chuyển sang render phụ đề cứng."),
                duration=3000,
                position=InfoBarPosition.BOTTOM,
                parent=self,
            )
        else:
            InfoBar.info(
                self.tr("Đã tắt kiểu phụ đề"),
                self.tr("Sẽ dùng kiểu render phụ đề mặc định."),
                duration=3000,
                position=InfoBarPosition.BOTTOM,
                parent=self,
            )

    def on_use_style_changed(self, checked: bool):
        self.use_style_action.setChecked(checked)
        self._update_style_controls_state()

    def on_render_mode_changed(self, mode: SubtitleRenderModeEnum | str):
        mode_enum = (
            mode if isinstance(mode, SubtitleRenderModeEnum) else self._render_mode_from_text(mode)
        )
        if mode_enum:
            cfg.set(cfg.subtitle_render_mode, mode_enum)
            self.render_mode_button.setText(self._display_for_render_mode(mode_enum))
            signalBus.subtitle_render_mode_changed.emit(mode_enum.value)

    def on_render_mode_changed_external(self, mode_text: str):
        mode = self._render_mode_from_text(mode_text)
        self.render_mode_button.setText(
            self._display_for_render_mode(mode) if mode else mode_text
        )

    def _display_for_quality(self, quality: VideoQualityEnum) -> str:
        return self.tr(quality.value)

    def _quality_from_text(self, text: str) -> VideoQualityEnum | None:
        if text in self._quality_display_to_enum:
            return self._quality_display_to_enum[text]
        return next((e for e in VideoQualityEnum if e.value == text), None)

    def _display_for_render_mode(self, mode: SubtitleRenderModeEnum) -> str:
        return self.tr(mode.value)

    def _render_mode_from_text(self, text: str) -> SubtitleRenderModeEnum | None:
        if text in self._render_mode_display_to_enum:
            return self._render_mode_display_to_enum[text]
        return next((e for e in SubtitleRenderModeEnum if e.value == text), None)

    def _update_synthesis_controls_state(self):
        need_video = self.need_video_action.isChecked()
        self.soft_subtitle_action.setEnabled(need_video)
        self.use_style_action.setEnabled(need_video)
        self.video_quality_button.setEnabled(need_video)
        self._update_style_controls_state()

    def _update_style_controls_state(self):
        need_video = self.need_video_action.isChecked()
        use_style = self.use_style_action.isChecked()
        self.render_mode_button.setEnabled(need_video and use_style)

    def choose_subtitle_file(self):
        subtitle_formats = " ".join(
            f"*.{fmt.value}" for fmt in SupportedSubtitleFormats
        )
        filter_str = f"{self.tr('File phụ đề')} ({subtitle_formats})"

        file_path, _ = QFileDialog.getOpenFileName(
            self, self.tr("Chọn file phụ đề"), "", filter_str
        )
        if file_path:
            self.subtitle_input.setText(file_path)

    def choose_video_file(self):
        video_formats = " ".join(f"*.{fmt.value}" for fmt in SupportedVideoFormats)
        filter_str = f"{self.tr('File video')} ({video_formats})"

        file_path, _ = QFileDialog.getOpenFileName(
            self, self.tr("Chọn file video"), "", filter_str
        )
        if file_path:
            self.video_input.setText(file_path)

    def create_task(self):
        subtitle_file = self.subtitle_input.text()
        video_file = self.video_input.text()
        if not subtitle_file or not video_file:
            InfoBar.error(
                self.tr("Lỗi"),
                self.tr("Vui lòng chọn cả file phụ đề và file video."),
                duration=INFOBAR_DURATION_ERROR,
                position=InfoBarPosition.TOP,
                parent=self,
            )
            return None
        return TaskFactory.create_synthesis_task(video_file, subtitle_file)

    def set_task(self, task: SynthesisTask):
        self.task = task
        self.update_info()

    def update_info(self):
        if self.task:
            self.video_input.setText(self.task.video_path)
            self.subtitle_input.setText(self.task.subtitle_path)

    def start_video_synthesis(self, need_create_task=True):
        self.synthesize_button.setEnabled(False)
        self.progress_bar.resume()
        self.progress_bar.reset()
        if need_create_task:
            self.task = self.create_task()

        if self.task:
            self.video_synthesis_thread = VideoSynthesisThread(self.task)
            self.video_synthesis_thread.finished.connect(
                self.on_video_synthesis_finished
            )
            self.video_synthesis_thread.progress.connect(
                self.on_video_synthesis_progress
            )
            self.video_synthesis_thread.error.connect(self.on_video_synthesis_error)
            self.video_synthesis_thread.start()
        else:
            self.synthesize_button.setEnabled(True)

    def process(self):
        self.start_video_synthesis(need_create_task=False)

    def on_video_synthesis_finished(self, task):
        self.synthesize_button.setEnabled(True)
        self.progress_bar.setValue(100)
        self.open_video_folder()
        InfoBar.success(
            self.tr("Thành công"),
            self.tr("Ghép video đã hoàn tất."),
            duration=INFOBAR_DURATION_SUCCESS,
            position=InfoBarPosition.TOP,
            parent=self,
        )

    def on_video_synthesis_progress(self, progress, message):
        self.progress_bar.setValue(progress)
        self.status_label.setText(message)

    def on_video_synthesis_error(self, error):
        self.synthesize_button.setEnabled(True)
        self.progress_bar.error()
        InfoBar.error(
            self.tr("Lỗi"),
            str(error),
            duration=INFOBAR_DURATION_ERROR,
            position=InfoBarPosition.TOP,
            parent=self,
        )

    def open_video_folder(self):
        if self.task and self.task.output_path:
            file_path = Path(self.task.output_path)
            target_dir = str(
                file_path.parent
                if file_path.exists()
                else (
                    Path(str(self.task.video_path)).parent
                    if self.task.video_path
                    else file_path.parent
                )
            )
            open_folder(target_dir)
        else:
            InfoBar.warning(
                self.tr("Cảnh báo"),
                self.tr("Không có thư mục video khả dụng."),
                duration=INFOBAR_DURATION_WARNING,
                position=InfoBarPosition.TOP,
                parent=self,
            )

    def dragEnterEvent(self, event):
        event.accept() if event.mimeData().hasUrls() else event.ignore()

    def dropEvent(self, event: QDropEvent):
        files = [u.toLocalFile() for u in event.mimeData().urls()]
        for file_path in files:
            if not os.path.isfile(file_path):
                continue

            file_ext = os.path.splitext(file_path)[1][1:].lower()

            if file_ext in {fmt.value for fmt in SupportedSubtitleFormats}:
                self.subtitle_input.setText(file_path)
                InfoBar.success(
                    self.tr("Đã nhập file"),
                    self.tr("File phụ đề đã được đưa vào ô nhập."),
                    duration=INFOBAR_DURATION_SUCCESS,
                    parent=self,
                )
                break
            elif file_ext in {fmt.value for fmt in SupportedVideoFormats}:
                self.video_input.setText(file_path)
                InfoBar.success(
                    self.tr("Đã nhập file"),
                    self.tr("File video đã được đưa vào ô nhập."),
                    duration=INFOBAR_DURATION_SUCCESS,
                    parent=self,
                )
                break
            else:
                InfoBar.error(
                    self.tr("Sai định dạng: ") + file_ext,
                    self.tr("Vui lòng kéo thả file video hoặc file phụ đề."),
                    duration=INFOBAR_DURATION_ERROR,
                    parent=self,
                )


if __name__ == "__main__":
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)  # type: ignore
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps)  # type: ignore

    app = QApplication(sys.argv)
    window = VideoSynthesisInterface()
    window.resize(600, 400)
    window.show()
    sys.exit(app.exec_())

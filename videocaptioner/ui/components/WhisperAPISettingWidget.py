from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    ComboBoxSettingCard,
    InfoBar,
    InfoBarPosition,
    PushSettingCard,
    SettingCardGroup,
    SingleDirectionScrollArea,
)
from qfluentwidgets import FluentIcon as FIF

from videocaptioner.core.asr.api_profiles import MODEL_SUGGESTIONS
from videocaptioner.core.constant import INFOBAR_DURATION_ERROR, INFOBAR_DURATION_SUCCESS
from videocaptioner.core.entities import TranscribeLanguageEnum
from videocaptioner.ui.thread.whisper_connection_thread import WhisperConnectionThread

from ..common.config import cfg
from .EditComboBoxSettingCard import EditComboBoxSettingCard
from .LineEditSettingCard import LineEditSettingCard
from .WhisperProfileCards import WhisperProfileCards


class WhisperAPISettingWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()

    def setup_ui(self):
        self.main_layout = QVBoxLayout(self)

        # Create the scrolling container.
        self.scrollArea = SingleDirectionScrollArea(orient=Qt.Vertical, parent=self)  # type: ignore
        self.scrollArea.setStyleSheet(
            "QScrollArea{background: transparent; border: none}"
        )

        self.container = QWidget(self)
        self.container.setStyleSheet("QWidget{background: transparent}")
        self.containerLayout = QVBoxLayout(self.container)

        self.setting_group = SettingCardGroup(self.tr("Whisper API 设置"), self)

        self.profile_cards = WhisperProfileCards(self.setting_group)

        # API Base URL
        self.base_url_card = LineEditSettingCard(
            cfg.whisper_api_base,
            FIF.LINK,
            self.tr("API Base URL"),
            self.tr("输入 Whisper API Base URL"),
            "https://api.openai.com/v1",
            self.setting_group,
        )

        # API Key
        self.api_key_card = LineEditSettingCard(
            cfg.whisper_api_key,
            FIF.FINGERPRINT,
            self.tr("API Key"),
            self.tr("输入 Whisper API Key"),
            "sk-",
            self.setting_group,
        )

        # Model
        self.model_card = EditComboBoxSettingCard(
            cfg.whisper_api_model,
            FIF.ROBOT,  # type: ignore
            self.tr("Whisper 模型"),
            self.tr("选择 Whisper 模型"),
            MODEL_SUGGESTIONS,
            self.setting_group,
        )

        # Source language.
        self.language_card = ComboBoxSettingCard(
            cfg.transcribe_language,
            FIF.LANGUAGE,
            self.tr("源语言"),
            self.tr("音视频中说话的语言，默认根据前30秒自动识别"),
            [self.tr(lang.value) for lang in TranscribeLanguageEnum],
            self.setting_group,
        )

        # Optional prompt.
        self.prompt_card = LineEditSettingCard(
            cfg.whisper_api_prompt,
            FIF.CHAT,
            self.tr("提示词"),
            self.tr("可选的提示词,默认空"),
            "",
            self.setting_group,
        )

        # Recognition probe.
        self.check_connection_card = PushSettingCard(
            self.tr("测试连接"),
            FIF.CONNECT,
            self.tr("测试 Whisper API 连接"),
            self.tr("点击测试 API 连接是否正常"),
            self.setting_group,
        )

        # Keep input widths consistent.
        self.base_url_card.lineEdit.setMinimumWidth(200)
        self.api_key_card.lineEdit.setMinimumWidth(200)
        self.model_card.comboBox.setMinimumWidth(200)
        self.language_card.comboBox.setMinimumWidth(200)
        self.prompt_card.lineEdit.setMinimumWidth(200)

        # Register cards in display order.
        self.setting_group.addSettingCard(self.profile_cards.provider)
        self.setting_group.addSettingCard(self.profile_cards.profile)
        self.setting_group.addSettingCard(self.base_url_card)
        self.setting_group.addSettingCard(self.api_key_card)
        self.setting_group.addSettingCard(self.model_card)
        self.setting_group.addSettingCard(self.language_card)
        self.setting_group.addSettingCard(self.prompt_card)
        self.setting_group.addSettingCard(self.check_connection_card)

        # Connect the explicit probe action.
        self.check_connection_card.clicked.connect(self.on_check_connection)

        # Add the settings group.
        self.containerLayout.addWidget(self.setting_group)
        self.containerLayout.addStretch(1)

        # Configure scrolling.
        self.scrollArea.setWidget(self.container)
        self.scrollArea.setWidgetResizable(True)

        # Add the scroll area.
        self.main_layout.addWidget(self.scrollArea)

    def on_check_connection(self):
        """Test the Whisper API connection."""
        # Capture the current configuration.
        base_url = self.base_url_card.lineEdit.text().strip()
        api_key = self.api_key_card.lineEdit.text().strip()
        model = self.model_card.comboBox.currentText().strip()

        # Validate required fields.
        if not base_url or not api_key or not model:
            InfoBar.warning(
                self.tr("配置不完整"),
                self.tr("请输入 API Base URL、API Key 和 model"),
                duration=INFOBAR_DURATION_ERROR,
                position=InfoBarPosition.TOP,
                parent=self.window(),
            )
            return

        # Disable repeated probes while the worker runs.
        self.check_connection_card.button.setEnabled(False)
        self.check_connection_card.button.setText(self.tr("正在测试..."))

        # Start the probe worker.
        self.connection_thread = WhisperConnectionThread(
            base_url, api_key, model, cfg.whisper_api_provider.value,
            cfg.whisper_api_request_profile.value,
        )
        self.connection_thread.finished.connect(self.on_connection_check_finished)
        self.connection_thread.error.connect(self.on_connection_check_error)
        self.connection_thread.start()

    def on_connection_check_finished(self, success, result):
        """Handle a completed connection check."""
        # Restore the probe button.
        self.check_connection_card.button.setEnabled(True)
        self.check_connection_card.button.setText(self.tr("测试连接"))

        if success:
            InfoBar.success(
                self.tr("连接成功"),
                self.tr("Whisper API 连接成功！") + "\n" + result,
                duration=INFOBAR_DURATION_SUCCESS,
                position=InfoBarPosition.BOTTOM,
                parent=self.window(),
            )
        else:
            InfoBar.error(
                self.tr("连接失败"),
                self.tr(f"Whisper API 连接失败！\n{result}"),
                duration=INFOBAR_DURATION_ERROR,
                position=InfoBarPosition.BOTTOM,
                parent=self.window(),
            )

    def on_connection_check_error(self, message):
        """Handle a failed connection check."""
        # Restore the probe button.
        self.check_connection_card.button.setEnabled(True)
        self.check_connection_card.button.setText(self.tr("测试连接"))
        InfoBar.error(
            self.tr("测试错误"),
            message,
            duration=INFOBAR_DURATION_ERROR,
            position=InfoBarPosition.BOTTOM,
            parent=self.window(),
        )

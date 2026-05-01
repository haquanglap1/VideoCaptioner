from PyQt5.QtWidgets import QVBoxLayout
from qfluentwidgets import (
    ComboBox,
    InfoBar,
    InfoBarPosition,
    MessageBoxBase,
    SettingCard,
)
from qfluentwidgets import FluentIcon as FIF

from videocaptioner.core.entities import (
    TranscribeLanguageEnum,
    TranscribeModelEnum,
    get_asr_language_capability,
)
from videocaptioner.ui.common.config import cfg


class LanguageSettingDialog(MessageBoxBase):
    """语言设置对话框"""

    def __init__(self, model: TranscribeModelEnum, parent=None):
        self.model = model
        super().__init__(parent)
        self.widget.setMinimumWidth(500)
        self._setup_ui()
        self._connect_signals()

    def _get_available_languages(self) -> list[tuple[str, str]]:
        """获取当前模型支持的语言列表 (raw_value, display_text)."""
        capability = get_asr_language_capability(self.model)
        langs: list[tuple[str, str]] = [
            (lang.value, self.tr(lang.value)) for lang in capability.supported_languages
        ]
        if capability.supports_auto:
            langs.insert(
                0,
                (
                    TranscribeLanguageEnum.AUTO.value,
                    self.tr(TranscribeLanguageEnum.AUTO.value),
                ),
            )
        return langs

    def _setup_ui(self):
        """设置UI"""
        self.yesButton.setText(self.tr("确定"))
        self.cancelButton.setText(self.tr("取消"))

        # 主布局
        layout = QVBoxLayout()

        # 使用自定义 SettingCard 代替 ComboBoxSettingCard（因为需要动态选项）
        self.language_card = SettingCard(
            FIF.LANGUAGE,
            self.tr("源语言"),
            self.tr("音视频中说话的语言，默认根据前30秒自动识别"),
            self,
        )

        # 创建 ComboBox
        self.language_combo = ComboBox(self)
        self._available_languages = self._get_available_languages()
        self.language_combo.addItems([display for _, display in self._available_languages])
        self.language_combo.setMaxVisibleItems(6)
        self.language_combo.setMinimumWidth(160)

        # 设置当前值
        current_lang = cfg.transcribe_language.value
        raw_values = [raw for raw, _ in self._available_languages]
        if current_lang.value in raw_values:
            idx = raw_values.index(current_lang.value)
            self.language_combo.setCurrentIndex(idx)
        elif self._available_languages:
            # 当前选择的语言不在可选列表中，选择第一个
            self.language_combo.setCurrentIndex(0)

        # 添加 ComboBox 到卡片
        self.language_card.hBoxLayout.addWidget(self.language_combo)
        self.language_card.hBoxLayout.addSpacing(16)

        layout.addWidget(self.language_card)
        layout.addStretch(1)

        self.viewLayout.addLayout(layout)

    def _connect_signals(self):
        """连接信号"""
        self.yesButton.clicked.connect(self.__onYesButtonClicked)

    def __onYesButtonClicked(self):
        # 保存选中的语言到配置 — map display index back to raw enum value.
        idx = self.language_combo.currentIndex()
        if 0 <= idx < len(self._available_languages):
            raw_value = self._available_languages[idx][0]
            for lang in TranscribeLanguageEnum:
                if lang.value == raw_value:
                    cfg.set(cfg.transcribe_language, lang)
                    break

        self.accept()
        InfoBar.success(
            self.tr("设置已保存"),
            self.tr("语言设置已更新"),
            duration=3000,
            parent=self.window(),
            position=InfoBarPosition.BOTTOM,
        )
        if cfg.transcribe_language.value == TranscribeLanguageEnum.JAPANESE:
            InfoBar.warning(
                self.tr("请注意身体！！"),
                self.tr("小心肝儿,注意身体哦~"),
                duration=2000,
                parent=self.window(),
                position=InfoBarPosition.BOTTOM,
            )

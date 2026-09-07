import webbrowser

from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtWidgets import QFileDialog, QLabel, QWidget
from qfluentwidgets import (
    ComboBoxSettingCard,
    CustomColorSettingCard,
    ExpandLayout,
    HyperlinkCard,
    InfoBar,
    OptionsSettingCard,
    PrimaryPushSettingCard,
    PushSettingCard,
    RangeSettingCard,
    ScrollArea,
    SettingCardGroup,
    SwitchSettingCard,
    setTheme,
    setThemeColor,
)
from qfluentwidgets import FluentIcon as FIF

from videocaptioner.config import AUTHOR, RELEASE_URL, VERSION, YEAR
from videocaptioner.core.asr.api_profiles import MODEL_SUGGESTIONS
from videocaptioner.core.constant import (
    INFOBAR_DURATION_ERROR,
    INFOBAR_DURATION_SUCCESS,
    INFOBAR_DURATION_WARNING,
)
from videocaptioner.core.entities import (
    LLMServiceEnum,
    TranscribeModelEnum,
    TranslatorServiceEnum,
    enum_from_display,
)
from videocaptioner.core.llm.check_llm import check_llm_connection, get_available_models
from videocaptioner.core.llm.services import (
    LLM_SERVICE_PRESETS,
    fill_default_api_key,
    missing_whisper_api_fields,
)
from videocaptioner.core.utils.cache import disable_cache, enable_cache
from videocaptioner.ui.common.config import cfg
from videocaptioner.ui.common.signal_bus import signalBus
from videocaptioner.ui.components.EditComboBoxSettingCard import EditComboBoxSettingCard
from videocaptioner.ui.components.LineEditSettingCard import LineEditSettingCard
from videocaptioner.ui.components.WhisperProfileCards import WhisperProfileCards
from videocaptioner.ui.thread.whisper_connection_thread import WhisperConnectionThread


class SettingInterface(ScrollArea):
    """Settings page."""

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setWindowTitle(self.tr("设置"))
        self.scrollWidget = QWidget()
        self.expandLayout = ExpandLayout(self.scrollWidget)
        self.settingLabel = QLabel(self.tr("设置"), self)

        # Create every settings group
        self.__initGroups()
        # Create every settings card
        self.__initCards()
        # Set up the widget
        self.__initWidget()
        # Build the layout
        self.__initLayout()
        # Connect signals and slots
        self.__connectSignalToSlot()

    def __initGroups(self):
        """Create every settings group."""
        # Transcription group
        self.transcribeGroup = SettingCardGroup(self.tr("转录配置"), self.scrollWidget)
        # LLM group
        self.llmGroup = SettingCardGroup(self.tr("LLM配置"), self.scrollWidget)
        # Translation service group
        self.translate_serviceGroup = SettingCardGroup(
            self.tr("翻译服务"), self.scrollWidget
        )
        # Translation and optimization group
        self.translateGroup = SettingCardGroup(self.tr("翻译与优化"), self.scrollWidget)
        # Subtitle synthesis group
        self.subtitleGroup = SettingCardGroup(
            self.tr("字幕合成配置"), self.scrollWidget
        )
        # Save group
        self.saveGroup = SettingCardGroup(self.tr("保存配置"), self.scrollWidget)
        # Personalization group
        self.personalGroup = SettingCardGroup(self.tr("个性化"), self.scrollWidget)
        # About group
        self.aboutGroup = SettingCardGroup(self.tr("关于"), self.scrollWidget)

    def __initCards(self):
        """Create every settings card."""

        # ASR service card
        self.__createASRServiceCards()

        # LLM cards
        self.__createLLMServiceCards()

        # Translation cards
        self.__createTranslateServiceCards()

        # Translation and optimization cards
        self.subtitleCorrectCard = SwitchSettingCard(
            FIF.EDIT,
            self.tr("字幕校正"),
            self.tr("字幕处理过程是否对生成的字幕错别字、名词等进行校正"),
            cfg.need_optimize,
            self.translateGroup,
        )
        self.subtitleTranslateCard = SwitchSettingCard(
            FIF.LANGUAGE,
            self.tr("字幕翻译"),
            self.tr("字幕处理过程是否对生成的字幕进行翻译"),
            cfg.need_translate,
            self.translateGroup,
        )
        self.targetLanguageCard = ComboBoxSettingCard(
            cfg.target_language,
            FIF.LANGUAGE,
            self.tr("目标语言"),
            self.tr("选择翻译字幕的目标语言"),
            texts=[self.tr(lang.value) for lang in cfg.target_language.validator.options],  # type: ignore
            parent=self.translateGroup,
        )

        # Subtitle synthesis cards
        self.subtitleStyleCard = HyperlinkCard(
            "",
            self.tr("修改"),
            FIF.FONT,
            self.tr("字幕样式"),
            self.tr("选择字幕的样式（颜色、大小、字体等）"),
            self.subtitleGroup,
        )
        self.subtitleLayoutCard = HyperlinkCard(
            "",
            self.tr("修改"),
            FIF.FONT,
            self.tr("字幕布局"),
            self.tr("选择字幕的布局（单语、双语）"),
            self.subtitleGroup,
        )
        self.needVideoCard = SwitchSettingCard(
            FIF.VIDEO,
            self.tr("需要合成视频"),
            self.tr("开启时触发合成视频，关闭时跳过"),
            cfg.need_video,
            self.subtitleGroup,
        )
        self.softSubtitleCard = SwitchSettingCard(
            FIF.FONT,
            self.tr("软字幕"),
            self.tr("开启时字幕可在播放器中关闭或调整，关闭时字幕烧录到视频画面上"),
            cfg.soft_subtitle,
            self.subtitleGroup,
        )
        self.videoQualityCard = ComboBoxSettingCard(
            cfg.video_quality,
            FIF.SPEED_HIGH,
            self.tr("视频合成质量"),
            self.tr("硬字幕视频合成时的质量等级（质量越高文件越大，编码时间越长）"),
            texts=[self.tr(quality.value) for quality in cfg.video_quality.validator.options],  # type: ignore
            parent=self.subtitleGroup,
        )

        # Save cards
        self.savePathCard = PushSettingCard(
            self.tr("工作文件夹"),
            FIF.SAVE,
            self.tr("工作目录路径"),
            cfg.get(cfg.work_dir),
            self.saveGroup,
        )

        # Personalization cards
        self.cacheEnabledCard = SwitchSettingCard(
            FIF.HISTORY,
            self.tr("启用缓存"),
            self.tr("相同配置下会复用之前的 ASR 和 LLM 结果；关闭缓存后每次重新生成"),
            cfg.cache_enabled,
            self.personalGroup,
        )
        self.themeCard = OptionsSettingCard(
            cfg.themeMode,
            FIF.BRUSH,
            self.tr("应用主题"),
            self.tr("更改应用程序的外观"),
            texts=[self.tr("浅色"), self.tr("深色"), self.tr("使用系统设置")],
            parent=self.personalGroup,
        )
        self.themeColorCard = CustomColorSettingCard(
            cfg.themeColor,
            FIF.PALETTE,
            self.tr("主题颜色"),
            self.tr("更改应用程序的主题颜色"),
            self.personalGroup,
        )
        self.zoomCard = OptionsSettingCard(
            cfg.dpiScale,
            FIF.ZOOM,
            self.tr("界面缩放"),
            self.tr("更改小部件和字体的大小"),
            texts=["100%", "125%", "150%", "175%", "200%", self.tr("使用系统设置")],
            parent=self.personalGroup,
        )
        self.languageCard = ComboBoxSettingCard(
            cfg.language,
            FIF.LANGUAGE,
            self.tr("语言"),
            self.tr("设置您偏好的界面语言"),
            texts=["简体中文", "繁體中文", "English", "Tiếng Việt", self.tr("使用系统设置")],
            parent=self.personalGroup,
        )

        self.aboutCard = PrimaryPushSettingCard(
            self.tr("检查更新"),
            FIF.INFO,
            self.tr("关于"),
            "© "
            + self.tr("版权所有")
            + f" {YEAR}, {AUTHOR}. "
            + self.tr("版本")
            + " "
            + VERSION,
            self.aboutGroup,
        )

        # Add the cards to their groups
        self.translateGroup.addSettingCard(self.subtitleCorrectCard)
        self.translateGroup.addSettingCard(self.subtitleTranslateCard)
        self.translateGroup.addSettingCard(self.targetLanguageCard)

        self.subtitleGroup.addSettingCard(self.subtitleStyleCard)
        self.subtitleGroup.addSettingCard(self.subtitleLayoutCard)
        self.subtitleGroup.addSettingCard(self.needVideoCard)
        self.subtitleGroup.addSettingCard(self.softSubtitleCard)
        self.subtitleGroup.addSettingCard(self.videoQualityCard)

        self.saveGroup.addSettingCard(self.savePathCard)
        self.saveGroup.addSettingCard(self.cacheEnabledCard)

        self.personalGroup.addSettingCard(self.themeCard)
        self.personalGroup.addSettingCard(self.themeColorCard)
        self.personalGroup.addSettingCard(self.zoomCard)
        self.personalGroup.addSettingCard(self.languageCard)

        self.aboutGroup.addSettingCard(self.aboutCard)

    def __createLLMServiceCards(self):
        """Create the cards for the LLM services."""
        # Service selector card
        self.llmServiceCard = ComboBoxSettingCard(
            cfg.llm_service,
            FIF.ROBOT,
            self.tr("LLM 提供商"),
            self.tr("选择大模型提供商，用于字幕断句、优化、翻译"),
            texts=[self.tr(service.value) for service in cfg.llm_service.validator.options],  # type: ignore
            parent=self.llmGroup,
        )
        self.llmServiceCard.comboBox.setMinimumWidth(150)

        # Card linking to the official OpenAI API page
        self.openaiOfficialApiCard = HyperlinkCard(
            "https://api.videocaptioner.cn/register?aff=UrLB",
            self.tr("访问"),
            FIF.DEVELOPER_TOOLS,
            self.tr("VideoCaptioner 官方API"),
            self.tr("集成多种大语言模型，支持高并发字幕优化、翻译"),
            self.llmGroup,
        )
        # Hidden by default
        self.openaiOfficialApiCard.setVisible(False)

        # One key/base/model triple per provider; the presets carry the defaults.
        self.llm_service_configs = {}
        for service, preset in LLM_SERVICE_PRESETS.items():
            api_key_card = LineEditSettingCard(
                getattr(cfg, f"{preset.config_attr}_api_key"),
                FIF.FINGERPRINT,
                self.tr("API Key"),
                self.tr(f"输入您的 {service.value} API Key"),
                preset.key_placeholder,
                self.llmGroup,
            )
            api_base_card = LineEditSettingCard(
                getattr(cfg, f"{preset.config_attr}_api_base"),
                FIF.LINK,
                self.tr("Base URL"),
                self.tr(f"输入 {service.value} Base URL"),
                preset.default_base,
                self.llmGroup,
            )
            api_base_card.lineEdit.setReadOnly(not preset.base_url_editable)
            model_card = EditComboBoxSettingCard(
                getattr(cfg, f"{preset.config_attr}_model"),
                FIF.ROBOT,  # type: ignore
                self.tr("模型"),
                self.tr(f"选择 {service.value} 模型"),
                list(preset.default_models),
                self.llmGroup,
            )
            for suffix, card in (
                ("api_key", api_key_card),
                ("api_base", api_base_card),
                ("model", model_card),
            ):
                setattr(self, f"{preset.config_attr}_{suffix}_card", card)
            self.llm_service_configs[service] = {
                "cards": [api_key_card, api_base_card, model_card],
                "api_base": api_base_card,
                "api_key": api_key_card,
                "model": model_card,
            }

        # Connection check card
        self.checkLLMConnectionCard = PushSettingCard(
            self.tr("检查连接"),
            FIF.LINK,
            self.tr("检查 LLM 连接"),
            self.tr("点击检查 API 连接是否正常，并获取模型列表"),
            self.llmGroup,
        )

        # Initial visibility
        self.__onLLMServiceChanged(self.llmServiceCard.comboBox.currentText())

    def __createASRServiceCards(self):
        """Create the Whisper API cards."""
        # Transcription cards
        self.transcribeModelCard = ComboBoxSettingCard(
            cfg.transcribe_model,
            FIF.MICROPHONE,
            self.tr("转录模型"),
            self.tr("语音转换文字要使用的语音识别服务"),
            texts=[self.tr(model.value) for model in cfg.transcribe_model.validator.options],  # type: ignore
            parent=self.transcribeGroup,
        )
        self.transcribeModelCard.comboBox.setMinimumWidth(150)

        self.fasterWhisperManagerCard = PushSettingCard(
            self.tr("管理模型"),
            FIF.DOWNLOAD,
            self.tr("模型管理"),
            self.tr("下载或更新 Faster Whisper 模型"),
            self.transcribeGroup,
        )
        self.fasterWhisperManagerCard.setVisible(False)

        # API Base URL
        self.whisperProfileCards = WhisperProfileCards(self.transcribeGroup)
        self.whisperProfileCards.provider.setVisible(False)
        self.whisperProfileCards.profile.setVisible(False)
        self.whisperProfileCards.alignment.setVisible(False)
        self.whisperApiBaseCard = LineEditSettingCard(
            cfg.whisper_api_base,
            FIF.LINK,
            self.tr("Whisper API Base URL"),
            self.tr("输入 Whisper API Base URL"),
            "https://api.openai.com/v1",
            self.transcribeGroup,
        )

        # API Key
        self.whisperApiKeyCard = LineEditSettingCard(
            cfg.whisper_api_key,
            FIF.FINGERPRINT,
            self.tr("Whisper API Key"),
            self.tr("输入 Whisper API Key"),
            "sk-",
            self.transcribeGroup,
        )

        # Model selector
        self.whisperApiModelCard = EditComboBoxSettingCard(
            cfg.whisper_api_model,
            FIF.ROBOT,  # type: ignore
            self.tr("Whisper 模型"),
            self.tr("选择 Whisper 模型"),
            MODEL_SUGGESTIONS,
            self.transcribeGroup,
        )

        # Connection test button
        self.checkWhisperConnectionCard = PushSettingCard(
            self.tr("测试 Whisper 连接"),
            FIF.CONNECT,
            self.tr("测试 Whisper API 连接"),
            self.tr("点击测试 API 连接是否正常"),
            self.transcribeGroup,
        )

        # Whisper API cards start hidden; shown only when Whisper API is selected
        self.whisperApiBaseCard.setVisible(False)
        self.whisperApiKeyCard.setVisible(False)
        self.whisperApiModelCard.setVisible(False)
        self.checkWhisperConnectionCard.setVisible(False)

    def __createTranslateServiceCards(self):
        """Create the cards for the translation services."""
        # Translation service selector card
        self.translatorServiceCard = ComboBoxSettingCard(
            cfg.translator_service,
            FIF.ROBOT,
            self.tr("翻译服务"),
            self.tr("选择翻译服务"),
            texts=[
                self.tr(service.value)
                for service in cfg.translator_service.validator.options  # type: ignore
            ],
            parent=self.translate_serviceGroup,
        )
        self.translatorServiceCard.comboBox.setMinimumWidth(150)

        # Reflective translation switch
        self.needReflectTranslateCard = SwitchSettingCard(
            FIF.EDIT,
            self.tr("需要反思翻译"),
            self.tr("启用反思翻译可以提高翻译质量，但耗费更多时间和token"),
            cfg.need_reflect_translate,
            self.translate_serviceGroup,
        )

        # DeepLX endpoint
        self.deeplxEndpointCard = LineEditSettingCard(
            cfg.deeplx_endpoint,
            FIF.LINK,
            self.tr("DeepLx 后端"),
            self.tr("输入 DeepLx 的后端地址(开启deeplx翻译时必填)"),
            "https://api.deeplx.org/translate",
            self.translate_serviceGroup,
        )

        # Batch size
        self.batchSizeCard = RangeSettingCard(
            cfg.batch_size,
            FIF.ALIGNMENT,
            self.tr("批处理大小"),
            self.tr("每批处理字幕的数量，建议为 10 的倍数"),
            parent=self.translate_serviceGroup,
        )

        # Thread count
        self.threadNumCard = RangeSettingCard(
            cfg.thread_num,
            FIF.SPEED_HIGH,
            self.tr("线程数"),
            self.tr(
                "请求并行处理的数量，模型服务商允许的情况下建议尽可能大，数值越大速度越快"
            ),
            parent=self.translate_serviceGroup,
        )

        # Add the cards to the translation service group
        self.translate_serviceGroup.addSettingCard(self.translatorServiceCard)
        self.translate_serviceGroup.addSettingCard(self.needReflectTranslateCard)
        self.translate_serviceGroup.addSettingCard(self.deeplxEndpointCard)
        self.translate_serviceGroup.addSettingCard(self.batchSizeCard)
        self.translate_serviceGroup.addSettingCard(self.threadNumCard)

        # Initial visibility
        self.__onTranslatorServiceChanged(
            self.translatorServiceCard.comboBox.currentText()
        )

    def __initWidget(self):
        self.resize(1000, 800)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)  # type: ignore
        self.setViewportMargins(0, 80, 0, 20)
        self.setWidget(self.scrollWidget)
        self.setWidgetResizable(True)
        self.enableTransparentBackground()
        self.viewport().setAttribute(Qt.WA_TranslucentBackground, True)  # type: ignore
        self.scrollWidget.setAttribute(Qt.WA_TranslucentBackground, True)  # type: ignore
        self.setObjectName("settingInterface")

        # Style sheet
        self.scrollWidget.setObjectName("scrollWidget")
        self.settingLabel.setObjectName("settingLabel")

        # Initial visibility of the transcription model cards
        self.__onTranscribeModelChanged(self.transcribeModelCard.comboBox.currentText())

        # Initial visibility of the translation service cards
        self.__onTranslatorServiceChanged(
            self.translatorServiceCard.comboBox.currentText()
        )

        self.setStyleSheet(
            """
            SettingInterface, #scrollWidget {
                background-color: transparent;
            }
            QScrollArea {
                border: none;
                background-color: transparent;
            }
            QLabel#settingLabel {
                font: 33px 'Microsoft YaHei';
                background-color: transparent;
                color: white;
            }
        """
        )

    def __initLayout(self):
        """Build the layout."""
        self.settingLabel.move(36, 30)

        # Transcription cards
        self.transcribeGroup.addSettingCard(self.transcribeModelCard)
        self.transcribeGroup.addSettingCard(self.fasterWhisperManagerCard)
        # Whisper API cards
        self.transcribeGroup.addSettingCard(self.whisperProfileCards.provider)
        self.transcribeGroup.addSettingCard(self.whisperProfileCards.profile)
        self.transcribeGroup.addSettingCard(self.whisperProfileCards.alignment)
        self.transcribeGroup.addSettingCard(self.whisperApiBaseCard)
        self.transcribeGroup.addSettingCard(self.whisperApiKeyCard)
        self.transcribeGroup.addSettingCard(self.whisperApiModelCard)
        self.transcribeGroup.addSettingCard(self.checkWhisperConnectionCard)

        # LLM cards
        self.llmGroup.addSettingCard(self.llmServiceCard)
        # Official OpenAI API link card
        self.llmGroup.addSettingCard(self.openaiOfficialApiCard)
        for config in self.llm_service_configs.values():
            for card in config["cards"]:
                self.llmGroup.addSettingCard(card)
        self.llmGroup.addSettingCard(self.checkLLMConnectionCard)

        # Add every group to the layout
        self.expandLayout.setSpacing(28)
        self.expandLayout.setContentsMargins(36, 10, 36, 0)
        self.expandLayout.addWidget(self.transcribeGroup)
        self.expandLayout.addWidget(self.llmGroup)
        self.expandLayout.addWidget(self.translate_serviceGroup)
        self.expandLayout.addWidget(self.translateGroup)
        self.expandLayout.addWidget(self.subtitleGroup)
        self.expandLayout.addWidget(self.saveGroup)
        self.expandLayout.addWidget(self.personalGroup)
        self.expandLayout.addWidget(self.aboutGroup)

    def __connectSignalToSlot(self):
        """Connect signals and slots."""
        cfg.appRestartSig.connect(self.__showRestartTooltip)

        # LLM service switch
        self.llmServiceCard.comboBox.currentTextChanged.connect(
            self.__onLLMServiceChanged
        )

        # Translation service switch
        self.translatorServiceCard.comboBox.currentTextChanged.connect(
            self.__onTranslatorServiceChanged
        )

        # Transcription model switch
        self.transcribeModelCard.comboBox.currentTextChanged.connect(
            self.__onTranscribeModelChanged
        )
        self.fasterWhisperManagerCard.clicked.connect(
            self.__showFasterWhisperManager
        )

        # LLM connection check
        self.checkLLMConnectionCard.clicked.connect(self.checkLLMConnection)

        # Whisper connection check
        self.checkWhisperConnectionCard.clicked.connect(self.checkWhisperConnection)

        # Save path
        self.savePathCard.clicked.connect(self.__onsavePathCardClicked)

        # Jump to the subtitle style page
        self.subtitleStyleCard.linkButton.clicked.connect(
            lambda: self.window().switchTo(self.window().subtitleStyleInterface)  # type: ignore
        )
        self.subtitleLayoutCard.linkButton.clicked.connect(
            lambda: self.window().switchTo(self.window().subtitleStyleInterface)  # type: ignore
        )

        # Personalization
        self.cacheEnabledCard.checkedChanged.connect(self.__onCacheEnabledChanged)
        self.themeCard.optionChanged.connect(lambda ci: setTheme(cfg.get(ci)))
        self.themeColorCard.colorChanged.connect(setThemeColor)

        # About
        self.aboutCard.clicked.connect(self.checkUpdate)

        # Global signalBus
        self.transcribeModelCard.comboBox.currentTextChanged.connect(
            signalBus.transcription_model_changed
        )
        self.subtitleCorrectCard.checkedChanged.connect(
            signalBus.subtitle_optimization_changed
        )
        self.subtitleTranslateCard.checkedChanged.connect(
            signalBus.subtitle_translation_changed
        )
        self.targetLanguageCard.comboBox.currentTextChanged.connect(
            signalBus.target_language_changed
        )
        self.softSubtitleCard.checkedChanged.connect(signalBus.soft_subtitle_changed)
        self.needVideoCard.checkedChanged.connect(signalBus.need_video_changed)
        self.videoQualityCard.comboBox.currentTextChanged.connect(
            signalBus.video_quality_changed
        )

    def __showRestartTooltip(self):
        """Show the restart hint."""
        InfoBar.success(
            self.tr("更新成功"),
            self.tr("配置将在重启后生效"),
            duration=INFOBAR_DURATION_SUCCESS,
            parent=self,
        )

    def __onsavePathCardClicked(self):
        """Handle a click on the save path card."""
        folder = QFileDialog.getExistingDirectory(self, self.tr("选择文件夹"), "./")
        if not folder or cfg.get(cfg.work_dir) == folder:
            return
        cfg.set(cfg.work_dir, folder)
        self.savePathCard.setContent(folder)

    def __onCacheEnabledChanged(self, is_enabled: bool):
        """Handle the cache switch changing."""
        if is_enabled:
            enable_cache()
            InfoBar.success(
                self.tr("缓存已启用"),
                self.tr("ASR、翻译等操作将优先使用缓存"),
                duration=INFOBAR_DURATION_SUCCESS,
                parent=self,
            )
        else:
            disable_cache()
            InfoBar.warning(
                self.tr("缓存已禁用"),
                self.tr("所有操作将重新生成，不使用缓存（建议开启缓存）"),
                duration=INFOBAR_DURATION_WARNING,
                parent=self,
            )

    def checkLLMConnection(self):
        """Check the LLM connection."""
        # Remember the scroll position
        scroll_position = self.verticalScrollBar().value()

        # Currently selected service
        current_service = enum_from_display(
            LLMServiceEnum, self.llmServiceCard.comboBox.currentText(), self.tr
        )

        # Service configuration
        service_config = self.llm_service_configs.get(current_service)
        if not service_config:
            return

        api_base = (
            service_config["api_base"].lineEdit.text()
            if service_config["api_base"]
            else ""
        )
        api_key = (
            service_config["api_key"].lineEdit.text()
            if service_config["api_key"]
            else ""
        )
        model = (
            service_config["model"].comboBox.currentText()
            if service_config["model"]
            else ""
        )

        # Disable the check button and show the loading state
        self.checkLLMConnectionCard.button.setEnabled(False)
        self.checkLLMConnectionCard.button.setText(self.tr("正在检查..."))

        # Restore the scroll position right away; the button state change would auto-scroll
        self.verticalScrollBar().setValue(scroll_position)

        # Create and start the thread
        self.connection_thread = LLMConnectionThread(api_base, api_key, model)
        self.connection_thread.finished.connect(self.onConnectionCheckFinished)
        self.connection_thread.error.connect(self.onConnectionCheckError)
        self.connection_thread.start()

    def onConnectionCheckError(self, message):
        """Handle a connection check error."""
        self.checkLLMConnectionCard.button.setEnabled(True)
        self.checkLLMConnectionCard.button.setText(self.tr("检查连接"))
        InfoBar.error(
            self.tr("LLM 连接测试错误"),
            message,
            duration=INFOBAR_DURATION_ERROR,
            parent=self,
        )

    def onConnectionCheckFinished(self, is_success, message, models):
        """Handle a finished connection check."""
        self.checkLLMConnectionCard.button.setEnabled(True)
        self.checkLLMConnectionCard.button.setText(self.tr("检查连接"))

        # Current service
        current_service = enum_from_display(
            LLMServiceEnum, self.llmServiceCard.comboBox.currentText(), self.tr
        )

        if models:
            # Update the model list of the current service
            service_config = self.llm_service_configs.get(current_service)
            if service_config and service_config["model"]:
                temp = service_config["model"].comboBox.currentText()
                service_config["model"].setItems(models)
                service_config["model"].comboBox.setCurrentText(temp)

            InfoBar.success(
                self.tr("获取模型列表成功:"),
                self.tr("一共") + str(len(models)) + self.tr("个模型"),
                duration=INFOBAR_DURATION_SUCCESS,
                parent=self,
            )
        if not is_success:
            InfoBar.error(
                self.tr("LLM 连接测试错误"),
                message,
                duration=INFOBAR_DURATION_ERROR,
                parent=self,
            )
        else:
            InfoBar.success(
                self.tr("LLM 连接测试成功"),
                message,
                duration=INFOBAR_DURATION_SUCCESS,
                parent=self,
            )

    def checkUpdate(self):
        """Kiểm tra cập nhật và hiện UpdateDialog nếu có phiên bản mới."""
        from videocaptioner.ui.components.UpdateDialog import UpdateDialog
        from videocaptioner.ui.thread.version_checker_thread import VersionChecker

        # Disable button while checking
        self.aboutCard.button.setEnabled(False)
        self.aboutCard.button.setText(self.tr("Đang kiểm tra..."))

        try:
            checker = VersionChecker()
            data = checker.get_latest_version_info()

            self.aboutCard.button.setEnabled(True)
            self.aboutCard.button.setText(self.tr("检查更新"))

            if not data:
                InfoBar.warning(
                    self.tr("Kiểm tra cập nhật"),
                    self.tr("Không thể kết nối tới server. Thử lại sau."),
                    duration=INFOBAR_DURATION_WARNING,
                    parent=self,
                )
                return

            if not checker.has_new_version():
                InfoBar.success(
                    self.tr("Đã cập nhật"),
                    self.tr("Bạn đang dùng phiên bản mới nhất!"),
                    duration=INFOBAR_DURATION_SUCCESS,
                    parent=self,
                )
                return

            # Có phiên bản mới — hiện UpdateDialog
            dialog = UpdateDialog(
                version=checker.latest_version,
                update_info=checker.update_info,
                download_url=checker.download_url,
                parent=self.window(),
            )
            dialog.exec()

        except Exception as e:
            self.aboutCard.button.setEnabled(True)
            self.aboutCard.button.setText(self.tr("检查更新"))
            InfoBar.error(
                self.tr("Lỗi"),
                str(e),
                duration=INFOBAR_DURATION_ERROR,
                parent=self,
            )
            # Fallback: mở browser
            webbrowser.open(RELEASE_URL)

    def __onLLMServiceChanged(self, service):
        """Handle the LLM service changing."""
        current_service = enum_from_display(LLMServiceEnum, service, self.tr)

        # Hide every card
        for config in self.llm_service_configs.values():
            for card in config["cards"]:
                card.setVisible(False)

        # Hide the official OpenAI API link card
        self.openaiOfficialApiCard.setVisible(False)

        # Show the cards of the selected service
        if current_service in self.llm_service_configs:
            for card in self.llm_service_configs[current_service]["cards"]:
                card.setVisible(True)

            # Local servers accept any token: fill the placeholder when blank.
            key_edit = self.llm_service_configs[current_service]["api_key"].lineEdit
            filled = fill_default_api_key(current_service, key_edit.text())
            if filled != key_edit.text():
                key_edit.setText(filled)

            # Show the official API link card for the OpenAI service
            if current_service == LLMServiceEnum.OPENAI:
                self.openaiOfficialApiCard.setVisible(True)

        # Refresh the layout
        self.llmGroup.adjustSize()
        self.expandLayout.update()

    def __onTranslatorServiceChanged(self, service):
        openai_cards = [
            self.needReflectTranslateCard,
            self.batchSizeCard,
        ]
        deeplx_cards = [self.deeplxEndpointCard]

        all_cards = openai_cards + deeplx_cards
        for card in all_cards:
            card.setVisible(False)

        # Show the cards that belong to the selected service
        # `service` is the comboBox display text — translated. Resolve via helper.
        try:
            current = enum_from_display(TranslatorServiceEnum, service, self.tr)
        except ValueError:
            return
        if current is TranslatorServiceEnum.DEEPLX:
            for card in deeplx_cards:
                card.setVisible(True)
        elif current is TranslatorServiceEnum.OPENAI:
            for card in openai_cards:
                card.setVisible(True)

        # Refresh the layout
        self.translate_serviceGroup.adjustSize()
        self.expandLayout.update()

    def __onTranscribeModelChanged(self, model_name):
        """Handle the transcription model changing."""
        # Whisper API cards
        whisper_api_cards = [
            self.whisperProfileCards.provider,
            self.whisperProfileCards.profile,
            self.whisperProfileCards.alignment,
            self.whisperApiBaseCard,
            self.whisperApiKeyCard,
            self.whisperApiModelCard,
            self.checkWhisperConnectionCard,
        ]

        # The combo shows translated text, so resolve it before checking which
        # model-specific cards should be visible.
        try:
            current = enum_from_display(TranscribeModelEnum, model_name, self.tr)
        except ValueError:
            current = None
        is_whisper_api = current is TranscribeModelEnum.WHISPER_API
        self.fasterWhisperManagerCard.setVisible(
            current is TranscribeModelEnum.FASTER_WHISPER
        )
        for card in whisper_api_cards:
            card.setVisible(is_whisper_api)

        # Refresh the layout
        self.transcribeGroup.adjustSize()
        self.expandLayout.update()

    def __showFasterWhisperManager(self):
        """Open the program/model manager from the global Settings page."""
        from videocaptioner.ui.components.FasterWhisperSettingWidget import (
            FasterWhisperDownloadDialog,
        )

        dialog = FasterWhisperDownloadDialog(self.window())
        dialog.exec_()

    def checkWhisperConnection(self):
        """Check the Whisper API connection."""
        # Remember the scroll position
        scroll_position = self.verticalScrollBar().value()

        # Configuration
        base_url = self.whisperApiBaseCard.lineEdit.text().strip()
        api_key = self.whisperApiKeyCard.lineEdit.text().strip()
        model = self.whisperApiModelCard.comboBox.currentText().strip()

        missing = missing_whisper_api_fields(base_url, api_key, model)
        if missing:
            prompts = {
                "base_url": self.tr("请输入 Whisper API Base URL"),
                "api_key": self.tr("请输入 Whisper API Key"),
                "model": self.tr("请输入 Whisper 模型名称"),
            }
            InfoBar.warning(
                self.tr("配置不完整"),
                prompts[missing[0]],
                duration=INFOBAR_DURATION_ERROR,
                parent=self,
            )
            return

        # Disable the button and show the loading state
        self.checkWhisperConnectionCard.button.setEnabled(False)
        self.checkWhisperConnectionCard.button.setText(self.tr("正在测试..."))

        # Restore the scroll position right away; the button state change would auto-scroll
        self.verticalScrollBar().setValue(scroll_position)

        # Create and start the test thread
        self.whisper_connection_thread = WhisperConnectionThread(
            base_url, api_key, model, cfg.whisper_api_provider.value,
            cfg.whisper_api_request_profile.value,
        )
        self.whisper_connection_thread.finished.connect(
            self.onWhisperConnectionCheckFinished
        )
        self.whisper_connection_thread.error.connect(self.onWhisperConnectionCheckError)
        self.whisper_connection_thread.start()

    def onWhisperConnectionCheckFinished(self, success, result):
        """Handle a finished Whisper connection check."""
        # Restore the button
        self.checkWhisperConnectionCard.button.setEnabled(True)
        self.checkWhisperConnectionCard.button.setText(self.tr("测试 Whisper 连接"))

        if success:
            InfoBar.success(
                self.tr("连接成功"),
                self.tr("Whisper API 连接成功！\n转录结果:") + result,
                duration=INFOBAR_DURATION_SUCCESS,
                parent=self,
            )
        else:
            InfoBar.error(
                self.tr("连接失败"),
                self.tr(f"Whisper API 连接失败！\n{result}"),
                duration=INFOBAR_DURATION_ERROR,
                parent=self,
            )

    def onWhisperConnectionCheckError(self, message):
        """Handle a Whisper connection check error."""
        # Restore the button
        self.checkWhisperConnectionCard.button.setEnabled(True)
        self.checkWhisperConnectionCard.button.setText(self.tr("测试 Whisper 连接"))

        InfoBar.error(
            self.tr("测试错误"),
            message,
            duration=INFOBAR_DURATION_ERROR,
            parent=self,
        )


class LLMConnectionThread(QThread):
    finished = pyqtSignal(bool, str, list)
    error = pyqtSignal(str)

    def __init__(self, api_base, api_key, model):
        super().__init__()
        self.api_base = api_base
        self.api_key = api_key
        self.model = model

    def run(self):
        """Check the LLM connection and fetch the model list."""
        try:
            is_success, message = check_llm_connection(
                self.api_base, self.api_key, self.model
            )
            models = get_available_models(self.api_base, self.api_key)
            self.finished.emit(is_success, message, models)
        except Exception as e:
            self.error.emit(str(e))

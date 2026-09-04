from pathlib import Path
from typing import Optional, Tuple

from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QColor, QFontDatabase
from PyQt5.QtWidgets import QFileDialog, QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import (
    BodyLabel,
    CardWidget,
    ImageLabel,
    InfoBar,
    InfoBarPosition,
    LineEdit,
    MessageBoxBase,
    PushSettingCard,
    ScrollArea,
    SettingCardGroup,
)
from qfluentwidgets import FluentIcon as FIF

from videocaptioner.config import ASSETS_PATH, SUBTITLE_STYLE_PATH
from videocaptioner.core.constant import INFOBAR_DURATION_SUCCESS, INFOBAR_DURATION_WARNING
from videocaptioner.core.entities import SubtitleLayoutEnum, SubtitleRenderModeEnum
from videocaptioner.core.subtitle import get_builtin_fonts
from videocaptioner.core.subtitle.style_manager import SecondaryStyle, StyleMode, SubtitleStyle
from videocaptioner.core.subtitle.style_presenter import (
    DEFAULT_STYLE_ID,
    PREVIEW_ORIENTATIONS,
    PREVIEW_TEXTS,
    choose_style_id,
    default_background,
    first_image_path,
    font_choices,
    format_rgba_hex,
    list_style_ids,
    parse_rgba_hex,
    pil_can_load_font,
    preview_background,
    preview_text_pair,
    render_style_preview,
    resolve_style_path,
    save_style,
    style_mode_for,
)
from videocaptioner.core.utils.platform_utils import open_folder
from videocaptioner.ui.common.config import cfg
from videocaptioner.ui.common.signal_bus import signalBus
from videocaptioner.ui.components.MySettingCard import (
    ColorSettingCard,
    ComboBoxSettingCard,
    DoubleSpinBoxSettingCard,
    SpinBoxSettingCard,
)


class StylePreviewThread(QThread):
    """Render one preview image off the UI thread; the presenter picks the renderer."""

    previewReady = pyqtSignal(str)

    def __init__(
        self,
        style: SubtitleStyle,
        preview_text: Tuple[str, Optional[str]],
        bg_image_path: str,
    ):
        super().__init__()
        self.style = style
        self.preview_text = preview_text
        self.bg_image_path = bg_image_path

    def run(self):
        self.previewReady.emit(
            render_style_preview(self.style, self.preview_text, self.bg_image_path)
        )


class SubtitleStyleInterface(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setObjectName("SubtitleStyleInterface")
        self.setWindowTitle(self.tr("字幕样式配置"))
        self.setAcceptDrops(True)  # 启用拖放功能

        # 创建主布局
        self.hBoxLayout = QHBoxLayout(self)

        # 初始化界面组件
        self._initSettingsArea()
        self._initPreviewArea()
        self._initSettingCards()
        self._initLayout()
        self._initStyle()

        # 控制是否触发样式变更回调（加载样式时禁用）
        self._loading_style = False

        # 设置初始值,加载样式
        self.__setValues()

        # 连接信号
        self.connectSignals()

    def _initSettingsArea(self):
        """初始化左侧设置区域"""
        self.settingsScrollArea = ScrollArea()
        self.settingsScrollArea.setFixedWidth(350)
        self.settingsWidget = QWidget()
        self.settingsLayout = QVBoxLayout(self.settingsWidget)
        self.settingsScrollArea.setWidget(self.settingsWidget)
        self.settingsScrollArea.setWidgetResizable(True)
        self.settingsScrollArea.enableTransparentBackground()
        self.settingsScrollArea.viewport().setAttribute(
            Qt.WA_TranslucentBackground, True  # type: ignore
        )
        self.settingsWidget.setAttribute(Qt.WA_TranslucentBackground, True)  # type: ignore

        # 创建设置组 - 通用
        self.layoutGroup = SettingCardGroup(self.tr("字幕排布"), self.settingsWidget)

        # ASS 样式设置组
        self.assPrimaryGroup = SettingCardGroup(
            self.tr("主字幕样式"), self.settingsWidget
        )
        self.assSecondaryGroup = SettingCardGroup(
            self.tr("副字幕样式"), self.settingsWidget
        )

        # 圆角背景设置组
        self.roundedBgGroup = SettingCardGroup(
            self.tr("圆角背景样式"), self.settingsWidget
        )

        # 预览设置组
        self.previewGroup = SettingCardGroup(self.tr("预览设置"), self.settingsWidget)

    def _initPreviewArea(self):
        """初始化右侧预览区域"""
        self.previewCard = CardWidget()
        self.previewLayout = QVBoxLayout(self.previewCard)
        self.previewLayout.setSpacing(16)

        # 顶部预览区域
        self.previewTopWidget = QWidget()
        self.previewTopWidget.setFixedHeight(430)
        self.previewTopLayout = QVBoxLayout(self.previewTopWidget)

        self.previewLabel = BodyLabel(self.tr("预览效果"))
        self.previewImage = ImageLabel()
        self.previewImage.setAlignment(Qt.AlignCenter)  # type: ignore
        self.previewTopLayout.addWidget(self.previewImage, 0, Qt.AlignCenter)  # type: ignore
        self.previewTopLayout.setAlignment(Qt.AlignVCenter)  # type: ignore

        # 底部控件区域
        self.previewBottomWidget = QWidget()
        self.previewBottomLayout = QVBoxLayout(self.previewBottomWidget)

        self.styleNameComboBox = ComboBoxSettingCard(
            FIF.VIEW,  # type: ignore
            self.tr("选择样式"),
            self.tr("选择已保存的字幕样式"),
            texts=[],  # type: ignore
        )

        self.newStyleButton = PushSettingCard(
            self.tr("新建样式"),
            FIF.ADD,
            self.tr("新建样式"),
            self.tr("基于当前样式新建预设"),
        )

        self.openStyleFolderButton = PushSettingCard(
            self.tr("打开样式文件夹"),
            FIF.FOLDER,
            self.tr("打开样式文件夹"),
            self.tr("在文件管理器中打开样式文件夹"),
        )

        self.previewBottomLayout.addWidget(self.styleNameComboBox)
        self.previewBottomLayout.addWidget(self.newStyleButton)
        self.previewBottomLayout.addWidget(self.openStyleFolderButton)

        self.previewLayout.addWidget(self.previewTopWidget)
        self.previewLayout.addWidget(self.previewBottomWidget)
        self.previewLayout.addStretch(1)

    def _initSettingCards(self):
        """初始化所有设置卡片"""
        self._render_mode_display_to_enum = {
            self.tr(e.value): e for e in SubtitleRenderModeEnum
        }
        self._layout_display_to_enum = {
            self.tr(e.value): e for e in SubtitleLayoutEnum
        }

        # 渲染模式切换
        self.renderModeCard = ComboBoxSettingCard(
            FIF.BRUSH,  # type: ignore
            self.tr("渲染模式"),
            self.tr("选择字幕渲染方式"),
            texts=list(self._render_mode_display_to_enum.keys()),
        )

        # 字幕排布设置
        self.layoutCard = ComboBoxSettingCard(
            FIF.ALIGNMENT,  # type: ignore
            self.tr("字幕排布"),
            self.tr("设置主字幕和副字幕的显示方式"),
            texts=list(self._layout_display_to_enum.keys()),
        )

        # ASS 模式 - 垂直间距
        self.assVerticalSpacingCard = SpinBoxSettingCard(
            FIF.ALIGNMENT,  # type: ignore
            self.tr("垂直间距"),
            self.tr("设置字幕的垂直间距"),
            minimum=8,
            maximum=10000,
        )

        # ASS 模式 - 主字幕样式
        self.assPrimaryFontCard = ComboBoxSettingCard(
            FIF.FONT,  # type: ignore
            self.tr("主字幕字体"),
            self.tr("设置主字幕的字体"),
        )

        self.assPrimarySizeCard = SpinBoxSettingCard(
            FIF.FONT_SIZE,  # type: ignore
            self.tr("主字幕字号"),
            self.tr("设置主字幕的大小"),
            minimum=8,
            maximum=1000,
        )

        self.assPrimarySpacingCard = DoubleSpinBoxSettingCard(
            FIF.ALIGNMENT,  # type: ignore
            self.tr("主字幕间距"),
            self.tr("设置主字幕的字符间距"),
            minimum=0.0,
            maximum=10.0,
            decimals=1,
        )

        self.assPrimaryColorCard = ColorSettingCard(
            QColor(255, 255, 255),
            FIF.PALETTE,  # type: ignore
            self.tr("主字幕颜色"),
            self.tr("设置主字幕的颜色"),
        )

        self.assPrimaryOutlineColorCard = ColorSettingCard(
            QColor(0, 0, 0),
            FIF.PALETTE,  # type: ignore
            self.tr("主字幕边框颜色"),
            self.tr("设置主字幕的边框颜色"),
        )

        self.assPrimaryOutlineSizeCard = DoubleSpinBoxSettingCard(
            FIF.ZOOM,  # type: ignore
            self.tr("主字幕边框大小"),
            self.tr("设置主字幕的边框粗细"),
            minimum=0.0,
            maximum=10.0,
            decimals=1,
        )

        # ASS 模式 - 副字幕样式
        self.assSecondaryFontCard = ComboBoxSettingCard(
            FIF.FONT,  # type: ignore
            self.tr("副字幕字体"),
            self.tr("设置副字幕的字体"),
        )

        self.assSecondarySizeCard = SpinBoxSettingCard(
            FIF.FONT_SIZE,  # type: ignore
            self.tr("副字幕字号"),
            self.tr("设置副字幕的大小"),
            minimum=8,
            maximum=1000,
        )

        self.assSecondarySpacingCard = DoubleSpinBoxSettingCard(
            FIF.ALIGNMENT,  # type: ignore
            self.tr("副字幕间距"),
            self.tr("设置副字幕的字符间距"),
            minimum=0.0,
            maximum=50.0,
            decimals=1,
        )

        self.assSecondaryColorCard = ColorSettingCard(
            QColor(255, 255, 255),
            FIF.PALETTE,  # type: ignore
            self.tr("副字幕颜色"),
            self.tr("设置副字幕的颜色"),
        )

        self.assSecondaryOutlineColorCard = ColorSettingCard(
            QColor(0, 0, 0),
            FIF.PALETTE,  # type: ignore
            self.tr("副字幕边框颜色"),
            self.tr("设置副字幕的边框颜色"),
        )

        self.assSecondaryOutlineSizeCard = DoubleSpinBoxSettingCard(
            FIF.ZOOM,  # type: ignore
            self.tr("副字幕边框大小"),
            self.tr("设置副字幕的边框粗细"),
            minimum=0.0,
            maximum=50.0,
            decimals=1,
        )

        # 圆角背景样式设置
        self.roundedFontCard = ComboBoxSettingCard(
            FIF.FONT,  # type: ignore
            self.tr("字体"),
            self.tr("设置字幕字体"),
        )

        self.roundedFontSizeCard = SpinBoxSettingCard(
            FIF.FONT_SIZE,  # type: ignore
            self.tr("字体大小"),
            self.tr("设置字幕字体大小"),
            minimum=16,
            maximum=120,
        )

        self.roundedTextColorCard = ColorSettingCard(
            QColor(255, 255, 255),
            FIF.PALETTE,  # type: ignore
            self.tr("文字颜色"),
            self.tr("设置字幕文字颜色"),
        )

        self.roundedBgColorCard = ColorSettingCard(
            QColor(25, 25, 25, 200),
            FIF.PALETTE,  # type: ignore
            self.tr("背景颜色"),
            self.tr("设置圆角矩形背景颜色"),
            enableAlpha=True,
        )

        self.roundedCornerRadiusCard = SpinBoxSettingCard(
            FIF.ZOOM,  # type: ignore
            self.tr("圆角半径"),
            self.tr("设置背景圆角大小"),
            minimum=0,
            maximum=50,
        )

        self.roundedPaddingHCard = SpinBoxSettingCard(
            FIF.ALIGNMENT,  # type: ignore
            self.tr("水平内边距"),
            self.tr("文字与背景边缘的水平距离"),
            minimum=4,
            maximum=100,
        )

        self.roundedPaddingVCard = SpinBoxSettingCard(
            FIF.ALIGNMENT,  # type: ignore
            self.tr("垂直内边距"),
            self.tr("文字与背景边缘的垂直距离"),
            minimum=4,
            maximum=50,
        )

        self.roundedMarginBottomCard = SpinBoxSettingCard(
            FIF.ALIGNMENT,  # type: ignore
            self.tr("底部边距"),
            self.tr("字幕距视频底部的距离"),
            minimum=20,
            maximum=300,
        )

        self.roundedLineSpacingCard = SpinBoxSettingCard(
            FIF.ALIGNMENT,  # type: ignore
            self.tr("行间距"),
            self.tr("双语字幕的行间距"),
            minimum=0,
            maximum=50,
        )

        self.roundedLetterSpacingCard = SpinBoxSettingCard(
            FIF.FONT,  # type: ignore
            self.tr("字符间距"),
            self.tr("每个字符之间的额外间距"),
            minimum=0,
            maximum=20,
            step=1,
        )

        # 预览设置
        self.previewTextCard = ComboBoxSettingCard(
            FIF.MESSAGE,  # type: ignore
            self.tr("预览文字"),
            self.tr("设置预览显示的文字内容"),
            texts=list(PREVIEW_TEXTS.keys()),
            parent=self.previewGroup,
        )

        self.orientationCard = ComboBoxSettingCard(
            FIF.LAYOUT,  # type: ignore
            self.tr("预览方向"),
            self.tr("设置预览图片的显示方向"),
            texts=list(PREVIEW_ORIENTATIONS),
            parent=self.previewGroup,
        )

        self.previewImageCard = PushSettingCard(
            self.tr("选择图片"),
            FIF.PHOTO,
            self.tr("预览背景"),
            self.tr("选择预览使用的背景图片"),
            parent=self.previewGroup,
        )

    def _initLayout(self):
        """初始化布局"""
        # 通用设置
        self.layoutGroup.addSettingCard(self.renderModeCard)
        self.layoutGroup.addSettingCard(self.layoutCard)
        self.layoutGroup.addSettingCard(self.assVerticalSpacingCard)

        # ASS 样式卡片
        self.assPrimaryGroup.addSettingCard(self.assPrimaryFontCard)
        self.assPrimaryGroup.addSettingCard(self.assPrimarySizeCard)
        self.assPrimaryGroup.addSettingCard(self.assPrimarySpacingCard)
        self.assPrimaryGroup.addSettingCard(self.assPrimaryColorCard)
        self.assPrimaryGroup.addSettingCard(self.assPrimaryOutlineColorCard)
        self.assPrimaryGroup.addSettingCard(self.assPrimaryOutlineSizeCard)

        self.assSecondaryGroup.addSettingCard(self.assSecondaryFontCard)
        self.assSecondaryGroup.addSettingCard(self.assSecondarySizeCard)
        self.assSecondaryGroup.addSettingCard(self.assSecondarySpacingCard)
        self.assSecondaryGroup.addSettingCard(self.assSecondaryColorCard)
        self.assSecondaryGroup.addSettingCard(self.assSecondaryOutlineColorCard)
        self.assSecondaryGroup.addSettingCard(self.assSecondaryOutlineSizeCard)

        # 圆角背景卡片
        self.roundedBgGroup.addSettingCard(self.roundedFontCard)
        self.roundedBgGroup.addSettingCard(self.roundedFontSizeCard)
        self.roundedBgGroup.addSettingCard(self.roundedTextColorCard)
        self.roundedBgGroup.addSettingCard(self.roundedBgColorCard)
        self.roundedBgGroup.addSettingCard(self.roundedCornerRadiusCard)
        self.roundedBgGroup.addSettingCard(self.roundedPaddingHCard)
        self.roundedBgGroup.addSettingCard(self.roundedPaddingVCard)
        self.roundedBgGroup.addSettingCard(self.roundedMarginBottomCard)
        self.roundedBgGroup.addSettingCard(self.roundedLineSpacingCard)
        self.roundedBgGroup.addSettingCard(self.roundedLetterSpacingCard)

        # 预览设置
        self.previewGroup.addSettingCard(self.previewTextCard)
        self.previewGroup.addSettingCard(self.orientationCard)
        self.previewGroup.addSettingCard(self.previewImageCard)

        # 添加组到布局
        self.settingsLayout.addWidget(self.layoutGroup)
        self.settingsLayout.addWidget(self.assPrimaryGroup)
        self.settingsLayout.addWidget(self.assSecondaryGroup)
        self.settingsLayout.addWidget(self.roundedBgGroup)
        self.settingsLayout.addWidget(self.previewGroup)
        self.settingsLayout.addStretch(1)

        # 添加左右两侧到主布局
        self.hBoxLayout.addWidget(self.settingsScrollArea)
        self.hBoxLayout.addWidget(self.previewCard)

    def _initStyle(self):
        """初始化样式"""
        self.settingsWidget.setObjectName("settingsWidget")
        self.setStyleSheet(
            """
            SubtitleStyleInterface, #settingsWidget {
                background-color: transparent;
            }
            QScrollArea {
                border: none;
                background-color: transparent;
            }
        """
        )

    def __setValues(self):
        """Seed the widgets from cfg, then load the persisted style."""
        self.renderModeCard.comboBox.setCurrentText(
            self._display_for_render_mode(cfg.subtitle_render_mode.value)
        )
        self.layoutCard.comboBox.setCurrentText(
            self._display_for_layout(cfg.subtitle_layout.value)
        )
        self.styleNameComboBox.comboBox.setCurrentText(cfg.get(cfg.subtitle_style_name))

        # Bundled fonts first; system families only when Pillow can open them,
        # otherwise the rounded renderer would silently fall back to a default.
        builtin_font_names = [font["name"] for font in get_builtin_fonts()]
        all_fonts = font_choices(
            builtin_font_names, QFontDatabase().families(), pil_can_load_font
        )
        for card in (self.assPrimaryFontCard, self.assSecondaryFontCard, self.roundedFontCard):
            card.addItems(all_fonts)
            card.comboBox.setMaxVisibleItems(12)

        self.roundedFontSizeCard.spinBox.setValue(cfg.get(cfg.rounded_bg_font_size))
        self.roundedCornerRadiusCard.spinBox.setValue(cfg.get(cfg.rounded_bg_corner_radius))
        self.roundedPaddingHCard.spinBox.setValue(cfg.get(cfg.rounded_bg_padding_h))
        self.roundedPaddingVCard.spinBox.setValue(cfg.get(cfg.rounded_bg_padding_v))
        self.roundedMarginBottomCard.spinBox.setValue(cfg.get(cfg.rounded_bg_margin_bottom))
        self.roundedLineSpacingCard.spinBox.setValue(cfg.get(cfg.rounded_bg_line_spacing))
        self.roundedLetterSpacingCard.spinBox.setValue(cfg.get(cfg.rounded_bg_letter_spacing))
        self.roundedTextColorCard.setColor(QColor(cfg.get(cfg.rounded_bg_text_color)))
        self.roundedBgColorCard.setColor(QColor(*parse_rgba_hex(cfg.get(cfg.rounded_bg_color))))

        self._refreshStyleList()
        self._updateVisibleGroups()

    def connectSignals(self):
        """连接所有设置变更的信号到预览更新函数"""
        # 渲染模式切换
        self.renderModeCard.currentTextChanged.connect(self.onRenderModeChanged)

        # 字幕排布（通用设置）
        self.layoutCard.currentTextChanged.connect(self.updatePreview)
        self.layoutCard.currentTextChanged.connect(
            lambda: cfg.set(
                cfg.subtitle_layout,
                self._getCurrentLayout(),
            )
        )
        # ASS 模式 - 垂直间距
        self.assVerticalSpacingCard.spinBox.valueChanged.connect(
            self.onAssSettingChanged
        )

        # ASS 模式 - 主字幕样式
        self.assPrimaryFontCard.currentTextChanged.connect(self.onAssSettingChanged)
        self.assPrimarySizeCard.spinBox.valueChanged.connect(self.onAssSettingChanged)
        self.assPrimarySpacingCard.spinBox.valueChanged.connect(
            self.onAssSettingChanged
        )
        self.assPrimaryColorCard.colorChanged.connect(self.onAssSettingChanged)
        self.assPrimaryOutlineColorCard.colorChanged.connect(self.onAssSettingChanged)
        self.assPrimaryOutlineSizeCard.spinBox.valueChanged.connect(
            self.onAssSettingChanged
        )

        # ASS 模式 - 副字幕样式
        self.assSecondaryFontCard.currentTextChanged.connect(self.onAssSettingChanged)
        self.assSecondarySizeCard.spinBox.valueChanged.connect(self.onAssSettingChanged)
        self.assSecondarySpacingCard.spinBox.valueChanged.connect(
            self.onAssSettingChanged
        )
        self.assSecondaryColorCard.colorChanged.connect(self.onAssSettingChanged)
        self.assSecondaryOutlineColorCard.colorChanged.connect(self.onAssSettingChanged)
        self.assSecondaryOutlineSizeCard.spinBox.valueChanged.connect(
            self.onAssSettingChanged
        )

        # 圆角背景样式信号
        self.roundedFontCard.currentTextChanged.connect(self.onRoundedBgSettingChanged)
        self.roundedFontSizeCard.spinBox.valueChanged.connect(
            self.onRoundedBgSettingChanged
        )
        self.roundedTextColorCard.colorChanged.connect(self.onRoundedBgSettingChanged)
        self.roundedBgColorCard.colorChanged.connect(self.onRoundedBgSettingChanged)
        self.roundedCornerRadiusCard.spinBox.valueChanged.connect(
            self.onRoundedBgSettingChanged
        )
        self.roundedPaddingHCard.spinBox.valueChanged.connect(
            self.onRoundedBgSettingChanged
        )
        self.roundedPaddingVCard.spinBox.valueChanged.connect(
            self.onRoundedBgSettingChanged
        )
        self.roundedMarginBottomCard.spinBox.valueChanged.connect(
            self.onRoundedBgSettingChanged
        )
        self.roundedLineSpacingCard.spinBox.valueChanged.connect(
            self.onRoundedBgSettingChanged
        )
        self.roundedLetterSpacingCard.spinBox.valueChanged.connect(
            self.onRoundedBgSettingChanged
        )

        # 预览设置（通用设置）
        self.previewTextCard.currentTextChanged.connect(self.updatePreview)
        self.orientationCard.currentTextChanged.connect(self.onOrientationChanged)
        self.previewImageCard.clicked.connect(self.selectPreviewImage)

        # 连接样式切换信号
        self.styleNameComboBox.currentTextChanged.connect(self.loadStyle)
        self.newStyleButton.clicked.connect(self.createNewStyle)
        self.openStyleFolderButton.clicked.connect(self.on_open_style_folder_clicked)

        # 连接字幕排布信号
        self.layoutCard.comboBox.currentTextChanged.connect(
            signalBus.subtitle_layout_changed
        )
        signalBus.subtitle_layout_changed.connect(self.on_subtitle_layout_changed)

        # 连接渲染模式信号（从视频合成界面同步）
        signalBus.subtitle_render_mode_changed.connect(self.on_render_mode_changed_external)

    def on_open_style_folder_clicked(self):
        open_folder(str(SUBTITLE_STYLE_PATH))

    def on_subtitle_layout_changed(self, layout: str):
        layout_enum = self._layout_from_text(layout)
        cfg.subtitle_layout.value = layout_enum
        self.layoutCard.setCurrentText(self._display_for_layout(layout_enum))

    def on_render_mode_changed_external(self, mode_text: str):
        """Mirror a render-mode change made on the synthesis page."""
        mode = self._render_mode_from_text(mode_text)
        # Block the combo signal so this does not bounce back through onRenderModeChanged.
        self.renderModeCard.comboBox.blockSignals(True)
        self.renderModeCard.comboBox.setCurrentText(self._display_for_render_mode(mode))
        self.renderModeCard.comboBox.blockSignals(False)
        self._updateVisibleGroups()
        self._refreshStyleList()
        self.updatePreview()

    def onRenderModeChanged(self):
        """Render mode changed on this page: persist, broadcast, reload styles."""
        mode = self._getCurrentRenderMode()
        cfg.set(cfg.subtitle_render_mode, mode)
        # Disconnect our own listener so the broadcast does not re-run this handler.
        signalBus.subtitle_render_mode_changed.disconnect(self.on_render_mode_changed_external)
        signalBus.subtitle_render_mode_changed.emit(mode.value)
        signalBus.subtitle_render_mode_changed.connect(self.on_render_mode_changed_external)
        self._updateVisibleGroups()
        self._refreshStyleList()
        self.updatePreview()

    def onRoundedBgSettingChanged(self):
        """Persist rounded settings to cfg and the current style file, then re-render."""
        if self._loading_style:
            return
        style = self._rounded_style()
        cfg.set(cfg.rounded_bg_font_name, style.font_name)
        cfg.set(cfg.rounded_bg_font_size, style.font_size)
        cfg.set(cfg.rounded_bg_corner_radius, style.corner_radius)
        cfg.set(cfg.rounded_bg_padding_h, style.padding_h)
        cfg.set(cfg.rounded_bg_padding_v, style.padding_v)
        cfg.set(cfg.rounded_bg_margin_bottom, style.margin_bottom_rounded)
        cfg.set(cfg.rounded_bg_line_spacing, style.line_spacing)
        cfg.set(cfg.rounded_bg_letter_spacing, style.letter_spacing)
        cfg.set(cfg.rounded_bg_text_color, style.text_color)
        cfg.set(cfg.rounded_bg_color, style.bg_color)

        current_style = self.styleNameComboBox.comboBox.currentText()
        if current_style:
            self.saveStyle(current_style)
        self.updatePreview()

    def _updateVisibleGroups(self):
        """Only the groups of the active render mode stay visible."""
        is_ass_mode = self._getCurrentRenderMode() == SubtitleRenderModeEnum.ASS_STYLE
        self.assVerticalSpacingCard.setVisible(is_ass_mode)
        self.assPrimaryGroup.setVisible(is_ass_mode)
        self.assSecondaryGroup.setVisible(is_ass_mode)
        self.roundedBgGroup.setVisible(not is_ass_mode)

    def _refreshStyleList(self):
        """Repopulate the style combo for the current render mode and load one entry."""
        # Block signals: addItems/setCurrentText would otherwise call loadStyle repeatedly.
        self.styleNameComboBox.comboBox.blockSignals(True)
        self.styleNameComboBox.comboBox.clear()
        style_ids = list_style_ids(SUBTITLE_STYLE_PATH, self._current_style_mode())
        if DEFAULT_STYLE_ID not in style_ids:
            # First run for this mode: persist the widget defaults as "default".
            self.saveStyle(DEFAULT_STYLE_ID)
            style_ids.insert(0, DEFAULT_STYLE_ID)
        self.styleNameComboBox.comboBox.addItems(style_ids)
        style_id = choose_style_id(style_ids, cfg.get(cfg.subtitle_style_name))
        self.styleNameComboBox.comboBox.setCurrentText(style_id)
        self.styleNameComboBox.comboBox.blockSignals(False)
        self.loadStyle(style_id)

    def _getCurrentRenderMode(self) -> SubtitleRenderModeEnum:
        return self._render_mode_from_text(self.renderModeCard.comboBox.currentText())

    def _current_style_mode(self) -> StyleMode:
        return style_mode_for(self._getCurrentRenderMode())

    def _getCurrentLayout(self) -> SubtitleLayoutEnum:
        return self._layout_from_text(self.layoutCard.comboBox.currentText())

    def _display_for_render_mode(self, mode: SubtitleRenderModeEnum) -> str:
        return self.tr(mode.value)

    def _display_for_layout(self, layout: SubtitleLayoutEnum) -> str:
        return self.tr(layout.value)

    def _render_mode_from_text(self, text: str) -> SubtitleRenderModeEnum:
        return self._render_mode_display_to_enum.get(text) or SubtitleRenderModeEnum(text)

    def _layout_from_text(self, text: str) -> SubtitleLayoutEnum:
        return self._layout_display_to_enum.get(text) or SubtitleLayoutEnum(text)

    def onOrientationChanged(self):
        """Switching orientation resets the background to the bundled image."""
        preview = default_background(ASSETS_PATH, self.orientationCard.comboBox.currentText())
        cfg.set(cfg.subtitle_preview_image, str(preview))
        self.updatePreview()

    def onAssSettingChanged(self):
        if self._loading_style:
            return
        self.updatePreview()
        self.saveStyle(self.styleNameComboBox.comboBox.currentText() or DEFAULT_STYLE_ID)

    def selectPreviewImage(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            self.tr("选择背景图片"),
            "",
            self.tr("图片文件") + " (*.png *.jpg *.jpeg)",
        )
        if file_path:
            cfg.set(cfg.subtitle_preview_image, file_path)
            self.updatePreview()

    # ------------------------------------------------------------ widget <-> style

    def _ass_style(self, style_id: str = "") -> SubtitleStyle:
        """Snapshot the ASS widgets (720p reference; renderers scale)."""
        return SubtitleStyle(
            name=style_id,
            mode=StyleMode.ASS,
            font_name=self.assPrimaryFontCard.comboBox.currentText(),
            font_size=self.assPrimarySizeCard.spinBox.value(),
            primary_color=self.assPrimaryColorCard.colorPicker.color.name(),
            outline_color=self.assPrimaryOutlineColorCard.colorPicker.color.name(),
            outline_width=self.assPrimaryOutlineSizeCard.spinBox.value(),
            bold=True,
            spacing=self.assPrimarySpacingCard.spinBox.value(),
            margin_bottom=self.assVerticalSpacingCard.spinBox.value(),
            secondary=SecondaryStyle(
                font_name=self.assSecondaryFontCard.comboBox.currentText(),
                font_size=self.assSecondarySizeCard.spinBox.value(),
                color=self.assSecondaryColorCard.colorPicker.color.name(),
                outline_color=self.assSecondaryOutlineColorCard.colorPicker.color.name(),
                outline_width=self.assSecondaryOutlineSizeCard.spinBox.value(),
                spacing=self.assSecondarySpacingCard.spinBox.value(),
            ),
        )

    def _rounded_style(self, style_id: str = "") -> SubtitleStyle:
        """Snapshot the rounded-background widgets."""
        bg_color = self.roundedBgColorCard.colorPicker.color
        return SubtitleStyle(
            name=style_id,
            mode=StyleMode.ROUNDED,
            font_name=self.roundedFontCard.comboBox.currentText(),
            font_size=self.roundedFontSizeCard.spinBox.value(),
            text_color=self.roundedTextColorCard.colorPicker.color.name(),
            bg_color=format_rgba_hex(
                bg_color.red(), bg_color.green(), bg_color.blue(), bg_color.alpha()
            ),
            corner_radius=self.roundedCornerRadiusCard.spinBox.value(),
            padding_h=self.roundedPaddingHCard.spinBox.value(),
            padding_v=self.roundedPaddingVCard.spinBox.value(),
            margin_bottom_rounded=self.roundedMarginBottomCard.spinBox.value(),
            line_spacing=self.roundedLineSpacingCard.spinBox.value(),
            letter_spacing=self.roundedLetterSpacingCard.spinBox.value(),
        )

    def _current_style(self, style_id: str = "") -> SubtitleStyle:
        """Snapshot the widgets of the active render mode."""
        if self._current_style_mode() is StyleMode.ROUNDED:
            return self._rounded_style(style_id)
        return self._ass_style(style_id)

    def _apply_style(self, style: SubtitleStyle) -> None:
        """Push a loaded style into the widgets of the active render mode."""
        if self._current_style_mode() is StyleMode.ROUNDED:
            self._apply_rounded_style(style)
        else:
            self._apply_ass_style(style)

    def _apply_ass_style(self, style: SubtitleStyle) -> None:
        self.assPrimaryFontCard.setCurrentText(style.font_name)
        self.assPrimarySizeCard.spinBox.setValue(style.font_size)
        self.assVerticalSpacingCard.spinBox.setValue(style.margin_bottom)
        self.assPrimaryColorCard.setColor(QColor(style.primary_color))
        self.assPrimaryOutlineColorCard.setColor(QColor(style.outline_color))
        self.assPrimarySpacingCard.spinBox.setValue(style.spacing)
        self.assPrimaryOutlineSizeCard.spinBox.setValue(style.outline_width)

        secondary = style.secondary
        if secondary:
            self.assSecondaryFontCard.setCurrentText(secondary.font_name)
            self.assSecondarySizeCard.spinBox.setValue(secondary.font_size)
            self.assSecondaryColorCard.setColor(QColor(secondary.color))
            self.assSecondaryOutlineColorCard.setColor(QColor(secondary.outline_color))
            self.assSecondarySpacingCard.spinBox.setValue(secondary.spacing)
            self.assSecondaryOutlineSizeCard.spinBox.setValue(secondary.outline_width)

    def _apply_rounded_style(self, style: SubtitleStyle) -> None:
        self.roundedFontCard.setCurrentText(style.font_name)
        self.roundedFontSizeCard.spinBox.setValue(style.font_size)
        self.roundedTextColorCard.setColor(QColor(style.text_color))
        self.roundedBgColorCard.setColor(QColor(*parse_rgba_hex(style.bg_color)))
        self.roundedCornerRadiusCard.spinBox.setValue(style.corner_radius)
        self.roundedPaddingHCard.spinBox.setValue(style.padding_h)
        self.roundedPaddingVCard.spinBox.setValue(style.padding_v)
        self.roundedMarginBottomCard.spinBox.setValue(style.margin_bottom_rounded)
        self.roundedLineSpacingCard.spinBox.setValue(style.line_spacing)
        self.roundedLetterSpacingCard.spinBox.setValue(style.letter_spacing)

    # ------------------------------------------------------------------ preview

    def updatePreview(self):
        """Render the preview for the current widgets on a worker thread."""
        original, translation = PREVIEW_TEXTS[self.previewTextCard.comboBox.currentText()]
        preview_text = preview_text_pair(original, translation, self._getCurrentLayout())
        background = preview_background(
            cfg.get(cfg.subtitle_preview_image),
            default_background(ASSETS_PATH, self.orientationCard.comboBox.currentText()),
        )
        self.preview_thread = StylePreviewThread(
            self._current_style(), preview_text, str(background)
        )
        self.preview_thread.previewReady.connect(self.onPreviewReady)
        self.preview_thread.start()

    def onPreviewReady(self, preview_path):
        self.previewImage.setImage(preview_path)
        self.updatePreviewImage()

    def updatePreviewImage(self):
        """Fit the rendered image into the preview card, keeping its aspect."""
        height = int(self.previewTopWidget.height() * 0.98)
        width = int(self.previewTopWidget.width() * 0.98)
        self.previewImage.scaledToWidth(width)
        if self.previewImage.height() > height:
            self.previewImage.scaledToHeight(height)
        self.previewImage.setBorderRadius(8, 8, 8, 8)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.updatePreviewImage()

    def showEvent(self, event):
        super().showEvent(event)
        self.updatePreviewImage()

    # -------------------------------------------------------------- style files

    def loadStyle(self, style_name):
        """Load a style of the current render mode into the widgets."""
        style_path = resolve_style_path(
            SUBTITLE_STYLE_PATH, self._current_style_mode(), style_name
        )
        if not style_path.exists():
            return

        self._loading_style = True
        try:
            self._apply_style(SubtitleStyle.from_file(style_path))
        finally:
            self._loading_style = False

        cfg.set(cfg.subtitle_style_name, style_name)
        self.updatePreview()

        InfoBar.success(
            title=self.tr("成功"),
            content=self.tr("已加载样式 ") + style_name,
            orient=Qt.Horizontal,  # type: ignore
            isClosable=True,
            position=InfoBarPosition.TOP,
            duration=INFOBAR_DURATION_SUCCESS,
            parent=self,
        )

    def createNewStyle(self):
        dialog = StyleNameDialog(self)
        if not dialog.exec():
            return
        style_name = dialog.nameLineEdit.text().strip()
        if not style_name:
            return

        if resolve_style_path(SUBTITLE_STYLE_PATH, self._current_style_mode(), style_name).exists():
            InfoBar.warning(
                title=self.tr("警告"),
                content=self.tr("样式 ") + style_name + self.tr(" 已存在"),
                orient=Qt.Horizontal,  # type: ignore
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=INFOBAR_DURATION_WARNING,
                parent=self,
            )
            return

        self.saveStyle(style_name)
        self.styleNameComboBox.addItem(style_name)
        self.styleNameComboBox.comboBox.setCurrentText(style_name)

        InfoBar.success(
            title=self.tr("成功"),
            content=self.tr("已创建新样式 ") + style_name,
            orient=Qt.Horizontal,  # type: ignore
            isClosable=True,
            position=InfoBarPosition.TOP,
            duration=INFOBAR_DURATION_SUCCESS,
            parent=self,
        )

    def saveStyle(self, style_name):
        """Write the current widgets as ``<mode>-<name>.json``."""
        save_style(SUBTITLE_STYLE_PATH, self._current_style(style_name))

    def dragEnterEvent(self, event):
        """Accept drags that carry at least one preview image."""
        urls = event.mimeData().urls() if event.mimeData().hasUrls() else []
        if first_image_path(url.toLocalFile() for url in urls):
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        """Use the first dropped image as the preview background."""
        file_path = first_image_path(url.toLocalFile() for url in event.mimeData().urls())
        if not file_path:
            return
        cfg.set(cfg.subtitle_preview_image, file_path)
        self.updatePreview()
        InfoBar.success(
            title=self.tr("成功"),
            content=self.tr("已设置预览背景：") + Path(file_path).name,
            orient=Qt.Horizontal,  # type: ignore
            isClosable=True,
            position=InfoBarPosition.TOP,
            duration=INFOBAR_DURATION_SUCCESS,
            parent=self,
        )


class StyleNameDialog(MessageBoxBase):
    """样式名称输入对话框"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.titleLabel = BodyLabel(self.tr("新建样式"), self)
        self.nameLineEdit = LineEdit(self)

        self.nameLineEdit.setPlaceholderText(self.tr("输入样式名称"))
        self.nameLineEdit.setClearButtonEnabled(True)

        # 添加控件到布局
        self.viewLayout.addWidget(self.titleLabel)
        self.viewLayout.addWidget(self.nameLineEdit)

        # 设置按钮文本
        self.yesButton.setText(self.tr("确定"))
        self.cancelButton.setText(self.tr("取消"))

        self.widget.setMinimumWidth(350)
        self.yesButton.setDisabled(True)
        self.nameLineEdit.textChanged.connect(self._validateInput)

    def _validateInput(self, text):
        self.yesButton.setEnabled(bool(text.strip()))

from PyQt5.QtWidgets import (
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from videocaptioner.core.entities import (
    TranscribeModelEnum,
)
from videocaptioner.core.utils.platform_utils import is_macos


class TranscriptionSettingCard(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()

    def setup_ui(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)

        # 设置界面堆叠
        self.stacked_widget = QStackedWidget(self)

        # Provider setting widgets import network/model download stacks. Keep
        # them out of application startup and create only the selected page.
        self.empty_widget = QWidget(self)
        self.stacked_widget.addWidget(self.empty_widget)
        self._widgets: dict[str, QWidget] = {}
        self._pending_model = ""

        self.main_layout.addWidget(self.stacked_widget)

    def on_model_changed(self, value: str, *, load: bool = True) -> None:
        self._pending_model = value
        if not load:
            self.stacked_widget.setCurrentWidget(self.empty_widget)
            return
        widget = self._ensure_widget(value)
        self.stacked_widget.setCurrentWidget(widget or self.empty_widget)

    def activate_current_model(self) -> None:
        self.on_model_changed(self._pending_model, load=True)

    def _ensure_widget(self, value: str) -> QWidget | None:
        if value in self._widgets:
            return self._widgets[value]

        widget: QWidget | None = None
        if value == TranscribeModelEnum.WHISPER_CPP.value:
            from .WhisperCppSettingWidget import WhisperCppSettingWidget

            widget = WhisperCppSettingWidget(self)
        elif value == TranscribeModelEnum.WHISPER_API.value:
            from .WhisperAPISettingWidget import WhisperAPISettingWidget

            widget = WhisperAPISettingWidget(self)
        elif value in (TranscribeModelEnum.SONIOX.value, TranscribeModelEnum.SCRIBE.value):
            from .NativeASRSettingWidget import NativeASRSettingWidget

            widget = NativeASRSettingWidget("soniox" if value == TranscribeModelEnum.SONIOX.value else "scribe", self)
        elif value == TranscribeModelEnum.FASTER_WHISPER.value and not is_macos():
            from .FasterWhisperSettingWidget import FasterWhisperSettingWidget

            widget = FasterWhisperSettingWidget(self)

        if widget is not None:
            self._widgets[value] = widget
            self.stacked_widget.addWidget(widget)
        return widget

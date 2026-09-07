from typing import Optional

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QSizePolicy, QStackedWidget, QVBoxLayout, QWidget
from qfluentwidgets import SegmentedWidget

from videocaptioner.core.llm.context import generate_task_id


class HomeInterface(QWidget):
    openInVideoEditorRequested = pyqtSignal(str, str)
    dubbingInterfaceReady = pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_task_id: Optional[str] = None
        self.setObjectName("HomeInterface")
        self.setStyleSheet("HomeInterface{background: white}")

        self.pivot = SegmentedWidget(self)
        self.pivot.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.stackedWidget = QStackedWidget(self)
        self.vBoxLayout = QVBoxLayout(self)

        self._interfaces: dict[str, QWidget] = {}
        self._placeholders: dict[str, QWidget] = {}
        page_titles = {
            "TaskCreationInterface": self.tr("任务创建"),
            "TranscriptionInterface": self.tr("语音转录"),
            "SubtitleInterface": self.tr("字幕优化与翻译"),
            "DubbingInterface": self.tr("Lồng tiếng"),
            "VideoSynthesisInterface": self.tr("字幕视频合成"),
        }
        for route_key, title in page_titles.items():
            self._add_lazy_sub_interface(route_key, title)

        self.vBoxLayout.addWidget(self.pivot)
        self.vBoxLayout.addWidget(self.stackedWidget)
        self.vBoxLayout.setContentsMargins(30, 10, 30, 30)

        self.stackedWidget.currentChanged.connect(self.onCurrentIndexChanged)
        self.stackedWidget.setCurrentWidget(self.task_creation_interface)
        self.pivot.setCurrentItem("TaskCreationInterface")

    @property
    def task_creation_interface(self):
        return self._ensure_interface("TaskCreationInterface")

    @property
    def transcription_interface(self):
        return self._ensure_interface("TranscriptionInterface")

    @property
    def subtitle_optimization_interface(self):
        return self._ensure_interface("SubtitleInterface")

    @property
    def dubbing_interface(self):
        return self._ensure_interface("DubbingInterface")

    @property
    def video_synthesis_interface(self):
        return self._ensure_interface("VideoSynthesisInterface")

    def _ensure_interface(self, route_key: str) -> QWidget:
        existing = self._interfaces.get(route_key)
        if existing is not None:
            return existing

        if route_key == "TaskCreationInterface":
            from videocaptioner.ui.view.task_creation_interface import TaskCreationInterface

            interface = TaskCreationInterface(self)
            interface.finished.connect(self.switch_to_transcription)
        elif route_key == "TranscriptionInterface":
            from videocaptioner.ui.view.transcription_interface import TranscriptionInterface

            interface = TranscriptionInterface(self)
            interface.finished.connect(self.switch_to_subtitle_optimization)
            interface.recognized.connect(lambda task: self.switch_to_subtitle_optimization(
                task.output_path, task.file_path, task.asr_data))
        elif route_key == "SubtitleInterface":
            from videocaptioner.ui.view.subtitle_interface import SubtitleInterface

            interface = SubtitleInterface(self)
            interface.finished.connect(self.switch_to_dubbing)
            interface.openInVideoEditorRequested.connect(
                self.openInVideoEditorRequested.emit
            )
        elif route_key == "DubbingInterface":
            from videocaptioner.ui.view.dubbing_interface import DubbingInterface

            interface = DubbingInterface(self)
            interface.finished.connect(self.switch_to_video_synthesis)
            interface.openInVideoEditorRequested.connect(
                self.openInVideoEditorRequested.emit
            )
            self.dubbingInterfaceReady.emit(interface)
        else:
            from videocaptioner.ui.view.video_synthesis_interface import (
                VideoSynthesisInterface,
            )

            interface = VideoSynthesisInterface(self)

        interface.setObjectName(route_key)
        placeholder = self._placeholders[route_key]
        index = self.stackedWidget.indexOf(placeholder)
        self.stackedWidget.removeWidget(placeholder)
        placeholder.deleteLater()
        self.stackedWidget.insertWidget(index, interface)
        self._interfaces[route_key] = interface
        return interface

    def _activate_interface(self, route_key: str) -> None:
        interface = self._ensure_interface(route_key)
        self.stackedWidget.setCurrentWidget(interface)
        self.pivot.setCurrentItem(route_key)

    def switch_to_transcription(self, file_path):
        from videocaptioner.ui.task_factory import TaskFactory

        self._current_task_id = generate_task_id()
        transcribe_task = TaskFactory.create_transcribe_task(
            file_path, need_next_task=True, task_id=self._current_task_id
        )
        interface = self.transcription_interface
        interface.set_task(transcribe_task)
        interface.process()
        self.stackedWidget.setCurrentWidget(interface)
        self.pivot.setCurrentItem("TranscriptionInterface")

    def switch_to_subtitle_optimization(self, file_path, video_path, asr_data=None):
        from videocaptioner.ui.task_factory import TaskFactory

        subtitle_task = TaskFactory.create_subtitle_task(
            file_path, video_path, need_next_task=True, task_id=self._current_task_id
        )
        interface = self.subtitle_optimization_interface
        subtitle_task.asr_data = asr_data
        interface.set_task(subtitle_task)
        interface.process()
        self.stackedWidget.setCurrentWidget(interface)
        self.pivot.setCurrentItem("SubtitleInterface")

    def switch_to_dubbing(self, video_path, subtitle_path):
        from videocaptioner.ui.task_factory import TaskFactory

        subtitle_interface = self.subtitle_optimization_interface
        dubbing_task = TaskFactory.create_dubbing_task(
            video_path,
            subtitle_path,
            display_subtitle_path=(
                subtitle_interface.task.output_path
                if subtitle_interface.task
                else subtitle_path
            ),
            task_id=self._current_task_id,
        )
        interface = self.dubbing_interface
        interface.set_task(dubbing_task)
        interface.process()
        self.stackedWidget.setCurrentWidget(interface)
        self.pivot.setCurrentItem("DubbingInterface")

    def switch_to_video_synthesis(self, video_path, subtitle_path):
        from videocaptioner.ui.task_factory import TaskFactory

        synthesis_task = TaskFactory.create_synthesis_task(
            video_path, subtitle_path, need_next_task=True, task_id=self._current_task_id
        )
        self._current_task_id = None
        interface = self.video_synthesis_interface
        interface.set_task(synthesis_task)
        interface.process()
        self.stackedWidget.setCurrentWidget(interface)
        self.pivot.setCurrentItem("VideoSynthesisInterface")

    def _add_lazy_sub_interface(self, route_key: str, text: str) -> None:
        placeholder = QWidget(self)
        placeholder.setObjectName(route_key)
        self._placeholders[route_key] = placeholder
        self.stackedWidget.addWidget(placeholder)
        self.pivot.addItem(
            routeKey=route_key,
            text=text,
            onClick=lambda _checked=False, key=route_key: self._activate_interface(key),
        )

    def onCurrentIndexChanged(self, index):
        widget = self.stackedWidget.widget(index)
        if widget:
            self.pivot.setCurrentItem(widget.objectName())

    def closeEvent(self, event):
        for interface in self._interfaces.values():
            interface.close()
        super().closeEvent(event)

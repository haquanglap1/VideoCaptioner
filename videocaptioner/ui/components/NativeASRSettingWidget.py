"""Shared native cloud cards for Settings and the transcription popover."""

from PyQt5.QtWidgets import QApplication, QLineEdit, QVBoxLayout, QWidget
from qfluentwidgets import FluentIcon as FIF
from qfluentwidgets import PushSettingCard, SettingCardGroup, SwitchSettingCard

from videocaptioner.core.asr.native_profiles import NATIVE_PROFILES
from videocaptioner.ui.common.config import cfg
from videocaptioner.ui.common.native_asr_settings import native_config
from videocaptioner.ui.thread.native_asr_thread import NativeASRProbeThread

from .LineEditSettingCard import LineEditSettingCard


class NativeASRCards(QWidget):
    def __init__(self, provider: str, group: SettingCardGroup):
        super().__init__(group)
        self.hide()
        self.provider = provider
        self.worker: NativeASRProbeThread | None = None
        profile = NATIVE_PROFILES[provider]
        self.base = LineEditSettingCard(getattr(cfg, f"{provider}_api_base"), FIF.LINK,
                                       self.tr("API Base URL"), profile.label, profile.endpoint, group)
        self.key = LineEditSettingCard(getattr(cfg, f"{provider}_api_key"), FIF.FINGERPRINT,
                                      self.tr("API Key"), profile.label, "", group)
        self.key.lineEdit.setEchoMode(QLineEdit.Password)
        self.diarize = SwitchSettingCard(FIF.PEOPLE, self.tr("Anonymous speaker labels"),
                                        self.tr("Labels belong to one request; unknown speakers remain unknown."),
                                        configItem=getattr(cfg, f"{provider}_diarize"), parent=group)
        self.probe = PushSettingCard(self.tr("Check service"), FIF.CONNECT, profile.model,
                                    self.tr("No audio upload. Cancel stops local waiting; remote recognition may continue and incur charges."), group)
        self.cards = [self.base, self.key, self.diarize, self.probe]
        for card in (self.diarize, self.probe):
            card.contentLabel.setWordWrap(True)
            # SettingCard's centered layout does not grow a wrapped QLabel automatically.
            card.contentLabel.setMinimumHeight(54)
            card.setFixedHeight(110)
        self.probe.clicked.connect(self.start_probe)
        group.destroyed.connect(self.shutdown)
        app = QApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self.shutdown)

    def start_probe(self):
        if self.worker is not None:
            self.worker.requestInterruption()
            return
        config = native_config(cfg, self.provider)
        if config is None:
            return
        worker = NativeASRProbeThread(config, QApplication.instance())
        self.worker = worker
        self.probe.button.setText(self.tr("Cancel"))
        worker.result.connect(self.probe.setContent)
        worker.finished.connect(self._finished)
        worker.start()

    def _finished(self):
        worker = self.sender()
        if isinstance(worker, NativeASRProbeThread):
            worker.wait()
            if self.worker is worker:
                self.worker = None
                self.probe.button.setText(self.tr("Check service"))
            worker.deleteLater()

    def shutdown(self):
        if self.worker is not None:
            self.worker.requestInterruption()
            self.worker.wait()


class NativeASRSettingWidget(QWidget):
    def __init__(self, provider: str, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        group = SettingCardGroup(NATIVE_PROFILES[provider].label, self)
        self.controls = NativeASRCards(provider, group)
        for card in self.controls.cards:
            group.addSettingCard(card)
        layout.addWidget(group)

    def closeEvent(self, event):
        self.controls.shutdown()
        super().closeEvent(event)

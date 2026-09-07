"""Shared provider/profile controls for both Whisper settings surfaces."""

from PyQt5.QtCore import QCoreApplication, QObject
from qfluentwidgets import ComboBoxSettingCard, PushSettingCard
from qfluentwidgets import FluentIcon as FIF

from videocaptioner.core.asr.api_profiles import PROVIDER_PRESETS, ASRAPIError, resolve_profile
from videocaptioner.ui.common.config import cfg
from videocaptioner.ui.thread.alignment_thread import AlignmentThread


class WhisperProfileCards(QObject):
    def __init__(self, parent):
        super().__init__(parent)
        self.provider = ComboBoxSettingCard(
            cfg.whisper_api_provider, FIF.GLOBE, self.tr("ASR provider"),
            self.tr("Presets keep separate endpoint keys. Chinese (zh) is recommended for Chinese speech."),
            [p.label for p in PROVIDER_PRESETS.values()], parent,
        )
        self.profile = ComboBoxSettingCard(
            cfg.whisper_api_request_profile, FIF.SETTING, self.tr("Request profile"), "",
            [self.tr("Auto (known models; otherwise Whisper)"),
             self.tr("Whisper timestamps"), self.tr("JSON text (needs alignment)")], parent,
        )
        self.alignment = PushSettingCard(
            self.tr("Check alignment"), FIF.PLAY, self.tr("Chinese alignment runtime"),
            self.tr("Local probe only. Install the separate runtime first; no automatic download."), parent,
        )
        self.worker = None
        parent.destroyed.connect(self.shutdown)
        app = QCoreApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self.shutdown)
        self.alignment.clicked.connect(self.probe_alignment)
        cfg.whisper_api_model.valueChanged.connect(self.update_hint)
        cfg.whisper_api_request_profile.valueChanged.connect(self.update_hint)
        self.update_hint()

    def update_hint(self, *_):
        try:
            profile = resolve_profile(cfg.whisper_api_model.value, cfg.whisper_api_request_profile.value)
            text = (self.tr("Word/segment timestamps requested; actual timing is checked after recognition.")
                    if profile.timestamp_levels else
                    self.tr("Subtitle export requires Chinese (zh) and a ready alignment runtime. Unmatched timing stops for review."))
        except ASRAPIError:
            text = self.tr("Enter a model and choose a compatible request profile. Custom aliases can use Whisper or JSON text.")
        self.profile.setContent(text)

    def probe_alignment(self):
        if self.worker is not None and self.worker.isRunning():
            self.worker.requestInterruption()
            return
        worker = AlignmentThread(self)
        self.worker = worker
        worker.status.connect(lambda message: self.alignment.setContent(message)
                              if self.worker is worker else None)
        worker.finished.connect(lambda: self._probe_finished(worker))
        self.alignment.button.setText(self.tr("Cancel alignment check"))
        worker.start()

    def _probe_finished(self, worker):
        worker.wait()
        if self.worker is worker:
            self.worker = None
            self.alignment.button.setText(self.tr("Check alignment"))
        worker.deleteLater()

    def shutdown(self):
        if self.worker is not None:
            self.worker.requestInterruption()
            self.worker.wait()

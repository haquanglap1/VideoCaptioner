"""Shared provider/profile controls for both Whisper settings surfaces."""

from PyQt5.QtCore import QObject
from qfluentwidgets import ComboBoxSettingCard
from qfluentwidgets import FluentIcon as FIF

from videocaptioner.core.asr.api_profiles import PROVIDER_PRESETS, ASRAPIError, resolve_profile
from videocaptioner.ui.common.config import cfg


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
        cfg.whisper_api_model.valueChanged.connect(self.update_hint)
        cfg.whisper_api_request_profile.valueChanged.connect(self.update_hint)
        self.update_hint()

    def update_hint(self, *_):
        try:
            profile = resolve_profile(cfg.whisper_api_model.value, cfg.whisper_api_request_profile.value)
            text = (self.tr("Word/segment timestamps requested; actual timing is checked after recognition.")
                    if profile.timestamp_levels else
                    self.tr("Recognition test available. Subtitle export needs alignment (S2), not available yet."))
        except ASRAPIError:
            text = self.tr("Enter a model and choose a compatible request profile. Custom aliases can use Whisper or JSON text.")
        self.profile.setContent(text)

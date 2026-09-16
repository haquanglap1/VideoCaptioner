"""OmniVoice adapter for the existing measured dubbing pipeline."""

from dataclasses import replace

from videocaptioner.core.tts.base import BaseTTS

from .runtime import get_omnivoice_service


class OmniVoiceTTS(BaseTTS):
    def __init__(self, config):
        # The orchestration cache includes model/voice identity; avoid the older
        # BaseTTS cache whose key does not include all managed runtime settings.
        super().__init__(replace(config, use_cache=False, response_format="wav", sample_rate=24000))

    def _synthesize(self, segment, output_path):
        segment.audio_duration = get_omnivoice_service().synthesize(segment.text, output_path,
            voice=segment.voice or self.config.voice or "auto", speed=self.config.speed)
        segment.audio_path = output_path

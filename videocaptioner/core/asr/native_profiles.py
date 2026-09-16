"""SDK-free native cloud contracts. These are never Whisper/gateway aliases."""

from dataclasses import dataclass, field

from .api_profiles import ASRAPIError, normalize_endpoint


@dataclass(frozen=True)
class NativeProfile:
    label: str
    endpoint: str
    model: str
    max_duration_ms: int
    max_upload_bytes: int


NATIVE_PROFILES = {
    # Conservative application byte cap; provider/account quotas may be lower.
    "soniox": NativeProfile("Soniox v5", "https://api.soniox.com/v1", "stt-async-v5",
                            5 * 3600_000, 1_000_000_000),
    "scribe": NativeProfile("ElevenLabs Scribe v2", "https://api.elevenlabs.io/v1", "scribe_v2",
                            10 * 3600_000, 3_000_000_000),
}


@dataclass(frozen=True)
class NativeASRConfig:
    provider: str
    api_key: str = field(default="", repr=False)
    api_base: str = ""
    model: str = ""
    diarize: bool = True

    def validated(self) -> "NativeASRConfig":
        profile = NATIVE_PROFILES.get(self.provider)
        if not isinstance(self.diarize, bool):
            raise ASRAPIError("Native diarization must be a boolean.")
        if profile is None:
            raise ASRAPIError("Unknown native ASR provider.")
        endpoint = normalize_endpoint(self.api_base or profile.endpoint)
        if not self.api_key.strip():
            raise ASRAPIError("Set the API key for the selected native ASR provider.")
        if (self.model or profile.model) != profile.model:
            raise ASRAPIError("Select the documented native model for this provider.")
        return NativeASRConfig(self.provider, self.api_key, endpoint, profile.model, self.diarize)

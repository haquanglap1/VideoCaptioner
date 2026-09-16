"""Offline native settings with credentials isolated per provider and endpoint."""

from videocaptioner.core.asr.api_profiles import endpoint_identity
from videocaptioner.core.asr.native_profiles import NativeASRConfig
from videocaptioner.core.entities import TranscribeModelEnum


class NativeASRSettings:
    def __init__(self, config, provider: str):
        self.cfg = config
        self.base_item = getattr(config, f"{provider}_api_base")
        self.key_item = getattr(config, f"{provider}_api_key")
        self.keys_item = getattr(config, f"{provider}_endpoint_keys")
        self.base = self.base_item.value
        self.base_item.valueChanged.connect(self._base_changed)
        self.key_item.valueChanged.connect(self._key_changed)

    def _base_changed(self, base: str) -> None:
        old, new = endpoint_identity(self.base), endpoint_identity(base)
        self.base = base
        if old != new:
            keys = dict(self.keys_item.value)
            keys[old] = self.key_item.value
            self.cfg.set(self.keys_item, keys)
            self.cfg.set(self.key_item, keys.get(new, ""))

    def _key_changed(self, key: str) -> None:
        keys = dict(self.keys_item.value)
        keys[endpoint_identity(self.base)] = key
        self.cfg.set(self.keys_item, keys)


def native_config(config, provider: str | None = None) -> NativeASRConfig | None:
    if provider is None:
        provider = {TranscribeModelEnum.SONIOX: "soniox", TranscribeModelEnum.SCRIBE: "scribe"}.get(
            config.transcribe_model.value)
    if provider is None:
        return None
    return NativeASRConfig(provider, getattr(config, f"{provider}_api_key").value,
                           getattr(config, f"{provider}_api_base").value,
                           getattr(config, f"{provider}_model").value,
                           getattr(config, f"{provider}_diarize").value)

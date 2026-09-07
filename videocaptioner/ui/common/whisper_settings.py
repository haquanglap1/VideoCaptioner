"""Offline preset switching and endpoint-bound keys for the existing Whisper settings."""

from typing import Any

from videocaptioner.core.asr.api_profiles import PROVIDER_PRESETS, endpoint_identity


class WhisperSettings:
    def __init__(self, config: Any):
        self.cfg = config
        self.base = config.whisper_api_base.value
        self.provider = config.whisper_api_provider.value
        config.whisper_api_base.valueChanged.connect(self._base_changed)
        config.whisper_api_key.valueChanged.connect(self._key_changed)
        config.whisper_api_provider.valueChanged.connect(self._provider_changed)

    def _base_changed(self, base: str) -> None:
        cfg = self.cfg
        old_id, new_id = endpoint_identity(self.base), endpoint_identity(base)
        self.base = base
        if old_id == new_id:
            return
        keys = dict(cfg.whisper_api_endpoint_keys.value)
        keys[old_id] = cfg.whisper_api_key.value
        cfg.set(cfg.whisper_api_endpoint_keys, keys)
        cfg.set(cfg.whisper_api_key, keys.get(new_id, ""))

    def _key_changed(self, key: str) -> None:
        keys = dict(self.cfg.whisper_api_endpoint_keys.value)
        keys[endpoint_identity(self.base)] = key
        self.cfg.set(self.cfg.whisper_api_endpoint_keys, keys)

    def _provider_changed(self, provider: str) -> None:
        if provider == self.provider:
            return
        cfg = self.cfg
        saved = dict(cfg.whisper_api_saved_profiles.value)
        names = ("base", "model", "prompt", "request_profile")
        saved[self.provider] = {
            name: getattr(cfg, f"whisper_api_{name}").value for name in names
        }
        cfg.set(cfg.whisper_api_saved_profiles, saved)
        self.provider = provider
        preset = PROVIDER_PRESETS[provider]
        target = saved.get(provider, {
            "base": preset.base_url, "model": preset.models[0] if preset.models else "",
            "prompt": "", "request_profile": "auto",
        })
        # Changing base synchronously clears/restores the key before any request can start.
        for name in names:
            cfg.set(getattr(cfg, f"whisper_api_{name}"), target[name])

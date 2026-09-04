"""Provider presets and option keys shared by the dubbing tab and the CLI.

The GUI stores dubbing choices as short string keys in ``settings.json``; the
same keys appear as CLI flags. Keeping the tables here means the view only
maps combo indexes to keys and never owns provider knowledge.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Tuple

from videocaptioner.core.dubbing.config import AudioMixMode, TTSProviderEnum

# Combo-box order in the dubbing tab and the persisted `Dubbing.TTSProvider` key.
TTS_PROVIDER_KEYS: Tuple[str, ...] = ("openai", "minimax", "local_ai", "vieneu-local")
MANAGED_PROVIDER_KEY = "vieneu-local"

MIX_MODE_KEYS: Tuple[str, ...] = ("keep", "reduce", "mute")
TEXT_SOURCE_KEYS: Tuple[str, ...] = ("auto", "translated", "original")
TIMING_MODE_KEYS: Tuple[str, ...] = ("natural", "legacy")
UNRESOLVED_POLICY_KEYS: Tuple[str, ...] = ("review", "allow-overlap")
SAMPLE_RATES: Tuple[int, ...] = (16000, 24000, 32000, 44100, 48000)


@dataclass(frozen=True)
class ProviderPreset:
    """Suggested voices and endpoint defaults for one TTS provider."""

    voices: Tuple[str, ...]
    voice: str
    api_base: str
    model: str


TTS_PROVIDER_PRESETS: Dict[str, ProviderPreset] = {
    "openai": ProviderPreset(
        voices=("alloy", "echo", "fable", "onyx", "nova", "shimmer"),
        voice="alloy",
        api_base="https://api.openai.com/v1",
        model="tts-1",
    ),
    "minimax": ProviderPreset(
        voices=(
            "male-qn-qingse",
            "female-shaonv",
            "female-yujie",
            "male-tiehan",
            "speech-01-nova",
            "speech-01-turbo",
        ),
        voice="male-qn-qingse",
        api_base="https://api.minimax.chat/v1/t2a_v2",
        model="speech-01-turbo",
    ),
    "local_ai": ProviderPreset(
        voices=(), voice="", api_base="http://localhost:8000/v1", model=""
    ),
    "vieneu-local": ProviderPreset(voices=(), voice="", api_base="", model=""),
}

_PROVIDERS = {
    "openai": TTSProviderEnum.OPENAI,
    "minimax": TTSProviderEnum.MINIMAX,
    "local-ai": TTSProviderEnum.LOCAL_AI,
    "vieneu-local": TTSProviderEnum.VIENEU_LOCAL,
}
_MIX_MODES = {
    "keep": AudioMixMode.KEEP_ORIGINAL,
    "reduce": AudioMixMode.REDUCE_ORIGINAL,
    "mute": AudioMixMode.MUTE_ORIGINAL,
}


def normalize_provider_key(key: str) -> str:
    """Accept ``local_ai``/``local-ai`` and ``vieneu_local``/``vieneu-local`` alike."""
    return key.strip().lower().replace("_", "-")


def provider_from_key(key: str) -> TTSProviderEnum:
    """Map a settings/CLI key to the provider enum (unknown keys mean OpenAI)."""
    return _PROVIDERS.get(normalize_provider_key(key), TTSProviderEnum.OPENAI)


def is_managed_provider(key: str) -> bool:
    return normalize_provider_key(key) == MANAGED_PROVIDER_KEY


def mix_mode_from_key(key: str) -> AudioMixMode:
    """Map ``keep``/``reduce``/``mute`` to the enum (unknown keys mean reduce)."""
    return _MIX_MODES.get(key.strip().lower(), AudioMixMode.REDUCE_ORIGINAL)


def fill_provider_defaults(
    preset: ProviderPreset, voice: str, api_base: str, model: str
) -> Tuple[str, str, str]:
    """Return (voice, api_base, model) after switching provider.

    Only blank fields are filled from the preset so values the user typed are
    never overwritten; a non-blank voice is kept even if it belongs to the
    previous provider.
    """
    voice = voice.strip() or preset.voice
    api_base = api_base.strip() or preset.api_base
    model = model.strip() or preset.model
    return voice, api_base, model


def merged_output_path(video_path: str) -> str:
    """Default output for the manual audio-merge tool, beside the video."""
    video = Path(video_path)
    return str(video.parent / f"{video.stem}_merged.mp4")

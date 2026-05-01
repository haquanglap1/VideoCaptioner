"""Dubbing (lồng tiếng) module

Cung cấp engine để chuyển phụ đề thành giọng nói và mix vào video.
"""

from .audio_mixer import (
    adjust_audio_speed,
    build_voice_track,
    get_audio_duration,
    mix_audio_tracks,
)
from .config import AudioMixMode, DubbingConfig
from .engine import DubbingEngine

__all__ = [
    "DubbingEngine",
    "DubbingConfig",
    "AudioMixMode",
    "get_audio_duration",
    "adjust_audio_speed",
    "build_voice_track",
    "mix_audio_tracks",
]

"""TTS (Text-To-Speech) 模块

提供多种 TTS 服务的统一接口
"""

from .base import BaseTTS
from .minimax_tts import MiniMaxTTS
from .openai_tts import OpenAITTS
from .status import TTSStatus
from .tts_data import TTSConfig, TTSData, TTSDataSeg

__all__ = [
    "BaseTTS",
    "OpenAITTS",
    "MiniMaxTTS",
    "TTSStatus",
    "TTSConfig",
    "TTSData",
    "TTSDataSeg",
]

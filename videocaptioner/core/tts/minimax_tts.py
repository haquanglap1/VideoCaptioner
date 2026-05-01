"""MiniMax TTS API 实现"""

import requests
import json
from pathlib import Path

from videocaptioner.core.tts.base import BaseTTS
from videocaptioner.core.tts.tts_data import TTSConfig, TTSDataSeg
from videocaptioner.core.utils.logger import setup_logger

logger = setup_logger("tts.minimax")


class MiniMaxTTS(BaseTTS):
    """MiniMax TTS API 实现 (T2A V2)"""

    def __init__(self, config: TTSConfig):
        """初始化
        
        Args:
            config: TTS 配置
        """
        super().__init__(config)
        if not config.api_key:
            raise ValueError("API key is required for MiniMax TTS")
            
        self.api_key = config.api_key
        # Default base URL if not provided or left as OpenAI default
        self.base_url = config.base_url
        if not self.base_url or "api.openai.com" in self.base_url:
            self.base_url = "https://api.minimax.chat/v1/t2a_v2"
        elif not self.base_url.endswith("t2a_v2"):
            # Ensure it ends with the right endpoint if user provides base URL
            self.base_url = self.base_url.rstrip("/") + "/v1/t2a_v2"
            
        # Optional: set model (default speech-01-turbo)
        self.model = config.model if config.model and config.model != "tts-1" else "speech-01-turbo"

    def _synthesize(self, segment: TTSDataSeg, output_path: str) -> None:
        """合成语音的核心实现

        Args:
            segment: TTS 数据段
            output_path: 输出音频路径
        """
        logger.debug(f"Calling MiniMax TTS API: {segment.text[:50]}...")

        # 音色选择
        voice_to_use = segment.voice or self.config.voice or "male-qn-qingse"
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": self.model,
            "text": segment.text,
            "stream": False,
            "voice_setting": {
                "voice_id": voice_to_use,
                "speed": self.config.speed or 1.0,
                "vol": 1.0,
                "pitch": 0
            },
            "audio_setting": {
                "sample_rate": 32000,
                "bitrate": 128000,
                "format": "mp3",
                "channel": 1
            }
        }
        
        response = requests.post(
            self.base_url,
            headers=headers,
            json=payload,
            timeout=30
        )
        
        if response.status_code != 200:
            raise RuntimeError(f"MiniMax TTS HTTP {response.status_code}: {response.text}")
            
        data = response.json()
        base_resp = data.get("base_resp", {})
        if base_resp.get("status_code", 0) != 0:
            raise RuntimeError(f"MiniMax TTS Error: {base_resp.get('status_msg')}")
            
        audio_hex = data.get("data", {}).get("audio", "")
        if not audio_hex:
            raise RuntimeError("MiniMax TTS Error: No audio data returned")
            
        # Write binary file from hex
        with open(output_path, "wb") as f:
            f.write(bytes.fromhex(audio_hex))

        logger.debug(f"TTS success: {output_path}")

        # 更新 segment
        segment.audio_path = output_path
        segment.voice = voice_to_use

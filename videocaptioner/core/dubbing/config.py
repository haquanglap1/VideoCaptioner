"""Dubbing configuration data classes."""

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from videocaptioner.core.tts.tts_data import TTSConfig


class AudioMixMode(Enum):
    """Chế độ xử lý audio gốc khi mix voice track."""

    KEEP_ORIGINAL = "Giữ nguyên"
    REDUCE_ORIGINAL = "Giảm âm lượng nền"
    MUTE_ORIGINAL = "Tắt audio gốc"


class TTSProviderEnum(Enum):
    """TTS provider."""

    OPENAI = "OpenAI"
    MINIMAX = "MiniMax"
    LOCAL_AI = "Local AI"


@dataclass
class DubbingConfig:
    """Cấu hình dubbing."""

    # TTS provider
    tts_provider: TTSProviderEnum = TTSProviderEnum.OPENAI
    tts_config: Optional[TTSConfig] = None

    # Audio mixing
    mix_mode: AudioMixMode = AudioMixMode.REDUCE_ORIGINAL
    original_volume: float = 0.4  # Âm lượng audio gốc khi REDUCE (0.0 - 1.0)
    voice_volume: float = 1.0  # Hệ số khuếch đại giọng lồng tiếng (sau loudnorm)

    # TTS concurrency
    tts_concurrency: int = 1  # Số luồng TTS chạy song song

    # Timeline alignment — engine chỉ tăng tốc (>= 1.0x), không kéo giãn chậm,
    # nên chỉ cần trần tốc độ. (Trước đây là speed_range tuple nhưng phần tử
    # min chưa bao giờ được đọc.)
    max_speed: float = 1.5

    # Text preprocessing
    # Xóa ký tự CJK khỏi text trước khi gọi TTS. Chỉ đúng khi ngôn ngữ đích là
    # hệ Latin (lọc phần dịch còn sót tiếng Trung). Phải đặt False khi lồng
    # tiếng sang Trung/Nhật/Quảng — nếu không mọi câu sẽ bị xóa trắng.
    strip_cjk: bool = True

    # Enable/disable
    enabled: bool = False  # Mặc định tắt, user bật khi cần

    def print_config(self) -> str:
        """Print dubbing configuration."""
        lines = ["=========== Dubbing Task ==========="]
        lines.append(f"Enabled: {self.enabled}")
        if self.enabled:
            lines.append(f"TTS Provider: {self.tts_provider.value}")
            lines.append(f"Mix Mode: {self.mix_mode.value}")
            if self.mix_mode == AudioMixMode.REDUCE_ORIGINAL:
                lines.append(f"Original Volume: {self.original_volume:.0%}")
            lines.append(f"Voice Volume: {self.voice_volume:.0%}")
            lines.append(f"TTS Concurrency: {self.tts_concurrency}")
            lines.append(f"Max Speed: {self.max_speed}x")
            lines.append(f"Strip CJK: {self.strip_cjk}")
        lines.append("=" * 36)
        return "\n".join(lines)

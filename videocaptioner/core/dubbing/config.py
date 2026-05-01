"""Dubbing configuration data classes."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Tuple

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

    # Timeline alignment
    speed_range: Tuple[float, float] = (0.75, 1.5)  # min/max tốc độ co giãn
    gap_ms: int = 100  # Khoảng trống tối thiểu giữa segments (ms)

    # Output
    output_format: str = "wav"  # Format audio intermediate

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
            lines.append(f"Speed Range: {self.speed_range[0]}x - {self.speed_range[1]}x")
            lines.append(f"Gap: {self.gap_ms}ms")
        lines.append("=" * 36)
        return "\n".join(lines)

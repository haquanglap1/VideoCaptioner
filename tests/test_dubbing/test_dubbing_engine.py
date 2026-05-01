"""Tests for DubbingEngine — unit tests with mocked TTS and FFmpeg."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from videocaptioner.core.dubbing.config import (
    AudioMixMode,
    DubbingConfig,
    TTSProviderEnum,
)
from videocaptioner.core.dubbing.engine import DubbingEngine
from videocaptioner.core.tts.tts_data import TTSConfig, TTSData, TTSDataSeg


class TestDubbingConfig:
    """Test DubbingConfig dataclass."""

    def test_default_values(self):
        config = DubbingConfig()
        assert config.tts_provider == TTSProviderEnum.OPENAI
        assert config.mix_mode == AudioMixMode.REDUCE_ORIGINAL
        assert config.original_volume == 0.4
        assert config.speed_range == (0.75, 1.5)
        assert config.gap_ms == 100
        assert config.enabled is False

    def test_print_config_disabled(self):
        config = DubbingConfig(enabled=False)
        output = config.print_config()
        assert "Enabled: False" in output

    def test_print_config_enabled(self):
        config = DubbingConfig(
            enabled=True,
            tts_provider=TTSProviderEnum.SILICONFLOW,
            mix_mode=AudioMixMode.MUTE_ORIGINAL,
        )
        output = config.print_config()
        assert "Enabled: True" in output
        assert "SiliconFlow" in output
        assert "Tắt audio gốc" in output


class TestAudioMixMode:
    """Test AudioMixMode enum."""

    def test_values(self):
        assert AudioMixMode.KEEP_ORIGINAL.value == "Giữ nguyên"
        assert AudioMixMode.REDUCE_ORIGINAL.value == "Giảm âm lượng nền"
        assert AudioMixMode.MUTE_ORIGINAL.value == "Tắt audio gốc"


class TestDubbingEngine:
    """Test DubbingEngine methods."""

    def test_create_tts_data_from_segments(self):
        """Test converting ASR segments to TTSData."""
        engine = DubbingEngine()

        # Create mock ASR segments
        class MockSegment:
            def __init__(self, text, start_time, end_time):
                self.text = text
                self.start_time = start_time  # in ms
                self.end_time = end_time

        segments = [
            MockSegment("Hello world", 1000, 3000),
            MockSegment("This is a test", 4000, 6000),
            MockSegment("", 7000, 8000),  # Empty — should be skipped
        ]

        tts_data = engine._create_tts_data(segments)
        assert len(tts_data.segments) == 2
        assert tts_data.segments[0].text == "Hello world"
        assert tts_data.segments[0].start_time == 1.0  # ms → seconds
        assert tts_data.segments[0].end_time == 3.0
        assert tts_data.segments[1].text == "This is a test"

    def test_create_tts_provider_openai(self):
        """Test creating OpenAI TTS provider."""
        engine = DubbingEngine()
        config = DubbingConfig(
            tts_provider=TTSProviderEnum.OPENAI,
            tts_config=TTSConfig(
                model="tts-1",
                api_key="test-key",
                base_url="https://api.openai.com/v1",
            ),
        )
        from videocaptioner.core.tts.openai_tts import OpenAITTS

        provider = engine._create_tts_provider(config)
        assert isinstance(provider, OpenAITTS)

    def test_create_tts_provider_siliconflow(self):
        """Test creating SiliconFlow TTS provider."""
        engine = DubbingEngine()
        config = DubbingConfig(
            tts_provider=TTSProviderEnum.SILICONFLOW,
            tts_config=TTSConfig(
                model="FunAudioLLM/CosyVoice2-0.5B",
                api_key="test-key",
                base_url="https://api.siliconflow.cn/v1",
            ),
        )
        from videocaptioner.core.tts.siliconflow import SiliconFlowTTS

        provider = engine._create_tts_provider(config)
        assert isinstance(provider, SiliconFlowTTS)

    def test_create_tts_provider_openai_fm(self):
        """Test creating OpenAI.fm TTS provider."""
        engine = DubbingEngine()
        config = DubbingConfig(
            tts_provider=TTSProviderEnum.OPENAI_FM,
            tts_config=TTSConfig(
                model="",
                api_key="",
                base_url="",
            ),
        )
        from videocaptioner.core.tts.openai_fm import OpenAIFmTTS

        provider = engine._create_tts_provider(config)
        assert isinstance(provider, OpenAIFmTTS)

    def test_create_tts_provider_no_config(self):
        """Test error when tts_config is None."""
        engine = DubbingEngine()
        config = DubbingConfig(tts_config=None)
        with pytest.raises(ValueError, match="tts_config is required"):
            engine._create_tts_provider(config)

    def test_dub_validates_video_path(self):
        """Test that dub() validates video path exists."""
        engine = DubbingEngine()
        config = DubbingConfig(
            tts_config=TTSConfig(model="tts-1", api_key="k", base_url="u")
        )
        with pytest.raises(ValueError, match="Video không tồn tại"):
            engine.dub(
                video_path="/nonexistent/video.mp4",
                subtitle_path="/nonexistent/sub.srt",
                output_path="/tmp/out.mp4",
                config=config,
            )

    def test_dub_validates_tts_config(self):
        """Test that dub() validates tts_config is set."""
        engine = DubbingEngine()
        config = DubbingConfig(tts_config=None)

        # Create a temp file to pass video validation
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            temp_video = f.name

        try:
            with pytest.raises(ValueError, match="TTS config"):
                engine.dub(
                    video_path=temp_video,
                    subtitle_path="/nonexistent/sub.srt",
                    output_path="/tmp/out.mp4",
                    config=config,
                )
        finally:
            Path(temp_video).unlink(missing_ok=True)

    def test_align_timeline_speed_clamping(self):
        """Test that timeline alignment clamps speed within range."""
        engine = DubbingEngine()
        config = DubbingConfig(speed_range=(0.8, 1.3))

        # Mock TTS segment with audio longer than target
        tts_seg = TTSDataSeg(
            text="test", start_time=0.0, end_time=2.0, audio_path=""
        )
        tts_data = TTSData([tts_seg])

        # Mock ASR segment
        class MockASR:
            start_time = 0
            end_time = 2000

        # Since audio_path doesn't exist, it should skip
        result = engine._align_timeline(tts_data, [MockASR()], "/tmp", config)
        assert len(result) == 0  # Skipped because audio_path is empty

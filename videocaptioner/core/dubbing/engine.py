"""Dubbing Engine — orchestrator chính cho pipeline lồng tiếng.

Pipeline:
1. Parse subtitle → ASRData
2. Tạo TTSData từ ASRData segments
3. Gọi TTS provider batch synthesize
4. Căn chỉnh timeline (speed up/slow down từng segment)
5. Ghép voice track (silence padding + concat)
6. Mix voice track vào video gốc
"""

import tempfile
from pathlib import Path
from typing import Callable, Optional

from videocaptioner.core.asr.asr_data import ASRData
from videocaptioner.core.dubbing.audio_mixer import (
    adjust_audio_speed,
    build_voice_track,
    get_audio_duration,
    mix_audio_tracks,
)
from videocaptioner.core.dubbing.config import DubbingConfig, TTSProviderEnum
from videocaptioner.core.tts import (
    BaseTTS,
    OpenAIFmTTS,
    OpenAITTS,
    SiliconFlowTTS,
    TTSData,
    TTSDataSeg,
)
from videocaptioner.core.utils.logger import setup_logger
from videocaptioner.core.utils.video_utils import get_video_info

logger = setup_logger("dubbing.engine")


class DubbingEngine:
    """Engine lồng tiếng video.

    Nhận video + subtitle, tạo voice track bằng TTS, căn chỉnh timeline,
    và mix vào video gốc.
    """

    def dub(
        self,
        video_path: str,
        subtitle_path: str,
        output_path: str,
        config: DubbingConfig,
        callback: Optional[Callable[[int, str], None]] = None,
    ) -> str:
        """Thực hiện toàn bộ pipeline dubbing.

        Args:
            video_path: Đường dẫn video gốc.
            subtitle_path: Đường dẫn file phụ đề (SRT/ASS/VTT).
            output_path: Đường dẫn video đầu ra.
            config: Cấu hình dubbing.
            callback: Hàm callback tiến độ (progress: int, message: str).

        Returns:
            Đường dẫn video đầu ra.

        Raises:
            ValueError: Nếu thiếu config hoặc file không tồn tại.
            RuntimeError: Nếu bất kỳ bước nào thất bại.
        """
        if callback is None:
            callback = lambda p, m: None

        # Validate inputs
        if not Path(video_path).is_file():
            raise ValueError(f"Video không tồn tại: {video_path}")
        if not Path(subtitle_path).is_file():
            raise ValueError(f"Subtitle không tồn tại: {subtitle_path}")
        if not config.tts_config:
            raise ValueError("TTS config chưa được cấu hình")

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        # Tạo thư mục tạm cho intermediate files
        work_dir = Path(tempfile.mkdtemp(prefix="vc_dub_"))
        logger.info("Dubbing work dir: %s", work_dir)

        try:
            # --- Step 1: Parse subtitle ---
            callback(5, "Đang đọc phụ đề...")
            asr_data = ASRData.from_subtitle_file(subtitle_path)
            segments = asr_data.segments
            if not segments:
                raise ValueError("Phụ đề trống, không có gì để lồng tiếng")
            logger.info("Parsed %d subtitle segments", len(segments))

            # Lấy tổng thời lượng video
            video_info = get_video_info(video_path)
            total_duration = video_info.duration_seconds if video_info else 0.0
            if total_duration <= 0:
                # Fallback: dùng end time của segment cuối
                total_duration = max(seg.end_time / 1000.0 for seg in segments) + 1.0

            # --- Step 2: Tạo TTSData ---
            callback(10, "Đang chuẩn bị văn bản...")
            tts_data = self._create_tts_data(segments)
            logger.info("Created TTSData with %d segments", len(tts_data))

            # --- Step 3: TTS Synthesize ---
            callback(15, "Đang tổng hợp giọng nói...")
            tts_output_dir = str(work_dir / "tts_audio")
            tts_provider = self._create_tts_provider(config)

            def tts_callback(progress: int, message: str):
                # TTS chiếm 15-60% tổng tiến độ
                mapped = 15 + int(progress * 0.45)
                callback(mapped, f"Đang tổng hợp giọng nói... {progress}%")

            tts_data = tts_provider.synthesize(tts_data, tts_output_dir, tts_callback)

            # Kiểm tra kết quả TTS
            success_count = sum(1 for seg in tts_data.segments if seg.audio_path)
            if success_count == 0:
                raise RuntimeError("TTS thất bại cho tất cả segments")
            logger.info("TTS success: %d/%d segments", success_count, len(tts_data.segments))

            # --- Step 4: Timeline Alignment ---
            callback(60, "Đang căn chỉnh timeline...")
            adjusted_dir = str(work_dir / "adjusted")
            Path(adjusted_dir).mkdir(parents=True, exist_ok=True)
            segment_infos = self._align_timeline(
                tts_data, segments, adjusted_dir, config
            )
            logger.info("Timeline aligned: %d segments", len(segment_infos))

            # --- Step 5: Build Voice Track ---
            callback(75, "Đang ghép voice track...")
            voice_track_path = str(work_dir / "voice_track.wav")
            if not build_voice_track(segment_infos, total_duration, voice_track_path):
                raise RuntimeError("Ghép voice track thất bại")

            # --- Step 6: Mix vào video ---
            callback(85, "Đang mix audio vào video...")
            if not mix_audio_tracks(
                video_path,
                voice_track_path,
                output_path,
                mix_mode=config.mix_mode,
                original_volume=config.original_volume,
            ):
                raise RuntimeError("Mix audio thất bại")

            callback(100, "Lồng tiếng hoàn tất!")
            logger.info("Dubbing complete: %s", output_path)
            return output_path

        finally:
            # Cleanup work dir
            import shutil
            shutil.rmtree(str(work_dir), ignore_errors=True)

    def _create_tts_data(self, segments) -> TTSData:
        """Chuyển ASRData segments thành TTSData.

        Args:
            segments: Danh sách ASRDataSeg (có text, start_time, end_time in ms).

        Returns:
            TTSData instance.
        """
        tts_segments = []
        for seg in segments:
            text = seg.text.strip()
            if not text:
                continue
            tts_seg = TTSDataSeg(
                text=text,
                start_time=seg.start_time / 1000.0,  # ms → seconds
                end_time=seg.end_time / 1000.0,
            )
            tts_segments.append(tts_seg)
        return TTSData(tts_segments)

    def _create_tts_provider(self, config: DubbingConfig) -> BaseTTS:
        """Tạo TTS provider instance từ config.

        Args:
            config: Dubbing config chứa tts_provider và tts_config.

        Returns:
            BaseTTS instance.
        """
        tts_config = config.tts_config
        if tts_config is None:
            raise ValueError("tts_config is required")

        if config.tts_provider == TTSProviderEnum.SILICONFLOW:
            return SiliconFlowTTS(tts_config)
        elif config.tts_provider == TTSProviderEnum.OPENAI_FM:
            return OpenAIFmTTS(tts_config)
        else:
            # Default: OpenAI-compatible
            return OpenAITTS(tts_config)

    def _align_timeline(
        self,
        tts_data: TTSData,
        asr_segments,
        output_dir: str,
        config: DubbingConfig,
    ) -> list:
        """Căn chỉnh timeline: speed up/slow down TTS audio cho vừa subtitle gap.

        Args:
            tts_data: TTSData đã synthesize (có audio_path).
            asr_segments: ASRData segments gốc (có start_time, end_time in ms).
            output_dir: Thư mục lưu audio đã điều chỉnh.
            config: DubbingConfig.

        Returns:
            List[dict] — mỗi item: {"audio_path", "start_time", "end_time"} (seconds).
        """
        min_speed, max_speed = config.speed_range
        result = []

        for idx, tts_seg in enumerate(tts_data.segments):
            if not tts_seg.audio_path or not Path(tts_seg.audio_path).is_file():
                continue

            # Timeline target (seconds)
            target_start = tts_seg.start_time
            target_end = tts_seg.end_time
            target_duration = target_end - target_start

            if target_duration <= 0:
                continue

            # Actual TTS audio duration
            actual_duration = get_audio_duration(tts_seg.audio_path)
            if actual_duration <= 0:
                continue

            # Tính tốc độ cần thiết
            if actual_duration > 0:
                needed_speed = actual_duration / target_duration
            else:
                needed_speed = 1.0

            # Clamp speed trong giới hạn cho phép
            clamped_speed = max(min_speed, min(max_speed, needed_speed))

            # Áp dụng speed adjustment
            if abs(clamped_speed - 1.0) > 0.02:
                adjusted_path = str(Path(output_dir) / f"seg_{idx:04d}_adj.wav")
                if adjust_audio_speed(tts_seg.audio_path, adjusted_path, clamped_speed):
                    audio_path = adjusted_path
                else:
                    audio_path = tts_seg.audio_path  # Fallback: giữ nguyên
            else:
                audio_path = tts_seg.audio_path

            # Nếu audio vẫn dài hơn target sau adjust, truncate
            final_duration = get_audio_duration(audio_path)
            if final_duration > target_duration + 0.05:
                truncated_path = str(Path(output_dir) / f"seg_{idx:04d}_trunc.wav")
                if _truncate_audio(audio_path, truncated_path, target_duration):
                    audio_path = truncated_path

            result.append({
                "audio_path": audio_path,
                "start_time": target_start,
                "end_time": target_end,
            })

        return result


def _truncate_audio(input_path: str, output_path: str, max_duration: float) -> bool:
    """Cắt audio tới max_duration giây.

    Args:
        input_path: File đầu vào.
        output_path: File đầu ra.
        max_duration: Thời lượng tối đa (giây).

    Returns:
        True nếu thành công.
    """
    import subprocess as sp

    _flags = getattr(sp, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    cmd = [
        "ffmpeg",
        "-i", input_path,
        "-t", f"{max_duration:.3f}",
        "-y",
        output_path,
    ]
    try:
        result = sp.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=_flags,
        )
        return result.returncode == 0 and Path(output_path).is_file()
    except Exception:
        return False

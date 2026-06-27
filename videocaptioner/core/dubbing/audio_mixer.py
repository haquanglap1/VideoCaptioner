"""FFmpeg audio utilities for dubbing.

Provides functions to:
- Get audio duration via ffprobe
- Adjust audio playback speed via atempo filter
- Build a full-length voice track from TTS segments with silence padding
- Mix voice track into original video audio
"""

import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import List, Optional

from videocaptioner.core.dubbing.config import AudioMixMode
from videocaptioner.core.utils.logger import setup_logger

logger = setup_logger("dubbing.audio_mixer")

_FFMPEG_CREATE_FLAGS = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0


def get_audio_duration(audio_path: str) -> float:
    """Lấy thời lượng audio bằng ffprobe (giây).

    Args:
        audio_path: Đường dẫn file audio.

    Returns:
        Thời lượng tính bằng giây, hoặc 0.0 nếu lỗi.
    """
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "csv=p=0",
                audio_path,
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=_FFMPEG_CREATE_FLAGS,
        )
        duration_str = result.stdout.strip()
        if duration_str and duration_str.upper() != "N/A":
            return float(duration_str)
    except Exception as e:
        logger.warning("Không lấy được duration cho %s: %s", audio_path, e)
    return 0.0


def adjust_audio_speed(
    input_path: str,
    output_path: str,
    speed: float,
) -> bool:
    """Co giãn tốc độ audio bằng FFmpeg atempo filter.

    atempo chỉ chấp nhận giá trị trong [0.5, 100.0], nên nếu speed < 0.5
    ta chain nhiều atempo filter.

    Args:
        input_path: File audio đầu vào.
        output_path: File audio đầu ra.
        speed: Tốc độ mong muốn (1.0 = giữ nguyên, 1.5 = nhanh 50%).

    Returns:
        True nếu thành công.
    """
    if abs(speed - 1.0) < 0.01:
        # Không cần thay đổi, copy trực tiếp
        import shutil
        shutil.copy2(input_path, output_path)
        return True

    # Build atempo filter chain (atempo accepts 0.5–100.0 per stage)
    filters: List[str] = []
    remaining = speed
    while remaining < 0.5:
        filters.append("atempo=0.5")
        remaining /= 0.5
    while remaining > 100.0:
        filters.append("atempo=100.0")
        remaining /= 100.0
    filters.append(f"atempo={remaining:.4f}")
    filter_str = ",".join(filters)

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-i", input_path,
        "-filter:a", filter_str,
        "-y",
        output_path,
    ]
    logger.debug("adjust_audio_speed cmd: %s", " ".join(cmd))

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=_FFMPEG_CREATE_FLAGS,
        )
        if result.returncode == 0 and Path(output_path).is_file():
            return True
        logger.error("adjust_audio_speed failed: %s", result.stderr[-500:] if result.stderr else "")
        return False
    except Exception as e:
        logger.exception("adjust_audio_speed error: %s", e)
        return False


def build_voice_track(
    segment_infos: List[dict],
    total_duration_s: float,
    output_path: str,
    sample_rate: int = 24000,
) -> bool:
    """Ghép các audio segment thành voice track hoàn chỉnh.

    Mỗi segment_info là dict:
        {"audio_path": str, "start_time": float, "end_time": float}

    Silence được chèn giữa các segment để khớp timeline.

    Args:
        segment_infos: Danh sách segment đã sắp xếp theo start_time.
        total_duration_s: Tổng thời lượng video (giây).
        output_path: Đường dẫn voice track đầu ra.
        sample_rate: Sample rate của output.

    Returns:
        True nếu thành công.
    """
    if not segment_infos:
        logger.warning("Không có segment nào để build voice track")
        return False

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    # Tạo concat file cho FFmpeg
    temp_dir = Path(tempfile.mkdtemp(prefix="vc_dubbing_"))

    try:
        parts: List[str] = []
        current_pos = 0.0  # Vị trí hiện tại trên timeline (giây)

        for idx, seg in enumerate(segment_infos):
            audio_path = seg["audio_path"]
            start_time = seg["start_time"]

            if not audio_path or not Path(audio_path).is_file():
                logger.warning("Segment %d: audio không tồn tại: %s", idx, audio_path)
                continue

            # Chèn silence nếu cần
            silence_duration = start_time - current_pos
            if silence_duration > 0.01:
                silence_path = str(temp_dir / f"silence_{idx:04d}.wav")
                _generate_silence(silence_path, silence_duration, sample_rate)
                parts.append(silence_path)

            parts.append(audio_path)

            # Cập nhật vị trí
            audio_dur = get_audio_duration(audio_path)
            current_pos = start_time + audio_dur

        # Chèn silence cuối để khớp tổng thời lượng
        remaining = total_duration_s - current_pos
        if remaining > 0.01:
            tail_silence = str(temp_dir / "silence_tail.wav")
            _generate_silence(tail_silence, remaining, sample_rate)
            parts.append(tail_silence)

        if not parts:
            logger.error("Không có audio part nào hợp lệ")
            return False

        # Ghi concat list
        concat_list_path = str(temp_dir / "concat_list.txt")
        with open(concat_list_path, "w", encoding="utf-8") as f:
            for part in parts:
                # FFmpeg concat demuxer cần đường dẫn tuyệt đối, escape single quotes
                abs_path = str(Path(part).resolve()).replace("'", "'\\''")
                f.write(f"file '{abs_path}'\n")

        # Concat tất cả thành voice track
        cmd = [
            "ffmpeg",
            "-f", "concat",
            "-safe", "0",
            "-i", concat_list_path,
            "-ac", "1",
            "-ar", str(sample_rate),
            "-y",
            output_path,
        ]
        logger.debug("build_voice_track cmd: %s", " ".join(cmd))

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=_FFMPEG_CREATE_FLAGS,
        )
        if result.returncode == 0 and Path(output_path).is_file():
            logger.info("Voice track built: %s", output_path)
            return True
        logger.error("build_voice_track failed: %s", result.stderr[-500:] if result.stderr else "")
        return False

    finally:
        # Cleanup temp silence files
        import shutil
        shutil.rmtree(str(temp_dir), ignore_errors=True)


def mix_audio_tracks(
    video_path: str,
    voice_track_path: str,
    output_path: str,
    mix_mode: AudioMixMode = AudioMixMode.REDUCE_ORIGINAL,
    original_volume: float = 0.2,
) -> bool:
    """Mix voice track vào video, xử lý audio gốc theo mix_mode.

    Args:
        video_path: Video gốc (có audio).
        voice_track_path: Voice track đã tạo.
        output_path: Video đầu ra.
        mix_mode: Chế độ xử lý audio gốc.
        original_volume: Âm lượng audio gốc (0.0-1.0) khi REDUCE.

    Returns:
        True nếu thành công.
    """
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    if mix_mode == AudioMixMode.MUTE_ORIGINAL:
        # Thay hoàn toàn audio bằng voice track
        cmd = [
            "ffmpeg",
            "-i", video_path,
            "-i", voice_track_path,
            "-c:v", "copy",
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-shortest",
            "-y",
            output_path,
        ]
    elif mix_mode == AudioMixMode.REDUCE_ORIGINAL:
        # Giảm âm lượng audio gốc, mix với voice track
        vol = max(0.0, min(1.0, original_volume))
        # normalize=0: giữ nguyên âm lượng từng input (không chia đôi).
        # Giọng lồng tiếng [1:a] giữ 100%, chỉ audio gốc bị giảm theo `vol`.
        filter_complex = (
            f"[0:a]volume={vol}[orig];"
            f"[orig][1:a]amix=inputs=2:duration=first:dropout_transition=2:normalize=0[aout]"
        )
        cmd = [
            "ffmpeg",
            "-i", video_path,
            "-i", voice_track_path,
            "-c:v", "copy",
            "-filter_complex", filter_complex,
            "-map", "0:v:0",
            "-map", "[aout]",
            "-shortest",
            "-y",
            output_path,
        ]
    else:
        # KEEP_ORIGINAL: mix cả hai ở full volume (normalize=0 để không bị chia đôi)
        filter_complex = (
            "[0:a][1:a]amix=inputs=2:duration=first:dropout_transition=2:normalize=0[aout]"
        )
        cmd = [
            "ffmpeg",
            "-i", video_path,
            "-i", voice_track_path,
            "-c:v", "copy",
            "-filter_complex", filter_complex,
            "-map", "0:v:0",
            "-map", "[aout]",
            "-shortest",
            "-y",
            output_path,
        ]

    logger.debug("mix_audio_tracks cmd: %s", subprocess.list2cmdline(cmd))

    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=_FFMPEG_CREATE_FLAGS,
        )
        _, stderr = process.communicate()

        if process.returncode == 0 and Path(output_path).is_file():
            logger.info("Audio mix complete: %s", output_path)
            return True
        logger.error("mix_audio_tracks failed (rc=%d): %s", process.returncode, stderr[-500:] if stderr else "")
        return False

    except Exception as e:
        logger.exception("mix_audio_tracks error: %s", e)
        return False


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _generate_silence(output_path: str, duration_s: float, sample_rate: int = 24000) -> bool:
    """Tạo file audio im lặng.

    Args:
        output_path: Đường dẫn file đầu ra.
        duration_s: Thời lượng (giây).
        sample_rate: Sample rate.

    Returns:
        True nếu thành công.
    """
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-f", "lavfi",
        "-i", f"anullsrc=r={sample_rate}:cl=mono",
        "-t", f"{duration_s:.3f}",
        "-y",
        output_path,
    ]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=_FFMPEG_CREATE_FLAGS,
        )
        return result.returncode == 0
    except Exception as e:
        logger.warning("_generate_silence failed: %s", e)
        return False

import os
import re
import shutil
import subprocess
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Literal, Optional

from videocaptioner.core.utils.subprocess_helper import child_environment

from ..entities import (
    AudioStreamInfo,
    SubtitleLayoutEnum,
    SubtitleRenderModeEnum,
    VideoInfo,
)
from ..subtitle.ass_renderer import render_ass_video
from ..subtitle.ass_utils import auto_wrap_ass_file
from ..subtitle.rounded_renderer import render_rounded_video
from ..utils.logger import setup_logger

if TYPE_CHECKING:
    from videocaptioner.core.asr.asr_data import ASRData

# FFmpeg preset names
PresetType = Literal[
    "ultrafast",
    "superfast",
    "veryfast",
    "faster",
    "fast",
    "medium",
    "slow",
    "slower",
    "veryslow",
]

logger = setup_logger("video_utils")


@dataclass(frozen=True)
class VideoChunkPlan:
    """One logical video chunk plus the source range used for processing.

    ``start_ms``/``end_ms`` are the non-overlapping timeline range shown to the
    user. ``source_start_ms``/``source_end_ms`` include optional overlap for
    ASR/proxy generation so boundaries have enough context.
    """

    index: int
    start_ms: int
    end_ms: int
    source_start_ms: int
    source_end_ms: int

    @property
    def duration_ms(self) -> int:
        return self.end_ms - self.start_ms

    @property
    def source_duration_ms(self) -> int:
        return self.source_end_ms - self.source_start_ms


def plan_video_chunks(
    duration_seconds: float,
    chunk_length_seconds: int = 20 * 60,
    overlap_seconds: int = 10,
) -> list[VideoChunkPlan]:
    """Plan ~20 minute chunks for long-video editing/transcription.

    Args:
        duration_seconds: Total media duration in seconds.
        chunk_length_seconds: Logical chunk length. Defaults to 20 minutes.
        overlap_seconds: Extra source context around chunk boundaries.

    Returns:
        Ordered chunk plans. Short videos return a single chunk.
    """
    if duration_seconds < 0:
        raise ValueError("duration_seconds must be >= 0")
    if chunk_length_seconds <= 0:
        raise ValueError("chunk_length_seconds must be > 0")
    if overlap_seconds < 0:
        raise ValueError("overlap_seconds must be >= 0")
    if overlap_seconds >= chunk_length_seconds:
        raise ValueError("overlap_seconds must be smaller than chunk_length_seconds")

    total_ms = int(round(duration_seconds * 1000))
    chunk_ms = chunk_length_seconds * 1000
    overlap_ms = overlap_seconds * 1000

    if total_ms == 0:
        return [
            VideoChunkPlan(
                index=1,
                start_ms=0,
                end_ms=0,
                source_start_ms=0,
                source_end_ms=0,
            )
        ]

    chunks: list[VideoChunkPlan] = []
    start_ms = 0
    while start_ms < total_ms:
        end_ms = min(start_ms + chunk_ms, total_ms)
        source_start_ms = max(0, start_ms - overlap_ms)
        source_end_ms = min(total_ms, end_ms + overlap_ms)
        chunks.append(
            VideoChunkPlan(
                index=len(chunks) + 1,
                start_ms=start_ms,
                end_ms=end_ms,
                source_start_ms=source_start_ms,
                source_end_ms=source_end_ms,
            )
        )
        start_ms = end_ms
    return chunks


@contextmanager
def temporary_subtitle_file(subtitle_path: str):
    """Context manager that copies a subtitle file to a temporary path.

    The copy is removed on exit, so FFmpeg gets a path that stays untouched
    even if the original is edited meanwhile.

    Args:
        subtitle_path: original subtitle file

    Yields:
        path of the temporary copy
    """
    suffix = Path(subtitle_path).suffix.lower()
    temp_fd, temp_path = tempfile.mkstemp(
        suffix=suffix, prefix="VideoCaptioner_subtitle_"
    )
    os.close(temp_fd)

    try:
        # Copy the subtitle to the temporary location
        shutil.copy2(subtitle_path, temp_path)
        yield temp_path
    finally:
        # Remove the temporary copy
        Path(temp_path).unlink(missing_ok=True)


def video2audio(input_file: str, output: str = "", audio_track_index: int = 0) -> bool:
    """Extract one audio track with ffmpeg as 16 kHz mono.

    Args:
        input_file: input video path
        output: output audio path
        audio_track_index: audio track to extract (0 = first track)

    Returns:
        True when the conversion succeeded
    """
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output = str(output_path)

    logger.debug(f"Extracting audio track {audio_track_index}")
    cmd = [
        "ffmpeg",
        "-i",
        input_file,
        "-map",
        f"0:a:{audio_track_index}",
        "-vn",
        "-ac",
        "1",  # mono
        "-ar",
        "16000",  # 16 kHz sample rate
        "-y",
        output,
    ]

    logger.debug(f"Audio conversion cmd: {' '.join(cmd)}")

    try:
        result = subprocess.run(
            cmd, env=child_environment(),
            capture_output=True,
            check=True,
            encoding="utf-8",
            errors="replace",
            creationflags=(
                getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
            ),
        )
        if result.returncode == 0 and Path(output).is_file():
            logger.debug("Audio conversion complete")
            return True
        else:
            logger.error("Audio conversion failed")
            return False
    except subprocess.CalledProcessError as e:
        logger.error("FFmpeg execution failed")
        logger.error(f"Return code: {e.returncode}")
        logger.error(f"Command: {' '.join(e.cmd)}")
        if e.stdout:
            logger.error(f"stdout: {e.stdout}")
        if e.stderr:
            logger.error(f"stderr: {e.stderr}")
        return False
    except Exception as e:
        logger.exception(f"音频转换出错: {str(e)}")
        return False


def check_cuda_available() -> bool:
    """Check if CUDA hardware acceleration is available via FFmpeg."""
    try:
        # First check whether this ffmpeg build lists cuda
        result = subprocess.run(
            ["ffmpeg", "-hwaccels"], env=child_environment(),
            capture_output=True,
            text=True,
            creationflags=(
                getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
            ),
        )
        if "cuda" not in result.stdout.lower():
            logger.debug("CUDA not in FFmpeg hwaccels list")
            return False

        # Then try to initialise the CUDA device
        result = subprocess.run(
            ["ffmpeg", "-hide_banner", "-init_hw_device", "cuda"], env=child_environment(),
            capture_output=True,
            text=True,
            creationflags=(
                getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
            ),
        )

        # "Cannot load cuda" / "Failed to load" in stderr means CUDA is unusable
        if any(
            error in result.stderr.lower()
            for error in ["cannot load cuda", "failed to load", "error"]
        ):
            logger.debug("CUDA device init failed")
            return False

        logger.debug("CUDA available")
        return True

    except Exception as e:
        logger.exception(f"CUDA check error: {str(e)}")
        return False


def add_subtitles(
    input_file: str,
    subtitle_file: str,
    output: str,
    crf: int = 23,
    preset: Literal[
        "ultrafast",
        "superfast",
        "veryfast",
        "faster",
        "fast",
        "medium",
        "slow",
        "slower",
        "veryslow",
    ] = "medium",
    vcodec: str = "libx264",
    soft_subtitle: bool = False,
    progress_callback: Optional[Callable] = None,
) -> None:
    assert Path(input_file).is_file(), "输入文件不存在"
    assert Path(subtitle_file).is_file(), "字幕文件不存在"

    # Work on a temporary copy of the subtitle (removed automatically)
    with temporary_subtitle_file(subtitle_file) as temp_subtitle_path:
        # ASS subtitles get automatic line wrapping first
        suffix = Path(subtitle_file).suffix.lower()
        processed_subtitle = temp_subtitle_path
        if suffix == ".ass":
            processed_subtitle = auto_wrap_ass_file(temp_subtitle_path)

        # WebM cannot carry mov_text: force hard subtitles
        if Path(output).suffix.lower() == ".webm":
            soft_subtitle = False
            logger.debug("WebM format, forcing hard subtitles")

        if soft_subtitle:
            # Soft subtitles: mux as a separate stream
            cmd = [
                "ffmpeg",
                "-i",
                input_file,
                "-i",
                processed_subtitle,
                "-c:v",
                "copy",
                "-c:a",
                "copy",
                "-c:s",
                "mov_text",
                "-y",
                output,
            ]
            logger.debug(f"FFmpeg soft subtitle cmd: {' '.join(cmd)}")
            try:
                subprocess.run(
                    cmd, env=child_environment(),
                    capture_output=True,
                    check=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    creationflags=(
                        getattr(subprocess, "CREATE_NO_WINDOW", 0)
                        if os.name == "nt"
                        else 0
                    ),
                )
                logger.debug("Soft subtitle added")
            except subprocess.CalledProcessError as e:
                logger.error("FFmpeg soft subtitle failed")
                logger.error(f"Return code: {e.returncode}")
                logger.error(f"Command: {' '.join(e.cmd)}")
                if e.stdout:
                    logger.error(f"stdout: {e.stdout}")
                if e.stderr:
                    logger.error(f"stderr: {e.stderr}")
                raise
        else:
            # Hard subtitles: burn into the frames
            subtitle_path_escaped = (
                Path(processed_subtitle).as_posix().replace(":", r"\:")
            )

            # Use ass= filter for ASS subtitle files, subtitles= for SRT/others
            if Path(subtitle_file).suffix.lower() == ".ass":
                vf = f"ass='{subtitle_path_escaped}'"
            else:
                vf = f"subtitles='{subtitle_path_escaped}'"

            if Path(output).suffix.lower() == ".webm":
                vcodec = "libvpx-vp9"
                logger.debug("WebM format, using libvpx-vp9")

            # Use CUDA when available
            use_cuda = check_cuda_available()
            cmd = ["ffmpeg"]
            if use_cuda:
                logger.debug("Using CUDA acceleration")
                cmd.extend(["-hwaccel", "cuda"])
            cmd.extend(
                [
                    "-i",
                    input_file,
                    "-acodec",
                    "copy",
                    "-vcodec",
                    vcodec,
                    "-crf",
                    str(crf),
                    "-preset",
                    preset,
                    "-vf",
                    vf,
                    "-y",
                    output,
                ]
            )

            cmd_str = subprocess.list2cmdline(cmd)
            logger.debug(f"FFmpeg hard subtitle cmd: {cmd_str}")

            process = None
            try:
                process = subprocess.Popen(
                    cmd, env=child_environment(),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    creationflags=(
                        getattr(subprocess, "CREATE_NO_WINDOW", 0)
                        if os.name == "nt"
                        else 0
                    ),
                )

                # Read stderr live and report progress through the callback
                total_duration = None
                current_time = 0

                while True:
                    output_line = process.stderr.readline()
                    if not output_line or (process.poll() is not None):
                        break
                    if not progress_callback:
                        continue

                    if total_duration is None:
                        duration_match = re.search(
                            r"Duration: (\d{2}):(\d{2}):(\d{2}\.\d{2})", output_line
                        )
                        if duration_match:
                            h, m, s = map(float, duration_match.groups())
                            total_duration = h * 3600 + m * 60 + s
                            logger.debug(f"Video duration: {total_duration}秒")

                    # Current position
                    time_match = re.search(
                        r"time=(\d{2}):(\d{2}):(\d{2}\.\d{2})", output_line
                    )
                    if time_match:
                        h, m, s = map(float, time_match.groups())
                        current_time = h * 3600 + m * 60 + s

                    # Progress percentage
                    if total_duration:
                        progress = (current_time / total_duration) * 100
                        progress_callback(f"{round(progress)}", "Đang ghép video")

                if progress_callback:
                    progress_callback("100", "Hoàn tất ghép video")

                # Check the exit code
                return_code = process.wait()
                if return_code != 0:
                    error_info = process.stderr.read()
                    logger.error("FFmpeg hard subtitle failed")
                    logger.error(f"Return code: {return_code}")
                    logger.error(f"Command: {cmd_str}")
                    if error_info:
                        logger.error(f"Error output: {error_info}")
                    raise Exception(f"FFmpeg Return code: {return_code}")
                logger.debug("Video synthesis complete")

            except subprocess.SubprocessError as e:
                logger.error("FFmpeg process error")
                logger.error(f"Error: {str(e)}")
                if process and process.poll() is None:
                    process.kill()
                raise
            except Exception as e:
                logger.error(f"Loi trong qua trinh ghep video: {str(e)}")
                if process and process.poll() is None:
                    process.kill()
                raise


def get_video_info(
    file_path: str, thumbnail_path: Optional[str] = None
) -> Optional["VideoInfo"]:
    """Probe a media file (video or audio) with ffmpeg.

    Args:
        file_path: media file (video or audio)
        thumbnail_path: where to save a thumbnail (optional, video only)

    Returns:
        VideoInfo, or None on failure.
        Audio-only files report width/height/fps as 0.
    """
    try:
        # Run ffmpeg to get the stream banner
        result = subprocess.run(
            ["ffmpeg", "-i", file_path], env=child_environment(),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=(
                getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
            ),
        )
        info = result.stderr

        # Duration
        duration_seconds = 0.0
        if duration_match := re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", info):
            hours, minutes, seconds = map(float, duration_match.groups())
            duration_seconds = hours * 3600 + minutes * 60 + seconds

        # Bitrate
        bitrate_kbps = 0
        if bitrate_match := re.search(r"bitrate: (\d+) kb/s", info):
            bitrate_kbps = int(bitrate_match.group(1))

        # Video stream
        width, height, fps, video_codec = 0, 0, 0.0, ""
        has_video_stream = False
        if video_stream_match := re.search(
            r"Stream #.*?Video: (\w+)(?:\s*\([^)]*\))?.* (\d+)x(\d+).*?(?:(\d+(?:\.\d+)?)\s*(?:fps|tb[rn]))",
            info,
            re.DOTALL,
        ):
            video_codec = video_stream_match.group(1)
            width = int(video_stream_match.group(2))
            height = int(video_stream_match.group(3))
            fps = float(video_stream_match.group(4))
            has_video_stream = True

        # First audio stream (kept for compatibility)
        audio_codec, audio_sampling_rate = "", 0
        if audio_stream_match := re.search(
            r"Stream #\d+:\d+.*Audio: (\w+).* (\d+) Hz", info
        ):
            audio_codec = audio_stream_match.group(1)
            audio_sampling_rate = int(audio_stream_match.group(2))

        # Every audio stream (for multi-track selection)
        audio_streams: list[AudioStreamInfo] = []
        for match in re.finditer(
            r"Stream #\d+:(\d+)(?:\[0x[0-9a-fA-F]+\])?(?:\(([a-z]{3})\))?: Audio: (\w+)",
            info,
        ):
            audio_streams.append(
                AudioStreamInfo(
                    index=int(match.group(1)),
                    codec=match.group(3),
                    language=match.group(2) or "",
                )
            )

        if audio_streams:
            logger.debug(f"Detected {len(audio_streams)}  audio tracks")

        # Reject files without any media stream
        if not has_video_stream and not audio_streams:
            logger.error("File has no video or audio streams")
            return None

        # Thumbnail (only when requested and a video stream exists)
        final_thumbnail_path = ""
        if thumbnail_path and duration_seconds > 0 and has_video_stream:
            if _extract_thumbnail(file_path, duration_seconds * 0.3, thumbnail_path):
                final_thumbnail_path = thumbnail_path

        # Build the VideoInfo
        return VideoInfo(
            file_name=Path(file_path).stem,
            file_path=file_path,
            width=width,
            height=height,
            fps=fps,
            duration_seconds=duration_seconds,
            bitrate_kbps=bitrate_kbps,
            video_codec=video_codec,
            audio_codec=audio_codec,
            audio_sampling_rate=audio_sampling_rate,
            thumbnail_path=final_thumbnail_path,
            audio_streams=audio_streams,
        )
    except Exception as e:
        logger.exception(f"获取视频信息时出错: {str(e)}")
        return None


def _extract_thumbnail(video_path: str, seek_time: float, thumbnail_path: str) -> bool:
    """Grab one frame as a thumbnail.

    Args:
        video_path: video file
        seek_time: position in seconds
        thumbnail_path: where to write the image

    Returns:
        True on success
    """
    if not Path(video_path).is_file():
        logger.error(f"视频文件不存在: {video_path}")
        return False

    try:
        timestamp = f"{int(seek_time // 3600):02}:{int((seek_time % 3600) // 60):02}:{seek_time % 60:06.3f}"
        Path(thumbnail_path).parent.mkdir(parents=True, exist_ok=True)

        result = subprocess.run(
            [
                "ffmpeg",
                "-ss",
                timestamp,
                "-i",
                Path(video_path).as_posix(),
                "-vframes",
                "1",
                "-q:v",
                "2",
                "-y",
                Path(thumbnail_path).as_posix(),
            ], env=child_environment(),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=(
                getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
            ),
        )
        return result.returncode == 0

    except Exception as e:
        logger.exception(f"提取缩略图时出错: {str(e)}")
        return False


def add_subtitles_with_style(
    video_path: str,
    asr_data: "ASRData",
    output_path: str,
    render_mode: SubtitleRenderModeEnum,
    subtitle_layout: SubtitleLayoutEnum,
    ass_style: str = "",
    rounded_style: Optional[dict] = None,
    crf: int = 23,
    preset: PresetType = "medium",
    progress_callback: Optional[Callable] = None,
) -> None:
    """
    Burn subtitles using the selected render mode.

    Args:
        video_path: input video
        asr_data: subtitle data
        output_path: output video
        render_mode: ASS_STYLE or ROUNDED_BG
        subtitle_layout: subtitle layout
        ass_style: ASS style string (ASS_STYLE only)
        rounded_style: rounded-background style dict (ROUNDED_BG only)
        crf: video quality
        preset: FFmpeg encoder preset
        progress_callback: progress callback
    """

    if render_mode == SubtitleRenderModeEnum.ROUNDED_BG:
        # Rounded background mode
        render_rounded_video(
            video_path=video_path,
            asr_data=asr_data,
            output_path=output_path,
            rounded_style=rounded_style,
            layout=subtitle_layout,
            crf=crf,
            preset=preset,
            progress_callback=progress_callback,
        )
    else:
        # ASS style mode
        render_ass_video(
            video_path=video_path,
            asr_data=asr_data,
            output_path=output_path,
            style_str=ass_style,
            layout=subtitle_layout,
            crf=crf,
            preset=preset,
            progress_callback=progress_callback,
        )

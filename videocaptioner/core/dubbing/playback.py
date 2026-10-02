"""Explicit playback rates, cancellable media rendering and source-bound captions."""

from __future__ import annotations

import hashlib
import math
import shutil
import subprocess
import tempfile
from copy import deepcopy
from pathlib import Path

from videocaptioner.core.asr.alignment.audio import stop_process
from videocaptioner.core.asr.asr_data import ASRData, ASRDataSeg
from videocaptioner.core.dubbing.audio_mixer import _has_audio_stream
from videocaptioner.core.dubbing.cache import PersistentTTSCache, measure_audio_duration
from videocaptioner.core.dubbing.config import DubbingConfig
from videocaptioner.core.dubbing.models import (
    DubbingFitStatus,
    DubbingTimingMode,
    UnresolvedFitPolicy,
)
from videocaptioner.core.utils.subprocess_helper import _NO_WINDOW, child_environment


def validate_rates(voice_tempo: float, video_speed: float) -> None:
    for name, value, low, high in (("Voice tempo", voice_tempo, 1.0, 1.2),
                                   ("Video speed", video_speed, .5, 1.0)):
        if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
            raise ValueError(f"{name} must be between {low:.2f} and {high:.2f}")


def playback_config(config: DubbingConfig) -> DubbingConfig:
    validate_rates(config.voice_tempo, config.video_speed)
    if config.subtitle_mode not in ("none", "soft", "hard"):
        raise ValueError("Playback subtitles must be none, soft or hard")
    if config.voice_tempo == config.video_speed == 1:
        return config
    result = deepcopy(config)
    if config.voice_tempo != 1 or config.video_speed != 1:
        result.timing_mode = DubbingTimingMode.NATURAL
        result.unresolved_policy = UnresolvedFitPolicy.SEQUENTIAL
        result.natural_max_speed = 1.0
        result.rewrite_enabled = False
        if result.tts_config:
            result.tts_config.speed = 1.0
    return result


def run_media(command: list[str], callback, message: str) -> None:
    """Poll cancellation while retaining stderr without filling a pipe."""
    with tempfile.TemporaryFile() as log:
        process = subprocess.Popen(command, env=child_environment(), stdout=subprocess.DEVNULL,
                                   stderr=log, creationflags=_NO_WINDOW)
        try:
            while True:
                callback(70, message)
                try:
                    code = process.wait(timeout=.2)
                    break
                except subprocess.TimeoutExpired:
                    pass
            if code:
                log.seek(0)
                detail = log.read().decode("utf-8", errors="replace")[-1500:]
                raise RuntimeError(f"Media rendering failed ({code}): {detail}")
            callback(70, message)
        finally:
            if process.poll() is None:
                stop_process(process)


def apply_voice_tempo(groups, config: DubbingConfig, cache: PersistentTTSCache, directory: Path, callback) -> None:
    """Keep native cache keys; derived WAVs have their own content/rate identity."""
    if config.voice_tempo == 1:
        return
    derived = PersistentTTSCache(cache.root / "playback-v1", enabled=config.cache_enabled)
    directory.mkdir(parents=True, exist_ok=True)
    for group in groups:
        callback(65, "Đang áp dụng tempo giọng đã chọn...")
        source = Path(group.audio_path)
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        key = hashlib.sha256(f"atempo-v1:{digest}:{config.voice_tempo:.4f}".encode()).hexdigest()
        entry = derived.get(key)
        if entry is None:
            target = directory / f"{key}.wav"
            run_media(["ffmpeg", "-nostdin", "-v", "error", "-i", str(source), "-af",
                       f"atempo={config.voice_tempo:.4f}", "-y", str(target)], callback,
                      "Đang đổi tempo; giữ nguyên lời đọc...")
            if measure_audio_duration(target) <= 0:
                raise RuntimeError("Tempo processing produced an empty WAV")
            entry = derived.put(key, target, provider="playback", model="atempo-v1", voice="",
                                sample_rate=config.tts_config.sample_rate if config.tts_config else 24000)
            group.audio_path = entry.audio_path if entry else str(target)
        else:
            group.audio_path = entry.audio_path
        group.measured_duration = measure_audio_duration(group.audio_path)
        group.applied_speed = config.voice_tempo
        group.action_taken = "+".join(filter(None, (group.action_taken, f"speed_adjust_{config.voice_tempo:.3f}x")))
        group.fit_status = DubbingFitStatus.SPEED_ADJUSTED


def retime_video(source: str, output: Path, speed: float, callback) -> str:
    if speed == 1:
        return source
    command = ["ffmpeg", "-nostdin", "-v", "error", "-itsscale", f"{1 / speed:.12f}", "-i", source]
    if _has_audio_stream(source):
        command += ["-i", source, "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy",
                    "-af", f"atempo={speed:.4f},apad", "-c:a", "aac", "-b:a", "192k", "-shortest"]
    else:
        command += ["-map", "0:v:0", "-c:v", "copy", "-an"]
    run_media(command + ["-y", str(output)], callback, "Đang áp dụng tốc độ video...")
    return str(output)


def playback_captions(plan) -> ASRData:
    """One event per whole speech group; never invent internal word timing."""
    segments = []
    for group in plan.groups:
        start = group.playback_start_time
        end = group.playback_end_time
        if start is None or end is None or end <= start:
            raise ValueError("Playback captions require measured speech timing")
        segments.append(ASRDataSeg(group.tts_text, round(start * 1000), round(end * 1000), cue_id=group.group_id))
    return ASRData(segments)


def render_captions(source: str, output: Path, subtitles: Path, config: DubbingConfig, callback) -> None:
    from videocaptioner.core.subtitle.style_manager import SubtitleStyle
    from videocaptioner.core.utils.video_utils import auto_wrap_ass_file, check_cuda_available

    command = ["ffmpeg", "-nostdin", "-v", "error", "-i", source]
    if config.subtitle_mode == "soft":
        command += ["-i", str(subtitles), "-map", "0:v:0", "-map", "0:a?", "-map", "1:0",
                    "-c", "copy", "-c:s", "mov_text", "-metadata:s:s:0", "language=vie",
                    "-disposition:s:0", "default"]
    else:
        rendered = subtitles.with_suffix(".ass")
        style = config.subtitle_style or SubtitleStyle(
            name="Playback", font_name="Arial", font_size=40, primary_color="#FFFFFF",
            outline_color="#000000", outline_width=1.4, bold=False, spacing=0,
        ).to_ass_string(margin_l=80, margin_r=80, margin_v=18)
        ASRData.from_subtitle_file(str(subtitles)).to_ass(style_str=style, save_path=str(rendered),
                                                        video_width=1920, video_height=1080)
        rendered = Path(auto_wrap_ass_file(str(rendered)))
        escaped = rendered.as_posix().replace(":", r"\:").replace("'", r"\'")
        # Opaque black boxes cover source captions without changing the user's font/placement.
        box = "BorderStyle=3,OutlineColour=&H00000000,BackColour=&H00000000,Outline=6,Shadow=0"
        command += ["-map", "0:v:0", "-map", "0:a?", "-vf",
                    f"subtitles='{escaped}':force_style='{box}'", "-c:a", "copy"]
        if check_cuda_available():
            command += ["-c:v", "h264_nvenc", "-preset", "p5", "-cq", "20", "-b:v", "0"]
        else:
            command += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20"]
        command += ["-pix_fmt", "yuv420p", "-fps_mode", "passthrough"]
    run_media(command + ["-movflags", "+faststart", "-y", str(output)], callback,
              "Đang xuất phụ đề theo lời đọc...")


def publish_captions(staged: Path, output: str) -> str:
    """Keep sidecars separate from automatic player subtitle discovery."""
    target = Path(output)
    directory = target.with_name(target.stem + "-subtitles")
    index = 1
    while directory.exists():
        directory = target.with_name(target.stem + f"-subtitles-{index}")
        index += 1
    directory.mkdir()
    destination = directory / "playback.srt"
    shutil.copy2(staged, destination)
    return str(destination)

"""FFmpeg audio utilities for dubbing.

Provides functions to:
- Get audio duration via ffprobe
- Adjust audio playback speed via atempo filter
- Build a full-length voice track from TTS segments (adelay + amix), with
  short fades at each segment edge to avoid clicks
- Mix voice track into original video audio (with voice loudness
  normalization, optional boost, and a final limiter to avoid clipping)
"""

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import List

from videocaptioner.core.dubbing.config import AudioMixMode
from videocaptioner.core.utils.logger import setup_logger

logger = setup_logger("dubbing.audio_mixer")

_FFMPEG_CREATE_FLAGS = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0

# Số segment tối đa trộn trong một lần gọi ffmpeg (giới hạn độ dài command line
# và số input). Video dài nhiều câu sẽ được chia batch rồi trộn lại.
_MAX_INPUTS_PER_PASS = 50

# Độ dài fade in/out ở mỗi mép segment (giây) để khử click/pop.
_EDGE_FADE_S = 0.008

# Tham số loudnorm mục tiêu cho giọng lồng tiếng.
_LOUDNORM_I = -16.0
_LOUDNORM_TP = -1.5
_LOUDNORM_LRA = 11.0


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

    Cách dựng: mỗi segment được giải mã về PCM cùng sample rate/mono, thêm
    fade in/out ngắn để khử click, rồi đặt vào đúng mốc thời gian bằng
    `adelay` và trộn chồng bằng `amix` (normalize=0). Cách này tránh hoàn
    toàn việc trộn các định dạng khác nhau (PCM/MP3) như khi dùng concat
    demuxer — vốn gây tiếng "xoẹt"/click ở ranh giới các đoạn.

    Args:
        segment_infos: Danh sách segment (không bắt buộc sắp xếp).
        total_duration_s: Tổng thời lượng video (giây).
        output_path: Đường dẫn voice track đầu ra.
        sample_rate: Sample rate của output.

    Returns:
        True nếu thành công.
    """
    valid = [
        s for s in segment_infos
        if s.get("audio_path") and Path(s["audio_path"]).is_file()
    ]
    if not valid:
        logger.warning("Không có segment hợp lệ để build voice track")
        return False

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    if len(valid) <= _MAX_INPUTS_PER_PASS:
        return _render_voice_track(valid, total_duration_s, output_path, sample_rate)

    # Quá nhiều segment: chia batch, render từng batch thành track full-length
    # (im lặng ở các đoạn không có segment), rồi amix các batch lại.
    temp_dir = Path(tempfile.mkdtemp(prefix="vc_dub_track_"))
    try:
        batch_tracks: List[str] = []
        for bi, start in enumerate(range(0, len(valid), _MAX_INPUTS_PER_PASS)):
            chunk = valid[start:start + _MAX_INPUTS_PER_PASS]
            btrack = str(temp_dir / f"batch_{bi:03d}.wav")
            if _render_voice_track(chunk, total_duration_s, btrack, sample_rate):
                batch_tracks.append(btrack)
        if not batch_tracks:
            return False
        if len(batch_tracks) == 1:
            shutil.copy2(batch_tracks[0], output_path)
            return True
        return _mix_full_tracks(batch_tracks, output_path, sample_rate)
    finally:
        shutil.rmtree(str(temp_dir), ignore_errors=True)


def mix_audio_tracks(
    video_path: str,
    voice_track_path: str,
    output_path: str,
    mix_mode: AudioMixMode = AudioMixMode.REDUCE_ORIGINAL,
    original_volume: float = 0.2,
    voice_volume: float = 1.0,
) -> bool:
    """Mix voice track vào video, xử lý audio gốc theo mix_mode.

    Giọng lồng tiếng được chuẩn hóa độ to (loudnorm) rồi nhân thêm hệ số
    voice_volume; output qua alimiter để tránh vỡ tiếng (clipping).

    Args:
        video_path: Video gốc (có audio).
        voice_track_path: Voice track đã tạo.
        output_path: Video đầu ra.
        mix_mode: Chế độ xử lý audio gốc.
        original_volume: Âm lượng audio gốc (0.0-1.0) khi REDUCE.
        voice_volume: Hệ số khuếch đại giọng lồng (1.0 = giữ nguyên sau loudnorm).

    Returns:
        True nếu thành công.
    """
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    vv = max(0.1, float(voice_volume))
    # Chuẩn hóa độ to giọng lồng (two-pass nếu đo được) + boost theo người dùng.
    loudnorm = _loudnorm_filter(voice_track_path)
    voice_chain = f"[1:a]{loudnorm},volume={vv:.3f}[voice]"
    # Limiter cuối để chống clipping khi giọng + nền cộng dồn.
    limiter = "[mixed]alimiter=limit=0.95[aout]"

    if mix_mode == AudioMixMode.MUTE_ORIGINAL:
        # Thay hoàn toàn audio bằng voice track (đã chuẩn hóa + limiter).
        # apad + -shortest: nếu audio ngắn hơn video thì đệm im lặng tới hết
        # video (không cắt video); nếu dài hơn thì cắt theo video.
        filter_complex = (
            f"[1:a]{loudnorm},volume={vv:.3f},"
            f"apad,alimiter=limit=0.95[aout]"
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
    elif mix_mode == AudioMixMode.REDUCE_ORIGINAL:
        vol = max(0.0, min(1.0, original_volume))
        # normalize=0: giữ nguyên âm lượng từng input (không bị chia đôi).
        filter_complex = (
            f"[0:a]volume={vol:.3f}[orig];"
            f"{voice_chain};"
            f"[orig][voice]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[mixed];"
            f"{limiter}"
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
        # KEEP_ORIGINAL: giữ nguyên audio gốc, trộn với giọng lồng
        filter_complex = (
            f"{voice_chain};"
            f"[0:a][voice]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[mixed];"
            f"{limiter}"
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

def _loudnorm_filter(audio_path: str) -> str:
    """Tạo chuỗi filter loudnorm cho giọng lồng tiếng.

    Chạy two-pass: pass 1 phân tích độ to của voice track (print_format=json),
    pass 2 (dùng trong filter_complex) áp dụng với các giá trị measured_* +
    linear=true cho kết quả chính xác và ổn định hơn one-pass. Nếu phân tích
    thất bại thì fallback về one-pass.

    Args:
        audio_path: Voice track cần đo.

    Returns:
        Chuỗi filter loudnorm (không gồm input/output label).
    """
    base = f"loudnorm=I={_LOUDNORM_I}:TP={_LOUDNORM_TP}:LRA={_LOUDNORM_LRA}"
    stats = _measure_loudnorm(audio_path)
    if not stats:
        logger.warning("Loudnorm one-pass (không đo được số liệu): %s", audio_path)
        return base
    return (
        f"{base}"
        f":measured_I={stats['input_i']}"
        f":measured_TP={stats['input_tp']}"
        f":measured_LRA={stats['input_lra']}"
        f":measured_thresh={stats['input_thresh']}"
        f":offset={stats['target_offset']}"
        f":linear=true"
    )


def _measure_loudnorm(audio_path: str) -> dict | None:
    """Pass 1 loudnorm: đo số liệu độ to, trả về dict hoặc None nếu lỗi.

    ffmpeg in JSON ra stderr ở cuối quá trình phân tích.
    """
    cmd = [
        "ffmpeg",
        "-i", audio_path,
        "-af",
        f"loudnorm=I={_LOUDNORM_I}:TP={_LOUDNORM_TP}:LRA={_LOUDNORM_LRA}:print_format=json",
        "-f", "null",
        "-",
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
    except Exception as e:
        logger.warning("Loudnorm measure error: %s", e)
        return None

    stderr = result.stderr or ""
    start = stderr.rfind("{")
    end = stderr.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        data = json.loads(stderr[start:end + 1])
    except json.JSONDecodeError:
        return None

    required = ("input_i", "input_tp", "input_lra", "input_thresh", "target_offset")
    if not all(k in data for k in required):
        return None
    # Giá trị im lặng/không hợp lệ (-inf, nan) → không dùng được two-pass.
    for k in required:
        try:
            v = float(data[k])
        except (TypeError, ValueError):
            return None
        if v != v or v in (float("inf"), float("-inf")):
            return None
    return {k: data[k] for k in required}


def _render_voice_track(
    segments: List[dict],
    total_duration_s: float,
    output_path: str,
    sample_rate: int,
) -> bool:
    """Dựng một track full-length từ <= _MAX_INPUTS_PER_PASS segment.

    Mỗi segment: aresample về sample_rate mono, fade in/out, adelay tới đúng
    mốc, rồi amix. Pad/trim về đúng total_duration_s.
    """
    inputs: List[str] = []
    filters: List[str] = []
    labels: List[str] = []

    inp_idx = 0
    for seg in segments:
        audio_path = seg["audio_path"]
        dur = get_audio_duration(audio_path)
        if dur <= 0:
            continue
        start = max(0.0, float(seg.get("start_time", 0.0)))
        delay_ms = int(round(start * 1000))
        fade = max(0.001, min(_EDGE_FADE_S, dur / 2.0))
        out_start = max(0.0, dur - fade)

        inputs += ["-i", audio_path]
        filters.append(
            f"[{inp_idx}:a]aresample={sample_rate},"
            f"aformat=sample_fmts=s16:channel_layouts=mono,"
            f"afade=t=in:st=0:d={fade:.4f},"
            f"afade=t=out:st={out_start:.4f}:d={fade:.4f},"
            f"adelay={delay_ms}:all=1[s{inp_idx}]"
        )
        labels.append(f"[s{inp_idx}]")
        inp_idx += 1

    if not labels:
        logger.error("_render_voice_track: không có segment hợp lệ")
        return False

    n = len(labels)
    total = max(0.0, float(total_duration_s))
    if n == 1:
        graph = (
            ";".join(filters)
            + f";{labels[0]}apad=whole_dur={total:.3f},atrim=0:{total:.3f}[out]"
        )
    else:
        graph = (
            ";".join(filters)
            + ";"
            + "".join(labels)
            + f"amix=inputs={n}:normalize=0:dropout_transition=0[mx];"
            + f"[mx]apad=whole_dur={total:.3f},atrim=0:{total:.3f}[out]"
        )

    # Đưa filter graph vào file để không bị giới hạn độ dài command line.
    filt_dir = Path(tempfile.mkdtemp(prefix="vc_dub_filt_"))
    try:
        script_path = filt_dir / "filter.txt"
        script_path.write_text(graph, encoding="utf-8")
        cmd = [
            "ffmpeg",
            *inputs,
            "-filter_complex_script", str(script_path),
            "-map", "[out]",
            "-ac", "1",
            "-ar", str(sample_rate),
            "-y",
            output_path,
        ]
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
        logger.error(
            "_render_voice_track failed: %s",
            result.stderr[-800:] if result.stderr else "",
        )
        return False
    finally:
        shutil.rmtree(str(filt_dir), ignore_errors=True)


def _mix_full_tracks(
    track_paths: List[str],
    output_path: str,
    sample_rate: int,
) -> bool:
    """Trộn nhiều track full-length (cùng độ dài) thành một, amix normalize=0."""
    inputs: List[str] = []
    labels: List[str] = []
    for i, p in enumerate(track_paths):
        inputs += ["-i", p]
        labels.append(f"[{i}:a]")

    graph = (
        "".join(labels)
        + f"amix=inputs={len(track_paths)}:normalize=0:dropout_transition=0[out]"
    )
    cmd = [
        "ffmpeg",
        *inputs,
        "-filter_complex", graph,
        "-map", "[out]",
        "-ac", "1",
        "-ar", str(sample_rate),
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
        if result.returncode == 0 and Path(output_path).is_file():
            return True
        logger.error(
            "_mix_full_tracks failed: %s",
            result.stderr[-500:] if result.stderr else "",
        )
        return False
    except Exception as e:
        logger.exception("_mix_full_tracks error: %s", e)
        return False

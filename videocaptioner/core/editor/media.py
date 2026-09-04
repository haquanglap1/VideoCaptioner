"""FFmpeg-backed editor media operations shared by preview and final export."""

from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import time
from array import array
from copy import deepcopy
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from videocaptioner.config import CACHE_PATH, FONTS_PATH
from videocaptioner.core.dubbing.audio_mixer import build_voice_track, mix_audio_tracks
from videocaptioner.core.dubbing.config import AudioMixMode
from videocaptioner.core.dubbing.engine import DubbingEngine
from videocaptioner.core.utils.installer import ffmpeg_path
from videocaptioner.core.utils.subprocess_helper import child_environment

from .adapters import project_to_tts_asr
from .models import EditorLayer, EditorLayerKind, EditorProject
from .project_store import EditorProjectStore

if TYPE_CHECKING:
    from videocaptioner.core.dubbing.config import DubbingConfig

_CREATE_FLAGS = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0


class EditorMediaError(RuntimeError):
    pass


class EditorRenderCancelled(EditorMediaError):
    """Raised when the caller asked to stop a preview/export run."""


CancelCheck = Callable[[], bool]


@dataclass(frozen=True)
class MediaInfo:
    duration_ms: int
    width: int
    height: int
    fps: float
    has_audio: bool


def _tool_path(name: str) -> str:
    if name == "ffmpeg":
        managed = ffmpeg_path()
        if managed:
            return str(managed)
    candidate = shutil.which(name) or shutil.which(f"{name}.exe")
    if candidate:
        return candidate
    if name == "ffprobe":
        managed_ffmpeg = ffmpeg_path()
        if managed_ffmpeg:
            sibling = Path(managed_ffmpeg).with_name("ffprobe.exe")
            if sibling.is_file():
                return str(sibling)
    raise EditorMediaError(f"Không tìm thấy {name}. Hãy cài FFmpeg và thêm vào PATH.")


def _stop_process(process: subprocess.Popen) -> None:
    """Kill an FFmpeg child that outlived its timeout or was cancelled."""
    for stop in (process.terminate, process.kill):
        try:
            stop()
            process.wait(timeout=5)
            return
        except (OSError, subprocess.TimeoutExpired):
            continue


def _run(
    command: list[str],
    *,
    cwd: Path | None = None,
    timeout: float = 300,
    should_cancel: CancelCheck | None = None,
) -> subprocess.CompletedProcess:
    """Run FFmpeg, polling ``should_cancel`` so long renders stay interruptible."""
    poll_interval = 0.2 if should_cancel else timeout
    deadline = time.monotonic() + timeout
    try:
        process = subprocess.Popen(
            command, env=child_environment(),
            cwd=str(cwd) if cwd else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=_CREATE_FLAGS,
        )
    except OSError as exc:
        raise EditorMediaError(f"Không chạy được {Path(command[0]).name}: {exc}") from exc
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            _stop_process(process)
            raise EditorMediaError(f"FFmpeg quá thời gian chờ sau {timeout:.0f} giây")
        try:
            # Retrying communicate() after TimeoutExpired keeps the buffered output.
            stdout, stderr = process.communicate(timeout=min(poll_interval, remaining))
            break
        except subprocess.TimeoutExpired:
            if should_cancel and should_cancel():
                _stop_process(process)
                raise EditorRenderCancelled("Đã hủy render theo yêu cầu")
    if process.returncode != 0:
        message = (stderr or b"").decode("utf-8", errors="replace").strip()
        raise EditorMediaError(message[-4000:] or f"FFmpeg exit code {process.returncode}")
    return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)


def _raise_if_cancelled(should_cancel: CancelCheck | None) -> None:
    if should_cancel and should_cancel():
        raise EditorRenderCancelled("Đã hủy render theo yêu cầu")


def editor_font_file() -> str:
    """Pin drawtext to a bundled font: fontconfig defaults vary per machine."""
    for name in ("NotoSansSC-Regular.ttf", "LXGWWenKai-Regular.ttf"):
        candidate = FONTS_PATH / name
        if candidate.is_file():
            return str(candidate)
    return ""


def probe_media(path: str | Path) -> MediaInfo:
    media_path = Path(path)
    if not media_path.is_file():
        raise FileNotFoundError(f"Video không tồn tại: {media_path}")
    result = _run(
        [
            _tool_path("ffprobe"),
            "-v", "error",
            "-show_entries", "format=duration:stream=index,codec_type,width,height,r_frame_rate",
            "-of", "json",
            str(media_path),
        ],
        timeout=30,
    )
    try:
        payload = json.loads(result.stdout.decode("utf-8", errors="replace"))
    except json.JSONDecodeError as exc:
        raise EditorMediaError("ffprobe trả về metadata không hợp lệ") from exc
    video_stream = next(
        (item for item in payload.get("streams", []) if item.get("codec_type") == "video"), {}
    )
    has_audio = any(item.get("codec_type") == "audio" for item in payload.get("streams", []))
    duration = float(payload.get("format", {}).get("duration", 0.0) or 0.0)
    rate = str(video_stream.get("r_frame_rate", "0/1"))
    try:
        numerator, denominator = rate.split("/", 1)
        fps = float(numerator) / max(float(denominator), 1.0)
    except (TypeError, ValueError, ZeroDivisionError):
        fps = 0.0
    return MediaInfo(
        duration_ms=max(0, int(round(duration * 1000))),
        width=int(video_stream.get("width", 0) or 0),
        height=int(video_stream.get("height", 0) or 0),
        fps=fps,
        has_audio=has_audio,
    )


def media_fingerprint(path: str | Path) -> str:
    media_path = Path(path).resolve()
    stat = media_path.stat()
    payload = f"editor-media-v1\0{media_path}\0{stat.st_size}\0{stat.st_mtime_ns}"
    return hashlib.sha256(payload.encode("utf-8", errors="replace")).hexdigest()


class EditorMediaCache:
    def __init__(self, root: str | Path | None = None):
        self.root = Path(root) if root else CACHE_PATH / "editor_media" / "v1"

    def media_dir(self, fingerprint: str) -> Path:
        return self.root / fingerprint

    def load_waveform(self, fingerprint: str) -> tuple[list[float], float] | None:
        path = self.media_dir(fingerprint) / "waveform.json"
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return [float(item) for item in data["samples"]], float(data["duration_s"])
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            return None

    def save_waveform(self, fingerprint: str, samples: list[float], duration_s: float) -> None:
        directory = self.media_dir(fingerprint)
        directory.mkdir(parents=True, exist_ok=True)
        EditorProjectStore._atomic_write(
            directory / "waveform.json",
            json.dumps(
                {"samples": [round(float(item), 6) for item in samples], "duration_s": duration_s},
                separators=(",", ":"),
            ),
        )

    def thumbnail_dir(self, fingerprint: str) -> Path:
        return self.media_dir(fingerprint) / "thumbnails"

    def load_thumbnails(self, fingerprint: str) -> list[tuple[float, str]] | None:
        directory = self.thumbnail_dir(fingerprint)
        manifest = directory / "manifest.json"
        if not manifest.is_file():
            return None
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
            items = [
                (float(item["time_s"]), str(directory / item["file"]))
                for item in data.get("items", [])
            ]
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            return None
        return items if items and all(Path(path).is_file() for _, path in items) else None


def build_waveform(
    video_path: str | Path,
    *,
    cache: EditorMediaCache | None = None,
    bucket_limit: int = 2000,
) -> tuple[str, list[float], float]:
    fingerprint = media_fingerprint(video_path)
    cache = cache or EditorMediaCache()
    cached = cache.load_waveform(fingerprint)
    if cached:
        return fingerprint, cached[0], cached[1]
    info = probe_media(video_path)
    if not info.has_audio:
        duration_s = info.duration_ms / 1000.0
        cache.save_waveform(fingerprint, [], duration_s)
        return fingerprint, [], duration_s
    result = _run(
        [
            _tool_path("ffmpeg"), "-v", "error", "-i", str(video_path),
            "-vn", "-ac", "1", "-ar", "800", "-f", "s16le", "pipe:1",
        ],
        timeout=180,
    )
    samples = array("h")
    samples.frombytes(result.stdout)
    if sys.byteorder != "little":
        samples.byteswap()
    duration_s = info.duration_ms / 1000.0
    if not samples:
        envelope: list[float] = []
    else:
        bucket_count = min(max(240, int(duration_s * 8)), max(240, int(bucket_limit)))
        bucket_size = max(1, math.ceil(len(samples) / bucket_count))
        envelope = []
        for offset in range(0, len(samples), bucket_size):
            chunk = samples[offset : offset + bucket_size]
            peak = max((abs(value) for value in chunk), default=0) / 32768.0
            envelope.append(min(1.0, max(0.0, peak**0.85)))
    cache.save_waveform(fingerprint, envelope, duration_s)
    return fingerprint, envelope, duration_s


def build_thumbnails(
    video_path: str | Path,
    *,
    duration_ms: int | None = None,
    cache: EditorMediaCache | None = None,
    max_count: int = 120,
) -> tuple[str, list[tuple[float, str]]]:
    fingerprint = media_fingerprint(video_path)
    cache = cache or EditorMediaCache()
    cached = cache.load_thumbnails(fingerprint)
    if cached:
        return fingerprint, cached
    duration_s = (duration_ms or probe_media(video_path).duration_ms) / 1000.0
    if duration_s <= 0:
        return fingerprint, []
    count = max(1, min(int(max_count), max(12, math.ceil(duration_s / 20.0))))
    interval = duration_s / count
    directory = cache.thumbnail_dir(fingerprint)
    directory.mkdir(parents=True, exist_ok=True)
    items: list[tuple[float, str]] = []
    for index in range(count):
        timestamp = min(max(0.0, duration_s - 0.05), index * interval)
        output = directory / f"thumb-{index:03d}.jpg"
        if not output.is_file():
            _run(
                [
                    _tool_path("ffmpeg"), "-v", "error", "-ss", f"{timestamp:.3f}",
                    "-i", str(video_path), "-frames:v", "1", "-q:v", "4",
                    "-vf", "scale=180:-1:force_original_aspect_ratio=decrease", "-y", str(output),
                ],
                timeout=30,
            )
        if output.is_file() and output.stat().st_size:
            items.append((timestamp, str(output)))
    EditorProjectStore._atomic_write(
        directory / "manifest.json",
        json.dumps(
            {
                "fingerprint": fingerprint,
                "items": [
                    {"time_s": round(timestamp, 6), "file": Path(path).name}
                    for timestamp, path in items
                ],
            },
            indent=2,
        ),
    )
    return fingerprint, items


def _escape_filter_path(path: str) -> str:
    return path.replace("\\", "/").replace(":", r"\:").replace("'", r"\'")


def _escape_filter_value(value: str) -> str:
    return value.replace("\\", r"\\").replace("'", r"\'").replace(":", r"\:")


def _enable(layer: EditorLayer, *, offset_ms: int = 0) -> str:
    start = max(0.0, (layer.start_ms - offset_ms) / 1000.0)
    end = max(start, (layer.end_ms - offset_ms) / 1000.0)
    return f"between(t,{start:.3f},{end:.3f})"


def build_visual_filter_graph(
    project: EditorProject,
    run_dir: Path,
    *,
    include_subtitles: bool = True,
    offset_ms: int = 0,
    frame_width: int = 0,
    frame_height: int = 0,
) -> tuple[list[str], str, str]:
    """Return extra input args, filter graph and output label for preview/export.

    ``frame_width``/``frame_height`` come from the rendered source so logo scaling
    and blur radii never fall back to a guessed resolution.
    """
    frame_width = int(frame_width or project.width or 1920)
    frame_height = int(frame_height or project.height or 1080)
    font_file = editor_font_file()
    filters: list[str] = []
    current = "v0"
    subtitle_track = next((track for track in project.tracks if track.id == "track-ts1"), None)
    if include_subtitles and (subtitle_track is None or subtitle_track.visible):
        srt_path = _escape_filter_path(str(run_dir / "display.srt"))
        filters.append(f"[0:v]subtitles='{srt_path}'[{current}]")
    else:
        filters.append(f"[0:v]null[{current}]")

    extra_inputs: list[str] = []
    logo_input_index = 1
    visual_track = next((track for track in project.tracks if track.id == "track-fx1"), None)
    layers = [] if visual_track is not None and not visual_track.visible else project.layers
    for layer_index, layer in enumerate(layers):
        if not layer.visible:
            continue
        next_label = f"v{layer_index + 1}"
        enable = _enable(layer, offset_ms=offset_ms)
        # Keep the box inside the frame: crop/drawbox reject regions that run past the edge.
        box_x = min(max(0.0, layer.x), 0.999)
        box_y = min(max(0.0, layer.y), 0.999)
        box_w = max(0.001, min(layer.width, 1.0 - box_x))
        box_h = max(0.001, min(layer.height, 1.0 - box_y))
        if layer.kind == EditorLayerKind.TEXT:
            text_file = run_dir / f"text-{layer.id}.txt"
            text_file.write_text(str(layer.properties.get("text", "")), encoding="utf-8")
            size = max(8, int(layer.properties.get("font_size", 42)))
            color = _escape_filter_value(str(layer.properties.get("font_color", "white")))
            outline = _escape_filter_value(str(layer.properties.get("outline_color", "black")))
            # Centre the text inside the layer box so export matches the preview overlay.
            x_expr = f"(w*{box_x:.6f})+(w*{box_w:.6f}-text_w)/2"
            y_expr = f"(h*{box_y:.6f})+(h*{box_h:.6f}-text_h)/2"
            font_arg = f"fontfile='{_escape_filter_path(font_file)}':" if font_file else ""
            filters.append(
                f"[{current}]drawtext={font_arg}"
                f"textfile='{_escape_filter_path(str(text_file))}':"
                f"fontsize={size}:fontcolor={color}@{layer.opacity:.3f}:"
                f"borderw={max(0, int(layer.properties.get('outline_width', 2)))}:"
                f"bordercolor={outline}:x='{x_expr}':y='{y_expr}':enable='{enable}'[{next_label}]"
            )
        elif layer.kind == EditorLayerKind.LOGO:
            image_path = str(layer.properties.get("path", ""))
            if not image_path or not Path(image_path).is_file():
                raise EditorMediaError(f"Logo layer thiếu file ảnh: {layer.name or layer.id}")
            extra_inputs.extend(["-loop", "1", "-i", image_path])
            logo_label = f"logo{layer_index}"
            target_width = max(1, int(frame_width * box_w))
            filters.append(
                f"[{logo_input_index}:v]scale={target_width}:-1,format=rgba,"
                f"colorchannelmixer=aa={layer.opacity:.3f}[{logo_label}]"
            )
            filters.append(
                f"[{current}][{logo_label}]overlay=x='main_w*{box_x:.6f}':"
                f"y='main_h*{box_y:.6f}':enable='{enable}':shortest=1[{next_label}]"
            )
            logo_input_index += 1
        elif layer.kind == EditorLayerKind.MASK and str(layer.properties.get("mode", "solid")) == "solid":
            color = _escape_filter_value(str(layer.properties.get("color", "black")))
            filters.append(
                f"[{current}]drawbox=x='iw*{box_x:.6f}':y='ih*{box_y:.6f}':"
                f"w='iw*{box_w:.6f}':h='ih*{box_h:.6f}':"
                f"color={color}@{layer.opacity:.3f}:t=fill:enable='{enable}'[{next_label}]"
            )
        else:
            pixelate = layer.kind == EditorLayerKind.MASK and str(
                layer.properties.get("mode", "")
            ) == "pixelate"
            base_label = f"base{layer_index}"
            crop_label = f"crop{layer_index}"
            effect_label = f"effect{layer_index}"
            filters.append(f"[{current}]split=2[{base_label}][{crop_label}]")
            region_w = max(2, int(frame_width * box_w))
            region_h = max(2, int(frame_height * box_h))
            # boxblur caps each plane at half its size, and 4:2:0 chroma is half again,
            # so the usable radius is region/4 - 1. Going over aborts the whole render.
            radius = max(0, min(int(layer.properties.get("strength", 12)), min(region_w, region_h) // 4 - 1))
            effect = (
                "scale='max(1,iw/12)':'max(1,ih/12)':flags=neighbor,"
                "scale='iw*12':'ih*12':flags=neighbor"
                if pixelate
                else f"boxblur={radius}:1"
            )
            if layer.opacity < 0.999:
                effect += f",format=rgba,colorchannelmixer=aa={layer.opacity:.3f}"
            filters.append(
                f"[{crop_label}]crop='trunc(iw*{box_w:.6f}/2)*2':"
                f"'trunc(ih*{box_h:.6f}/2)*2':'iw*{box_x:.6f}':'ih*{box_y:.6f}',"
                f"{effect}[{effect_label}]"
            )
            filters.append(
                f"[{base_label}][{effect_label}]overlay=x='main_w*{box_x:.6f}':"
                f"y='main_h*{box_y:.6f}':enable='{enable}'[{next_label}]"
            )
        current = next_label
    return extra_inputs, ";".join(filters), current


def _shifted_display_srt(project: EditorProject, start_ms: int, end_ms: int) -> str:
    from videocaptioner.core.asr.asr_data import ASRData, ASRDataSeg

    segments = []
    for cue in project.cues:
        if cue.start_ms >= end_ms or cue.end_ms <= start_ms:
            continue
        shifted_start = max(0, cue.start_ms - start_ms)
        shifted_end = min(end_ms, cue.end_ms) - start_ms
        segments.append(ASRDataSeg(cue.display_text, shifted_start, shifted_end))
    return ASRData(segments).to_srt()


def _render_from_project(
    project: EditorProject,
    output_path: str | Path,
    *,
    start_ms: int = 0,
    end_ms: int | None = None,
    include_subtitles: bool = True,
    source_video: str | None = None,
    force_audio_map: bool = False,
    callback: Callable[[int, str], None] | None = None,
    should_cancel: CancelCheck | None = None,
) -> str:
    callback = callback or (lambda _progress, _message: None)
    output = Path(output_path).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    end_ms = project.duration_ms if end_ms is None else min(project.duration_ms, int(end_ms))
    start_ms = max(0, int(start_ms))
    if end_ms <= start_ms:
        raise ValueError("Preview/export range is empty")
    source = str(source_video or project.video_path)
    if Path(source).resolve() == output:
        raise ValueError("Editor export cannot overwrite the input video")
    _raise_if_cancelled(should_cancel)
    frame_width, frame_height = project.width, project.height
    if project.layers and not (frame_width and frame_height):
        probed = probe_media(source)
        frame_width, frame_height = probed.width, probed.height
    with tempfile.TemporaryDirectory(prefix="vc_editor_render_") as temp_dir:
        run_dir = Path(temp_dir)
        EditorProjectStore._atomic_write(
            run_dir / "display.srt",
            _shifted_display_srt(project, start_ms, end_ms),
        )
        extra_inputs, graph, output_label = build_visual_filter_graph(
            project,
            run_dir,
            include_subtitles=include_subtitles,
            offset_ms=start_ms,
            frame_width=frame_width,
            frame_height=frame_height,
        )
        command = [_tool_path("ffmpeg"), "-v", "error", "-y"]
        if start_ms:
            command.extend(["-ss", f"{start_ms / 1000.0:.3f}"])
        command.extend(["-i", source])
        command.extend(extra_inputs)
        command.extend(
            [
                "-filter_complex", graph,
                "-map", f"[{output_label}]",
            ]
        )
        audio_track = next((track for track in project.tracks if track.id == "track-a1"), None)
        if force_audio_map or audio_track is None or not audio_track.muted:
            command.extend(["-map", "0:a?"])
        command.extend(
            [
                "-t", f"{(end_ms - start_ms) / 1000.0:.3f}",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                "-c:a", "aac", "-movflags", "+faststart", str(output),
            ]
        )
        callback(20, "Đang render từ editor state hiện tại...")
        _run(
            command,
            cwd=run_dir,
            timeout=max(120, (end_ms - start_ms) / 1000.0 * 4),
            should_cancel=should_cancel,
        )
    if not output.is_file() or output.stat().st_size <= 0:
        raise EditorMediaError("FFmpeg không tạo video đầu ra")
    callback(100, "Render hoàn tất")
    return str(output)


def fast_preview_range(project: EditorProject, *, window_ms: int = 5000) -> tuple[int, int]:
    if (
        project.selection_start_ms is not None
        and project.selection_end_ms is not None
        and project.selection_end_ms > project.selection_start_ms
    ):
        return project.selection_start_ms, project.selection_end_ms
    half = max(500, int(window_ms) // 2)
    start = max(0, project.playhead_ms - half)
    end = min(project.duration_ms, start + max(1000, int(window_ms)))
    start = max(0, end - max(1000, int(window_ms)))
    return start, end


def cleanup_preview_files(directory: str | Path, *, keep: str = "") -> int:
    """Drop stale Fast Preview renders; the player may still lock the newest one."""
    folder = Path(directory)
    if not folder.is_dir():
        return 0
    keep_path = Path(keep).resolve() if keep else None
    removed = 0
    for candidate in folder.glob("preview-*.mp4"):
        if keep_path and candidate.resolve() == keep_path:
            continue
        try:
            candidate.unlink()
            removed += 1
        except OSError:
            continue  # still open in the player; the next run retries
    return removed


def render_fast_preview(
    project: EditorProject,
    output_path: str | Path,
    *,
    callback: Callable[[int, str], None] | None = None,
    should_cancel: CancelCheck | None = None,
) -> str:
    start_ms, end_ms = fast_preview_range(project)
    voice_segments = _existing_voice_segments(project, start_ms, end_ms)
    if not voice_segments:
        return _render_from_project(
            project,
            output_path,
            start_ms=start_ms,
            end_ms=end_ms,
            callback=callback,
            should_cancel=should_cancel,
        )
    with tempfile.TemporaryDirectory(prefix="vc_editor_preview_audio_") as temp_dir:
        base_video = Path(temp_dir) / "preview-base.mp4"
        _render_from_project(
            project,
            base_video,
            start_ms=start_ms,
            end_ms=end_ms,
            callback=lambda progress, message: (callback or (lambda *_: None))(
                int(progress * 0.7), message
            ),
            should_cancel=should_cancel,
        )
        _raise_if_cancelled(should_cancel)
        return _mix_existing_editor_voice(
            project,
            str(base_video),
            output_path,
            voice_segments,
            (end_ms - start_ms) / 1000.0,
            callback=callback,
        )


def export_editor_video(
    project: EditorProject,
    output_path: str | Path,
    *,
    dubbing_config: "DubbingConfig | None" = None,
    callback: Callable[[int, str], None] | None = None,
    engine: DubbingEngine | None = None,
    should_cancel: CancelCheck | None = None,
) -> str:
    """Export from live state, optionally reusing Natural/Legacy dubbing first."""
    callback = callback or (lambda _progress, _message: None)
    _raise_if_cancelled(should_cancel)
    source_video = project.video_path
    with tempfile.TemporaryDirectory(prefix="vc_editor_export_") as temp_dir:
        run_dir = Path(temp_dir)
        subtitle_track = next((track for track in project.tracks if track.id == "track-ts1"), None)
        dubbing_enabled = bool(
            dubbing_config
            and dubbing_config.enabled
            and (subtitle_track is None or not subtitle_track.muted)
        )
        if dubbing_enabled:
            assert dubbing_config is not None
            dubbing_config = deepcopy(dubbing_config)
            audio_track = next((track for track in project.tracks if track.id == "track-a1"), None)
            if audio_track and audio_track.muted:
                dubbing_config.mix_mode = AudioMixMode.MUTE_ORIGINAL
            tts_srt = run_dir / "tts.srt"
            EditorProjectStore._atomic_write(tts_srt, project_to_tts_asr(project).to_srt())
            dubbed_video = run_dir / "dubbed.mp4"
            dubbing_engine = engine or DubbingEngine()
            callback(5, "Đang lồng tiếng từ editor state hiện tại...")
            dubbing_engine.dub(
                project.video_path,
                str(tts_srt),
                str(dubbed_video),
                dubbing_config,
                lambda progress, message: callback(min(70, 5 + int(progress * 0.65)), message),
            )
            source_video = str(dubbed_video)
        _raise_if_cancelled(should_cancel)
        existing_voice = [] if dubbing_enabled else _existing_voice_segments(
            project, 0, project.duration_ms
        )
        render_target = run_dir / "render-base.mp4" if existing_voice else Path(output_path)
        rendered = _render_from_project(
            project,
            render_target,
            source_video=source_video,
            force_audio_map=dubbing_enabled,
            callback=lambda progress, message: callback(
                progress if not dubbing_enabled else 70 + int(progress * 0.3), message
            ),
            should_cancel=should_cancel,
        )
        if existing_voice:
            _raise_if_cancelled(should_cancel)
            return _mix_existing_editor_voice(
                project,
                rendered,
                output_path,
                existing_voice,
                project.duration_ms / 1000.0,
                callback=callback,
            )
        return rendered


def _existing_voice_segments(
    project: EditorProject, start_ms: int, end_ms: int
) -> list[dict[str, object]]:
    subtitle_track = next((track for track in project.tracks if track.id == "track-ts1"), None)
    if subtitle_track and subtitle_track.muted:
        return []
    return [
        {
            "audio_path": cue.audio_path,
            "start_time": max(0, cue.start_ms - start_ms) / 1000.0,
            "end_time": max(0, min(end_ms, cue.end_ms) - start_ms) / 1000.0,
        }
        for cue in project.cues
        if cue.audio_path
        and Path(cue.audio_path).is_file()
        and cue.start_ms < end_ms
        and cue.end_ms > start_ms
    ]


def _mix_existing_editor_voice(
    project: EditorProject,
    base_video: str,
    output_path: str | Path,
    segments: list[dict[str, object]],
    duration_s: float,
    *,
    callback: Callable[[int, str], None] | None = None,
) -> str:
    callback = callback or (lambda _progress, _message: None)
    output = Path(output_path).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="vc_editor_voice_track_") as temp_dir:
        voice_track = Path(temp_dir) / "voice-track.wav"
        sample_rate = int(project.voice_settings.get("sample_rate", 24000) or 24000)
        if not build_voice_track(
            segments,
            max(0.05, float(duration_s)),
            str(voice_track),
            sample_rate=sample_rate,
            normalize=True,
        ):
            raise EditorMediaError("Không dựng được voice track từ audio editor hiện tại")
        audio_track = next((track for track in project.tracks if track.id == "track-a1"), None)
        mix_mode = AudioMixMode.MUTE_ORIGINAL if audio_track and audio_track.muted else AudioMixMode(
            str(project.voice_settings.get("mix_mode", AudioMixMode.REDUCE_ORIGINAL.value))
        )
        callback(82, "Đang mix voice đã tạo lại từ editor state...")
        if not mix_audio_tracks(
            base_video,
            str(voice_track),
            str(output),
            mix_mode=mix_mode,
            original_volume=float(project.voice_settings.get("original_volume", 0.2)),
            voice_volume=float(project.voice_settings.get("voice_volume", 1.0)),
            normalize_voice=False,
        ):
            raise EditorMediaError("Không mix được voice editor vào video")
    callback(100, "Render hoàn tất")
    return str(output)


def media_info_dict(path: str | Path) -> dict[str, object]:
    return asdict(probe_media(path))

"""Tests for audio_mixer — the ffmpeg-facing half of dubbing.

These need a real ffmpeg/ffprobe on PATH and are skipped otherwise: the bugs they
cover are precisely the kind that unit tests with mocked subprocesses cannot see
(a removed ffmpeg CLI option, a filter graph that references a missing stream).
"""

import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from videocaptioner.core.dubbing.audio_mixer import (
    _FFMPEG_CREATE_FLAGS,
    _filter_complex_file_flag,
    _has_audio_stream,
    build_voice_track,
    get_audio_duration,
    mix_audio_tracks,
)
from videocaptioner.core.dubbing.config import AudioMixMode

pytestmark = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="requires ffmpeg and ffprobe on PATH",
)


def _run_ffmpeg(args) -> None:
    result = subprocess.run(
        ["ffmpeg", "-hide_banner", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=_FFMPEG_CREATE_FLAGS,
    )
    assert result.returncode == 0, result.stderr[-800:]


def _make_tone(path: Path, seconds: float, freq: int = 440) -> None:
    _run_ffmpeg([
        "-f", "lavfi", "-i", f"sine=frequency={freq}:duration={seconds}",
        "-ar", "24000", "-ac", "1", "-y", str(path),
    ])


def _make_video(path: Path, seconds: float, with_audio: bool) -> None:
    args = ["-f", "lavfi", "-i", f"testsrc=size=320x240:rate=10:duration={seconds}"]
    if with_audio:
        args += ["-f", "lavfi", "-i", f"sine=frequency=200:duration={seconds}"]
    args += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-t", str(seconds), "-y", str(path)]
    _run_ffmpeg(args)


def test_filter_complex_file_flag_is_accepted_by_ffmpeg():
    """The chosen flag must exist in the installed ffmpeg.

    ffmpeg 8.0 removed -filter_complex_script; using it there aborts with
    "Unrecognized option" and the whole voice track build fails.
    """
    flag = _filter_complex_file_flag()
    assert flag in ("-filter_complex_script", "-/filter_complex")

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        source = tmp_path / "in.wav"
        _make_tone(source, 0.5)
        graph = tmp_path / "graph.txt"
        graph.write_text("[0:a]aresample=24000[out]", encoding="utf-8")
        output = tmp_path / "out.wav"

        result = subprocess.run(
            [
                "ffmpeg", "-hide_banner", "-i", str(source),
                flag, str(graph),
                "-map", "[out]", "-y", str(output),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=_FFMPEG_CREATE_FLAGS,
        )
        assert "Unrecognized option" not in (result.stderr or "")
        assert result.returncode == 0, result.stderr[-800:]
        assert output.is_file()


def test_build_voice_track_batched_path():
    """More than _MAX_INPUTS_PER_PASS segments must still yield one full track."""
    from videocaptioner.core.dubbing.audio_mixer import _MAX_INPUTS_PER_PASS

    total_duration = 60.0
    count = _MAX_INPUTS_PER_PASS + 5

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        infos = []
        for i in range(count):
            seg = tmp_path / f"seg_{i:03d}.wav"
            _make_tone(seg, 0.2, 300 + (i % 5) * 40)
            infos.append(
                {"audio_path": str(seg), "start_time": i * 1.0, "end_time": i * 1.0 + 0.2}
            )

        out = tmp_path / "track.wav"
        assert build_voice_track(infos, total_duration, str(out), sample_rate=24000)
        assert out.is_file()
        assert abs(get_audio_duration(str(out)) - total_duration) < 1.0


def test_mix_falls_back_to_mute_on_video_without_audio():
    """A silent video must not fail: the [0:a] filter has no stream to read."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        video = tmp_path / "silent.mp4"
        _make_video(video, 5, with_audio=False)
        assert _has_audio_stream(str(video)) is False

        voice = tmp_path / "voice.wav"
        _make_tone(voice, 2.0)

        out = tmp_path / "out.mp4"
        assert mix_audio_tracks(
            str(video),
            str(voice),
            str(out),
            mix_mode=AudioMixMode.REDUCE_ORIGINAL,
            normalize_voice=False,
        )
        assert _has_audio_stream(str(out)) is True


def test_has_audio_stream_detects_audio():
    with tempfile.TemporaryDirectory() as tmp:
        video = Path(tmp) / "with_audio.mp4"
        _make_video(video, 3, with_audio=True)
        assert _has_audio_stream(str(video)) is True

"""Tests for core/utils/video_utils.

The parsing and command-building logic runs against a fake ``subprocess``
module so it is checked on every machine; the tests at the bottom drive a real
FFmpeg and skip when none is installed.
"""

import subprocess
import wave
from types import SimpleNamespace

import pytest

from videocaptioner.core.utils import video_utils
from videocaptioner.core.utils.video_utils import (
    VideoChunkPlan,
    _extract_thumbnail,
    add_subtitles,
    check_cuda_available,
    get_video_info,
    plan_video_chunks,
    temporary_subtitle_file,
    video2audio,
)

_MP4_BANNER = """ffmpeg version 6.1 Copyright (c) 2000-2023 the FFmpeg developers
Input #0, mov,mp4,m4a,3gp,3g2,mj2, from 'sample.mp4':
  Metadata:
    major_brand     : isom
  Duration: 00:01:30.50, start: 0.000000, bitrate: 1500 kb/s
  Stream #0:0[0x1](und): Video: h264 (High) (avc1 / 0x31637661), yuv420p(progressive), 1920x1080 [SAR 1:1 DAR 16:9], 1400 kb/s, 29.97 fps, 29.97 tbr, 30k tbn (default)
  Stream #0:1[0x2](eng): Audio: aac (LC) (mp4a / 0x6134706D), 48000 Hz, stereo, fltp, 128 kb/s (default)
  Stream #0:2[0x3](jpn): Audio: aac (LC) (mp4a / 0x6134706D), 44100 Hz, stereo, fltp, 96 kb/s
At least one output file must be specified
"""

_MP3_BANNER = """Input #0, mp3, from 'en.mp3':
  Duration: 00:00:05.20, start: 0.025057, bitrate: 128 kb/s
  Stream #0:0: Audio: mp3, 44100 Hz, mono, fltp, 128 kb/s
At least one output file must be specified
"""


class FakeSubprocess:
    """Stand-in for the ``subprocess`` module inside video_utils.

    Records every ``run``/``Popen`` call so tests can assert on the command
    and keyword arguments without touching a real binary.
    """

    def __init__(self, run_results=None, popen_factory=None):
        self.calls: list[tuple[str, list, dict]] = []
        self._run_results = list(run_results or [])
        self._popen_factory = popen_factory

    def __getattr__(self, name):
        # Constants and exception types keep their real definitions.
        return getattr(subprocess, name)

    def run(self, cmd, **kwargs):
        self.calls.append(("run", list(cmd), kwargs))
        result = self._run_results.pop(0)
        if isinstance(result, BaseException):
            raise result
        if callable(result):
            return result(cmd)
        return result

    def Popen(self, cmd, **kwargs):  # noqa: N802 - mirrors subprocess API
        self.calls.append(("Popen", list(cmd), kwargs))
        return self._popen_factory(cmd, kwargs)


def _completed(stdout="", stderr="", returncode=0):
    return SimpleNamespace(stdout=stdout, stderr=stderr, returncode=returncode)


@pytest.fixture
def fake_subprocess(monkeypatch):
    def install(run_results=None, popen_factory=None):
        fake = FakeSubprocess(run_results, popen_factory)
        monkeypatch.setattr(video_utils, "subprocess", fake)
        return fake

    return install


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


class TestPlanVideoChunks:
    def test_short_video_is_one_chunk(self):
        plan = plan_video_chunks(90.0)
        assert plan == [VideoChunkPlan(1, 0, 90_000, 0, 90_000)]
        assert plan[0].duration_ms == 90_000

    def test_zero_duration_still_yields_one_empty_chunk(self):
        assert plan_video_chunks(0) == [VideoChunkPlan(1, 0, 0, 0, 0)]

    def test_boundaries_and_overlap(self):
        plan = plan_video_chunks(50, chunk_length_seconds=20, overlap_seconds=5)
        assert [(c.start_ms, c.end_ms) for c in plan] == [
            (0, 20_000),
            (20_000, 40_000),
            (40_000, 50_000),
        ]
        assert [(c.source_start_ms, c.source_end_ms) for c in plan] == [
            (0, 25_000),
            (15_000, 45_000),
            (35_000, 50_000),
        ]
        assert [c.index for c in plan] == [1, 2, 3]
        assert plan[1].source_duration_ms == 30_000

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"duration_seconds": -1},
            {"duration_seconds": 10, "chunk_length_seconds": 0},
            {"duration_seconds": 10, "overlap_seconds": -1},
            {"duration_seconds": 10, "chunk_length_seconds": 5, "overlap_seconds": 5},
        ],
    )
    def test_invalid_arguments_raise(self, kwargs):
        with pytest.raises(ValueError):
            plan_video_chunks(**kwargs)


def test_temporary_subtitle_file_copies_and_cleans_up(tmp_path):
    source = tmp_path / "sub.ASS"
    source.write_text("[Script Info]\n", encoding="utf-8")

    with temporary_subtitle_file(str(source)) as temp_path:
        assert temp_path != str(source)
        assert temp_path.lower().endswith(".ass")
        assert open(temp_path, encoding="utf-8").read() == "[Script Info]\n"

    assert not video_utils.Path(temp_path).exists()
    assert source.exists()


# ---------------------------------------------------------------------------
# get_video_info parsing
# ---------------------------------------------------------------------------


class TestGetVideoInfo:
    def test_parses_video_and_all_audio_streams(self, fake_subprocess, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-leak")
        fake = fake_subprocess([_completed(stderr=_MP4_BANNER, returncode=1)])

        info = get_video_info("sample.mp4")

        assert info is not None
        assert (info.width, info.height) == (1920, 1080)
        assert info.fps == pytest.approx(29.97)
        assert info.duration_seconds == pytest.approx(90.5)
        assert info.bitrate_kbps == 1500
        assert info.video_codec == "h264"
        assert (info.audio_codec, info.audio_sampling_rate) == ("aac", 48000)
        assert [(s.index, s.codec, s.language) for s in info.audio_streams] == [
            (1, "aac", "eng"),
            (2, "aac", "jpn"),
        ]
        assert info.thumbnail_path == ""
        assert info.file_name == "sample"

        kind, cmd, kwargs = fake.calls[0]
        assert (kind, cmd) == ("run", ["ffmpeg", "-i", "sample.mp4"])
        assert "OPENAI_API_KEY" not in kwargs["env"]

    def test_audio_only_file_has_zero_video_fields_and_no_thumbnail(
        self, fake_subprocess, tmp_path
    ):
        fake = fake_subprocess([_completed(stderr=_MP3_BANNER, returncode=1)])

        info = get_video_info("en.mp3", thumbnail_path=str(tmp_path / "thumb.jpg"))

        assert info is not None
        assert (info.width, info.height, info.fps) == (0, 0, 0.0)
        assert info.duration_seconds == pytest.approx(5.2)
        assert [(s.index, s.codec, s.language) for s in info.audio_streams] == [(0, "mp3", "")]
        assert info.thumbnail_path == ""
        # No second ffmpeg call for a thumbnail on audio-only input.
        assert len(fake.calls) == 1

    def test_thumbnail_is_requested_at_thirty_percent(self, fake_subprocess, tmp_path):
        thumb = tmp_path / "thumbs" / "t.jpg"
        video = tmp_path / "v.mp4"
        video.write_bytes(b"x")
        fake = fake_subprocess(
            [_completed(stderr=_MP4_BANNER, returncode=1), _completed(returncode=0)]
        )

        info = get_video_info(str(video), thumbnail_path=str(thumb))

        assert info is not None and info.thumbnail_path == str(thumb)
        _, cmd, _ = fake.calls[1]
        assert cmd[:3] == ["ffmpeg", "-ss", "00:00:27.150"]
        assert thumb.parent.is_dir()

    def test_file_without_streams_returns_none(self, fake_subprocess):
        fake_subprocess([_completed(stderr="Invalid data found when processing input", returncode=1)])
        assert get_video_info("broken.bin") is None

    def test_subprocess_failure_returns_none(self, fake_subprocess):
        fake_subprocess([FileNotFoundError("ffmpeg")])
        assert get_video_info("sample.mp4") is None


def test_extract_thumbnail_skips_missing_video(fake_subprocess, tmp_path):
    fake = fake_subprocess()
    assert _extract_thumbnail(str(tmp_path / "missing.mp4"), 1.0, str(tmp_path / "t.jpg")) is False
    assert fake.calls == []


# ---------------------------------------------------------------------------
# video2audio / CUDA probe
# ---------------------------------------------------------------------------


class TestVideo2Audio:
    def test_builds_mono_16k_command_for_selected_track(self, fake_subprocess, tmp_path):
        target = tmp_path / "out" / "audio.wav"

        def create_output(cmd):
            target.write_bytes(b"RIFF")
            return _completed(returncode=0)

        fake = fake_subprocess([create_output])

        assert video2audio("in.mp4", str(target), audio_track_index=1) is True
        _, cmd, kwargs = fake.calls[0]
        assert cmd[:4] == ["ffmpeg", "-i", "in.mp4", "-map"]
        assert cmd[4] == "0:a:1"
        assert cmd[cmd.index("-ac") + 1] == "1"
        assert cmd[cmd.index("-ar") + 1] == "16000"
        assert cmd[-1] == str(target)
        assert kwargs["check"] is True
        assert "env" in kwargs

    def test_ffmpeg_error_is_reported_as_false(self, fake_subprocess, tmp_path):
        error = subprocess.CalledProcessError(1, ["ffmpeg"], stderr="no such track")
        fake_subprocess([error])
        assert video2audio("in.mp4", str(tmp_path / "a.wav")) is False

    def test_missing_output_file_is_false(self, fake_subprocess, tmp_path):
        fake_subprocess([_completed(returncode=0)])
        assert video2audio("in.mp4", str(tmp_path / "never.wav")) is False


class TestCheckCudaAvailable:
    def test_missing_hwaccel_short_circuits(self, fake_subprocess):
        fake = fake_subprocess([_completed(stdout="Hardware acceleration methods:\ndxva2\n")])
        assert check_cuda_available() is False
        assert len(fake.calls) == 1

    def test_device_init_error_is_false(self, fake_subprocess):
        fake_subprocess(
            [
                _completed(stdout="Hardware acceleration methods:\ncuda\n"),
                _completed(stderr="Device creation failed: Cannot load cuda"),
            ]
        )
        assert check_cuda_available() is False

    def test_clean_init_is_true(self, fake_subprocess):
        fake_subprocess(
            [_completed(stdout="cuda\n"), _completed(stderr="")]
        )
        assert check_cuda_available() is True

    def test_exception_is_false(self, fake_subprocess):
        fake_subprocess([OSError("boom")])
        assert check_cuda_available() is False


# ---------------------------------------------------------------------------
# add_subtitles
# ---------------------------------------------------------------------------


class _FakeProcess:
    def __init__(self, stderr_lines, returncode=0):
        self._lines = list(stderr_lines)
        self.returncode = returncode
        self.stderr = self
        self.killed = False

    def readline(self):
        return self._lines.pop(0) if self._lines else ""

    def read(self):
        return "ffmpeg failed"

    def poll(self):
        return None if self._lines else self.returncode

    def wait(self):
        return self.returncode

    def kill(self):
        self.killed = True


class TestAddSubtitles:
    def test_missing_inputs_fail_fast(self, tmp_path):
        with pytest.raises(AssertionError):
            add_subtitles(str(tmp_path / "no.mp4"), str(tmp_path / "no.srt"), str(tmp_path / "o.mp4"))

    def test_soft_subtitles_use_mov_text_stream_copy(self, fake_subprocess, tmp_path):
        video = tmp_path / "in.mp4"
        video.write_bytes(b"v")
        srt = tmp_path / "in.srt"
        srt.write_text("1\n00:00:00,000 --> 00:00:01,000\nhi\n", encoding="utf-8")
        fake = fake_subprocess([_completed(returncode=0)])

        add_subtitles(str(video), str(srt), str(tmp_path / "out.mp4"), soft_subtitle=True)

        _, cmd, kwargs = fake.calls[0]
        assert cmd[cmd.index("-c:s") + 1] == "mov_text"
        assert cmd[cmd.index("-c:v") + 1] == "copy"
        assert cmd[-1] == str(tmp_path / "out.mp4")
        assert "env" in kwargs
        # The subtitle passed to ffmpeg is the temporary copy, already removed.
        assert cmd[4] != str(srt)
        assert not video_utils.Path(cmd[4]).exists()

    def test_hard_subtitles_report_progress_and_use_subtitles_filter(
        self, fake_subprocess, tmp_path
    ):
        video = tmp_path / "in.mp4"
        video.write_bytes(b"v")
        srt = tmp_path / "in.srt"
        srt.write_text("1\n00:00:00,000 --> 00:00:01,000\nhi\n", encoding="utf-8")
        processes = []

        def popen(cmd, kwargs):
            proc = _FakeProcess(
                [
                    "  Duration: 00:00:10.00, start: 0.000000, bitrate: 1 kb/s\n",
                    "frame=  120 fps=0.0 q=28.0 size=N/A time=00:00:05.00 bitrate=N/A\n",
                    "frame=  240 fps=0.0 q=28.0 size=N/A time=00:00:10.00 bitrate=N/A\n",
                ]
            )
            processes.append(proc)
            return proc

        # First run() answers the CUDA probe with "no cuda".
        fake = fake_subprocess([_completed(stdout="dxva2\n")], popen_factory=popen)
        progress = []

        add_subtitles(
            str(video),
            str(srt),
            str(tmp_path / "out.mp4"),
            crf=20,
            preset="fast",
            progress_callback=lambda pct, msg: progress.append(pct),
        )

        kind, cmd, kwargs = fake.calls[-1]
        assert kind == "Popen"
        assert "-hwaccel" not in cmd
        assert cmd[cmd.index("-crf") + 1] == "20"
        assert cmd[cmd.index("-preset") + 1] == "fast"
        assert cmd[cmd.index("-vf") + 1].startswith("subtitles='")
        assert "env" in kwargs
        assert progress[-1] == "100"
        assert "50" in progress

    def test_hard_subtitle_failure_raises(self, fake_subprocess, tmp_path):
        video = tmp_path / "in.mp4"
        video.write_bytes(b"v")
        ass = tmp_path / "in.ass"
        ass.write_text(
            "[Script Info]\n\n[V4+ Styles]\nFormat: Name, Fontname\n"
            "Style: Default,Arial\n\n[Events]\nFormat: Layer, Start, End, Style, Text\n",
            encoding="utf-8",
        )
        fake_subprocess(
            [_completed(stdout="dxva2\n")],
            popen_factory=lambda cmd, kwargs: _FakeProcess([], returncode=1),
        )

        with pytest.raises(Exception, match="Return code: 1"):
            add_subtitles(str(video), str(ass), str(tmp_path / "out.mp4"))


# ---------------------------------------------------------------------------
# Real FFmpeg (skipped when absent)
# ---------------------------------------------------------------------------


class TestWithRealFfmpeg:
    def test_get_video_info_reads_generated_clip(self, silent_video, tmp_path):
        thumb = tmp_path / "thumb.jpg"
        info = get_video_info(str(silent_video), thumbnail_path=str(thumb))

        assert info is not None
        assert (info.width, info.height) == (320, 240)
        assert info.fps == pytest.approx(25, abs=0.5)
        assert info.duration_seconds == pytest.approx(1.0, abs=0.2)
        assert info.video_codec == "h264"
        assert info.audio_codec == "aac"
        assert info.audio_sampling_rate == 48000
        assert len(info.audio_streams) == 1
        assert info.thumbnail_path == str(thumb) and thumb.stat().st_size > 0

    def test_video2audio_produces_mono_16k_wav(self, silent_video, tmp_path):
        target = tmp_path / "nested" / "audio.wav"
        assert video2audio(str(silent_video), str(target)) is True
        with wave.open(str(target)) as wav:
            assert wav.getframerate() == 16000
            assert wav.getnchannels() == 1
            assert wav.getnframes() > 0

    def test_soft_subtitles_are_muxed(self, silent_video, tmp_path):
        srt = tmp_path / "clip.srt"
        srt.write_text("1\n00:00:00,000 --> 00:00:01,000\nhello\n", encoding="utf-8")
        output = tmp_path / "out.mp4"

        add_subtitles(str(silent_video), str(srt), str(output), soft_subtitle=True)

        assert output.stat().st_size > 0

    def test_cuda_probe_does_not_crash(self, ffmpeg):
        assert check_cuda_available() in (True, False)

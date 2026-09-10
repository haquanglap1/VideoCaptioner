"""Bounded RGB/PTS streaming from one owned FFmpeg process, without a frame-rate filter."""

from __future__ import annotations

import json
import math
import os
import queue
import re
import signal
import subprocess
import threading
import time
from contextvars import copy_context
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Iterator

from videocaptioner.core.utils.subprocess_helper import _NO_WINDOW, child_environment

from .geometry import Roi, VideoGeometry
from .models import Check, FrameSpan, OcrError, RoiFrame, Selection, VideoInfo


def stop_owned_process(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       env=child_environment(), creationflags=_NO_WINDOW, timeout=10, check=False)
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    if process.poll() is None:
        process.kill()
    process.wait(timeout=3)


def probe_video(source: Path, ffprobe: str = "ffprobe", check: Check = lambda: None,
                timeout: float = 30) -> VideoInfo:
    check()
    if not source.is_file():
        raise OcrError("OCR source must be a local video file")
    command = [ffprobe, "-v", "error", "-select_streams", "v:0", "-show_entries",
               "stream=index,width,height,time_base,start_pts,sample_aspect_ratio:"
               "stream_tags=rotate:stream_side_data=rotation,displaymatrix:format=start_time",
               "-of", "json", str(source.resolve())]
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                               env=child_environment(), creationflags=_NO_WINDOW,
                               start_new_session=os.name != "nt")
    deadline = time.monotonic() + timeout
    try:
        while True:
            check()
            if time.monotonic() >= deadline:
                raise OcrError("Video probe timed out")
            try:
                data, _ = process.communicate(timeout=0.05)
                break
            except subprocess.TimeoutExpired:
                continue
        if process.returncode or len(data) > 65536:
            raise OcrError("Video probe failed")
        try:
            payload = json.loads(data)
            stream = payload["streams"][0]
            tb = Fraction(stream["time_base"])
            side_data = stream.get("side_data_list", [])
            rotation = float(stream.get("tags", {}).get("rotate", 0))
            for side in side_data:
                rotation = float(side.get("rotation", rotation))
                matrix = side.get("displaymatrix")
                if matrix:
                    values = [int(value) for row in matrix.strip().splitlines()
                              for value in row.split(":", 1)[1].split()]
                    # A pure quarter-turn has unit scale, no mirroring, shear or perspective.
                    if (len(values) != 9 or values[2:3] != [0] or values[5:9] != [0, 0, 0, 1073741824]
                            or any(abs(values[i]) not in (0, 65536) for i in (0, 1, 3, 4))
                            or values[0] * values[4] - values[1] * values[3] != 65536**2):
                        raise ValueError
            if not math.isfinite(rotation) or rotation % 90:
                raise ValueError
            sar = stream.get("sample_aspect_ratio", "1:1")
            if sar in ("N/A", "0:1"):
                sar = "1:1"
            origin = payload.get("format", {}).get("start_time")
            origin = Fraction(origin) if origin is not None else int(stream["start_pts"]) * tb
            return VideoInfo(int(stream["index"]), VideoGeometry(int(stream["width"]),
                             int(stream["height"]), Fraction(sar.replace(":", "/")),
                             int(rotation) % 360), tb, origin)
        except (KeyError, ValueError, IndexError, TypeError, ZeroDivisionError):
            raise OcrError("Missing timing or unsupported video geometry") from None
    finally:
        stop_owned_process(process)
        if process.stdout:
            process.stdout.close()


@dataclass
class DecodeMetrics:
    frames: int = 0
    queue_peak: int = 0
    stderr_lines: int = 0
    process_wall_s: float = 0
    queue_capacity: int = 4
    # Queue (4), producer read/assembly (2), consumer lookahead (2).
    roi_buffer_bound: int = 8


class RoiDecoder:
    """Use as a context manager; early break, error and cancellation always close/join."""

    def __init__(self, source: Path, info: VideoInfo, roi: Roi, *, ffmpeg: str = "ffmpeg",
                 check: Check = lambda: None, timeout: float = 30):
        if timeout <= 0 or not math.isfinite(timeout):
            raise OcrError("Invalid decode timeout")
        self.source, self.info, self.roi = source, info, roi
        self.ffmpeg, self.check, self.timeout = ffmpeg, check, timeout
        self.rect = roi.pixels(*info.geometry.display_size)
        if self.rect.width * self.rect.height * 3 > 32 * 1024 * 1024:
            raise OcrError("OCR ROI exceeds the frame memory limit")
        self.metrics = DecodeMetrics()
        self.process: subprocess.Popen | None = None
        self.readers: list[threading.Thread] = []
        self.frames: queue.Queue[RoiFrame] = queue.Queue(maxsize=4)
        self.metadata: queue.Queue[tuple[int, int, Fraction]] = queue.Queue(maxsize=8)
        self.stop = threading.Event()
        self.stderr_done = threading.Event()
        self.stdout_done = threading.Event()
        self.errors: queue.Queue[str] = queue.Queue(maxsize=1)
        self.started = 0.0
        self.closed = False

    def _fail(self, reason: str) -> None:
        try:
            self.errors.put_nowait(reason)
        except queue.Full:
            pass

    def _put(self, target: queue.Queue, value: object) -> bool:
        while not self.stop.is_set():
            try:
                target.put(value, timeout=0.05)
                return True
            except queue.Full:
                continue
        return False

    def _stderr(self) -> None:
        assert self.process is not None and self.process.stderr is not None
        tb: Fraction | None = None
        expected = 0
        try:
            while not self.stop.is_set():
                line = self.process.stderr.readline(16385)
                if not line:
                    break
                self.metrics.stderr_lines += 1
                if len(line) > 16384:
                    raise OcrError("Oversized FFmpeg metadata line")
                if b"showinfo" not in line:
                    continue
                match = re.search(rb"config in time_base:\s*(\d+/\d+)", line)
                if match:
                    tb = Fraction(match[1].decode("ascii"))
                    if tb != self.info.time_base:
                        raise OcrError("FFmpeg changed the source time base")
                if not re.search(rb"\bn:\s*\S+", line):
                    continue
                match = re.search(rb"\bn:\s*(\d+)\s+pts:\s*(-?\d+)\s+pts_time:", line)
                size = re.search(rb"\bs:(\d+)x(\d+)", line)
                if (match is None or tb is None or size is None
                        or int(match[1]) != expected
                        or (int(size[1]), int(size[2])) != (self.rect.width, self.rect.height)
                        or b"fmt:rgb24" not in line):
                    raise OcrError("Missing or malformed FFmpeg frame metadata")
                if not self._put(self.metadata, (expected, int(match[2]), tb)):
                    return
                expected += 1
        except Exception as exc:
            self._fail(str(exc) if isinstance(exc, OcrError) else "FFmpeg metadata reader failed")
        finally:
            self.stderr_done.set()

    def _stdout(self) -> None:
        assert self.process is not None and self.process.stdout is not None
        size = self.rect.width * self.rect.height * 3
        previous: int | None = None
        try:
            while not self.stop.is_set():
                raw = self.process.stdout.read(size)
                if not raw:
                    break
                if len(raw) != size:
                    raise OcrError("Truncated ROI frame")
                while not self.stop.is_set():
                    try:
                        index, pts, tb = self.metadata.get(timeout=0.05)
                        break
                    except queue.Empty:
                        if self.stderr_done.is_set():
                            raise OcrError("ROI frame has no source PTS")
                else:
                    return
                if previous is not None and pts <= previous:
                    raise OcrError("Non-increasing source PTS")
                previous = pts
                frame = RoiFrame(index, pts, tb, (pts * tb - self.info.timeline_origin) * 1000,
                                 self.rect.width, self.rect.height, raw)
                if not self._put(self.frames, frame):
                    return
                self.metrics.frames += 1
                self.metrics.queue_peak = max(self.metrics.queue_peak, self.frames.qsize())
                del raw, frame
        except Exception as exc:
            self._fail(str(exc) if isinstance(exc, OcrError) else "FFmpeg frame reader failed")
        finally:
            self.stdout_done.set()

    def __enter__(self) -> RoiDecoder:
        self.check()
        if self.process is not None or self.stop.is_set() or not self.source.is_file():
            raise OcrError("Decoder needs a local file and a fresh session")
        graph = ",".join(self.info.geometry.filters(self.roi) + ["showinfo"])
        command = [self.ffmpeg, "-hide_banner", "-nostdin", "-nostats", "-loglevel", "info",
                   "-copyts", "-noautorotate", "-threads", "1", "-i", str(self.source.resolve()),
                   "-map", f"0:{self.info.stream_index}", "-an", "-sn", "-dn", "-vf", graph,
                   "-fps_mode", "passthrough", "-threads", "1", "-c:v", "rawvideo", "-pix_fmt",
                   "rgb24", "-f", "rawvideo", "pipe:1"]
        self.started = time.monotonic()
        try:
            self.process = subprocess.Popen(command, stdin=subprocess.DEVNULL,
                                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                            env=child_environment(), creationflags=_NO_WINDOW,
                                            start_new_session=os.name != "nt")
            for name, target in (("ocr-stderr", self._stderr), ("ocr-frames", self._stdout)):
                reader = threading.Thread(target=copy_context().run, args=(target,), name=name)
                reader.start()
                self.readers.append(reader)
            return self
        except BaseException:
            self.close()
            raise

    def __iter__(self) -> Iterator[RoiFrame]:
        if self.process is None:
            raise OcrError("Decoder is not started")
        while True:
            # Consumer/OCR time does not count as an FFmpeg stall.
            deadline = time.monotonic() + self.timeout
            while True:
                self.check()
                if not self.errors.empty():
                    raise OcrError(self.errors.get_nowait())
                try:
                    frame = self.frames.get(timeout=0.05)
                    break
                except queue.Empty:
                    # A reader can fail during get(); EOF must not win that race.
                    if not self.errors.empty():
                        raise OcrError(self.errors.get_nowait())
                    if self.stdout_done.is_set() and self.stderr_done.is_set():
                        if not self.metadata.empty():
                            raise OcrError("Source PTS without an ROI frame")
                        code = self.process.poll()
                        if code is not None:
                            if code:
                                raise OcrError("FFmpeg decode failed")
                            return
                    if time.monotonic() >= deadline:
                        raise OcrError("FFmpeg decode timed out")
            yield frame
            del frame

    def spans(self, selection: Selection) -> Iterator[FrameSpan]:
        """One-frame lookahead preserves a frame already visible at selection start.

        Scan from the source origin; seeking optimizations need a separate PTS gate.
        Unknown EOF duration is review data, never a fabricated frame-rate duration.
        """
        previous: RoiFrame | None = None
        for frame in self:
            if previous is not None:
                start = max(Fraction(selection.start_ms), previous.timeline_ms)
                end = min(Fraction(selection.end_ms), frame.timeline_ms)
                if start < end:
                    yield FrameSpan(previous, start, end, start == selection.start_ms,
                                    end == selection.end_ms)
            if frame.timeline_ms >= selection.end_ms:
                return
            previous = frame
        if previous is not None and previous.timeline_ms < selection.end_ms:
            start = max(Fraction(selection.start_ms), previous.timeline_ms)
            yield FrameSpan(previous, start, Fraction(selection.end_ms),
                            previous.timeline_ms < selection.start_ms, True, True)

    def close(self) -> None:
        if self.closed:
            return
        self.stop.set()
        try:
            if self.process is not None:
                stop_owned_process(self.process)
        finally:
            for reader in self.readers:
                reader.join(timeout=3)
            if any(reader.is_alive() for reader in self.readers):
                raise OcrError("OCR reader did not stop")
            if self.process is not None:
                for stream in (self.process.stdout, self.process.stderr):
                    if stream:
                        stream.close()
            if self.started:
                self.metrics.process_wall_s = time.monotonic() - self.started
            self.closed = True

    def __exit__(self, *_args) -> None:
        self.close()

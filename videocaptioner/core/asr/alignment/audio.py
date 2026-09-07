"""Lossless shared ASR/alignment chunks with measured silence boundaries."""

from __future__ import annotations

import io
import os
import subprocess
import tempfile
import wave
from pathlib import Path
from typing import Callable, cast

from pydub import AudioSegment

from videocaptioner.core.utils.subprocess_helper import _NO_WINDOW, child_environment

from .contract import CHUNK_MS, AlignmentError

Check = Callable[[], None]


def stop_process(process: subprocess.Popen) -> None:
    if process.poll() is None:
        if os.name == "nt":
            # A Windows venv launcher owns a second Python process. Kill only this job's tree.
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           env=child_environment(), creationflags=_NO_WINDOW, timeout=10, check=False)
            process.wait(timeout=3)
            return
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)


def decode_audio(path: str, check: Check) -> AudioSegment:
    with tempfile.TemporaryDirectory(prefix="vc-align-audio-") as directory:
        wav_path = Path(directory) / "audio.wav"
        try:
            process = subprocess.Popen(
                ["ffmpeg", "-nostdin", "-v", "error", "-i", path, "-vn", "-ac", "1", "-ar", "16000",
                 "-c:a", "pcm_s16le", str(wav_path)],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=_NO_WINDOW, env=child_environment(),
            )
        except OSError:
            raise AlignmentError("FFmpeg unavailable") from None
        try:
            import time
            deadline = time.monotonic() + 600
            while process.poll() is None:
                check()
                if time.monotonic() >= deadline:
                    raise AlignmentError("audio decode timeout")
                try:
                    process.wait(timeout=0.1)
                except subprocess.TimeoutExpired:
                    pass
            if process.returncode:
                raise AlignmentError("audio decode failed")
            with wave.open(str(wav_path), "rb") as handle:
                return AudioSegment(handle.readframes(handle.getnframes()), sample_width=2,
                                    frame_rate=16000, channels=1)
        finally:
            stop_process(process)


def wav_bytes(audio: AudioSegment) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(16000)
        handle.writeframes(cast(bytes, audio.raw_data))
    return buffer.getvalue()


def split_audio(audio: AudioSegment, check: Check, chunk_ms: int = CHUNK_MS) -> list[tuple[AudioSegment, int]]:
    if not len(audio):
        raise AlignmentError("empty audio")
    if not 1000 <= chunk_ms <= CHUNK_MS:
        raise AlignmentError("invalid chunk limit")
    chunks = []
    start = 0
    while start < len(audio):
        check()
        end = min(start + chunk_ms, len(audio))
        if end < len(audio):
            # No fuzzy text deduplication: split once inside >=300 ms of near-silence.
            cut = next((t for t in range(end - 150, max(start + 500, end - 30_000), -50)
                        if audio[t - 150:t + 150].rms <= 104), None)
            if cut is None:
                raise AlignmentError("no safe silence boundary; split the recording for review")
            end = cut
        # Pydub's millisecond slicing pads partial final milliseconds with zeros.
        # Sample slicing retains the original tail bytes exactly.
        stop_sample = int(audio.frame_count()) if end == len(audio) else int(end * audio.frame_rate / 1000)
        chunks.append((audio.get_sample_slice(int(start * audio.frame_rate / 1000), stop_sample), start))
        start = end
    return chunks


def verify_acoustic_support(audio: AudioSegment, spans) -> None:
    for span in spans:
        if cast(AudioSegment, audio[span.start_ms:span.end_ms]).rms <= 32:
            raise AlignmentError("text aligned to silence")

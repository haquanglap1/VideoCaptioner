"""A job-owned source snapshot shared by all hybrid stages."""

import os
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path

from pydub import AudioSegment

from ..alignment.audio import Check
from .runtime import LocalRuntimeError

RECOGNITION_CHUNK_MS = 30_000


def split_recognition_audio(audio: AudioSegment, check: Check, chunk_ms: int) -> list[tuple[AudioSegment, int]]:
    """Bound decoding work; keep all samples even when continuous speech has no silence.

    Prefer the existing silence rule. A lowest-energy cut in the final two seconds
    is only a recognition window boundary, never a subtitle timestamp.
    """
    if not len(audio) or type(chunk_ms) is not int or not 1000 <= chunk_ms <= 240_000:
        raise LocalRuntimeError("Invalid recognition audio or chunk limit.")
    limit = min(chunk_ms, RECOGNITION_CHUNK_MS)
    chunks, start = [], 0
    while start < len(audio):
        check()
        end = min(start + limit, len(audio))
        if end < len(audio):
            candidates = range(end - 150, max(start + 500, end - 30_000), -50)
            cut = None
            for candidate in candidates:
                check()
                if audio[candidate - 150:candidate + 150].rms <= 104:
                    cut = candidate
                    break
            if cut is None:
                candidates = range(end - 150, max(start + 500, end - 2000), -50)
                measured = []
                for candidate in candidates:
                    check()
                    measured.append((audio[candidate - 150:candidate + 150].rms, -candidate))
                cut = -min(measured)[1]
            end = cut
        stop_sample = int(audio.frame_count()) if end == len(audio) else end * audio.frame_rate // 1000
        chunks.append((audio.get_sample_slice(start * audio.frame_rate // 1000, stop_sample), start))
        start = end
    return chunks


@contextmanager
def source_snapshot(path: str, check: Check):
    with tempfile.TemporaryDirectory(prefix="vc-hybrid-source-") as directory:
        source = Path(path)
        snapshot = Path(directory) / ("audio" + source.suffix)

        def signature(stat):
            return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns

        try:
            check()
            deadline = time.monotonic() + 600
            with source.open("rb") as incoming, snapshot.open("xb") as outgoing:
                before = signature(os.fstat(incoming.fileno()))
                path_before = signature(source.stat())
                if before[:2] != path_before[:2]:
                    raise LocalRuntimeError("Audio changed while preparing the hybrid job; retry with a stable source.")
                while True:
                    check()
                    if time.monotonic() >= deadline:
                        raise LocalRuntimeError("Hybrid source snapshot timed out.")
                    block = incoming.read(1024 * 1024)
                    if not block:
                        break
                    outgoing.write(block)
                # Windows fstat ctime and path stat ctime can have different semantics.
                # Compare each source to its own baseline, and identity across both.
                if before != signature(os.fstat(incoming.fileno())) or path_before != signature(source.stat()):
                    raise LocalRuntimeError("Audio changed while preparing the hybrid job; retry with a stable source.")
            check()
        except OSError:
            raise LocalRuntimeError("Cannot prepare the hybrid audio snapshot. Check source and temporary disk space.") from None
        # Later edits to the original cannot change the recording used for this job.
        yield str(snapshot)

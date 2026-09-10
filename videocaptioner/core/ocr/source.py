"""A cancellable, hashed video snapshot owned by one OCR job; user source stays untouched."""

from __future__ import annotations

import hashlib
import math
import os
import shutil
import tempfile
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from .models import Check, OcrError


@dataclass(frozen=True)
class VideoSnapshot:
    path: Path
    sha256: str
    size_bytes: int


@contextmanager
def video_snapshot(source: Path, jobs_root: Path, check: Check = lambda: None,
                   timeout: float = 600) -> Iterator[VideoSnapshot]:
    """Caller supplies the job root (app OCR jobs or isolated pilot/test scratch)."""
    check()
    if not source.is_file() or timeout <= 0 or not math.isfinite(timeout):
        raise OcrError("Invalid video snapshot source or timeout")
    jobs_root.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(jobs_root).free < source.stat().st_size + 64 * 1024 * 1024:
        raise OcrError("Insufficient disk space for the OCR video snapshot")

    def signature(stat):
        return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns

    with tempfile.TemporaryDirectory(prefix="video-", dir=jobs_root) as temporary:
        destination = Path(temporary) / ("source" + source.suffix)
        hasher = hashlib.sha256()
        size = 0
        deadline = time.monotonic() + timeout
        try:
            with source.open("rb") as incoming, destination.open("xb") as outgoing:
                before, path_before = signature(os.fstat(incoming.fileno())), signature(source.stat())
                if before[:2] != path_before[:2]:
                    raise OcrError("Video changed before OCR snapshot")
                while True:
                    check()
                    if time.monotonic() >= deadline:
                        raise OcrError("Video snapshot timed out")
                    block = incoming.read(1024 * 1024)
                    if not block:
                        break
                    outgoing.write(block)
                    hasher.update(block)
                    size += len(block)
                if (before != signature(os.fstat(incoming.fileno()))
                        or path_before != signature(source.stat())):
                    raise OcrError("Video changed during OCR snapshot")
        except OSError:
            raise OcrError("Cannot create OCR snapshot; check source and available disk space") from None
        check()
        yield VideoSnapshot(destination, hasher.hexdigest(), size)

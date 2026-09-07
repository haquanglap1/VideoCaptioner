"""A job-owned source snapshot shared by all hybrid stages."""

import os
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path

from ..alignment.audio import Check
from .runtime import LocalRuntimeError


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

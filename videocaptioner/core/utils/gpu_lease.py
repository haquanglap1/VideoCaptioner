"""One managed GPU sidecar at a time, including separate app processes.

The OS releases this advisory lease after a host crash. It never kills a user process.
"""

import os
import tempfile
from pathlib import Path


class GPUBusyError(RuntimeError):
    pass


def lease_path() -> Path:
    return Path(tempfile.gettempdir()) / "videocaptioner-gpu-v1.lock"


class GPULease:
    def __init__(self):
        self.handle = None

    def acquire(self):
        if self.handle is not None:
            return
        handle = lease_path().open("a+b")
        try:
            if not handle.tell():
                handle.write(b"0")
                handle.flush()
            handle.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            handle.close()
            raise GPUBusyError("GPU busy: stop the idle managed runtime or wait for its active job to finish.") from None
        self.handle = handle

    def close(self):
        if self.handle is None:
            return
        handle, self.handle = self.handle, None
        try:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()

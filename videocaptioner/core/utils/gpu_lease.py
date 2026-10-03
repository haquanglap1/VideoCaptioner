"""Exclusive GPU ownership between apps; bounded sharing inside one batch.

The OS releases this advisory lease after a host crash. It never kills a user process.
"""

import os
import tempfile
import time
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from threading import RLock


class GPUBusyError(RuntimeError):
    pass


def lease_path() -> Path:
    return Path(tempfile.gettempdir()) / "videocaptioner-gpu-v1.lock"


class GPULease:
    def __init__(self):
        self.handle = None
        self.shared_job = None

    def acquire(self):
        if self.handle is not None:
            return
        job = current_gpu_job()
        if job is not None:
            self.shared_job = job
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
        self.shared_job = None
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


class GPUJob:
    def __init__(self):
        self.active = True
        self.services = {}
        self.lock = RLock()

    def service(self, name, factory):
        with self.lock:
            if not self.active:
                raise RuntimeError("GPU job has retired")
            if name not in self.services:
                self.services[name] = factory()
            return self.services[name]

    def close(self):
        try:
            for service in self.services.values():
                service.close()
        finally:
            self.active = False


_gpu_job: ContextVar[GPUJob | None] = ContextVar("batch_gpu_job", default=None)


def current_gpu_job() -> GPUJob | None:
    job = _gpu_job.get()
    if job is not None and not job.active:
        raise RuntimeError("GPU job has retired")
    return job


class BatchGPUSession:
    """Hold one OS lease until all admitted batch workers have closed their children."""

    def __init__(self, limit=1):
        if limit not in (1, 2):
            raise ValueError("GPU job limit must be 1 or 2")
        self.limit = limit
        self.active = 0
        self.lock = RLock()
        self.lease = GPULease()

    @contextmanager
    def acquire(self, check, waiting):
        while True:
            check()
            with self.lock:
                if self.active < self.limit:
                    try:
                        self.lease.acquire()
                    except GPUBusyError:
                        pass
                    else:
                        self.active += 1
                        break
            waiting()
            time.sleep(.1)
        job = GPUJob()
        token = _gpu_job.set(job)
        try:
            check()
            yield job
        finally:
            try:
                job.close()
            finally:
                _gpu_job.reset(token)
                with self.lock:
                    self.active -= 1
                    if not self.active:
                        self.lease.close()


@contextmanager
def gpu_job_scope(session: BatchGPUSession | None, check, waiting):
    if session is None:
        yield
    else:
        with session.acquire(check, waiting):
            yield

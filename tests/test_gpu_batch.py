"""An opted-in batch shares its OS lease without sharing runtime or cancellation state."""

from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context
from threading import Event

import pytest

from videocaptioner.core.tts.omnivoice.runtime import get_omnivoice_service
from videocaptioner.core.utils.gpu_lease import BatchGPUSession, GPUBusyError, GPULease


def test_two_jobs_keep_distinct_runtimes_and_hold_exclusive_os_ownership():
    session = BatchGPUSession(2)
    ready, release = [Event(), Event()], [Event(), Event()]
    runtimes = {}
    def work(index):
        with session.acquire(lambda: None, lambda: None):
            runtime = get_omnivoice_service()
            runtime.voice = f"voice-{index}"
            nested = GPULease()
            nested.acquire()
            runtimes[index] = runtime
            ready[index].set()
            assert release[index].wait(5)
            assert get_omnivoice_service() is runtime and runtime.voice == f"voice-{index}"
            nested.close()
    with ThreadPoolExecutor(2) as pool:
        futures = [pool.submit(work, i) for i in range(2)]
        try:
            assert all(event.wait(3) for event in ready)
            assert session.active == 2 and runtimes[0] is not runtimes[1]
            with pytest.raises(GPUBusyError):
                GPULease().acquire()
            release[0].set()
            futures[0].result(3)
            assert session.active == 1 and runtimes[1].voice == "voice-1"
            with pytest.raises(GPUBusyError):
                GPULease().acquire()
        finally:
            for event in release:
                event.set()
        futures[1].result(3)
    assert session.active == 0 and session.lease.handle is None
    lease = GPULease()
    lease.acquire()
    lease.close()


def test_cancel_while_waiting_for_another_app_does_not_take_or_release_its_lease():
    owner, session = GPULease(), BatchGPUSession(2)
    owner.acquire()
    waiting, cancel = Event(), Event()
    def check():
        if cancel.is_set():
            raise RuntimeError("cancelled")
    def work():
        with session.acquire(check, waiting.set):
            pytest.fail("External owner must remain exclusive")
    try:
        with ThreadPoolExecutor(1) as pool:
            future = pool.submit(work)
            assert waiting.wait(3)
            cancel.set()
            with pytest.raises(RuntimeError, match="cancelled"):
                future.result(3)
        assert session.active == 0 and owner.handle is not None
        with pytest.raises(GPUBusyError):
            GPULease().acquire()
    finally:
        owner.close()


def test_retired_context_cannot_bypass_gpu_ownership():
    session = BatchGPUSession(1)
    with session.acquire(lambda: None, lambda: None):
        snapshot = copy_context()
        runtime = get_omnivoice_service()
    assert runtime.process is None and session.active == 0
    with pytest.raises(RuntimeError, match="retired"):
        snapshot.run(GPULease().acquire)
    assert get_omnivoice_service() is not runtime


def test_failure_releases_only_its_slot():
    session = BatchGPUSession(1)
    with pytest.raises(ValueError, match="fixture"):
        with session.acquire(lambda: None, lambda: None):
            raise ValueError("fixture")
    assert session.active == 0 and session.lease.handle is None
    with session.acquire(lambda: None, lambda: None):
        assert session.active == 1

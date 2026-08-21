import socket
import threading
import time

import psutil
import pytest
import requests

from videocaptioner.core.tts.vieneu.models import VieNeuRuntimeState
from videocaptioner.core.tts.vieneu.runtime_manager import (
    VieNeuPortOwnershipError,
    VieNeuRuntimeCancelled,
    VieNeuRuntimeError,
    VieNeuRuntimeIdentityError,
    VieNeuRuntimeManager,
)


def test_runtime_lazy_start_warm_reuse_auth_and_graceful_zero_process(runtime_config):
    manager = VieNeuRuntimeManager()
    config = runtime_config()
    identity = manager.ensure_ready(config)
    first_pid = manager.process_id
    assert identity.endpoint.startswith("http://127.0.0.1:")
    assert identity.model_revision == "a" * 40
    assert identity.sample_rate == 48000
    assert manager.state == VieNeuRuntimeState.READY
    assert manager.ensure_ready(config) is identity
    assert manager.process_id == first_pid
    unauthorized = requests.get(identity.endpoint + "health", timeout=2)
    assert unauthorized.status_code == 401
    assert identity.session_token not in "\n".join(manager._log_tail)
    assert manager.shutdown()
    assert manager.owned_processes_alive() == []
    assert manager.state == VieNeuRuntimeState.STOPPED


def test_runtime_acquire_pins_revision_and_defers_stop(runtime_config):
    manager = VieNeuRuntimeManager()
    config_a = runtime_config("a" * 40)
    config_b = runtime_config("b" * 40)
    with manager.acquire(config_a) as identity:
        assert identity.model_revision == "a" * 40
        assert manager.state == VieNeuRuntimeState.BUSY
        assert manager.shutdown() is False
        with pytest.raises(VieNeuRuntimeError, match="active"):
            manager.ensure_ready(config_b)
    assert manager.state == VieNeuRuntimeState.READY
    manager.shutdown(force=True)


def test_port_collision_never_kills_or_adopts_listener(runtime_config):
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    port = listener.getsockname()[1]
    manager = VieNeuRuntimeManager()
    try:
        with pytest.raises(VieNeuPortOwnershipError, match="unrelated"):
            manager.ensure_ready(runtime_config(port=port))
        assert manager.process_id is None
        assert listener.fileno() >= 0
    finally:
        listener.close()


def test_wrong_service_identity_is_rejected_and_owned_process_is_closed(runtime_config):
    manager = VieNeuRuntimeManager()
    with pytest.raises(VieNeuRuntimeIdentityError, match="Wrong"):
        manager.ensure_ready(runtime_config(extra_args=("--wrong-service",)))
    assert manager.process_id is None
    assert manager.state == VieNeuRuntimeState.STOPPED


def test_slow_start_is_bounded_but_succeeds(runtime_config):
    manager = VieNeuRuntimeManager()
    started = time.monotonic()
    identity = manager.ensure_ready(
        runtime_config(extra_args=("--ready-delay", "0.35"), timeout=2.0)
    )
    assert time.monotonic() - started >= 0.30
    assert identity.runtime_version == "fake-runtime-1"
    manager.shutdown(force=True)


def test_unexpected_first_crash_retries_once(runtime_config, tmp_path):
    marker = tmp_path / "crash-once.marker"
    manager = VieNeuRuntimeManager()
    identity = manager.ensure_ready(
        runtime_config(extra_args=("--crash-once-marker", str(marker)), timeout=3.0)
    )
    assert marker.is_file()
    assert identity.model_revision == "a" * 40
    manager.shutdown(force=True)


def test_startup_cancel_stops_owned_process(runtime_config):
    manager = VieNeuRuntimeManager()
    cancelled = threading.Event()
    timer = threading.Timer(0.15, cancelled.set)
    timer.start()
    try:
        with pytest.raises(VieNeuRuntimeCancelled):
            manager.ensure_ready(
                runtime_config(extra_args=("--ready-delay", "5"), timeout=6.0),
                cancel_event=cancelled,
            )
    finally:
        timer.cancel()
        manager.shutdown(force=True)
    assert manager.process_id is None


def test_shutdown_kills_only_owned_descendant_tree(runtime_config, tmp_path):
    child_marker = tmp_path / "child.pid"
    manager = VieNeuRuntimeManager()
    manager.ensure_ready(
        runtime_config(extra_args=("--spawn-child-marker", str(child_marker)))
    )
    deadline = time.monotonic() + 3
    while not child_marker.is_file() and time.monotonic() < deadline:
        time.sleep(0.02)
    child_pid = int(child_marker.read_text(encoding="utf-8"))
    assert psutil.pid_exists(child_pid)
    manager.shutdown(force=True)
    deadline = time.monotonic() + 3
    while psutil.pid_exists(child_pid) and time.monotonic() < deadline:
        time.sleep(0.02)
    assert not psutil.pid_exists(child_pid)

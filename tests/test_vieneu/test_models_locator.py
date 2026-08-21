import json
import sys
from pathlib import Path

import pytest

from videocaptioner.core.tts.vieneu.client_identity import VieNeuClientIdentity
from videocaptioner.core.tts.vieneu.models import (
    VIENEU_PROTOCOL_VERSION,
    VIENEU_SERVICE_ID,
    VieNeuHealth,
    VieNeuModelState,
    sanitize_error,
)
from videocaptioner.core.tts.vieneu.runtime_locator import VieNeuRuntimeLocator


def test_model_state_round_trip_is_versioned_relative_and_credential_free(tmp_path):
    state = VieNeuModelState(
        active_revision="a" * 40,
        active_snapshot="hf/models--repo/snapshots/" + "a" * 40,
        runtime_version="runtime-1",
        tokenizer_revision="b" * 40,
        codec_revision="c" * 40,
        last_error="Authorization: Bearer secret-token at C:\\private\\model",
    )
    payload = state.to_dict()
    serialized = json.dumps(payload)
    assert payload["schema_version"] == "vieneu-model-state-v1"
    assert "secret-token" not in serialized
    assert "C:\\private" not in serialized
    assert VieNeuModelState.from_dict(payload).active_revision == "a" * 40


def test_model_state_rejects_absolute_snapshot_and_invalid_revision():
    with pytest.raises(ValueError, match="relative"):
        VieNeuModelState(active_snapshot="C:/models/snapshot").validate()
    with pytest.raises(ValueError, match="revision"):
        VieNeuModelState(active_revision="main").validate()


def test_sanitize_error_removes_bearer_token_url_credential_and_local_path():
    value = sanitize_error(
        "Bearer abc.def token=secret https://user:pass@example.invalid C:\\Users\\Me\\model"
    )
    assert "abc.def" not in value
    assert "secret" not in value
    assert "user:pass" not in value
    assert "C:\\Users" not in value


def test_health_requires_service_protocol_session_revision_and_ready():
    payload = {
        "service_id": VIENEU_SERVICE_ID,
        "protocol_version": VIENEU_PROTOCOL_VERSION,
        "session_id": "session",
        "runtime_version": "runtime-1",
        "model_repository": "owner/repo",
        "model_revision": "a" * 40,
        "backend": "pytorch",
        "sample_rate": 48000,
        "ready": True,
    }
    health = VieNeuHealth.from_payload(
        payload, expected_session_id="session", expected_revision="a" * 40
    )
    assert health.sample_rate == 48000
    for key, value in (
        ("service_id", "wrong"),
        ("protocol_version", "v0"),
        ("session_id", "other"),
        ("model_revision", "b" * 40),
        ("ready", False),
    ):
        changed = dict(payload)
        changed[key] = value
        with pytest.raises(ValueError):
            VieNeuHealth.from_payload(
                changed, expected_session_id="session", expected_revision="a" * 40
            )


def test_client_cache_identity_has_revision_runtime_backend_but_no_token():
    health = VieNeuHealth(
        VIENEU_SERVICE_ID,
        VIENEU_PROTOCOL_VERSION,
        "session",
        "runtime-1",
        "owner/repo",
        "a" * 40,
        "pytorch",
        48000,
        True,
    )
    identity = VieNeuClientIdentity.from_health("http://127.0.0.1:9999/v1", "secret", health)
    cache = identity.cache_identity()
    assert cache["model_revision"] == "a" * 40
    assert cache["runtime_version"] == "runtime-1"
    assert cache["backend"] == "pytorch"
    assert "secret" not in json.dumps(cache)
    assert "session_token" not in cache


def test_runtime_locator_uses_explicit_python_and_bridge_without_machine_default(
    fake_bridge, tmp_path
):
    locator = VieNeuRuntimeLocator(app_root=tmp_path / "app")
    layout = locator.locate(Path(sys.executable), fake_bridge)
    assert layout.python_executable == Path(sys.executable)
    assert layout.bridge_script == fake_bridge
    assert layout.source == "explicit"

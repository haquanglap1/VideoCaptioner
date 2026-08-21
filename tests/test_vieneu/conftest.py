import sys
from pathlib import Path

import pytest

from videocaptioner.core.tts.vieneu.runtime_manager import VieNeuRuntimeLaunchConfig


@pytest.fixture
def fake_bridge() -> Path:
    return Path(__file__).resolve().parents[1] / "fixtures" / "vieneu" / "fake_bridge.py"


@pytest.fixture
def model_snapshot(tmp_path) -> Path:
    path = tmp_path / "model"
    path.mkdir()
    (path / "config.json").write_text("{}", encoding="utf-8")
    return path


@pytest.fixture
def runtime_config(fake_bridge, model_snapshot):
    def factory(revision="a" * 40, *, extra_args=(), port=None, timeout=4.0):
        return VieNeuRuntimeLaunchConfig(
            model_snapshot=model_snapshot,
            model_revision=revision,
            explicit_runtime=Path(sys.executable),
            explicit_bridge=fake_bridge,
            startup_timeout=timeout,
            health_interval=0.03,
            request_timeout=1.0,
            retry_count=1,
            port=port,
            extra_args=tuple(extra_args),
        )

    return factory

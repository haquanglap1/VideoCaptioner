import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from videocaptioner.cli.commands.dub import build_dubbing_config
from videocaptioner.cli.main import build_parser
from videocaptioner.core.dubbing.config import (
    AudioMixMode,
    DubbingConfig,
    TTSProviderEnum,
)
from videocaptioner.core.dubbing.engine import DubbingEngine
from videocaptioner.core.dubbing.models import DubbingTimingMode
from videocaptioner.core.tts import TTSConfig
from videocaptioner.core.tts.vieneu.model_updater import VieNeuModelPaths, VieNeuStateStore
from videocaptioner.core.tts.vieneu.models import VieNeuModelState
from videocaptioner.core.tts.vieneu.runtime_manager import VieNeuRuntimeManager
from videocaptioner.core.tts.vieneu.service import (
    VieNeuManagedService,
    set_vieneu_service_for_tests,
)


def build_service(tmp_path, fake_bridge, revision="a" * 40):
    store = VieNeuStateStore(VieNeuModelPaths.under(tmp_path / "models"))
    snapshot = store.paths.hf_cache / "snapshots" / revision
    dependency = store.paths.hf_cache / "snapshots" / ("d" * 40)
    snapshot.mkdir(parents=True)
    dependency.mkdir(parents=True)
    state = VieNeuModelState(
        active_revision=revision,
        active_snapshot=store.relative_snapshot(snapshot),
        tokenizer_revision="d" * 40,
        tokenizer_snapshot=store.relative_snapshot(dependency),
        codec_revision="d" * 40,
        codec_snapshot=store.relative_snapshot(dependency),
        runtime_version="fake-runtime-1",
    )
    store.save(state)
    return VieNeuManagedService(
        manager=VieNeuRuntimeManager(),
        store=store,
        explicit_runtime=Path(sys.executable),
        explicit_bridge=fake_bridge,
    )


def make_video_and_subtitle(tmp_path):
    if not shutil.which("ffmpeg"):
        pytest.skip("FFmpeg required")
    video = tmp_path / "input.mp4"
    result = subprocess.run(
        [
            "ffmpeg", "-v", "error", "-f", "lavfi", "-i",
            "color=c=black:s=160x90:r=10:d=2", "-c:v", "libx264",
            "-pix_fmt", "yuv420p", "-y", str(video),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    subtitle = tmp_path / "input.srt"
    subtitle.write_text(
        "1\n00:00:00,000 --> 00:00:01,000\nXin chào.\n",
        encoding="utf-8",
    )
    return video, subtitle


def managed_config():
    return DubbingConfig(
        enabled=True,
        tts_provider=TTSProviderEnum.VIENEU_LOCAL,
        tts_config=TTSConfig(
            model="",
            api_key="",
            base_url="",
            voice="fake-voice",
            speed=1.0,
            sample_rate=32000,
            response_format="wav",
        ),
        timing_mode=DubbingTimingMode.NATURAL,
        mix_mode=AudioMixMode.MUTE_ORIGINAL,
        strip_cjk=False,
        rewrite_enabled=False,
        target_language="vi",
    )


def test_managed_dubbing_uses_ephemeral_config_reports_identity_and_namespaces_cache(
    tmp_path, fake_bridge
):
    service = build_service(tmp_path, fake_bridge)
    set_vieneu_service_for_tests(service)
    video, subtitle = make_video_and_subtitle(tmp_path)
    config = managed_config()
    cache_root = tmp_path / "tts-cache"
    engine = DubbingEngine(cache_root=cache_root)
    try:
        first = tmp_path / "dubbed-a.mp4"
        engine.dub(str(video), str(subtitle), str(first), config)
        assert first.is_file()
        assert config.tts_config.api_key == ""
        assert config.tts_config.base_url == ""
        identity = engine.last_report["provider_identity"]
        assert identity["model_revision"] == "a" * 40
        assert identity["runtime_version"] == "fake-runtime-1"
        assert identity["backend"] == "pytorch"
        assert "session_token" not in identity
        metadata = [json.loads(path.read_text(encoding="utf-8")) for path in cache_root.glob("*.json")]
        assert len(metadata) == 1
        assert metadata[0]["runtime_identity"]["model_revision"] == "a" * 40
        old_wav = next(cache_root.glob("*.wav"))

        service.shutdown()
        state = service.store.load()
        revision_b = "b" * 40
        snapshot_b = service.store.paths.hf_cache / "snapshots" / revision_b
        snapshot_b.mkdir(parents=True)
        state.previous_revision = state.active_revision
        state.previous_snapshot = state.active_snapshot
        state.active_revision = revision_b
        state.active_snapshot = service.store.relative_snapshot(snapshot_b)
        service.store.save(state)
        second = tmp_path / "dubbed-b.mp4"
        engine.dub(str(video), str(subtitle), str(second), config)
        assert second.is_file()
        assert len(list(cache_root.glob("*.wav"))) == 2
        assert old_wav.is_file()
    finally:
        service.shutdown()
        set_vieneu_service_for_tests(None)


def test_cli_accepts_managed_provider_without_api_key_and_has_model_commands():
    parser = build_parser()
    args = parser.parse_args(
        ["dub", "video.mp4", "--subtitle", "sub.srt", "--tts-provider", "vieneu-local"]
    )
    assert args.tts_provider == "vieneu-local"
    assert parser.parse_args(["vieneu", "status"]).vieneu_action == "status"
    assert parser.parse_args(["vieneu", "update"]).vieneu_action == "update"
    assert parser.parse_args(["vieneu", "rollback"]).vieneu_action == "rollback"
    config = build_dubbing_config(
        {
            "dubbing": {"tts_provider": "vieneu-local", "tts_api_key": ""},
            "translate": {"target_language": "vi"},
        }
    )
    assert config.tts_provider == TTSProviderEnum.VIENEU_LOCAL
    assert config.tts_config and config.tts_config.api_key == ""

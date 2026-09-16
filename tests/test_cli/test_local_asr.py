"""Explicit S5 CLI configuration and local review, with no API/model calls."""

import pytest

from videocaptioner.cli.config import DEFAULTS, build_config, load_config_file, save_config_value
from videocaptioner.cli.main import _build_cli_overrides, build_parser


@pytest.mark.parametrize("command", ["transcribe", "process"])
def test_qwen_and_hybrid_cli_options(command, tmp_path):
    args = build_parser().parse_args([command, "input.wav", "--asr", "qwen-local", "--qwen-model", "qwen-0.6b",
        "--language", "zh", "--local-diarize", "--qwen-runtime", "installed-qwen", "--diarization-runtime", "installed-pyannote",
        "--local-timeout", "300", "--local-chunk-ms", "60000"])
    config = build_config(_build_cli_overrides(args), gui_settings_path=tmp_path / "none")
    assert config["transcribe"]["asr"] == "qwen-local"
    assert config["local_asr"] == {"model": "qwen-0.6b", "diarize": True, "runtime_root": "installed-qwen",
                                    "diarization_root": "installed-pyannote", "timeout": 300, "chunk_ms": 60000}
    assert DEFAULTS["transcribe"]["asr"] == "bijian"
    assert not DEFAULTS["local_asr"]["diarize"]


@pytest.mark.parametrize("key,value", [("model", "unknown"), ("timeout", "0"), ("timeout", "3601"),
                                      ("chunk_ms", "240001"), ("diarize", "sometimes")])
def test_bad_local_config_does_not_write(key, value, tmp_path):
    target = tmp_path / "config.toml"
    with pytest.raises(ValueError):
        save_config_value(f"local_asr.{key}", value, target)
    assert not target.exists()


def test_local_config_roundtrip_and_no_gui_behavior_mirroring(tmp_path):
    target = tmp_path / "config.toml"
    save_config_value("local_asr.diarize", "true", target)
    save_config_value("local_asr.model", "qwen-0.6b", target)
    assert load_config_file(target)["local_asr"] == {"diarize": True, "model": "qwen-0.6b"}
    gui = tmp_path / "gui.json"
    gui.write_text('{"LocalASR":{"Diarize":true,"Model":"qwen-0.6b"}}')
    assert build_config(config_path=tmp_path / "missing.toml", gui_settings_path=gui)["local_asr"]["diarize"] is False


def test_model_manager_has_no_token_argument_and_status_is_light(monkeypatch):
    from videocaptioner.cli.commands.local_asr import run
    args = build_parser().parse_args(["local-asr", "status", "--models", "qwen-0.6b"])
    monkeypatch.setattr("videocaptioner.cli.commands.local_asr.locate", lambda *a, **k: object())
    monkeypatch.setattr("videocaptioner.cli.commands.local_asr.LocalRuntime", lambda *a, **k: pytest.fail("Heavy status"))
    assert run(args) == 0
    with pytest.raises(SystemExit):
        build_parser().parse_args(["local-asr", "install", "--token", "fake"])


def test_mixed_install_fails_before_requesting_token(tmp_path, monkeypatch):
    from videocaptioner.cli.commands.local_asr import run
    monkeypatch.setattr("getpass.getpass", lambda *a: pytest.fail("Do not ask for credentials for an invalid install"))
    args = build_parser().parse_args(["local-asr", "install", "--root", str(tmp_path / "new")])
    assert run(args) == 2
    assert not (tmp_path / "new").exists()


def test_local_diarize_rejects_text_only_before_inference(tmp_path, monkeypatch):
    from videocaptioner.cli.commands.local_diarize import run
    monkeypatch.setattr("videocaptioner.cli.commands.local_diarize.add_local_speakers", lambda *a, **k: pytest.fail("Needs alignment"))
    args = build_parser().parse_args(["local-diarize", str(tmp_path / "text.txt"), "--audio", "audio.wav", "-o", "result.json"])
    assert run(args) == 2

"""Explicit native selection, precedence and provider/endpoint key isolation."""

import json

import pytest

from videocaptioner.cli.config import build_config, load_config_file, save_config_value
from videocaptioner.cli.main import _build_cli_overrides, build_parser
from videocaptioner.core.asr.native_profiles import NATIVE_PROFILES


@pytest.mark.parametrize("provider", ["soniox", "scribe"])
@pytest.mark.parametrize("command", ["transcribe", "process"])
def test_native_parser_flags_and_precedence(tmp_path, monkeypatch, provider, command):
    gui = tmp_path / "settings.json"
    gui.write_text(json.dumps({provider.title(): {"ApiKey": "gui-key", "ApiBase": NATIVE_PROFILES[provider].endpoint}}))
    monkeypatch.setenv(f"VIDEOCAPTIONER_{provider.upper()}_API_KEY", "env-key")
    monkeypatch.setenv(f"VIDEOCAPTIONER_{provider.upper()}_DIARIZE", "false")
    assert build_config(gui_settings_path=gui)[provider]["diarize"] is False
    args = build_parser().parse_args([
        command, "input.wav", "--asr", provider, f"--{provider}-api-key", "cli-key",
        f"--{provider}-diarize", "--language", "zh",
    ])
    config = build_config(_build_cli_overrides(args), gui_settings_path=gui)
    assert config[provider]["api_key"] == "cli-key"
    assert config[provider]["diarize"] is True
    assert config["transcribe"]["asr"] == provider
    assert config["whisper_api"]["api_key"] == ""


@pytest.mark.parametrize("provider", ["soniox", "scribe"])
def test_changing_endpoint_never_inherits_key_and_config_set_restores_owned_key(tmp_path, provider):
    gui = tmp_path / "settings.json"
    gui.write_text(json.dumps({provider.title(): {"ApiKey": "native-key", "ApiBase": NATIVE_PROFILES[provider].endpoint},
                                "WhisperAPI": {"WhisperApiKey": "gateway-key"}}))
    config = build_config({provider: {"api_base": "https://other.example/v1"}}, gui_settings_path=gui)
    assert config[provider]["api_key"] == ""
    assert config["whisper_api"]["api_key"] == "gateway-key"
    path = tmp_path / "config.toml"
    save_config_value(f"{provider}.api_key", "native-key", path)
    save_config_value(f"{provider}.api_base", "https://other.example/v1", path)
    assert load_config_file(path)[provider]["api_key"] == ""
    save_config_value(f"{provider}.api_base", NATIVE_PROFILES[provider].endpoint, path)
    assert load_config_file(path)[provider]["api_key"] == "native-key"


def test_gateway_alias_is_not_a_native_provider():
    from videocaptioner.core.asr.transcribe import _create_asr_instance
    from videocaptioner.core.entities import TranscribeConfig, TranscribeModelEnum
    cfg = TranscribeConfig(transcribe_model=TranscribeModelEnum.SONIOX, whisper_api_key="gateway-key")
    with pytest.raises(ValueError, match="native ASR"):
        _create_asr_instance("unused.wav", cfg)


def test_process_hands_the_same_asr_result_to_subtitle(monkeypatch, tmp_path):
    from videocaptioner.cli.commands import process
    from videocaptioner.core.asr.asr_data import ASRData, ASRDataSeg
    from videocaptioner.core.asr.metadata import ASRMetadata
    path = tmp_path / "clip.wav"
    path.touch()
    data = ASRData([ASRDataSeg("你好", 10, 100, metadata=ASRMetadata("soniox", "scope", "1"))])
    monkeypatch.setattr("videocaptioner.cli.validators.validate_process", lambda *a, **k: True)
    def transcribe(args, config):
        args.asr_data = data
        data.save(args.output)
        return 0
    def subtitle(args, config):
        assert args.asr_data is data
        assert args.asr_data.segments[0].speaker == "soniox:scope:1"
        return 0
    monkeypatch.setattr("videocaptioner.cli.commands.transcribe.run", transcribe)
    monkeypatch.setattr("videocaptioner.cli.commands.subtitle.run", subtitle)
    args = build_parser().parse_args(["process", str(path), "--asr", "soniox", "--no-synthesize"])
    assert process.run(args, build_config({"soniox": {"api_key": "test"}})) == 0

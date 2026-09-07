"""Provider/profile precedence and endpoint credential isolation in the CLI."""

import json

import pytest

from videocaptioner.cli.config import build_config, load_config_file, save_config_value


@pytest.fixture
def settings(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"WhisperAPI": {
        "WhisperApiBase": "https://old.example/v1", "WhisperApiKey": "old-test-key",
        "WhisperApiModel": "manual-alias", "WhisperApiPrompt": "synthetic hint",
        "WhisperApiRequestProfile": "whisper", "WhisperApiProvider": "custom",
    }}), encoding="utf-8")
    return path


def test_legacy_custom_values_remain(settings):
    config = build_config(gui_settings_path=settings)["whisper_api"]
    assert config["model"] == "manual-alias"
    assert config["api_key"] == "old-test-key"
    assert config["request_profile"] == "whisper"


def test_cli_preset_does_not_inherit_old_key_or_model(settings):
    config = build_config({"whisper_api": {"provider": "groq"}}, gui_settings_path=settings)["whisper_api"]
    assert config["api_base"] == "https://api.groq.com/openai/v1"
    assert config["model"] == "whisper-large-v3"
    assert config["api_key"] == ""
    assert config["request_profile"] == "auto"


def test_cli_explicit_overrides_and_environment_precedence(settings, monkeypatch):
    monkeypatch.setenv("VIDEOCAPTIONER_WHISPER_API_PROVIDER", "groq")
    monkeypatch.setenv("VIDEOCAPTIONER_WHISPER_API_KEY", "groq-test-key")
    monkeypatch.setenv("VIDEOCAPTIONER_WHISPER_API_REQUEST_PROFILE", "whisper")
    config = build_config({"whisper_api": {
        "provider": "videocaptioner", "api_base": "https://explicit.example/route",
        "model": "manual-gpt-alias", "request_profile": "json-text", "api_key": "explicit-test-key",
    }}, gui_settings_path=settings)["whisper_api"]
    assert config["api_base"] == "https://explicit.example/route"
    assert config["api_key"] == "explicit-test-key"
    assert config["model"] == "manual-gpt-alias"
    assert config["request_profile"] == "json-text"


def test_base_override_requires_own_key(settings, monkeypatch):
    monkeypatch.setenv("VIDEOCAPTIONER_WHISPER_API_BASE", "https://new.example")
    assert build_config(gui_settings_path=settings)["whisper_api"]["api_key"] == ""
    monkeypatch.setenv("VIDEOCAPTIONER_WHISPER_API_BASE", "https://OLD.example:443/v1/")
    assert build_config(gui_settings_path=settings)["whisper_api"]["api_key"] == "old-test-key"


def test_persistent_config_set_does_not_reuse_old_provider_key(tmp_path):
    path = tmp_path / "config.toml"
    save_config_value("whisper_api.api_base", "https://old.example", path)
    save_config_value("whisper_api.api_key", "old-test-key", path)
    save_config_value("whisper_api.provider", "groq", path)
    current = load_config_file(path)["whisper_api"]
    assert current["api_key"] == ""
    assert current["api_base"] == "https://api.groq.com/openai/v1"
    save_config_value("whisper_api.api_base", "https://old.example/v1", path)
    assert load_config_file(path)["whisper_api"]["api_key"] == "old-test-key"


@pytest.mark.parametrize("command", ["transcribe", "process"])
def test_new_flags_map_without_changing_old_flags(command):
    from videocaptioner.cli.main import _build_cli_overrides, build_parser

    args = build_parser().parse_args([
        command, "synthetic.wav", "--asr", "whisper-api", "--whisper-provider", "videocaptioner",
        "--whisper-model", "gpt-4o-transcribe", "--whisper-request-profile", "json-text",
    ])
    config = _build_cli_overrides(args)
    assert config["whisper_api"]["provider"] == "videocaptioner"
    assert config["whisper_api"]["request_profile"] == "json-text"
    assert config["whisper_api"]["model"] == "gpt-4o-transcribe"


def test_text_only_cli_preserves_runtime_exit_code_without_upload(tmp_path, monkeypatch, capsys):
    from videocaptioner.cli import exit_codes as EXIT
    from videocaptioner.cli.main import main

    audio = tmp_path / "synthetic.wav"
    audio.write_bytes(b"not-needed-preflight")
    monkeypatch.setattr("videocaptioner.core.asr.whisper_api.create_client",
                        lambda *a: pytest.fail("text-only subtitle command must not upload"))
    result = main(["transcribe", str(audio), "--asr", "whisper-api", "--whisper-provider",
                   "videocaptioner", "--whisper-model", "gpt-4o-transcribe", "--whisper-api-key", "fake"])
    assert result == EXIT.RUNTIME_ERROR
    captured = capsys.readouterr()
    assert "alignment" in captured.out + captured.err
    assert not audio.with_suffix(".srt").exists()

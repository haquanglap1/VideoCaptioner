"""Tests for CLI config system — TOML read/write, merging, type safety."""

import json

import pytest

from videocaptioner.cli.config import (
    DEFAULTS,
    _deep_merge,
    _get_nested,
    _parse_value,
    _set_nested,
    _toml_value,
    build_config,
    load_config_file,
    load_gui_settings,
    save_config_value,
)


def _write_gui_settings(path, **groups):
    """Write a settings.json shaped like qfluentwidgets' QConfig output."""
    path.write_text(json.dumps(groups, ensure_ascii=False), encoding="utf-8")
    return path


class TestDeepMerge:
    def test_flat_override(self):
        assert _deep_merge({"a": 1}, {"a": 2}) == {"a": 2}

    def test_nested_merge(self):
        base = {"x": {"a": 1, "b": 2}}
        override = {"x": {"b": 3, "c": 4}}
        result = _deep_merge(base, override)
        assert result == {"x": {"a": 1, "b": 3, "c": 4}}

    def test_does_not_mutate_base(self):
        base = {"a": 1}
        _deep_merge(base, {"a": 2})
        assert base == {"a": 1}

    def test_empty_override(self):
        base = {"a": 1}
        assert _deep_merge(base, {}) == {"a": 1}


class TestNestedAccess:
    def test_get_nested(self):
        d = {"a": {"b": {"c": 42}}}
        assert _get_nested(d, "a.b.c") == 42

    def test_get_nested_missing(self):
        assert _get_nested({"a": 1}, "b", "default") == "default"

    def test_get_nested_deep_missing(self):
        assert _get_nested({"a": {"b": 1}}, "a.c.d", None) is None

    def test_set_nested(self):
        d: dict = {}
        _set_nested(d, "a.b.c", 42)
        assert d == {"a": {"b": {"c": 42}}}

    def test_set_nested_overwrite(self):
        d = {"a": {"b": 1}}
        _set_nested(d, "a.b", 2)
        assert d == {"a": {"b": 2}}


class TestParseValue:
    def test_bool_true(self):
        assert _parse_value("true", "subtitle.optimize") is True
        assert _parse_value("yes", "subtitle.optimize") is True
        assert _parse_value("1", "subtitle.optimize") is True

    def test_bool_false(self):
        assert _parse_value("false", "subtitle.optimize") is False
        assert _parse_value("no", "subtitle.optimize") is False
        assert _parse_value("0", "subtitle.optimize") is False

    def test_bool_invalid(self):
        with pytest.raises(ValueError, match="Expected boolean"):
            _parse_value("maybe", "subtitle.optimize")

    def test_int(self):
        assert _parse_value("8", "subtitle.thread_num") == 8
        assert isinstance(_parse_value("8", "subtitle.thread_num"), int)

    def test_int_invalid(self):
        with pytest.raises(ValueError, match="Expected integer"):
            _parse_value("abc", "subtitle.thread_num")

    def test_string(self):
        assert _parse_value("gpt-4o", "llm.model") == "gpt-4o"

    def test_unknown_key_stays_string(self):
        # Key not in DEFAULTS → stays string
        assert _parse_value("anything", "unknown.key") == "anything"


class TestTomlValue:
    def test_bool(self):
        assert _toml_value(True) == "true"
        assert _toml_value(False) == "false"

    def test_int(self):
        assert _toml_value(42) == "42"

    def test_float(self):
        assert _toml_value(0.5) == "0.5"

    def test_string(self):
        assert _toml_value("hello") == '"hello"'

    def test_string_with_quotes(self):
        assert _toml_value('say "hi"') == '"say \\"hi\\""'

    def test_string_with_newline(self):
        assert _toml_value("line1\nline2") == '"line1\\nline2"'


class TestConfigRoundtrip:
    def test_save_and_load(self, tmp_path, monkeypatch):
        config_file = tmp_path / "custom" / "config.toml"

        def fail_if_global_config_is_touched():
            raise AssertionError("custom config path must not touch the global config directory")

        monkeypatch.setattr(
            "videocaptioner.cli.config.ensure_config_dir",
            fail_if_global_config_is_touched,
        )

        save_config_value("llm.model", "gpt-4o", config_path=config_file)
        save_config_value("subtitle.thread_num", "8", config_path=config_file)
        save_config_value("subtitle.optimize", "false", config_path=config_file)

        loaded = load_config_file(config_file)
        assert loaded["llm"]["model"] == "gpt-4o"
        assert loaded["subtitle"]["thread_num"] == 8
        assert loaded["subtitle"]["optimize"] is False


class TestBuildConfig:
    def test_defaults_only(self):
        config = build_config(config_path=None)
        assert config["llm"]["model"] == DEFAULTS["llm"]["model"]

    def test_cli_overrides(self):
        config = build_config(cli_overrides={"llm": {"model": "custom"}})
        assert config["llm"]["model"] == "custom"

    def test_env_overrides(self, monkeypatch):
        monkeypatch.setenv("VIDEOCAPTIONER_LLM_MODEL", "env-model")
        config = build_config()
        assert config["llm"]["model"] == "env-model"

    def test_priority_cli_over_env(self, monkeypatch):
        monkeypatch.setenv("VIDEOCAPTIONER_LLM_MODEL", "env-model")
        config = build_config(cli_overrides={"llm": {"model": "cli-model"}})
        assert config["llm"]["model"] == "cli-model"


class TestGuiSettingsFallback:
    """The CLI reuses credentials typed into the GUI (AppData/settings.json)."""

    def test_active_llm_service_credentials_are_mapped(self, tmp_path):
        settings = _write_gui_settings(
            tmp_path / "settings.json",
            LLM={
                "LLMService": "DeepSeek",
                "OpenAI_API_Key": "sk-openai-should-be-ignored",
                "OpenAI_Model": "gpt-4o-mini",
                "DeepSeek_API_Key": "sk-deepseek",
                "DeepSeek_API_Base": "https://api.deepseek.com/v1",
                "DeepSeek_Model": "deepseek-chat",
            },
        )
        assert load_gui_settings(settings) == {
            "llm": {
                "api_key": "sk-deepseek",
                "api_base": "https://api.deepseek.com/v1",
                "model": "deepseek-chat",
            }
        }

    def test_missing_service_key_means_gui_default_openai(self, tmp_path):
        settings = _write_gui_settings(
            tmp_path / "settings.json",
            LLM={"OpenAI_API_Key": "sk-openai", "OpenAI_Model": "gpt-4o"},
        )
        loaded = load_gui_settings(settings)
        assert loaded["llm"] == {"api_key": "sk-openai", "model": "gpt-4o"}

    def test_unknown_service_is_skipped(self, tmp_path):
        settings = _write_gui_settings(
            tmp_path / "settings.json",
            LLM={"LLMService": "FutureProvider", "OpenAI_API_Key": "sk-openai"},
        )
        assert load_gui_settings(settings) == {}

    def test_blank_and_non_string_values_are_skipped(self, tmp_path):
        settings = _write_gui_settings(
            tmp_path / "settings.json",
            LLM={"LLMService": "OpenAI 兼容", "OpenAI_API_Key": "   ", "OpenAI_Model": 7},
            WhisperAPI={"WhisperApiKey": ""},
        )
        assert load_gui_settings(settings) == {}

    def test_other_credentials_and_provider_normalisation(self, tmp_path):
        settings = _write_gui_settings(
            tmp_path / "settings.json",
            WhisperAPI={"WhisperApiKey": "wk", "WhisperApiBase": "https://w.example/v1"},
            Translate={"DeeplxEndpoint": "http://127.0.0.1:1188/translate"},
            Dubbing={"TTSProvider": "local_ai", "TTSApiKey": "tk", "Voice": "vi-female"},
        )
        loaded = load_gui_settings(settings)
        assert loaded["whisper_api"] == {"api_key": "wk", "api_base": "https://w.example/v1"}
        assert loaded["translate"] == {"deeplx_endpoint": "http://127.0.0.1:1188/translate"}
        assert loaded["dubbing"] == {
            "tts_provider": "local-ai",
            "tts_api_key": "tk",
            "voice": "vi-female",
        }

    def test_missing_file_is_empty(self, tmp_path):
        assert load_gui_settings(tmp_path / "nope.json") == {}

    def test_corrupt_file_warns_and_is_empty(self, tmp_path, capsys):
        broken = tmp_path / "settings.json"
        broken.write_text("{not json", encoding="utf-8")
        assert load_gui_settings(broken) == {}
        assert "GUI settings" in capsys.readouterr().err

    def test_gui_sits_below_file_env_and_cli(self, tmp_path, monkeypatch):
        settings = _write_gui_settings(
            tmp_path / "settings.json",
            LLM={
                "LLMService": "OpenAI 兼容",
                "OpenAI_API_Key": "sk-gui",
                "OpenAI_API_Base": "https://gui.example/v1",
                "OpenAI_Model": "gui-model",
            },
        )
        config_file = tmp_path / "config.toml"
        save_config_value("llm.model", "file-model", config_path=config_file)
        monkeypatch.setenv("VIDEOCAPTIONER_LLM_API_BASE", "https://env.example/v1")

        config = build_config(
            cli_overrides={"llm": {"api_key": "sk-cli"}},
            config_path=config_file,
            gui_settings_path=settings,
        )
        assert config["llm"] == {
            "api_key": "sk-cli",
            "api_base": "https://env.example/v1",
            "model": "file-model",
        }

    def test_gui_fills_gaps_above_defaults(self, tmp_path):
        settings = _write_gui_settings(
            tmp_path / "settings.json",
            LLM={"LLMService": "OpenAI 兼容", "OpenAI_API_Key": "sk-gui"},
        )
        config = build_config(gui_settings_path=settings)
        assert config["llm"]["api_key"] == "sk-gui"
        assert config["llm"]["api_base"] == DEFAULTS["llm"]["api_base"]
        assert config["llm"]["model"] == DEFAULTS["llm"]["model"]

    def test_default_path_is_the_gui_settings_file(self, tmp_path, monkeypatch):
        settings = _write_gui_settings(
            tmp_path / "settings.json",
            LLM={"LLMService": "Gemini", "Gemini_API_Key": "gk"},
        )
        monkeypatch.setattr("videocaptioner.cli.config.gui_settings_file", lambda: settings)
        assert build_config()["llm"]["api_key"] == "gk"

"""CLI configuration management.

Config priority (highest to lowest):
  1. Command-line arguments
  2. Environment variables (VIDEOCAPTIONER_*)
  3. User config file (~/.config/videocaptioner/config.toml)
  4. GUI settings (AppData/settings.json), credentials and endpoints only
  5. Built-in defaults
"""

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from platformdirs import user_config_dir

from videocaptioner.core.asr.api_profiles import PROVIDER_PRESETS, endpoint_identity
from videocaptioner.core.llm.services import LLM_SERVICE_PRESETS

if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomllib
    except ModuleNotFoundError:
        import tomli as tomllib  # type: ignore[no-redef]

APP_NAME = "videocaptioner"

# Default config directory
CONFIG_DIR = Path(user_config_dir(APP_NAME))
CONFIG_FILE = CONFIG_DIR / "config.toml"

# Environment variable mappings: env var name → config dotted key
# Supports both OpenAI standard names and VIDEOCAPTIONER_ prefixed names
ENV_MAP: Dict[str, str] = {
    # OpenAI standard (most tools recognize these)
    "OPENAI_API_KEY": "llm.api_key",
    "OPENAI_BASE_URL": "llm.api_base",
    "OPENAI_MODEL": "llm.model",
    # VIDEOCAPTIONER_ prefixed (take precedence over standard)
    "VIDEOCAPTIONER_LLM_API_KEY": "llm.api_key",
    "VIDEOCAPTIONER_LLM_API_BASE": "llm.api_base",
    "VIDEOCAPTIONER_LLM_MODEL": "llm.model",
    "VIDEOCAPTIONER_WHISPER_API_KEY": "whisper_api.api_key",
    "VIDEOCAPTIONER_WHISPER_API_BASE": "whisper_api.api_base",
    "VIDEOCAPTIONER_WHISPER_API_MODEL": "whisper_api.model",
    "VIDEOCAPTIONER_WHISPER_API_PROVIDER": "whisper_api.provider",
    "VIDEOCAPTIONER_WHISPER_API_REQUEST_PROFILE": "whisper_api.request_profile",
    "VIDEOCAPTIONER_DEEPLX_ENDPOINT": "translate.deeplx_endpoint",
    "VIDEOCAPTIONER_TARGET_LANG": "translate.target_language",
}

# GUI settings.json -> CLI dotted key. Only credentials and endpoints are mirrored:
# behaviour toggles (optimize/translate/...) have different defaults per front-end
# and pulling them across would silently change what a CLI run does.
GUI_KEY_MAP: Dict[str, str] = {
    "WhisperAPI.WhisperApiKey": "whisper_api.api_key",
    "WhisperAPI.WhisperApiBase": "whisper_api.api_base",
    "WhisperAPI.WhisperApiModel": "whisper_api.model",
    "WhisperAPI.WhisperApiPrompt": "whisper_api.prompt",
    "WhisperAPI.WhisperApiProvider": "whisper_api.provider",
    "WhisperAPI.WhisperApiRequestProfile": "whisper_api.request_profile",
    "Translate.DeeplxEndpoint": "translate.deeplx_endpoint",
    "Dubbing.TTSProvider": "dubbing.tts_provider",
    "Dubbing.TTSApiKey": "dubbing.tts_api_key",
    "Dubbing.TTSApiBase": "dubbing.tts_api_base",
    "Dubbing.TTSModel": "dubbing.tts_model",
    "Dubbing.Voice": "dubbing.voice",
}

# LLM.LLMService (serialized LLMServiceEnum value) -> prefix of the GUI's
# per-service ConfigItem names (LLM.<prefix>_API_Key / _API_Base / _Model).
GUI_LLM_SERVICE_PREFIX: Dict[str, str] = {
    service.value: preset.settings_prefix
    for service, preset in LLM_SERVICE_PRESETS.items()
}

DEFAULTS: Dict[str, Any] = {
    "llm": {
        "api_key": "",
        "api_base": "https://api.openai.com/v1",
        "model": "gpt-4o-mini",
    },
    "whisper_api": {
        "api_key": "",
        "api_base": "https://api.openai.com/v1",
        "model": "whisper-1",
        "prompt": "",
        "provider": "custom",
        "request_profile": "auto",
    },
    "transcribe": {
        "asr": "bijian",
        "language": "auto",
        "faster_whisper": {
            "model": "large-v3",
            "device": "auto",
            "vad_filter": True,
            "vad_method": "silero-v4-fw",
            "vad_threshold": 0.5,
            "voice_extraction": False,
            "prompt": "",
        },
        "whisper_cpp": {
            "model": "large-v2",
        },
    },
    "subtitle": {
        "optimize": True,
        "translate": False,
        "split": True,
        "max_word_count_cjk": 18,
        "max_word_count_english": 12,
        "thread_num": 4,
        "batch_size": 20,
    },
    "translate": {
        "service": "llm",
        "target_language": "zh-Hans",
        "reflect": False,
        "deeplx_endpoint": "",
    },
    "synthesize": {
        "subtitle_mode": "soft",
        "quality": "medium",
        "layout": "target-above",
        "render_mode": "ass",
        "style": "default",
    },
    "dubbing": {
        "tts_provider": "openai",
        "tts_api_key": "",
        "tts_api_base": "https://api.openai.com/v1",
        "tts_model": "tts-1",
        "voice": "alloy",
        "tts_speed": 1.0,
        "tts_concurrency": 4,
        "text_source": "auto",
        "timing_mode": "natural",
        "natural_max_speed": 1.08,
        "legacy_max_speed": 1.5,
        "fit_ratio_limit": 1.05,
        "borrow_gap_ms": 350,
        "max_rewrite_attempts": 2,
        "timing_rewrite": True,
        "tts_cache": True,
        "unresolved_policy": "review",
        "mix_mode": "reduce",
        "original_volume": 0.4,
        "voice_volume": 1.0,
        "sample_rate": 32000,
    },
    "output": {
        "format": "srt",
    },
}


def _deep_merge(base: dict, override: dict) -> dict:
    """Merge override into base recursively. Override values take precedence."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _set_nested(d: dict, dotted_key: str, value: Any) -> None:
    """Set a value in a nested dict using dotted key notation (e.g. 'llm.api_key')."""
    keys = dotted_key.split(".")
    for key in keys[:-1]:
        d = d.setdefault(key, {})
    d[keys[-1]] = value


def _get_nested(d: dict, dotted_key: str, default: Any = None) -> Any:
    """Get a value from a nested dict using dotted key notation."""
    keys = dotted_key.split(".")
    for key in keys:
        if not isinstance(d, dict):
            return default
        d = d.get(key, default)  # type: ignore[assignment]
        if d is default:
            return default
    return d


def load_config_file(path: Optional[Path] = None) -> dict:
    """Load and parse a TOML config file. Returns empty dict if file doesn't exist."""
    path = path or CONFIG_FILE
    if not path.exists():
        return {}
    try:
        with open(path, "rb") as f:
            return tomllib.load(f)
    except Exception as e:
        import sys
        print(f"! Warning: Failed to parse config file {path}: {e}", file=sys.stderr)
        print("  Run 'videocaptioner config init' to recreate it.", file=sys.stderr)
        return {}


def gui_settings_file() -> Path:
    """Location of the GUI's ``settings.json``.

    Imported lazily: ``videocaptioner.config`` creates the AppData directories
    and edits PATH on import, which ``config show`` should not trigger.
    """
    from videocaptioner.config import SETTINGS_PATH

    return SETTINGS_PATH


def load_gui_settings(path: Optional[Path] = None) -> dict:
    """Map the GUI's settings.json onto CLI config keys.

    Sits below ``config.toml`` so keys typed once into the GUI are reused by the
    CLI. Only string values are copied and blanks are skipped, so CLI defaults
    such as ``llm.api_base`` survive an unset GUI field.
    """
    path = path or gui_settings_file()
    try:
        if not path.is_file():
            return {}
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, ValueError) as e:
        print(f"! Warning: Failed to read GUI settings {path}: {e}", file=sys.stderr)
        return {}
    if not isinstance(raw, dict):
        return {}

    overrides: Dict[str, Any] = {}

    def _copy(group: str, name: str, dotted_key: str) -> None:
        section = raw.get(group)
        value = section.get(name) if isinstance(section, dict) else None
        if isinstance(value, str) and value.strip():
            _set_nested(overrides, dotted_key, value)

    llm = raw.get("LLM")
    if isinstance(llm, dict):
        # A settings.json written before LLMService existed means the GUI default.
        service = llm.get("LLMService", "OpenAI 兼容")
        prefix = GUI_LLM_SERVICE_PREFIX.get(service) if isinstance(service, str) else None
        if prefix:
            _copy("LLM", f"{prefix}_API_Key", "llm.api_key")
            _copy("LLM", f"{prefix}_API_Base", "llm.api_base")
            _copy("LLM", f"{prefix}_Model", "llm.model")

    for gui_key, dotted_key in GUI_KEY_MAP.items():
        group, name = gui_key.split(".", 1)
        _copy(group, name, dotted_key)

    # GUI stores "local_ai"; the CLI choice list uses "local-ai".
    provider = _get_nested(overrides, "dubbing.tts_provider")
    if isinstance(provider, str):
        _set_nested(overrides, "dubbing.tts_provider", provider.replace("_", "-"))
    return overrides


def load_env_overrides() -> dict:
    """Read environment variables and map them to config keys.

    Supports both OpenAI standard names (OPENAI_API_KEY) and
    VIDEOCAPTIONER_ prefixed names. Prefixed names take precedence.
    """
    overrides: Dict[str, Any] = {}
    for env_var, dotted_key in ENV_MAP.items():
        value = os.environ.get(env_var)
        if value is not None:
            _set_nested(overrides, dotted_key, value)
    return overrides


def _merge_asr_layer(config: dict, layer: dict) -> dict:
    """Apply preset suggestions within precedence and never inherit keys across endpoints."""
    overrides = layer.get("whisper_api", {})
    previous = config["whisper_api"]
    if not isinstance(overrides, dict):
        return _deep_merge(config, layer)
    overrides = dict(overrides)
    provider = overrides.get("provider", previous["provider"])
    if provider != previous["provider"] and provider in PROVIDER_PRESETS:
        preset = PROVIDER_PRESETS[provider]
        overrides.setdefault("api_base", preset.base_url)
        overrides.setdefault("model", preset.models[0] if preset.models else "whisper-1")
        overrides.setdefault("request_profile", "auto")
        overrides.setdefault("prompt", "")
    base = overrides.get("api_base", previous["api_base"])
    if endpoint_identity(base) != endpoint_identity(previous["api_base"]):
        overrides.setdefault("api_key", "")
    return _deep_merge(config, {**layer, "whisper_api": overrides})


def build_config(
    cli_overrides: Optional[dict] = None,
    config_path: Optional[Path] = None,
    gui_settings_path: Optional[Path] = None,
) -> dict:
    """Build final config by merging all sources.

    Priority: cli > env > config file > GUI settings > defaults.
    """
    config = DEFAULTS.copy()
    # Layer 0: GUI settings.json (credentials only)
    config = _merge_asr_layer(config, load_gui_settings(gui_settings_path))
    # Layer 1: config file
    file_config = load_config_file(config_path)
    config = _merge_asr_layer(config, file_config)
    # Layer 2: environment variables
    env_config = load_env_overrides()
    config = _merge_asr_layer(config, env_config)
    # Layer 3: CLI argument overrides
    if cli_overrides:
        config = _merge_asr_layer(config, cli_overrides)
    return config


def get(config: dict, key: str, default: Any = None) -> Any:
    """Convenience accessor for dotted keys."""
    return _get_nested(config, key, default)


def ensure_config_dir() -> Path:
    """Ensure the config directory exists and return its path."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    return CONFIG_DIR


def _parse_value(raw: str, key: str) -> Any:
    """Parse a string value into the correct Python type based on DEFAULTS."""
    # Infer type from defaults
    default_val = _get_nested(DEFAULTS, key)
    if isinstance(default_val, bool):
        if raw.lower() in ("true", "1", "yes"):
            return True
        if raw.lower() in ("false", "0", "no"):
            return False
        raise ValueError(f"Expected boolean for '{key}', got '{raw}' (use true/false)")
    if isinstance(default_val, int):
        try:
            return int(raw)
        except ValueError:
            raise ValueError(f"Expected integer for '{key}', got '{raw}'")
    if isinstance(default_val, float):
        try:
            return float(raw)
        except ValueError:
            raise ValueError(f"Expected number for '{key}', got '{raw}'")
    return raw


def save_config_value(key: str, value: str, config_path: Optional[Path] = None) -> None:
    """Set a single value in the config file. Creates the file if it doesn't exist."""
    path = config_path or CONFIG_FILE
    path.parent.mkdir(parents=True, exist_ok=True)

    existing = load_config_file(path)
    if key in ("whisper_api.provider", "whisper_api.api_base"):
        # A sequence of `config set` commands must be as safe as one CLI override.
        current = _deep_merge(DEFAULTS["whisper_api"], existing.get("whisper_api", {}))
        credentials = dict(current.get("endpoint_credentials", {}))
        credentials[endpoint_identity(current["api_base"])] = {"api_key": current["api_key"]}
        change = {key.split(".", 1)[1]: value}
        updated = _merge_asr_layer({"whisper_api": current}, {"whisper_api": change})["whisper_api"]
        if endpoint_identity(updated["api_base"]) != endpoint_identity(current["api_base"]):
            updated["api_key"] = credentials.get(endpoint_identity(updated["api_base"]), {}).get("api_key", "")
        updated["endpoint_credentials"] = credentials
        existing["whisper_api"] = updated
    else:
        _set_nested(existing, key, _parse_value(value, key))

    with open(path, "w", encoding="utf-8") as f:
        _write_toml(f, existing)
    # Restrict permissions — config may contain API keys
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def _write_toml(f, data: dict, parent_key: str = "") -> None:
    """Write a dict as valid TOML, handling arbitrary nesting depth."""
    # Write scalar values at this level first
    for key, value in data.items():
        if not isinstance(value, dict):
            f.write(f"{key} = {_toml_value(value)}\n")

    # Write sub-tables recursively
    for key, value in data.items():
        if isinstance(value, dict):
            full_key = f"{parent_key}.{key}" if parent_key else key
            f.write(f"\n[{full_key}]\n")
            _write_toml(f, value, full_key)


def _toml_value(value: Any) -> str:
    """Convert a Python value to TOML representation."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        escaped = (value
            .replace("\\", "\\\\")
            .replace('"', '\\"')
            .replace("\n", "\\n")
            .replace("\r", "\\r")
            .replace("\t", "\\t"))
        return f'"{escaped}"'
    return f'"{value!s}"'


def format_config(config: dict, indent: int = 0) -> str:
    """Format config dict for display."""
    lines = []
    prefix = "  " * indent
    for key, value in config.items():
        if isinstance(value, dict):
            lines.append(f"{prefix}{key}:")
            lines.append(format_config(value, indent + 1))
        elif isinstance(value, str) and ("key" in key or "token" in key) and value:
            # Mask sensitive values
            masked = f"{value[:4]}...{value[-4:]}" if len(value) > 8 else "****"
            lines.append(f"{prefix}{key} = {masked}")
        else:
            lines.append(f"{prefix}{key} = {value}")
    return "\n".join(lines)

"""Small, explicit contracts for OpenAI-compatible file transcription."""

import hashlib
import json
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit


class ASRAPIError(ValueError):
    """A safe, user-facing transcription error without provider response data."""


class MissingTimingError(ASRAPIError):
    """Recognition cannot yet be used for subtitle generation."""


@dataclass(frozen=True)
class RequestProfile:
    name: str
    response_format: str
    timestamp_levels: tuple[str, ...]
    supports_language: bool = True
    supports_prompt: bool = True
    supports_speaker: bool = False
    max_upload_bytes: int = 25_000_000


WHISPER = RequestProfile("whisper", "verbose_json", ("word", "segment"))
JSON_TEXT = RequestProfile("json-text", "json", ())
REQUEST_PROFILES = {p.name: p for p in (WHISPER, JSON_TEXT)}
PROFILE_CHOICES = ("auto", *REQUEST_PROFILES)


@dataclass(frozen=True)
class ProviderPreset:
    label: str
    base_url: str
    models: tuple[str, ...]


PROVIDER_PRESETS = {
    "custom": ProviderPreset("Custom", "", ()),
    "videocaptioner": ProviderPreset(
        "VideoCaptioner API", "https://api.videocaptioner.cn/v1",
        ("whisper-1", "gpt-4o-transcribe", "gpt-4o-mini-transcribe"),
    ),
    "groq": ProviderPreset(
        "Groq", "https://api.groq.com/openai/v1",
        ("whisper-large-v3", "whisper-large-v3-turbo"),
    ),
    "openai": ProviderPreset(
        "OpenAI", "https://api.openai.com/v1",
        ("whisper-1", "gpt-4o-transcribe", "gpt-4o-mini-transcribe"),
    ),
}
MODEL_SUGGESTIONS = list(dict.fromkeys(
    model for preset in PROVIDER_PRESETS.values() for model in preset.models
))
MODEL_PROFILES = {
    "whisper-1": WHISPER,
    "whisper-large-v3": WHISPER,
    "whisper-large-v3-turbo": WHISPER,
    "gpt-4o-transcribe": JSON_TEXT,
    "gpt-4o-mini-transcribe": JSON_TEXT,
}


def normalize_endpoint(base_url: str) -> str:
    """Reject credential-bearing URLs; keep custom route prefixes intact."""
    try:
        # Keep this module SDK-free: GUI configuration imports provider metadata at startup.
        parts = urlsplit(base_url.strip())
        if (parts.scheme not in ("https", "http") or not parts.hostname
                or parts.username or parts.password or parts.query or parts.fragment):
            raise ValueError
        port = parts.port
        host = parts.hostname.lower()
        if ":" in host:
            host = f"[{host}]"
        if port and (parts.scheme, port) not in (("https", 443), ("http", 80)):
            host += f":{port}"
        return urlunsplit((parts.scheme.lower(), host, parts.path.rstrip("/") or "/v1", "", ""))
    except ValueError:
        raise ASRAPIError("ASR Base URL must be HTTP(S), without credentials, query or fragment.") from None


def endpoint_identity(base_url: str) -> str:
    """Opaque identity suitable for settings maps and cache isolation."""
    try:
        normalized = normalize_endpoint(base_url)
    except ASRAPIError:
        normalized = base_url.strip()
    return hashlib.sha256(normalized.encode()).hexdigest()


def resolve_profile(model: str, profile: str = "auto", provider: str = "custom") -> RequestProfile:
    if provider not in PROVIDER_PRESETS or profile not in PROFILE_CHOICES:
        raise ASRAPIError("Unknown ASR provider or request profile.")
    if not model.strip():
        raise ASRAPIError("ASR model must be set.")
    known = MODEL_PROFILES.get(model.strip())
    if profile == "auto":
        # Preserve the historical Whisper contract for saved custom model IDs.
        return known or WHISPER
    selected = REQUEST_PROFILES[profile]
    if known is JSON_TEXT and selected.timestamp_levels:
        raise ASRAPIError("This model requires the JSON text request profile; timestamps are unsupported.")
    return selected


def require_subtitle_timing(profile: RequestProfile) -> None:
    if not profile.timestamp_levels:
        raise MissingTimingError(
            "This model returns text without timestamps. Use the Chinese alignment (S2) transcription "
            "pipeline with a ready runtime, or use a Whisper timestamp model."
        )


def fingerprint(audio: bytes, endpoint: str, model: str, language: str, prompt: str,
                profile: RequestProfile, word_timing: bool, provider: str) -> str:
    payload = {
        "version": 2, "audio": hashlib.sha256(audio).hexdigest(),
        "endpoint": endpoint_identity(normalize_endpoint(endpoint)), "model": model.strip(),
        "language": language, "prompt": hashlib.sha256(prompt.encode()).hexdigest(),
        "profile": profile.name, "response_format": profile.response_format,
        "timestamps": profile.timestamp_levels, "word_timing": word_timing, "provider": provider,
    }
    return "v2-" + hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()

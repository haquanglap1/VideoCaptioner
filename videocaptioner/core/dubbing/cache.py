"""Persistent credential-free WAV cache for natural dubbing."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import wave
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from videocaptioner.config import CACHE_PATH
from videocaptioner.core.dubbing.audio_mixer import get_audio_duration
from videocaptioner.core.dubbing.planner import NORMALIZATION_VERSION, normalize_tts_text

CACHE_SCHEMA_VERSION = "dubbing-tts-cache-v1"


@dataclass(frozen=True)
class TTSCacheEntry:
    key: str
    audio_path: str
    duration: float
    metadata_path: str


def _api_host(api_base: str) -> str:
    parsed = urlparse(api_base or "")
    host = (parsed.hostname or "").lower()
    return f"{host}:{parsed.port}" if parsed.port else host


def build_tts_cache_key(
    *,
    text: str,
    provider: str,
    api_base: str,
    model: str,
    voice: str,
    speed: float,
    sample_rate: int,
    runtime_identity: dict[str, Any] | None = None,
) -> str:
    payload = {
        "schema_version": CACHE_SCHEMA_VERSION,
        "normalization_version": NORMALIZATION_VERSION,
        "text": normalize_tts_text(text),
        "provider": provider,
        "api_host": _api_host(api_base),
        "model": model,
        "voice": voice,
        "speed": round(float(speed), 4),
        "sample_rate": int(sample_rate),
    }
    if runtime_identity:
        payload["runtime_identity"] = dict(runtime_identity)
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def measure_audio_duration(path: str | Path) -> float:
    audio_path = Path(path)
    if not audio_path.is_file():
        return 0.0
    try:
        with wave.open(str(audio_path), "rb") as wav:
            rate = wav.getframerate()
            return wav.getnframes() / rate if rate > 0 else 0.0
    except (wave.Error, OSError, EOFError):
        return get_audio_duration(str(audio_path))


class PersistentTTSCache:
    def __init__(self, root: str | Path | None = None, *, enabled: bool = True):
        self.root = Path(root) if root else CACHE_PATH / "dubbing_tts" / "v1"
        self.enabled = enabled

    def get(self, key: str) -> TTSCacheEntry | None:
        if not self.enabled:
            return None
        wav_path = self.root / f"{key}.wav"
        metadata_path = self.root / f"{key}.json"
        if not wav_path.is_file() or not metadata_path.is_file():
            return None
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        duration = measure_audio_duration(wav_path)
        if metadata.get("key") != key or duration <= 0:
            return None
        return TTSCacheEntry(key, str(wav_path), duration, str(metadata_path))

    def invalidate(self, key: str) -> bool:
        """Remove exactly one cache entry and leave every other key untouched."""
        if not self.enabled or not key:
            return False
        removed = False
        for suffix in (".wav", ".json"):
            path = self.root / f"{key}{suffix}"
            try:
                path.unlink()
                removed = True
            except FileNotFoundError:
                continue
        return removed

    def put(
        self,
        key: str,
        source_audio: str | Path,
        *,
        provider: str,
        model: str,
        voice: str,
        sample_rate: int,
        runtime_identity: dict[str, Any] | None = None,
    ) -> TTSCacheEntry | None:
        if not self.enabled:
            return None
        source_path = Path(source_audio)
        duration = measure_audio_duration(source_path)
        if duration <= 0:
            return None
        self.root.mkdir(parents=True, exist_ok=True)
        wav_path = self.root / f"{key}.wav"
        metadata_path = self.root / f"{key}.json"
        wav_tmp = self.root / f".{key}.{os.getpid()}.wav.tmp"
        json_tmp = self.root / f".{key}.{os.getpid()}.json.tmp"
        shutil.copyfile(source_path, wav_tmp)
        metadata = {
            "schema_version": CACHE_SCHEMA_VERSION,
            "key": key,
            "duration": round(duration, 6),
            "provider": provider,
            "model": model,
            "voice": voice,
            "sample_rate": int(sample_rate),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        if runtime_identity:
            metadata["runtime_identity"] = dict(runtime_identity)
        json_tmp.write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        os.replace(wav_tmp, wav_path)
        os.replace(json_tmp, metadata_path)
        return TTSCacheEntry(key, str(wav_path), duration, str(metadata_path))

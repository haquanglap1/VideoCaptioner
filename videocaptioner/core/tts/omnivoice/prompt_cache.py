"""Versioned reference prompts, stored as bounded JSON rather than executable pickle."""

import hashlib
import json
from pathlib import Path
from uuid import uuid4

MAX_BYTES = 2 * 1024 * 1024


def cache_directory() -> Path:
    from videocaptioner.config import CACHE_PATH
    return CACHE_PATH / "omnivoice-prompts"


def fingerprint(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
        separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


class PromptCache:
    def __init__(self, identity):
        self.identity = dict(identity)
        self.path = cache_directory() / (fingerprint(identity) + ".json")

    def restore(self, destination: Path) -> bool:
        try:
            if self.path.stat().st_size > MAX_BYTES:
                return False
            entry = json.loads(self.path.read_text(encoding="utf-8"))
            if entry["identity"] != self.identity or fingerprint(entry["prompt"]) != entry["sha256"]:
                return False
            destination.write_text(json.dumps(entry["prompt"], ensure_ascii=False, allow_nan=False), encoding="utf-8")
            return True
        except (OSError, ValueError, KeyError, TypeError):
            return False

    def store(self, source: Path) -> bool:
        temporary = self.path.with_name(uuid4().hex + ".tmp")
        try:
            if source.stat().st_size > MAX_BYTES:
                return False
            prompt = json.loads(source.read_text(encoding="utf-8"))
            entry = {"identity": self.identity, "prompt": prompt, "sha256": fingerprint(prompt)}
            content = json.dumps(entry, ensure_ascii=False, allow_nan=False)
            if len(content.encode("utf-8")) > MAX_BYTES:
                return False
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary.write_text(content, encoding="utf-8")
            temporary.replace(self.path)
            return True
        except (OSError, ValueError, TypeError):
            return False
        finally:
            temporary.unlink(missing_ok=True)

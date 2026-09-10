"""Discover and inspect an existing offline OCR installation without loading a model."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path

from .document import OcrConfig
from .geometry import Roi
from .models import Check, OcrError, Selection
from .profile import OcrProfileSnapshot
from .runtime import OcrRuntimeMissing


def resources() -> Path:
    return Path(__file__).resolve().parents[2] / "resources" / "ocr"


def default_runtime() -> Path:
    from videocaptioner.config import ROOT_PATH, portable_models_path

    portable = portable_models_path()
    return (portable / "ocr") if portable else Path(ROOT_PATH) / "runtime" / "ocr"


@dataclass(frozen=True)
class OcrInstallation:
    root: Path
    bridge: Path
    profile_sha256: str
    bridge_sha256: str
    profile: OcrProfileSnapshot

    def config(self, roi: Roi, selection: Selection) -> OcrConfig:
        return OcrConfig(roi, selection, self.profile_sha256, self.bridge_sha256, profile_snapshot=self.profile)


def inspect_installation(root: Path | None = None, check: Check = lambda: None) -> OcrInstallation:
    check()
    root = (root or default_runtime()).resolve()
    bundle = resources()
    bridge, recipe = bundle / "ocr_stream_worker.py", bundle / "profile.json"
    python = root / "env/python.exe"
    if not python.is_file():
        python = root / ("env/Scripts/python.exe" if os.name == "nt" else "env/bin/python")
    if not all(p.is_file() for p in (python, root / "profile.json", bridge, recipe)):
        raise OcrRuntimeMissing("Chưa có runtime OCR. Chọn thư mục OCR đã cài; ứng dụng không tự tải model.")
    raw = recipe.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    if hashlib.sha256((root / "profile.json").read_bytes()).hexdigest() != sha:
        raise OcrError("Profile OCR đã cài không khớp phiên bản của ứng dụng.")
    profile = OcrProfileSnapshot.from_bytes(raw, sha)
    models = json.loads(raw)["models"]
    for item in models.values():
        path = root / "weights" / item["file"]
        if path.parent.resolve() != (root / "weights").resolve() or not path.is_file():
            raise OcrRuntimeMissing("Thiếu model OCR trong runtime đã chọn.")
        hasher = hashlib.sha256()
        with path.open("rb") as stream:
            while block := stream.read(1024 * 1024):
                check()
                hasher.update(block)
        if hasher.hexdigest() != item["sha256"]:
            raise OcrError("Model OCR không khớp SHA đã ghim.")
    return OcrInstallation(root, bridge, sha, hashlib.sha256(bridge.read_bytes()).hexdigest(), profile)

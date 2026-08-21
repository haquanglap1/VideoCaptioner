"""Discover a versioned VieNeu runtime without hardcoded developer paths."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

from videocaptioner.config import ROOT_PATH


@dataclass(frozen=True)
class VieNeuRuntimeLayout:
    runtime_root: Path
    python_executable: Path
    bridge_script: Path
    runtime_version: str = ""
    source: str = ""

    def validate(self) -> None:
        if not self.python_executable.is_file():
            raise FileNotFoundError(f"VieNeu runtime Python not found: {self.python_executable}")
        if not self.bridge_script.is_file():
            raise FileNotFoundError(f"VieNeu bridge not found: {self.bridge_script}")


class VieNeuRuntimeLocator:
    ENV_RUNTIME = "VIDEOCAPTIONER_VIENEU_RUNTIME"
    ENV_BRIDGE = "VIDEOCAPTIONER_VIENEU_BRIDGE"

    def __init__(self, *, app_root: str | Path | None = None):
        self.app_root = Path(app_root) if app_root else Path(ROOT_PATH)

    @staticmethod
    def _source_root() -> Path:
        return Path(__file__).resolve().parents[4]

    @staticmethod
    def _python_from_root(root_or_python: Path) -> tuple[Path, Path]:
        if root_or_python.is_file():
            return root_or_python.parent, root_or_python
        candidates = (
            root_or_python / "python.exe",
            root_or_python / "Scripts" / "python.exe",
            root_or_python / "bin" / "python",
        )
        python = next((candidate for candidate in candidates if candidate.is_file()), candidates[0])
        return root_or_python, python

    @staticmethod
    def _read_version(runtime_root: Path) -> str:
        manifest = runtime_root / "runtime-manifest.json"
        if not manifest.is_file():
            return ""
        try:
            payload = json.loads(manifest.read_text(encoding="utf-8"))
            return str(payload.get("runtime_version", ""))
        except (OSError, json.JSONDecodeError):
            return ""

    def locate(
        self,
        explicit_runtime: str | Path | None = None,
        explicit_bridge: str | Path | None = None,
    ) -> VieNeuRuntimeLayout:
        runtime_value = explicit_runtime or os.environ.get(self.ENV_RUNTIME, "")
        bridge_value = explicit_bridge or os.environ.get(self.ENV_BRIDGE, "")
        if runtime_value:
            runtime_root, python = self._python_from_root(Path(runtime_value).expanduser().resolve())
            bridge = (
                Path(bridge_value).expanduser().resolve()
                if bridge_value
                else self._default_bridge(runtime_root)
            )
            layout = VieNeuRuntimeLayout(
                runtime_root,
                python,
                bridge,
                self._read_version(runtime_root),
                "explicit",
            )
            layout.validate()
            return layout

        packaged_root = self.app_root / "runtime" / "vieneu"
        runtime_root, python = self._python_from_root(packaged_root)
        bridge = self._default_bridge(packaged_root)
        layout = VieNeuRuntimeLayout(
            runtime_root,
            python,
            bridge,
            self._read_version(packaged_root),
            "packaged" if getattr(sys, "frozen", False) else "source-bundle",
        )
        layout.validate()
        return layout

    def _default_bridge(self, runtime_root: Path) -> Path:
        candidates = (
            runtime_root / "bridge" / "vieneu_bridge.py",
            self.app_root / "runtime" / "vieneu" / "bridge" / "vieneu_bridge.py",
            self._source_root() / "runtime" / "vieneu" / "bridge" / "vieneu_bridge.py",
        )
        return next((candidate for candidate in candidates if candidate.is_file()), candidates[0])

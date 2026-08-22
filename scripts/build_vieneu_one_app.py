#!/usr/bin/env python3
"""Build a one-app portable directory with VideoCaptioner, VieNeu runtime and model seed."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def run(command: list[str], *, env: dict[str, str] | None = None) -> None:
    result = subprocess.run(
        command,
        cwd=str(PROJECT_ROOT),
        env=env,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Command failed with exit code {result.returncode}: {command[0]}")


def tree_stats(root: Path) -> tuple[int, int]:
    count = 0
    size = 0
    for path in root.rglob("*"):
        if path.is_file():
            count += 1
            size += path.stat().st_size
    return count, size


def safe_remove_distribution(path: Path) -> None:
    dist_root = (PROJECT_ROOT / "dist").resolve()
    resolved = path.resolve()
    if not resolved.is_relative_to(dist_root) or resolved == dist_root:
        raise RuntimeError("Distribution overwrite is restricted to a named directory under dist/")
    shutil.rmtree(resolved)


def copy_model_seed(source_root: Path, package_root: Path) -> dict:
    state_path = source_root / "state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    active_revision = str(state.get("active_revision", ""))
    references = {
        str(state.get("active_snapshot", "")),
        str(state.get("tokenizer_snapshot", "")),
        str(state.get("codec_snapshot", "")),
    }
    if not active_revision or "" in references:
        raise RuntimeError("Model seed requires active model/tokenizer/codec snapshots")
    destination_root = package_root / "AppData" / "models" / "vieneu"
    for reference in references:
        source = (source_root / reference).resolve()
        if not source.is_dir() or not source.is_relative_to(source_root.resolve()):
            raise RuntimeError(f"Invalid model seed reference: {reference}")
        destination = destination_root / reference
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, destination, symlinks=False)
    packaged_state = dict(state)
    packaged_state.update(
        {
            "previous_revision": "",
            "previous_snapshot": "",
            "candidate_revision": "",
            "candidate_snapshot": "",
            "rejected_revisions": {},
            "last_error": "",
        }
    )
    destination_root.mkdir(parents=True, exist_ok=True)
    (destination_root / "state.json").write_text(
        json.dumps(packaged_state, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return packaged_state


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", required=True)
    parser.add_argument("--runtime", required=True)
    parser.add_argument("--model-root", required=True)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--skip-exe-build", action="store_true")
    args = parser.parse_args()

    runtime = Path(args.runtime).resolve()
    runtime_python = runtime / "python.exe"
    runtime_bridge = runtime / "bridge" / "vieneu_bridge.py"
    runtime_manifest_path = runtime / "runtime-manifest.json"
    for required in (runtime_python, runtime_bridge, runtime_manifest_path):
        if not required.is_file():
            raise RuntimeError(f"Built VieNeu runtime is incomplete: {required.name}")
    runtime_manifest = json.loads(runtime_manifest_path.read_text(encoding="utf-8"))

    package = PROJECT_ROOT / "dist" / args.name
    if not args.skip_exe_build:
        environment = os.environ.copy()
        environment["VC_BUILD_NAME"] = args.name
        run(
            [
                sys.executable,
                "-m",
                "PyInstaller",
                "VideoCaptioner.spec",
                "--clean",
                "--noconfirm",
            ],
            env=environment,
        )
    exe = package / f"{args.name}.exe"
    if not exe.is_file():
        legacy_exe = PROJECT_ROOT / "dist" / f"{args.name}.exe"
        if not legacy_exe.is_file():
            raise RuntimeError(f"VideoCaptioner onedir build is incomplete: {exe}")
        if package.exists():
            if not args.overwrite:
                raise RuntimeError(f"Distribution already exists: {package}")
            safe_remove_distribution(package)
        package.mkdir(parents=True)
        exe = package / legacy_exe.name
        shutil.copy2(legacy_exe, exe)

    runtime_target = package / "runtime" / "vieneu"
    model_target = package / "AppData" / "models" / "vieneu"
    manifest_target = package / "distribution-manifest.json"
    existing_managed = [
        path for path in (runtime_target, model_target, manifest_target) if path.exists()
    ]
    if existing_managed and not args.overwrite:
        raise RuntimeError(
            "Distribution already contains managed VieNeu data; pass --overwrite to replace it"
        )
    for path in existing_managed:
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()

    shutil.copytree(runtime, package / "runtime" / "vieneu")
    packaged_state = copy_model_seed(Path(args.model_root).resolve(), package)
    runtime_count, runtime_bytes = tree_stats(package / "runtime" / "vieneu")
    model_count, model_bytes = tree_stats(package / "AppData" / "models" / "vieneu")
    distribution_manifest = {
        "schema_version": "vieneu-one-app-distribution-v1",
        "name": args.name,
        "created_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "exe": {
            "file": exe.name,
            "bytes": exe.stat().st_size,
            "sha256": sha256(exe),
        },
        "runtime": {
            "file_count": runtime_count,
            "bytes": runtime_bytes,
            "runtime_version": runtime_manifest.get("runtime_version", ""),
            "source_revision": runtime_manifest.get("runtime_source_revision", ""),
            "requirements_sha256": runtime_manifest.get("requirements_sha256", ""),
            "wheel_sha256": runtime_manifest.get("vieneu_wheel_sha256", ""),
        },
        "model_seed": {
            "file_count": model_count,
            "bytes": model_bytes,
            "active_revision": packaged_state["active_revision"],
            "tokenizer_revision": packaged_state["tokenizer_revision"],
            "codec_revision": packaged_state["codec_revision"],
        },
    }
    (package / "distribution-manifest.json").write_text(
        json.dumps(distribution_manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"package": str(package), **distribution_manifest}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

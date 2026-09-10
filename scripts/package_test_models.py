"""Copy installed model/runtime payloads into one relocatable test-app models folder.

No downloads or dependency installation. Existing source installations are read-only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path

EXCLUDED = {"__pycache__", ".git", ".cache", ".locks", ".huggingface", "uv-cache", "download-cache",
            "pyvenv.cfg", "install.lock", "install.log", "source.zip", "CACHEDIR.TAG"}
SCHEMA = "portable-models-v1"


def digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def copy_payload(source: Path, target: Path, *, skip_site_packages: bool = False) -> None:
    source = source.resolve(strict=True)
    for parent, directories, files in os.walk(source, followlinks=False):
        directories[:] = [name for name in directories if name not in EXCLUDED and not name.startswith(".")
                          and not (skip_site_packages and name == "site-packages")]
        for name in directories:
            path = Path(parent) / name
            if path.is_symlink() or getattr(path, "is_junction", lambda: False)():
                raise ValueError("Runtime directory links must be materialized before packaging")
        for name in files:
            if name in EXCLUDED or name.startswith(".") or name.endswith((".pyc", ".log", ".part")):
                continue
            src = Path(parent) / name
            if not src.resolve().is_relative_to(source):
                raise ValueError("Payload file escapes the selected source folder")
            dst = target / src.relative_to(source)
            dst.parent.mkdir(parents=True, exist_ok=True)
            expected = digest(src)
            if dst.exists():
                if digest(dst) != expected:
                    raise ValueError(f"Conflicting existing payload: {dst.name}; use a new output folder")
            else:
                temporary = dst.with_name(dst.name + ".copying")
                shutil.copyfile(src, temporary)
                if digest(temporary) != expected:
                    raise ValueError("Payload verification failed")
                os.replace(temporary, dst)


def make_standalone_python(target: Path, base: Path) -> None:
    """Materialize the existing CPython base beside site-packages; no venv home paths."""
    if not (base / "python.exe").is_file() or not (base / "Lib/os.py").is_file():
        raise ValueError("An existing standalone Windows Python 3.12 base is required")
    copy_payload(base, target, skip_site_packages=True)


def append_ocr_payload(target: Path, incoming: Path) -> None:
    """Append a verified standalone OCR component to a newly copied owned collection.

    Existing ASR/TTS files and inventory entries are retained. Neither source
    collection is changed; the caller must supply a separate build destination.
    """
    target, incoming = target.resolve(), incoming.resolve()
    if target.is_relative_to(incoming) or incoming.is_relative_to(target):
        raise ValueError("OCR and destination model collections must be separate")
    owner = target / ".portable-models-staging.json"
    if not owner.is_file() or json.loads(owner.read_text(encoding="utf-8")).get("schema") != SCHEMA:
        raise ValueError("Destination model collection has no valid staging owner")
    manifest_path = target / "portable-models.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    ocr = json.loads((incoming / "portable-models.json").read_text(encoding="utf-8"))
    if (manifest.get("schema") != SCHEMA or ocr.get("schema") != SCHEMA
            or ocr.get("components") != ["ocr"] or "ocr" in manifest.get("components", [])
            or (target / "ocr").exists()):
        raise ValueError("Expected one new OCR component and an existing ASR/TTS inventory")
    incoming_files = ocr["files"]
    if not incoming_files or len(incoming_files) != len({name.lower() for name in incoming_files}):
        raise ValueError("Invalid OCR inventory")
    for name, expected in incoming_files.items():
        path = Path(name)
        if (not name.startswith("ocr/") or path.is_absolute() or ".." in path.parts
                or ":" in name or "\\" in name or name in manifest["files"]):
            raise ValueError("OCR inventory escapes its component")
        source = incoming / path
        if (not source.resolve().is_relative_to(incoming / "ocr") or not source.is_file()
                or source.stat().st_size != expected["size"] or digest(source) != expected["sha256"]):
            raise ValueError("OCR payload differs from its verified inventory")
    copy_payload(incoming / "ocr", target / "ocr")
    for name, expected in incoming_files.items():
        destination = target / name
        if destination.stat().st_size != expected["size"] or digest(destination) != expected["sha256"]:
            raise ValueError("Copied OCR payload verification failed")
    manifest["files"].update(incoming_files)
    manifest["components"].append("ocr")
    manifest["total_bytes"] = sum(item["size"] for item in manifest["files"].values())
    temporary = manifest_path.with_suffix(".json.ocr-tmp")
    with temporary.open("x", encoding="utf-8") as stream:
        json.dump(manifest, stream, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, manifest_path)


def package(args) -> dict:
    root = args.app_dir.resolve() / "models"
    owner = root / ".portable-models-staging.json"
    if root.exists() and any(root.iterdir()) and not owner.exists():
        raise ValueError("Refusing to merge into an existing model collection")
    root.mkdir(parents=True, exist_ok=True)
    owner.write_text(json.dumps({"schema": SCHEMA}), encoding="utf-8")
    components = []
    selections = [
        ("faster-whisper", args.faster_whisper, root / "tools/Faster-Whisper-XXL", None),
        ("qwen", args.qwen_runtime, root / "qwen", root / "qwen"),
        ("diarization", args.diarization_runtime, root / "diarization", root / "diarization"),
        ("omnivoice", args.omnivoice_runtime, root / "omnivoice", root / "omnivoice/env"),
        ("vieneu-runtime", args.vieneu_runtime, root / "vieneu-runtime", None),
        ("ocr", getattr(args, "ocr_runtime", None), root / "ocr", root / "ocr/env"),
    ]
    for name, source, target, environment in selections:
        if source is None:
            continue
        print(f"Copying installed {name}", flush=True)
        copy_payload(source, target)
        if environment is not None:
            make_standalone_python(environment, args.python_base)
        components.append(name)
    if args.weights_dir:
        for source in sorted(args.weights_dir.iterdir()):
            if source.is_dir() and (source.name.startswith("faster-whisper-") or source.name == "vieneu"):
                print(f"Copying installed weights: {source.name}", flush=True)
                copy_payload(source, root / source.name)
                components.append(source.name)
    files = {}
    for path in root.rglob("*"):
        if path.is_file() and path.name not in ("portable-models.json", owner.name):
            files[path.relative_to(root).as_posix()] = {"size": path.stat().st_size, "sha256": digest(path)}
    manifest = {"schema": SCHEMA, "components": components, "files": files,
                "total_bytes": sum(info["size"] for info in files.values()), "downloads": 0}
    (root / "portable-models.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in manifest.items() if key != "files"}), flush=True)
    return manifest


def main():
    if sys.version_info[:2] != (3, 12) or os.name != "nt":
        raise SystemExit("Package Windows test runtimes with the existing Python 3.12 interpreter")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app-dir", type=Path, required=True)
    parser.add_argument("--python-base", type=Path, default=Path(sys.base_prefix))
    for name in ("faster-whisper", "weights-dir", "qwen-runtime", "diarization-runtime", "omnivoice-runtime", "vieneu-runtime", "ocr-runtime"):
        parser.add_argument("--" + name, type=Path)
    package(parser.parse_args())


if __name__ == "__main__":
    main()

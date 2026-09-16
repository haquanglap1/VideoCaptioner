"""Stage the v6 medium candidate from verified installed CPU files, without downloads."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from scripts.package_test_models import SCHEMA, digest
from videocaptioner.core.ocr.installation import inspect_installation, resources


def package_candidate(source_models: Path, weights: Path, app_dir: Path) -> dict:
    source_models, weights, app_dir = source_models.resolve(), weights.resolve(), app_dir.resolve()
    target = app_dir / "models"
    if (target.exists() or app_dir.is_relative_to(source_models) or source_models.is_relative_to(app_dir)
            or app_dir.is_relative_to(weights) or weights.is_relative_to(app_dir)):
        raise ValueError("Use a new candidate destination separate from the installed sources")
    owner = json.loads((source_models / ".portable-models-staging.json").read_bytes())
    old = json.loads((source_models / "portable-models.json").read_bytes())
    if owner.get("schema") != SCHEMA or old.get("schema") != SCHEMA or "ocr" not in old["components"]:
        raise ValueError("Expected an owned, inventoried OCR source collection")
    recipe_path = resources() / "profile-v6-medium.json"
    recipe = json.loads(recipe_path.read_bytes())
    selected = []
    for name, expected in old["files"].items():
        if not name.startswith("ocr/env/"):
            continue
        if ".." in Path(name).parts or ":" in name or "\\" in name:
            raise ValueError("Invalid installed runtime inventory path")
        source = source_models / name
        if not source.resolve().is_relative_to(source_models / "ocr/env") or not source.is_file():
            raise ValueError("Installed runtime escapes its component")
        selected.append((source, name.replace("ocr/", "ocr-v6-medium/", 1), expected))
    if not any(name == "ocr-v6-medium/env/python.exe" for _, name, _ in selected):
        raise ValueError("Expected an already standalone Python runtime")
    for stage, model in recipe["models"].items():
        source = (source_models / "ocr/weights" if stage == "cls" else weights) / model["file"]
        if not source.is_file() or digest(source) != model["sha256"]:
            raise ValueError("Candidate model does not match the pinned SHA")
        selected.append((source, "ocr-v6-medium/weights/" + model["file"],
                         {"size": source.stat().st_size, "sha256": model["sha256"]}))
    selected.append((recipe_path, "ocr-v6-medium/profile.json",
                     {"size": recipe_path.stat().st_size, "sha256": digest(recipe_path)}))
    target.mkdir(parents=True)
    (target / ".portable-models-staging.json").write_text(json.dumps({"schema": SCHEMA}), encoding="utf-8")
    inventory = {}
    for source, name, expected in selected:
        destination = target / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("xb") as out, source.open("rb") as stream:
            shutil.copyfileobj(stream, out)
        if destination.stat().st_size != expected["size"] or digest(destination) != expected["sha256"]:
            raise ValueError("Candidate copy differs from its pinned source inventory")
        inventory[name] = expected
    inspect_installation(target / "ocr-v6-medium")
    manifest = {"schema": SCHEMA, "components": ["ocr-v6-medium"], "files": inventory,
                "total_bytes": sum(item["size"] for item in inventory.values()), "downloads": 0}
    with (target / "portable-models.json").open("x", encoding="utf-8") as stream:
        json.dump(manifest, stream, indent=2)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-models", type=Path, required=True)
    parser.add_argument("--weights", type=Path, required=True)
    parser.add_argument("--app-dir", type=Path, required=True)
    args = parser.parse_args()
    manifest = package_candidate(args.source_models, args.weights, args.app_dir)
    print(json.dumps({"files": len(manifest["files"]), "bytes": manifest["total_bytes"], "downloads": 0}))


if __name__ == "__main__":
    main()

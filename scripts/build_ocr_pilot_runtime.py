"""Build one isolated CPU OCR pilot runtime; never modify the application environment."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from scripts.package_test_models import digest
from videocaptioner.core.utils.subprocess_helper import child_environment

DATA = Path(__file__).with_name("ocr_pilot_data")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--lock", type=Path, required=True)
    args = parser.parse_args()
    if sys.version_info[:2] != (3, 12):
        parser.error("Use the existing Python 3.12 interpreter")
    root = args.root.resolve()
    if root.exists():
        parser.error("Use a new runtime root; existing installations are preserved")
    root.mkdir(parents=True)
    started = time.perf_counter()
    uv = shutil.which("uv")
    if uv is None:
        raise RuntimeError("uv is required")
    commands = [
        [uv, "venv", "--no-config", "--python", sys.executable, str(root / "env")],
        [uv, "pip", "install", "--no-config", "--python", str(root / "env/Scripts/python.exe"),
         "--require-hashes", "--no-deps", "-r", str(args.lock.resolve())],
    ]
    for number, command in enumerate(commands):
        with (root / f"setup-{number}.log").open("w", encoding="utf-8") as log:
            subprocess.run(command, env=child_environment(), stdout=log, stderr=log, check=True,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    profile = json.loads((DATA / "profile.json").read_text(encoding="utf-8"))
    (root / "weights").mkdir()
    downloads = []
    for item in profile["models"].values():
        destination = root / "weights" / item["file"]
        if item.get("bundled"):
            shutil.copyfile(root / "env/Lib/site-packages/rapidocr/models" / item["file"], destination)
        else:
            temporary = destination.with_suffix(".part")
            begun = time.perf_counter()
            with urllib.request.urlopen(item["url"], timeout=120) as response, temporary.open("wb") as out:
                shutil.copyfileobj(response, out)
            if digest(temporary) != item["sha256"]:
                raise ValueError("Model hash differs from the official pinned manifest")
            os.replace(temporary, destination)
            downloads.append({"file": item["file"], "bytes": destination.stat().st_size,
                              "wall_s": time.perf_counter() - begun, "url": item["url"]})
        if digest(destination) != item["sha256"]:
            raise ValueError("Model verification failed")
    shutil.copyfile(args.lock, root / "requirements.lock")
    shutil.copyfile(DATA / "profile.json", root / "profile.json")
    shutil.copyfile(DATA / "NOTICE.md", root / "NOTICE.md")
    (root / "bridge").mkdir()
    shutil.copyfile(Path(__file__).with_name("ocr_pilot_worker.py"), root / "bridge/ocr_pilot_worker.py")
    result = {"schema": "ocr-pilot-install-v1", "downloads": downloads,
              "setup_wall_s": time.perf_counter() - started,
              "profile_sha256": digest(root / "profile.json"),
              "lock_sha256": digest(root / "requirements.lock"), "app_environment_modified": False}
    (root / "installation.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

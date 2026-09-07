"""Explicit new-directory installation; nothing is installed when settings opens."""

import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Callable

from videocaptioner.core.utils.subprocess_helper import _NO_WINDOW

from ..alignment.audio import Check, stop_process
from .profiles import MODELS, PROTOCOL
from .runtime import LocalRuntimeError, file_hash, offline_environment, recipe_directory


def _run(args: list[str], env: dict[str, str], check: Check, payload: dict | None = None,
         timeout: int = 7200):
    process = subprocess.Popen(args, stdin=subprocess.PIPE if payload is not None else subprocess.DEVNULL,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               env=env, creationflags=_NO_WINDOW)
    try:
        if payload is not None:
            assert process.stdin is not None
            process.stdin.write(json.dumps(payload).encode() + b"\n")
            process.stdin.close()
        deadline = time.monotonic() + timeout
        while process.poll() is None:
            check()
            if time.monotonic() >= deadline:
                raise LocalRuntimeError("Local installation timed out; choose a new destination to retry.")
            try:
                process.wait(timeout=0.1)
            except subprocess.TimeoutExpired:
                pass
        check()
        if process.returncode:
            raise LocalRuntimeError("Local installation failed. Check uv/Python, disk/network and model access; choose a new destination to retry.")
    finally:
        stop_process(process)


def install(output: Path, model_ids: tuple[str, ...], *, token: str = "", check: Check = lambda: None,
            progress: Callable[[str], None] = lambda message: None):
    if os.name != "nt":
        raise LocalRuntimeError("The S5 installation recipe currently targets Windows Python 3.12.")
    if not model_ids or any(key not in MODELS for key in model_ids):
        raise ValueError("Select a pinned local model.")
    families = {MODELS[key].runtime for key in model_ids}
    if len(families) != 1:
        raise ValueError("Qwen and pyannote need separate runtime destinations.")
    if any(MODELS[key].gated for key in model_ids) and not token.strip():
        raise LocalRuntimeError("Community-1 requires accepted Hugging Face conditions and a read token entered securely.")
    check()
    output = output.resolve()
    # mkdir(exist_ok=False) closes the check/create race and prevents overwriting old artifacts.
    output.mkdir(parents=True, exist_ok=False)
    (output / ".installing").touch()
    family = next(iter(families))
    recipe = recipe_directory()
    env = offline_environment()
    for key in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE"):
        env.pop(key, None)
    env["HF_HOME"] = str(output / "download-cache")
    env["HF_HUB_DISABLE_SYMLINKS"] = "1"
    env["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
    env["UV_CACHE_DIR"] = str(output / "uv-cache")
    try:
        progress("Creating isolated Python 3.12 runtime")
        _run(["uv", "venv", "--no-config", "--python", "3.12", "--allow-existing", str(output)], env, check)
        python = output / "Scripts" / "python.exe"
        progress("Installing locked GPU dependencies")
        _run(["uv", "pip", "sync", "--no-config", "--python", str(python), "--require-hashes",
              "--extra-index-url", "https://download.pytorch.org/whl/cu128", "--index-strategy", "unsafe-best-match",
              str(recipe / f"{family}.lock")], env, check)
        models = {}
        for model_id in dict.fromkeys(model_ids):
            model = MODELS[model_id]
            progress(f"Downloading and verifying {model_id} at its pinned revision")
            destination = output / "models" / model_id
            _run([str(python), "-I", str(recipe / "download.py")], env, check,
                 {"repository": model.repository, "revision": model.revision,
                  "destination": str(destination), "token": token if model.gated else ""})
            models[model_id] = json.loads((destination / "inventory.json").read_text(encoding="utf-8"))
        shutil.copyfile(recipe / "bridge.py", output / "bridge.py")
        shutil.copyfile(recipe / f"{family}.lock", output / "requirements.lock")
        manifest = {"protocol": PROTOCOL, "recipe": json.loads((recipe / f"{family}.json").read_text(encoding="utf-8")),
                    "lock_sha256": file_hash(output / "requirements.lock"), "models": models}
        (output / "runtime-manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        progress("Installation complete; run an explicit health probe before inference")
    except BaseException:
        (output / ".failed").touch()
        raise
    finally:
        (output / ".installing").unlink(missing_ok=True)

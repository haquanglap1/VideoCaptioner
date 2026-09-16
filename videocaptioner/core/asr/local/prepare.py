"""Resumable preparation of a selected model, without modifying existing runtimes."""

import json
import os
import shutil
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Callable

from ..alignment.audio import Check
from .installer import _run
from .profiles import MODELS, PROTOCOL
from .runtime import (
    LocalLayout,
    LocalRuntimeError,
    _locate_exact,
    file_hash,
    locate,
    managed_root,
    offline_environment,
    recipe_directory,
)


def _partial_download_bytes(directory: Path) -> int:
    """Hub partial filenames can exceed MAX_PATH even in a usable runtime folder."""
    path = str(directory.resolve())
    if os.name == "nt" and not path.startswith("\\\\?\\"):
        path = "\\\\?\\UNC\\" + path[2:] if path.startswith("\\\\") else "\\\\?\\" + path
    total = 0
    for partial in Path(path).rglob("*.incomplete"):
        try:
            total += partial.stat().st_size
        except OSError:
            # The downloader may have finalized this file since enumeration.
            continue
    return total


@contextmanager
def installation_lock(path: Path, check: Check, progress: Callable[[str], None]):
    """OS ownership survives cancellation and is released by the OS after a crash."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+b")
    acquired = False
    deadline = time.monotonic() + 7200
    try:
        if not handle.tell():
            handle.write(b"0")
            handle.flush()
        announced = False
        while not acquired:
            check()
            handle.seek(0)
            try:
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
            except OSError:
                if not announced:
                    progress("Waiting for the selected model to finish installing in another job")
                    announced = True
                if time.monotonic() >= deadline:
                    raise LocalRuntimeError("Timed out waiting for model preparation.") from None
                time.sleep(0.1)
        yield
    finally:
        if acquired:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


def ensure_model(model_id: str, root: str | Path = "", *, token: str = "", check: Check = lambda: None,
                 progress: Callable[[str], None] = lambda message: None) -> LocalLayout:
    """Reuse a verified model, or prepare only the model needed by this stage."""
    check()
    try:
        return locate(model_id, root, verify=True, check=check)
    except LocalRuntimeError:
        check()  # A cancellation raised during verification must stay cancelled.
    model = MODELS[model_id]
    if model.gated and not token.strip():
        raise LocalRuntimeError("Community-1 requires accepted Hugging Face conditions and a read token entered securely in model management.")
    if os.name != "nt" or shutil.which("uv") is None:
        raise LocalRuntimeError("Automatic local model preparation requires Windows and uv with Python 3.12 support.")
    destination = managed_root(model_id, root).resolve()
    with installation_lock(destination.with_name(destination.name + ".lock"), check, progress):
        try:
            return locate(model_id, root, verify=True, check=check)
        except LocalRuntimeError:
            check()
        recipe = recipe_directory()
        owner = {"protocol": PROTOCOL, "model": model_id, "revision": model.revision,
                 "recipe": file_hash(recipe / f"{model.runtime}.json"),
                 "lock": file_hash(recipe / f"{model.runtime}.lock"), "bridge": file_hash(recipe / "bridge.py")}
        marker = destination / ".preparation.json"
        if destination.exists():
            try:
                if json.loads(marker.read_text(encoding="utf-8")) != owner:
                    raise ValueError
            except (OSError, ValueError):
                raise LocalRuntimeError("Model preparation destination is not owned by this installer; existing files were kept.") from None
        else:
            destination.mkdir(exist_ok=False)
            marker.write_text(json.dumps(owner), encoding="utf-8")
        (destination / ".installing").touch()
        # This directory is never relocated: venv launchers contain absolute paths.
        env = offline_environment()
        for key in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE"):
            env.pop(key, None)
        env.update(HF_HOME=str(destination / "download-cache"), HF_HUB_DISABLE_SYMLINKS="1",
                   HF_HUB_DISABLE_PROGRESS_BARS="1", HF_HUB_DISABLE_XET="1",
                   UV_CACHE_DIR=str(destination.parent / "uv-cache"))
        if shutil.disk_usage(destination).free < 1024 ** 3:
            raise LocalRuntimeError("Not enough free disk space to prepare the isolated GPU runtime.")
        progress(f"Preparing {model_id}; interrupted downloads will resume on the next start")
        python = destination / "Scripts/python.exe"
        if not python.is_file():
            _run(["uv", "venv", "--no-config", "--python", "3.12", "--allow-existing", str(destination)], env, check)
        progress("Installing locked GPU dependencies")
        _run(["uv", "pip", "sync", "--no-config", "--python", str(python), "--require-hashes",
              "--extra-index-url", "https://download.pytorch.org/whl/cu128", "--index-strategy", "unsafe-best-match",
              str(recipe / f"{model.runtime}.lock")], env, check)
        _run([str(python), "-I", "-c", "import torch; assert torch.cuda.is_available(), 'CUDA unavailable'"], env, check)
        model_path = destination / "models" / model_id
        last_progress = 0.0

        def download_check():
            nonlocal last_progress
            check()
            if time.monotonic() - last_progress < 0.5:
                return
            last_progress = time.monotonic()
            try:
                report = json.loads((model_path / "progress.json").read_text(encoding="utf-8"))
                done, total = report["verified_bytes"], report["total_bytes"]
                if type(done) is not int or type(total) is not int or not 0 <= done <= total:
                    return
                partial = _partial_download_bytes(model_path / ".cache/huggingface/download")
                progress(f"Preparing {model_id}: {min(done + partial, total) / 1048576:.0f}/{total / 1048576:.0f} MiB; verifying downloads")
            except (OSError, ValueError, KeyError):
                pass

        progress(f"Downloading {model_id} at its pinned revision")
        _run([str(python), "-I", str(recipe / "download.py")], env, download_check,
             {"repository": model.repository, "revision": model.revision,
              "destination": str(model_path), "token": token if model.gated else ""})
        check()
        inventory = json.loads((model_path / "inventory.json").read_text(encoding="utf-8"))
        shutil.copyfile(recipe / "bridge.py", destination / "bridge.py")
        shutil.copyfile(recipe / f"{model.runtime}.lock", destination / "requirements.lock")
        manifest = {"protocol": PROTOCOL, "recipe": json.loads((recipe / f"{model.runtime}.json").read_text(encoding="utf-8")),
                    "lock_sha256": owner["lock"], "models": {model_id: inventory}}
        temp = destination / "runtime-manifest.pending.json"
        temp.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        temp.replace(destination / "runtime-manifest.json")
        progress(f"Verifying {model_id}")
        layout = _locate_exact(model_id, destination, verify=True, check=check, preparing=True)
        check()
        (destination / ".installing").unlink()
        progress(f"{model_id} is prepared; starting the requested task")
        return layout

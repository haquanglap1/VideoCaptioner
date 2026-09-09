"""Resumable installation into an owned environment, separate from the Qt app."""

import hashlib
import json
import os
import shutil
import subprocess
import urllib.request
import zipfile
from pathlib import Path

from videocaptioner.core.asr.alignment.audio import stop_process
from videocaptioner.core.utils.subprocess_helper import _NO_WINDOW, child_environment

from .config import CODE_REVISION, MODEL_REVISION, recipe, resources, runtime_root


def digest(path: Path, check=lambda: None, *, git_blob=False) -> str:
    value = hashlib.sha1() if git_blob else hashlib.sha256()
    if git_blob:
        value.update(f"blob {path.stat().st_size}\0".encode())
    with path.open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            check()
            value.update(block)
    return value.hexdigest()


def download(url, path: Path, expected: str, *, git_blob=False, check=lambda: None, progress=lambda message: None):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file() and digest(path, check, git_blob=git_blob) == expected:
        return
    part = path.with_name(path.name + ".part")
    offset = part.stat().st_size if part.exists() else 0
    request = urllib.request.Request(url, headers={"Range": f"bytes={offset}-"} if offset else {})
    check()
    with urllib.request.urlopen(request, timeout=30) as response:
        append = offset > 0 and response.status == 206
        if append and not response.headers.get("Content-Range", "").startswith(f"bytes {offset}-"):
            raise RuntimeError("Download resume range mismatch")
        received = offset if append else 0
        with part.open("ab" if append else "wb") as file:
            while block := response.read(1024 * 1024):
                check()
                file.write(block)
                received += len(block)
                progress(f"{path.name}: {received // (1024 * 1024)} MiB")
    check()
    if digest(part, check, git_blob=git_blob) != expected:
        # Keep the bad transfer for diagnosis; a later attempt starts a new part.
        part.replace(path.with_name(path.name + ".rejected"))
        raise RuntimeError("OmniVoice download checksum mismatch; retry preparation.")
    part.replace(path)


def verify(root: Path, check=lambda: None) -> dict:
    try:
        saved = json.loads((root / "ready.json").read_text(encoding="utf-8"))
        if saved["code_revision"] != CODE_REVISION or saved["model_revision"] != MODEL_REVISION:
            raise ValueError("Unexpected runtime revision")
        python = root / "env" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        if not python.is_file():
            raise ValueError("Missing runtime interpreter")
        for item in recipe()["files"]:
            path = root / "model" / item["path"]
            expected = item["sha256"] or item["blob_id"]
            if not path.is_file() or digest(path, check, git_blob=not item["sha256"]) != expected:
                raise ValueError("Incomplete or altered model")
        return saved
    except (OSError, ValueError, KeyError) as exc:
        check()
        raise RuntimeError("OmniVoice is not ready. Use Prepare / resume OmniVoice first.") from exc


def prepare_runtime(explicit="", *, check=lambda: None, progress=lambda message: None) -> Path:
    if os.name != "nt":
        raise RuntimeError("The managed OmniVoice installer currently targets Windows/CUDA.")
    root = runtime_root(explicit)
    marker = root / "owner.json"
    if root.exists() and not marker.is_file() and any(root.iterdir()):
        raise RuntimeError("OmniVoice destination is not owned by this installer; choose an empty new folder.")
    root.mkdir(parents=True, exist_ok=True)
    owner = {"schema": "omnivoice-runtime-v1", "code_revision": CODE_REVISION, "model_revision": MODEL_REVISION}
    if not marker.exists():
        with marker.open("x", encoding="utf-8") as file:
            json.dump(owner, file)
    if json.loads(marker.read_text(encoding="utf-8")) != owner:
        raise RuntimeError("OmniVoice destination belongs to another runtime revision.")
    import msvcrt
    with (root / "install.lock").open("a+b") as lock:
        if not lock.tell():
            lock.write(b"0")
            lock.flush()
        lock.seek(0)
        try:
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            raise RuntimeError("OmniVoice preparation is already running.") from None
        try:
            if (root / "ready.json").exists():
                progress("Verifying installed OmniVoice")
                try:
                    verify(root, check)
                    return root
                except RuntimeError:
                    check()
            spec = recipe()
            archive = root / "source.zip"
            download(f"https://codeload.github.com/k2-fsa/OmniVoice/zip/{CODE_REVISION}", archive,
                     spec["source_sha256"], check=check, progress=progress)
            source = root / f"OmniVoice-{CODE_REVISION}"
            if not source.is_dir():
                with zipfile.ZipFile(archive) as bundle:
                    for entry in bundle.infolist():
                        target = (root / entry.filename).resolve()
                        if not target.is_relative_to(source.resolve()):
                            raise RuntimeError("Unsafe OmniVoice source archive path")
                    bundle.extractall(root)
            uv = shutil.which("uv")
            if not uv:
                raise RuntimeError("Install uv before preparing OmniVoice.")
            requirements = resources() / "requirements.lock"
            if digest(requirements, check) != spec["requirements_sha256"]:
                raise RuntimeError("OmniVoice dependency lock is inconsistent with its recipe")
            python = root / "env/Scripts/python.exe"
            commands = []
            if not python.is_file():
                commands.append([uv, "venv", "--no-config", "--python", "3.12", str(root / "env")])
            if not (root / "dependencies-ready.json").is_file():
                commands.extend([
                    [uv, "pip", "install", "--no-config", "--python", str(python), "--require-hashes", "-r", str(requirements),
                     "--extra-index-url", "https://download.pytorch.org/whl/cu128", "--index-strategy", "unsafe-best-match"],
                    [uv, "pip", "install", "--no-config", "--python", str(python), "--no-deps", str(source)],
                ])
            for args in commands:
                progress("Installing isolated OmniVoice runtime dependencies")
                with (root / "install.log").open("ab") as log:
                    process = subprocess.Popen(args, stdout=log, stderr=subprocess.STDOUT,
                                               env=child_environment(), creationflags=_NO_WINDOW)
                    try:
                        while process.poll() is None:
                            check()
                            try:
                                process.wait(timeout=0.1)
                            except subprocess.TimeoutExpired:
                                pass
                        if process.returncode:
                            raise RuntimeError("OmniVoice dependency installation failed; see its install.log and resume.")
                    finally:
                        stop_process(process)
            (root / "dependencies-ready.json").write_text(json.dumps(owner), encoding="utf-8")
            for item in spec["files"]:
                download(f"https://huggingface.co/k2-fsa/OmniVoice/resolve/{MODEL_REVISION}/{item['path']}",
                         root / "model" / item["path"], item["sha256"] or item["blob_id"],
                         git_blob=not item["sha256"], check=check, progress=progress)
            check()
            temp = root / "ready.tmp"
            temp.write_text(json.dumps(owner), encoding="utf-8")
            temp.replace(root / "ready.json")
            progress("OmniVoice runtime and model are prepared")
            return root
        finally:
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)

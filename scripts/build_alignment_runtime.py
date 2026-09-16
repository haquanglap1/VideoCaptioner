"""Explicitly build a separate Windows alignment environment; never overwrite a runtime."""

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from videocaptioner.core.utils.subprocess_helper import _NO_WINDOW, child_environment  # noqa: E402


def run(args):
    subprocess.run(args, check=True, env=child_environment(), creationflags=_NO_WINDOW)


def build(output: Path):
    source = ROOT / "runtime" / "alignment"
    lock = source / "requirements-win-py312.lock"
    run(["uv", "venv", "--no-config", "--python", "3.12", str(output)])
    (output / ".installing").touch()
    try:
        install(output, source, lock)
    except BaseException:
        (output / ".failed").touch()
        raise
    finally:
        (output / ".installing").unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    output = Path(args.output).resolve()
    if output.exists():
        parser.error("Output already exists; choose a new empty runtime destination.")
    build(output)


def install(output: Path, source: Path, lock: Path):
    python = output / "Scripts" / "python.exe"
    run(["uv", "pip", "sync", "--no-config", "--python", str(python), "--require-hashes",
         "--extra-index-url", "https://download.pytorch.org/whl/cu128",
         "--index-strategy", "unsafe-best-match", str(lock)])
    manifest = json.loads((source / "runtime-manifest.json").read_text(encoding="utf-8"))
    manifest["lock_sha256"] = hashlib.sha256(lock.read_bytes()).hexdigest()
    shutil.copyfile(source / "bridge.py", output / "bridge.py")
    shutil.copyfile(lock, output / lock.name)
    # Download is explicit here; all job/probe runtime launches force offline mode.
    download = (
        "from huggingface_hub import snapshot_download; "
        "import sys; snapshot_download(repo_id=sys.argv[1], revision=sys.argv[2], "
        "local_dir=sys.argv[3])"
    )
    run([str(python), "-I", "-c", download, manifest["model_repository"],
         manifest["model_revision"], str(output / "model")])
    (output / "runtime-manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print("Alignment runtime installed. Run the local health probe before transcription.")


if __name__ == "__main__":
    main()

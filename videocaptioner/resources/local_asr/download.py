"""Explicit model download helper. The optional access token arrives only on stdin."""

import hashlib
import json
import shutil
import sys
from pathlib import Path
from typing import cast


def hashes(path):
    sha256 = hashlib.sha256()
    sha1 = hashlib.sha1(f"blob {path.stat().st_size}\0".encode())
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            sha256.update(chunk)
            sha1.update(chunk)
    return sha256.hexdigest(), sha1.hexdigest()


def main():
    from huggingface_hub import HfApi, hf_hub_download

    request = json.loads(sys.stdin.readline())
    root = Path(request["destination"])
    token = request.pop("token", "") or False
    info = HfApi().model_info(request["repository"], revision=request["revision"], token=token, files_metadata=True)
    if info.sha != request["revision"] or not info.siblings:
        raise ValueError("Model revision mismatch")
    root.mkdir(parents=True, exist_ok=True)
    selected = [item for item in info.siblings if not item.rfilename.endswith((".gif", ".gitattributes"))]
    if any(type(item.size) is not int or item.size < 0 for item in selected):
        raise ValueError("Missing file size")
    total = sum(cast(int, item.size) for item in selected)
    existing = sum(p.stat().st_size for p in root.rglob("*") if p.is_file())
    if shutil.disk_usage(root).free < max(0, total - existing) + 64 * 1024 * 1024:
        raise ValueError("Insufficient disk space")
    files = {}
    done = 0
    for item in selected:
        progress = root / "progress.pending.json"
        progress.write_text(json.dumps({"verified_bytes": done, "total_bytes": total}), encoding="utf-8")
        progress.replace(root / "progress.json")
        relative = item.rfilename
        target = root / relative
        if not target.resolve().is_relative_to(root.resolve()):
            raise ValueError("Unsafe model path")
        expected = item.lfs.sha256 if item.lfs is not None else item.blob_id
        if not expected:
            raise ValueError("Missing model file hash")
        existing = hashes(target) if target.is_file() else None
        if existing is not None and target.stat().st_size == item.size and existing[0 if item.lfs is not None else 1] == expected:
            path, digest = target, existing
        else:
            # Only corrupt final files force a fresh transfer. Hub .incomplete files
            # retain their normal HTTP resume behavior after interruption.
            path = Path(hf_hub_download(request["repository"], relative, revision=request["revision"],
                        token=token, local_dir=root, force_download=target.exists()))
            digest = hashes(path)
        actual = digest[0 if item.lfs is not None else 1]
        if actual != expected or path.stat().st_size != item.size:
            raise ValueError("Model file hash mismatch")
        files[relative] = {"size": path.stat().st_size, "sha256": digest[0]}
        done += cast(int, item.size)
    (root / "inventory.json").write_text(json.dumps({"repository": info.id, "revision": info.sha, "files": files}), encoding="utf-8")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # Provider exceptions may include sensitive URLs or headers. Do not echo them.
        print("Download failed: check network, disk space and model access; no credentials were stored.", file=sys.stderr)
        sys.exit(1)

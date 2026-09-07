"""Explicit model download helper. The optional access token arrives only on stdin."""

import hashlib
import json
import sys
from pathlib import Path


def main():
    from huggingface_hub import HfApi, hf_hub_download

    request = json.loads(sys.stdin.readline())
    root = Path(request["destination"])
    token = request.pop("token", "") or False
    info = HfApi().model_info(request["repository"], revision=request["revision"], token=token, files_metadata=True)
    if info.sha != request["revision"] or not info.siblings:
        raise ValueError("Model revision mismatch")
    files = {}
    for item in info.siblings:
        relative = item.rfilename
        if relative.endswith((".gif", ".gitattributes")):
            continue
        target = root / relative
        if not target.resolve().is_relative_to(root.resolve()):
            raise ValueError("Unsafe model path")
        path = Path(hf_hub_download(request["repository"], relative, revision=request["revision"],
                    token=token, local_dir=root))
        sha256 = hashlib.sha256()
        sha1 = hashlib.sha1(f"blob {path.stat().st_size}\0".encode())
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                sha256.update(chunk)
                sha1.update(chunk)
        expected = item.lfs.sha256 if item.lfs is not None else item.blob_id
        actual = sha256.hexdigest() if item.lfs is not None else sha1.hexdigest()
        if not expected or actual != expected:
            raise ValueError("Model file hash mismatch")
        files[relative] = {"size": path.stat().st_size, "sha256": sha256.hexdigest()}
    (root / "inventory.json").write_text(json.dumps({"repository": info.id, "revision": info.sha, "files": files}), encoding="utf-8")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # Provider exceptions may include sensitive URLs or headers. Do not echo them.
        print("Download failed: check network, disk space and model access; no credentials were stored.", file=sys.stderr)
        sys.exit(1)

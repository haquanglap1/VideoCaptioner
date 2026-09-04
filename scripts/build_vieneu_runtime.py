#!/usr/bin/env python3
"""Build a clean relocatable VieNeu sidecar from pinned source and requirements."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MANIFEST = PROJECT_ROOT / "runtime" / "vieneu" / "runtime-manifest.json"
DEFAULT_REQUIREMENTS = PROJECT_ROOT / "runtime" / "vieneu" / "requirements-v3-gpu.lock"
BRIDGE_SOURCE = PROJECT_ROOT / "runtime" / "vieneu" / "bridge" / "vieneu_bridge.py"
NOTICE_SOURCE = PROJECT_ROOT / "runtime" / "vieneu" / "NOTICE.md"


def run(command: list[str], *, cwd: Path | None = None) -> str:
    result = subprocess.run(
        command,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr[-5000:] or result.stdout[-5000:])
    return result.stdout.strip()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def export_source(git: str, source: Path, revision: str, destination: Path) -> Path:
    git_prefix = [git, "-c", f"safe.directory={source.as_posix()}", "-C", str(source)]
    head = run([*git_prefix, "rev-parse", "HEAD"])
    if head != revision:
        raise RuntimeError(f"VieNeu source HEAD {head} != pinned {revision}")
    dirty = run([*git_prefix, "status", "--porcelain", "--untracked-files=no"])
    if dirty:
        raise RuntimeError("VieNeu tracked source is dirty; refusing non-reproducible runtime build")
    archive = subprocess.run(
        [*git_prefix, "archive", "--format=tar", revision],
        capture_output=True,
        check=False,
    )
    if archive.returncode != 0:
        raise RuntimeError(archive.stderr.decode("utf-8", errors="replace"))
    extracted = destination / "source"
    extracted.mkdir(parents=True)
    with tarfile.open(fileobj=io.BytesIO(archive.stdout), mode="r:") as tar:
        tar.extractall(extracted, filter="data")
    return extracted


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, help="Read-only VieNeu Git checkout")
    parser.add_argument("--output", required=True)
    parser.add_argument("--requirements", default=str(DEFAULT_REQUIREMENTS))
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    output = Path(args.output).resolve()
    requirements = Path(args.requirements).resolve()
    manifest_path = Path(args.manifest).resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    source = Path(args.source).resolve()
    uv = shutil.which("uv")
    git = shutil.which("git")
    if not uv or not git:
        raise RuntimeError("uv and git are required to build the VieNeu runtime")
    if output.exists():
        if not args.overwrite:
            raise RuntimeError(f"Runtime output already exists: {output}")
        allowed_roots = ((PROJECT_ROOT / "build").resolve(), (PROJECT_ROOT / "dist").resolve())
        if not any(output.is_relative_to(root) for root in allowed_roots):
            raise RuntimeError("Runtime overwrite is restricted to workspace build/ or dist/")
        shutil.rmtree(output)
    output.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="vc_vieneu_runtime_build_") as temp_dir:
        temp = Path(temp_dir)
        extracted = export_source(
            git,
            source,
            str(manifest["runtime_source_revision"]),
            temp,
        )
        wheel_dir = temp / "wheel"
        wheel_dir.mkdir()
        run([uv, "build", "--wheel", "--out-dir", str(wheel_dir), str(extracted)])
        wheels = list(wheel_dir.glob("vieneu-*.whl"))
        if len(wheels) != 1:
            raise RuntimeError("VieNeu wheel build did not produce exactly one wheel")
        wheel_hash = sha256(wheels[0])

        python_executable = Path(
            run(
                [
                    uv,
                    "python",
                    "find",
                    "--no-project",
                    "--managed-python",
                    "--system",
                    "3.12",
                ]
            )
            .splitlines()[-1]
        )
        python_root = python_executable.resolve().parent
        shutil.copytree(
            python_root,
            output,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
        runtime_python = output / python_executable.name
        if not runtime_python.is_file():
            raise RuntimeError("Copied Python runtime is incomplete")
        run(
            [
                uv,
                "pip",
                "install",
                # The workspace pyproject carries uv override-dependencies (PyQt5-Qt5);
                # they have no hashes and must not leak into the sidecar install.
                "--no-config",
                "--python",
                str(runtime_python),
                "--break-system-packages",
                "--require-hashes",
                "--index-strategy",
                "unsafe-best-match",
                "--default-index",
                "https://pypi.org/simple",
                "--index",
                "https://download.pytorch.org/whl/cu128",
                "-r",
                str(requirements),
            ]
        )
        run(
            [
                uv,
                "pip",
                "install",
                # The workspace pyproject carries uv override-dependencies (PyQt5-Qt5);
                # they have no hashes and must not leak into the sidecar install.
                "--no-config",
                "--python",
                str(runtime_python),
                "--break-system-packages",
                "--no-deps",
                str(wheels[0]),
            ]
        )

        # PyTorch wheels ship a >2 GiB static oneDNN development library.
        # Runtime inference loads DLLs, not this link-time archive; keeping it
        # breaks Windows Installer's per-file limit without adding capability.
        pruned_files = []
        dnnl_static = output / "Lib" / "site-packages" / "torch" / "lib" / "dnnl.lib"
        if dnnl_static.is_file():
            pruned_files.append(
                {"file": "Lib/site-packages/torch/lib/dnnl.lib", "bytes": dnnl_static.stat().st_size}
            )
            dnnl_static.unlink()

    bridge_dir = output / "bridge"
    bridge_dir.mkdir(exist_ok=True)
    shutil.copy2(BRIDGE_SOURCE, bridge_dir / BRIDGE_SOURCE.name)
    shutil.copy2(NOTICE_SOURCE, output / NOTICE_SOURCE.name)
    installed_manifest = dict(manifest)
    installed_manifest.update(
        {
            "requirements_sha256": sha256(requirements),
            "vieneu_wheel_sha256": wheel_hash,
            "python_executable": runtime_python.name,
            "runtime_layout": "portable-python-v1",
            "pruned_development_files": pruned_files,
        }
    )
    (output / "runtime-manifest.json").write_text(
        json.dumps(installed_manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    smoke = run(
        [
            str(runtime_python),
            "-c",
            "import fastapi,torch,transformers,uvicorn,vieneu; "
            "print(vieneu.__version__ if hasattr(vieneu,'__version__') else 'ok', "
            "torch.__version__, torch.cuda.is_available())",
        ]
    )
    print(
        json.dumps(
            {
                "runtime": str(output),
                "python": str(runtime_python),
                "requirements_sha256": installed_manifest["requirements_sha256"],
                "wheel_sha256": installed_manifest["vieneu_wheel_sha256"],
                "smoke": smoke,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

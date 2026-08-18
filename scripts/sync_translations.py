#!/usr/bin/env python3
"""Sync translations from resource/ into the package's fallback copy.

Two copies of the translation files have to exist:

- ``resource/translations/`` — used in dev mode and bundled by PyInstaller.
- ``videocaptioner/resources/translations/`` — the fallback used when installed
  via pip, where ``resource/`` is not shipped (see ``videocaptioner/config.py``).

They were previously kept in sync by hand, which silently drifts. Run this after
editing anything under ``resource/translations/``:

    uv run python scripts/sync_translations.py          # copy
    uv run python scripts/sync_translations.py --check  # verify only (CI-friendly)

``--check`` exits 1 when the two copies differ, without writing anything.
"""

from __future__ import annotations

import argparse
import filecmp
import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SOURCE_DIR = PROJECT_ROOT / "resource" / "translations"
TARGET_DIR = PROJECT_ROOT / "videocaptioner" / "resources" / "translations"

# Only runtime-loadable files. .ts files are Qt Linguist sources — they are
# compiled to .qm and are not read at runtime, so they stay out of the package.
SYNCED_SUFFIXES = {".json", ".qm"}


def _files_to_sync() -> list[Path]:
    return sorted(
        p for p in SOURCE_DIR.iterdir()
        if p.is_file() and p.suffix in SYNCED_SUFFIXES
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Report drift and exit 1 instead of copying",
    )
    args = parser.parse_args()

    if not SOURCE_DIR.is_dir():
        print(f"error: source dir not found: {SOURCE_DIR}", file=sys.stderr)
        return 1

    TARGET_DIR.mkdir(parents=True, exist_ok=True)

    drifted: list[str] = []
    for src in _files_to_sync():
        dst = TARGET_DIR / src.name
        in_sync = dst.exists() and filecmp.cmp(src, dst, shallow=False)
        if in_sync:
            continue
        drifted.append(src.name)
        if not args.check:
            shutil.copy2(src, dst)

    # Files that only exist in the package copy are stale leftovers.
    source_names = {p.name for p in _files_to_sync()}
    for dst in sorted(TARGET_DIR.iterdir()):
        if dst.is_file() and dst.suffix in SYNCED_SUFFIXES and dst.name not in source_names:
            drifted.append(f"{dst.name} (stale, only in package copy)")
            if not args.check:
                dst.unlink()

    if not drifted:
        print("translations in sync")
        return 0

    if args.check:
        print("translations out of sync:", file=sys.stderr)
        for name in drifted:
            print(f"  - {name}", file=sys.stderr)
        print(
            "\nRun: uv run python scripts/sync_translations.py",
            file=sys.stderr,
        )
        return 1

    print(f"synced {len(drifted)} file(s) into {TARGET_DIR.relative_to(PROJECT_ROOT)}:")
    for name in drifted:
        print(f"  - {name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

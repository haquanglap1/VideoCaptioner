"""download command — download online video via yt-dlp."""

import json
import shutil
from argparse import Namespace
from pathlib import Path

from videocaptioner.cli import exit_codes as EXIT
from videocaptioner.cli import output
from videocaptioner.core.utils.subprocess_helper import child_environment


def run(args: Namespace, config: dict) -> int:
    url = args.url
    out_dir = getattr(args, "output", None) or "."
    quiet = getattr(args, "quiet", False)

    if getattr(args, "playlist", False) or getattr(args, "list_playlist", False):
        return _run_playlist(args)
    if getattr(args, "playlist_items", "") or getattr(args, "cookies", None) or getattr(args, "playlist_scope", "auto") != "auto":
        output.error("Playlist options require --playlist or --list-playlist")
        return EXIT.USAGE_ERROR

    if not shutil.which("yt-dlp"):
        output.error("yt-dlp not found on PATH")
        output.hint("Install: pip install yt-dlp")
        return EXIT.DEPENDENCY_MISSING

    Path(out_dir).mkdir(parents=True, exist_ok=True)

    # Ensure Deno (JS runtime for YouTube signature solving) is available; auto-install
    # on first use. Non-fatal: without it the download degrades to low-res formats.
    # Auto-install is Windows-only, so check that before announcing anything.
    try:
        from videocaptioner.core.utils.installer import (
            can_auto_install,
            deno_path,
            ensure_deno,
        )

        if deno_path() is None:
            if can_auto_install():
                output.hint("Installing Deno (needed for YouTube HD downloads)...")
                ensure_deno()
            elif not quiet:
                output.warn(
                    "Deno not found — YouTube HD formats will be unavailable. "
                    "Install it with: curl -fsSL https://deno.land/install.sh | sh"
                )
    except Exception as exc:
        if not quiet:
            output.warn(f"Deno setup skipped: {exc}")

    progress = None if quiet else output.ProgressLine(f"Downloading {url}").start()

    try:
        import subprocess
        has_ffmpeg = bool(shutil.which("ffmpeg"))
        format_selector = (
            "bestvideo+bestaudio/best" if has_ffmpeg else "best[ext=mp4]/best"
        )
        cmd = [
            "yt-dlp",
            "-f", format_selector,
            "-o", f"{out_dir}/%(title)s.%(ext)s",
            "--no-playlist",
            "--retries", "5",
            "--fragment-retries", "5",
            # Auto-fetch the EJS solver so Deno can solve YouTube signature/n challenges;
            # without it adaptive formats are skipped. No player_client pin (it hides formats).
            "--remote-components", "ejs:github",
            url,
        ]
        if not has_ffmpeg:
            output.hint("ffmpeg not found — falling back to single-file format (≤720p).")
        if quiet:
            cmd.append("--quiet")

        result = subprocess.run(cmd, env=child_environment(), capture_output=quiet, text=True)

        if result.returncode != 0:
            if progress:
                progress.fail("Download failed")
            if result.stderr:
                output.error(result.stderr.strip())
            return EXIT.RUNTIME_ERROR

        if progress:
            progress.finish(f"Downloaded to {out_dir}/")
        return EXIT.SUCCESS

    except Exception as e:
        if progress:
            progress.fail(str(e))
        else:
            output.error(str(e))
        return EXIT.RUNTIME_ERROR


def _run_playlist(args: Namespace) -> int:
    from dataclasses import asdict

    from videocaptioner.config import APPDATA_PATH
    from videocaptioner.core.playlist import (
        discover_playlist,
        download_playlist,
        friendly_error,
        selection,
    )

    cookies = Path(args.cookies) if args.cookies else APPDATA_PATH / "cookies.txt"
    if args.cookies and not cookies.is_file():
        output.error("Cookies file does not exist")
        return EXIT.USAGE_ERROR
    try:
        info = discover_playlist(args.url, cookies=cookies, scope=args.playlist_scope)
        entries = selection(info, args.playlist_items)
        if args.list_playlist:
            print(json.dumps({"title": info.title, "kind": info.kind, "entries": [asdict(e) for e in entries]}, ensure_ascii=False))
            return EXIT.SUCCESS
        result = download_playlist(info, entries, Path(args.output or "."), cookies=cookies)
        print(json.dumps(asdict(result), ensure_ascii=False))
        return EXIT.SUCCESS if all(item.status in ("downloaded", "existing") for item in result.items) else EXIT.RUNTIME_ERROR
    except KeyboardInterrupt:
        output.error("Playlist download cancelled; completed files and partial downloads retained")
        return EXIT.RUNTIME_ERROR
    except Exception as exc:
        output.error(friendly_error(exc))
        return EXIT.RUNTIME_ERROR

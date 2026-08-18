"""download command — download online video via yt-dlp."""

import shutil
from argparse import Namespace
from pathlib import Path

from videocaptioner.cli import exit_codes as EXIT
from videocaptioner.cli import output


def run(args: Namespace, config: dict) -> int:
    url = args.url
    out_dir = getattr(args, "output", None) or "."
    quiet = getattr(args, "quiet", False)

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

        result = subprocess.run(cmd, capture_output=quiet, text=True)

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

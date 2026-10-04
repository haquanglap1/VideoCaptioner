"""Exercise yt-dlp's actual codec/container selection without network requests."""

import hashlib
import json
from pathlib import Path

import pytest
from yt_dlp import YoutubeDL
from yt_dlp.utils import ExtractorError

from videocaptioner.core.playlist import PlaylistEntry, _download_entry
from videocaptioner.core.utils.download_format import mp4_format_selector


@pytest.mark.parametrize("codec", ["hev1.1.6.L120.90", "hvc1.1.6.L120.90", "avc1.640028", "av01.0.08M.08"])
def test_hevc_and_other_mp4_streams_merge_to_mp4(codec):
    formats = [
        {"format_id": "video", "url": "https://example.invalid/video", "ext": "mp4", "vcodec": codec, "acodec": "none"},
        {"format_id": "audio", "url": "https://example.invalid/audio", "ext": "m4a", "vcodec": "none", "acodec": "mp4a.40.2"},
    ]
    with YoutubeDL({"format": mp4_format_selector(True), "merge_output_format": "mp4", "quiet": True}) as ydl:
        result = ydl.process_ie_result({"id": "fixture", "title": "Fixture", "extractor": "generic", "formats": formats}, download=False)
    assert result["ext"] == "mp4"
    assert [f["format_id"] for f in result["requested_formats"]] == ["video", "audio"]


@pytest.mark.parametrize("has_ffmpeg", [False, True])
def test_webm_only_source_is_rejected_instead_of_silent_format_fallback(has_ffmpeg):
    with YoutubeDL({"format": mp4_format_selector(has_ffmpeg), "quiet": True}) as ydl:
        with pytest.raises(ExtractorError, match="Requested format is not available"):
            ydl.process_ie_result({"id": "fixture", "title": "Fixture", "extractor": "generic", "formats": [
                {"format_id": "webm", "url": "https://example.invalid/video", "ext": "webm",
                 "vcodec": "vp9", "acodec": "opus"}]}, download=False)


def test_existing_mkv_is_preserved_and_not_handed_to_batch(tmp_path):
    source = tmp_path / "old.mkv"
    source.write_bytes(b"existing user video")
    receipt = tmp_path / "completed.json"
    entry = PlaylistEntry(1, "fixture", "Fixture", "https://example.invalid/video")
    receipt.write_text(json.dumps({"url": entry.url, "filename": source.name, "size": source.stat().st_size,
                                   "sha256": hashlib.sha256(source.read_bytes()).hexdigest()}))
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    with pytest.raises(ValueError, match="MP4"):
        _download_entry(entry, tmp_path, None, lambda: None, lambda _: None)
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir()} == before


@pytest.mark.parametrize("has_ffmpeg", [False, True])
def test_cli_single_download_obeys_mp4_policy(monkeypatch, tmp_path, has_ffmpeg):
    from types import SimpleNamespace

    from videocaptioner.cli.commands import download
    from videocaptioner.cli.main import build_parser

    monkeypatch.setattr(download.shutil, "which", lambda name: None if name == "ffmpeg" and not has_ffmpeg else name)
    monkeypatch.setattr("videocaptioner.core.utils.installer.deno_path", lambda: Path("existing-deno"))
    commands = []
    monkeypatch.setattr("subprocess.run", lambda cmd, **kw: commands.append(cmd) or SimpleNamespace(returncode=0))
    args = build_parser().parse_args(["download", "https://example.invalid/video", "-o", str(tmp_path)])
    assert download.run(args, {}) == 0
    command = commands[0]
    assert command[command.index("-f") + 1] == mp4_format_selector(has_ffmpeg)
    assert command[command.index("--merge-output-format") + 1] == "mp4"

"""Playlist CLI is opt-in, reports partial failure and lists without downloading."""

import json

from videocaptioner.cli.commands import download
from videocaptioner.cli.main import build_parser
from videocaptioner.core import playlist as core


def test_list_and_selected_download_use_same_core(monkeypatch, tmp_path, capsys):
    info = core.PlaylistInfo("https://example.test/list", "Fixture", (
        core.PlaylistEntry(1, "1", "First", "https://example.test/1"),
        core.PlaylistEntry(2, "2", "Second", "https://example.test/2")))
    calls = []
    monkeypatch.setattr(core, "discover_playlist", lambda *a, **k: info)
    def perform(source, entries, output, **kwargs):
        calls.append([entry.index for entry in entries])
        return core.PlaylistResult((core.PlaylistItemResult(2, "failed", error="fixture failure"),))
    monkeypatch.setattr(core, "download_playlist", perform)
    parser = build_parser()
    args = parser.parse_args(["download", info.source_url, "--list-playlist", "--playlist-items", "2"])
    assert download.run(args, {}) == 0
    data = json.loads(capsys.readouterr().out)
    assert [entry["index"] for entry in data["entries"]] == [2] and not calls
    args = parser.parse_args(["download", info.source_url, "--playlist", "--playlist-items", "2", "-o", str(tmp_path)])
    assert download.run(args, {}) == 5 and calls == [[2]]


def test_playlist_options_do_not_silently_change_single_video_mode(capsys):
    parser = build_parser()
    args = parser.parse_args(["download", "https://example.test/video", "--playlist-items", "1"])
    assert download.run(args, {}) == 2
    assert "require --playlist" in capsys.readouterr().err

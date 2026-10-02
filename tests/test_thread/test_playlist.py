"""Playlist discovery, isolated cookies and queue semantics without external services."""

import json
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

from videocaptioner.core import playlist as core


def info():
    entries = tuple(core.PlaylistEntry(i, str(i), "Same title", f"https://www.bilibili.com/video/BVfixture?p={i}", 2.0)
                    for i in range(1, 4))
    return core.PlaylistInfo("https://www.bilibili.com/video/BVfixture", "CON", entries)


def test_bilibili_collection_from_video_and_parts_are_distinct():
    season = {"id": 4, "mid": 5, "title": "Fixture collection", "ep_count": 2,
              "sections": [{"episodes": [{"bvid": "BVone", "title": "One", "arc": {"duration": 10}},
                                          {"bvid": "BVtwo", "title": "Two"}]}]}
    video = {"title": "Fixture", "bvid": "BVone", "ugc_season": season,
             "pages": [{"page": 1, "part": "Part one"}, {"page": 2, "part": "Part two"}]}
    extractor = SimpleNamespace(_download_webpage=lambda *a: "fixture", _search_json=lambda *a, **k: {"videoData": video})
    ydl = SimpleNamespace(get_info_extractor=lambda _: extractor)
    collection = core._bilibili_page(ydl, "https://www.bilibili.com/video/BVone", "auto", lambda: None)
    assert collection.kind == "bilibili-collection" and len(collection.entries) == 2
    assert collection.entries[1].url.endswith("/BVtwo")
    parts = core._bilibili_page(ydl, "https://www.bilibili.com/video/BVone?p=2", "parts", lambda: None)
    assert parts.kind == "bilibili-parts" and [e.url.rsplit("=", 1)[-1] for e in parts.entries] == ["1", "2"]
    assert core.canonical_url("https://www.bilibili.com/video/BVone?vd_source=private&p=2&spm_id_from=tracking").endswith("BVone?p=2")


def test_partial_collection_uses_paginated_extractor(monkeypatch):
    video = {"ugc_season": {"id": 4, "mid": 5, "ep_count": 10, "sections": []}}
    extractor = SimpleNamespace(_download_webpage=lambda *a: "fixture", _search_json=lambda *a, **k: {"videoData": video})
    called = []
    monkeypatch.setattr(core, "_extract_list", lambda y, url, c: called.append(url) or info())
    core._bilibili_page(SimpleNamespace(get_info_extractor=lambda _: extractor), "https://www.bilibili.com/video/BVone", "auto", lambda: None)
    assert called == ["https://space.bilibili.com/5/lists/4?type=season"]


@pytest.mark.parametrize("bad", ["0", "3-2", "4", "1,,2", "1:2", "1-999999999"])
def test_selection_rejects_invalid_indices(bad):
    with pytest.raises(ValueError):
        core.selection(info(), bad)


def test_selection_preserves_order_and_rejects_unsafe_url():
    assert [e.index for e in core.selection(info(), "3,1-2,1")] == [1, 2, 3]
    for url in ("file:///private", "https://user:password@example.test", "javascript:bad"):
        with pytest.raises(ValueError):
            core.canonical_url(url)
    assert core.safe_name("../CON") == "_CON"
    assert core.safe_name("CON") == "playlist_CON"


def test_discovery_late_page_error_does_not_return_partial_success():
    def entries():
        yield {"url": "https://www.bilibili.com/video/BVone"}
        raise RuntimeError("second page failed")
    ydl = SimpleNamespace(extract_info=lambda *a, **k: {"_type": "playlist", "entries": entries()})
    with pytest.raises(RuntimeError, match="second page"):
        core._extract_list(ydl, "https://example.test/list", lambda: None)


def test_missing_entry_is_visible_and_nested_lists_are_not_downloaded():
    ydl = SimpleNamespace(extract_info=lambda *a, **k: {"_type": "playlist", "entries": [None,
        {"_type": "playlist", "url": "https://example.test/list"}]})
    result = core._extract_list(ydl, "https://example.test/list", lambda: None)
    assert len(result.entries) == 2 and all(e.unavailable_reason for e in result.entries)


@pytest.fixture
def fake_download(monkeypatch):
    calls, failing, options = [], set(), []

    @contextmanager
    def downloader(opts, cookies, check):
        options.append(opts)
        class YDL:
            def extract_info(self, url, **kwargs):
                calls.append(url)
                assert kwargs == {"download": False, "process": False}
                check()
                if url in failing:
                    raise RuntimeError("fixture failure")
                return {"id": "part", "title": "Same title", "url": url}

            def process_ie_result(self, item, download):
                assert download and opts.get("continuedl", True)
                path = Path(opts["outtmpl"]).parent / "same.mp4"
                path.write_bytes(item["url"].encode())
                opts["progress_hooks"][0]({"downloaded_bytes": 1, "total_bytes": 2})
                opts["post_hooks"][0](str(path))
                return {"filepath": str(path)}
        yield YDL()
    monkeypatch.setattr(core, "_downloader", downloader)
    return calls, failing, options


def test_queue_individual_errors_same_titles_resume_and_integrity(tmp_path, fake_download):
    calls, failing, options = fake_download
    source = info()
    failing.add(source.entries[1].url)
    result = core.download_playlist(source, source.entries, tmp_path)
    assert [item.status for item in result.items] == ["downloaded", "failed", "downloaded"]
    assert len(set(result.paths)) == 2
    assert all(Path(path).is_relative_to(tmp_path) for path in result.paths)
    first_calls = list(calls)
    failing.clear()
    resumed = core.download_playlist(source, source.entries, tmp_path)
    assert [item.status for item in resumed.items] == ["existing", "downloaded", "existing"]
    assert calls == first_calls + [source.entries[1].url]
    Path(resumed.paths[0]).write_bytes(b"user modified media")
    protected = Path(resumed.paths[0]).read_bytes()
    again = core.download_playlist(source, source.entries[:1], tmp_path)
    assert again.items[0].status == "failed" and Path(resumed.paths[0]).read_bytes() == protected


def test_cancel_preserves_finished_items_and_unstarted_queue(tmp_path, fake_download):
    source = info()
    stopped = [False]
    def progress(item, _):
        if item.status == "downloaded":
            stopped[0] = True
    result = core.download_playlist(source, source.entries, tmp_path, cancelled=lambda: stopped[0], progress=progress)
    assert result.cancelled
    assert [i.status for i in result.items] == ["downloaded", "cancelled", "pending"]
    assert len(fake_download[0]) == 1 and Path(result.paths[0]).is_file()


def test_selection_identity_and_path_receipt_guard(tmp_path, fake_download):
    from dataclasses import replace
    source = info()
    with pytest.raises(ValueError, match="Selection"):
        core.download_playlist(source, (replace(source.entries[0], url="https://wrong.test"),), tmp_path)
    result = core.download_playlist(source, source.entries[:1], tmp_path)
    receipt = Path(result.paths[0]).parent / "completed.json"
    saved = json.loads(receipt.read_text())
    saved["filename"] = "../../outside.mp4"
    receipt.write_text(json.dumps(saved))
    result = core.download_playlist(source, source.entries[:1], tmp_path)
    assert result.items[0].status == "failed"


def test_cookie_file_is_snapshotted_and_never_written_back(tmp_path, monkeypatch):
    import yt_dlp
    original = tmp_path / "cookies.txt"
    original.write_text("fixture secret", encoding="utf-8")
    class YDL:
        def __init__(self, params):
            self.path = Path(params["cookiefile"])
            assert self.path != original and self.path.read_text() == "fixture secret"
        def __enter__(self):
            return self
        def __exit__(self, *args):
            self.path.write_text("server refreshed jar")
    monkeypatch.setattr(yt_dlp, "YoutubeDL", YDL)
    with core._downloader({}, original, lambda: None) as ydl:
        snapshot = ydl.path
    assert original.read_text() == "fixture secret" and not snapshot.exists()


def test_real_ytdlp_local_media_completion_and_zero_network_resume(tmp_path):
    import functools
    import http.server
    import shutil
    import subprocess
    import threading

    from videocaptioner.core.utils.subprocess_helper import child_environment

    if not shutil.which("ffmpeg"):
        pytest.skip("FFmpeg required")
    media = tmp_path / "sample.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=blue:s=160x90:r=10:d=1",
                    "-c:v", "libx264", str(media)], env=child_environment(), capture_output=True, check=True)
    requests = []
    class Handler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass
        def do_GET(self):
            requests.append(self.path)
            super().do_GET()
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Handler, directory=str(tmp_path)))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}/sample.mp4"
    entry = core.PlaylistEntry(1, "fixture", "Fixture", url)
    playlist = core.PlaylistInfo(url, "Fixture playlist", (entry,))
    try:
        result = core.download_playlist(playlist, playlist.entries, tmp_path / "output")
        assert result.items[0].status == "downloaded", result
        assert Path(result.paths[0]).read_bytes() == media.read_bytes()
        count = len(requests)
        assert count > 0
        again = core.download_playlist(playlist, playlist.entries, tmp_path / "output")
        assert again.items[0].status == "existing" and len(requests) == count
    finally:
        server.shutdown()
        server.server_close()
        thread.join(5)

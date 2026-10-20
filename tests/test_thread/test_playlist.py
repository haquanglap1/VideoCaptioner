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
            def get_info_extractor(self, name):
                return SimpleNamespace(extract_formats=lambda _: [])

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
    assert options[0]["merge_output_format"] == "mp4"
    assert options[0]["format"].endswith("best[ext=mp4]")
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


@pytest.fixture
def short_titles(monkeypatch):
    from videocaptioner.core.llm.client import LLMCredentials
    from videocaptioner.core.translate import video_title as titles

    requests = []

    class Request:
        def __init__(self, *args, **kwargs):
            pass

        def __call__(self, messages, model):
            requests.append(json.loads(messages[1]["content"])["title"])
            content = json.dumps({"title": "Cùng tên tiếng Việt"})
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])

    monkeypatch.setattr(titles, "OwnedLLMRequest", Request)
    monkeypatch.setattr(titles, "is_cache_enabled", lambda: False)
    config = titles.VideoTitleConfig("", "", "vi", "synthetic-model",
                                     LLMCredentials("synthetic-secret", "https://synthetic.invalid/v1"))
    return SimpleNamespace(config=config, requests=requests)


def test_finished_entries_are_renamed_before_the_receipt_and_resume_without_naming(tmp_path, fake_download,
                                                                                  short_titles):
    from videocaptioner.core.translate.series_context import load_video_context
    source = info()
    result = core.download_playlist(source, source.entries, tmp_path, naming=short_titles.config)
    assert [item.status for item in result.items] == ["downloaded"] * 3
    names = [Path(path).name for path in result.paths]
    assert all(name.startswith("Cùng tên tiếng Việt [") and name.endswith("].mp4") for name in names)
    assert len(set(names)) == 3 and short_titles.requests == ["Same title"] * 3
    for path in result.paths:
        receipt = json.loads((Path(path).parent / "completed.json").read_text(encoding="utf-8"))
        assert receipt["filename"] == Path(path).name and not (Path(path).parent / "same.mp4").exists()
        assert load_video_context(path).file_title == "Cùng tên tiếng Việt"
    resumed = core.download_playlist(source, source.entries, tmp_path, naming=short_titles.config)
    assert [item.status for item in resumed.items] == ["existing"] * 3 and resumed.paths == result.paths
    assert len(short_titles.requests) == 3 and len(fake_download[0]) == 3


def test_rename_collision_or_no_naming_keeps_the_downloaded_name(tmp_path, fake_download, short_titles):
    from videocaptioner.core.translate.series_context import load_video_context
    from videocaptioner.core.translate.video_title import download_id_tag
    source = info()
    entry = source.entries[0]
    folder = tmp_path / "entry"
    folder.mkdir()
    taken = folder / ("Cùng tên tiếng Việt" + download_id_tag("part", entry.url) + ".mp4")
    taken.write_bytes(b"user file")
    result = core._download_entry(entry, folder, None, lambda: None, lambda _: None, short_titles.config)
    assert Path(result.path).name == "same.mp4" and taken.read_bytes() == b"user file"
    assert load_video_context(result.path).file_title == ""
    plain = core.download_playlist(source, source.entries[1:2], tmp_path / "plain")
    assert Path(plain.paths[0]).name == "same.mp4" and len(short_titles.requests) == 1


@pytest.mark.parametrize("had_sidecar", [True, False])
def test_earlier_entries_are_renamed_in_place_without_downloading(tmp_path, fake_download, short_titles,
                                                                  had_sidecar):
    from videocaptioner.core.translate.series_context import load_video_context, sidecar_path
    source = info()
    before = core.download_playlist(source, source.entries, tmp_path)
    old = [Path(path) for path in before.paths]
    if not had_sidecar:  # downloads before 2026-10-07
        for path in old:
            sidecar_path(path).unlink()
    calls = len(fake_download[0])
    renamed = core.download_playlist(source, source.entries, tmp_path, naming=short_titles.config)
    assert [item.status for item in renamed.items] == ["existing"] * 3 and len(fake_download[0]) == calls
    for path, earlier, entry in zip(map(Path, renamed.paths), old, source.entries):
        assert path.parent == earlier.parent and path.name.startswith("Cùng tên tiếng Việt [")
        assert path.read_bytes() == entry.url.encode()
        assert not earlier.exists() and not sidecar_path(earlier).exists()
        receipt = json.loads((path.parent / "completed.json").read_text(encoding="utf-8"))
        assert (receipt["filename"], receipt["previous"]) == (path.name, earlier.name)
        assert load_video_context(path).file_title == "Cùng tên tiếng Việt"
    asked = len(short_titles.requests)
    again = core.download_playlist(source, source.entries, tmp_path, naming=short_titles.config)
    assert again.paths == renamed.paths and len(short_titles.requests) == asked == 3


def test_interrupted_rename_finishes_on_the_next_run(tmp_path, fake_download):
    source = info()
    path = Path(core.download_playlist(source, source.entries[:1], tmp_path).paths[0])
    receipt = path.parent / "completed.json"
    saved = json.loads(receipt.read_text(encoding="utf-8"))
    # The receipt moved first; the process stopped before the file did.
    receipt.write_text(json.dumps({**saved, "filename": "Tên mới [x].mp4", "previous": path.name}), encoding="utf-8")
    result = core.download_playlist(source, source.entries[:1], tmp_path)
    assert result.items[0].status == "existing" and Path(result.paths[0]).name == "Tên mới [x].mp4"
    assert not path.exists()
    receipt.write_text(json.dumps({**saved, "filename": "x.mp4", "previous": "../../outside.mp4"}), encoding="utf-8")
    assert core.download_playlist(source, source.entries[:1], tmp_path).items[0].status == "failed"


def test_new_folders_are_shorter_but_earlier_runs_keep_their_folders(tmp_path, fake_download):
    import hashlib
    from dataclasses import replace
    long_title = "很长的合集标题" * 12
    source = info()
    source = replace(source, title=long_title, entries=tuple(replace(e, title=long_title) for e in source.entries))
    identity = hashlib.sha256(source.source_url.encode()).hexdigest()[:10]
    legacy = tmp_path / "old" / f"{core.safe_name(long_title)}-{identity}"
    legacy.mkdir(parents=True)
    old = core.download_playlist(source, source.entries[:1], tmp_path / "old")
    assert Path(old.paths[0]).parent.parent == legacy
    fresh = core.download_playlist(source, source.entries[:1], tmp_path / "new")
    playlist_dir, entry_dir = Path(fresh.paths[0]).parent.parent, Path(fresh.paths[0]).parent
    assert playlist_dir.name == f"{core.safe_name(long_title, 40)}-{identity}"
    assert len(entry_dir.name) <= 6 + 40 + 11 and len(playlist_dir.name) <= 51


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


@pytest.mark.parametrize("message", [
    "ERROR: [download] Got error: 1403429 bytes read, 41200987 more expected",
    "ERROR: [download] Got error: 403 bytes read, 429 more expected",
    "ERROR: [download] Got error: [SSL: UNEXPECTED_EOF_WHILE_READING]",
])
def test_transport_errors_are_not_misreported_as_http_access_denied(message):
    assert core.friendly_error(RuntimeError(message)) == message


@pytest.mark.parametrize("status", [403, 412, 429])
def test_http_access_errors_are_recognized(status):
    assert "hạn chế truy cập" in core.friendly_error(RuntimeError(f"HTTP Error {status}: service error"))


@pytest.mark.parametrize("bilibili,disconnects,expected,max_requests", [
    (True, 4, "downloaded", None),
    (False, 4, "failed", 3),
    (True, 99, "failed", 11),
    (True, 99, "cancelled", 1),
])
def test_bilibili_transport_recovers_repeated_short_reads_without_resetting_bytes(
    tmp_path, monkeypatch, bilibili, disconnects, expected, max_requests,
):
    import hashlib
    import http.server
    import threading

    # Transport-only bytes: the real yt-dlp downloader must resume after four disconnects.
    payload = bytes(range(256)) * 10000
    requests = []
    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            value = self.headers.get("Range", "bytes=0-")
            first, last = value.removeprefix("bytes=").split("-")
            start, end = int(first), min(int(last) if last else len(payload) - 1, len(payload) - 1)
            requests.append((start, end))
            self.send_response(206)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Content-Length", str(end - start + 1))
            self.send_header("Content-Range", f"bytes {start}-{end}/{len(payload)}")
            self.end_headers()
            sent_end = min(end + 1, start + 65536) if len(requests) <= disconnects else end + 1
            self.wfile.write(payload[start:sent_end])
            self.wfile.flush()
            self.close_connection = True

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}/fixture.mp4"
    original = core._downloader

    @contextmanager
    def downloader(options, cookies, check):
        with original(options, cookies, check) as ydl:
            # Isolate website metadata from the transport being exercised.
            monkeypatch.setattr(ydl, "extract_info", lambda *a, **k: {
                "id": "fixture", "title": "Fixture", "url": url, "ext": "mp4"})
            yield ydl

    monkeypatch.setattr(core, "_downloader", downloader)
    entry_url = "https://www.bilibili.com/video/BVfixture" if bilibili else url
    entry = core.PlaylistEntry(1, "fixture", "Fixture", entry_url)
    source = core.PlaylistInfo(entry_url, "Fixture", (entry,))
    cancelled = [False]
    def progress(item, percent):
        if expected == "cancelled" and percent > 0:
            cancelled[0] = True
    try:
        result = core.download_playlist(source, source.entries, tmp_path / "output",
                                        cancelled=lambda: cancelled[0], progress=progress)
        assert result.items[0].status == expected, result
        if expected != "downloaded":
            assert len(requests) == max_requests
            assert result.cancelled == (expected == "cancelled")
            assert list((tmp_path / "output").rglob("*.part"))
            assert not list((tmp_path / "output").rglob("completed.json"))
            return
        assert Path(result.paths[0]).read_bytes() == payload
        assert len(requests) > 4 and requests[1][0] > 0
        assert all(end - start + 1 <= 1024 * 1024 for start, end in requests)
        receipt = json.loads((Path(result.paths[0]).parent / "completed.json").read_text())
        assert receipt["sha256"] == hashlib.sha256(payload).hexdigest()
        before = len(requests)
        assert core.download_playlist(source, source.entries, tmp_path / "output").items[0].status == "existing"
        assert len(requests) == before
    finally:
        server.shutdown()
        server.server_close()
        thread.join(5)


@pytest.mark.parametrize("named", [False, True])
def test_real_ytdlp_local_media_completion_and_zero_network_resume(tmp_path, short_titles, named):
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
        naming = short_titles.config if named else None
        result = core.download_playlist(playlist, playlist.entries, tmp_path / "output", naming=naming)
        assert result.items[0].status == "downloaded", result
        assert Path(result.paths[0]).read_bytes() == media.read_bytes()
        assert Path(result.paths[0]).name.startswith("Cùng tên tiếng Việt [" if named else "sample [")
        assert not list((tmp_path / "output").rglob("*.part"))
        count = len(requests)
        assert count > 0
        again = core.download_playlist(playlist, playlist.entries, tmp_path / "output", naming=naming)
        assert again.items[0].status == "existing" and len(requests) == count
        assert again.paths == result.paths and len(short_titles.requests) == int(named)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(5)

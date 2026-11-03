"""YouTube redirects, playlist identity and single-entry download boundaries."""

from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from videocaptioner.core import playlist as core

PLAYLIST = "PL1234567890abcdefghijk"
VIDEO = "BaW_jenozKc"
URL = f"https://www.youtube.com/playlist?list={PLAYLIST}"


@pytest.mark.parametrize("url", [
    URL + "&si=tracking",
    f"https://www.youtube.com/watch?v={VIDEO}&list={PLAYLIST}&index=3",
    f"https://youtu.be/{VIDEO}?si=tracking&list={PLAYLIST}",
    f"https://m.youtube.com/watch?list={PLAYLIST}&v={VIDEO}",
    f"https://music.youtube.com/playlist?list={PLAYLIST}",
    f"https://www.youtube.com/embed/videoseries?list={PLAYLIST}",
])
def test_shared_links_discover_same_whole_playlist_without_extracting_videos(monkeypatch, url):
    from yt_dlp.extractor.youtube import YoutubeTabIE

    calls = []
    def extract(self, target):
        calls.append(target)
        assert not self.get_param("noplaylist")
        return {"_type": "playlist", "id": PLAYLIST, "title": "Fixture playlist", "entries": iter([
            {"_type": "url", "ie_key": "Youtube", "id": VIDEO, "title": "First",
             "url": f"https://www.youtube.com/watch?v={VIDEO}&list={PLAYLIST}&index=1"},
            {"_type": "url", "ie_key": "Youtube", "id": "abcdefghijk", "title": "[Private video]",
             "url": "https://www.youtube.com/watch?v=abcdefghijk"},
            {"_type": "url", "ie_key": "Youtube", "id": VIDEO, "title": "Repeated video",
             "url": f"https://youtu.be/{VIDEO}"},
        ])}
    monkeypatch.setattr(YoutubeTabIE, "_real_extract", extract)
    info = core.discover_playlist(url)
    assert calls == [URL] and info.source_url == URL
    assert [entry.index for entry in info.entries] == [1, 2, 3]
    assert info.entries[0].url == info.entries[2].url == f"https://www.youtube.com/watch?v={VIDEO}"
    assert info.entries[1].unavailable_reason
    assert [entry.index for entry in core.selection(info, "3,1")] == [1, 3]
    assert "list=" in core.canonical_url(url)


def test_similar_host_is_not_rewritten():
    url = f"https://youtube.com.example.test/watch?v={VIDEO}&list={PLAYLIST}"
    assert core._youtube_playlist_url(url) == url


def test_real_ytdlp_short_link_redirect_is_resolved_without_processing_entries(monkeypatch):
    from yt_dlp.extractor.youtube import YoutubeTabIE

    calls = []
    def extract(self, url):
        calls.append(url)
        return {"_type": "playlist", "id": PLAYLIST, "entries": [
            {"id": VIDEO, "url": f"https://www.youtube.com/watch?v={VIDEO}"}]}
    monkeypatch.setattr(YoutubeTabIE, "_real_extract", extract)
    with core._downloader({"noplaylist": False}, None, lambda: None) as ydl:
        info = core._extract_list(ydl, f"https://youtu.be/{VIDEO}?list={PLAYLIST}", lambda: None)
    assert len(calls) == 1 and f"list={PLAYLIST}" in calls[0]
    assert len(info.entries) == 1 and info.entries[0].entry_id == VIDEO


@pytest.mark.parametrize("kind", ["url", "url_transparent"])
def test_redirected_video_download_stays_one_entry(tmp_path, monkeypatch, kind):
    calls, processed = [], []
    @contextmanager
    def downloader(options, cookies, check):
        assert options["remote_components"] == ["ejs:github"]
        def extract(url, **kwargs):
            calls.append((url, kwargs))
            if len(calls) == 1:
                return {"_type": kind, "url": f"https://www.youtube.com/watch?v={VIDEO}", "ie_key": "Youtube"}
            return {"id": VIDEO, "title": "Fixture", "url": "https://media.example.test/video.mp4"}
        def process(info, download):
            processed.append(info)
            path = tmp_path / "fixture.mp4"
            path.write_bytes(b"fixture media")
            options["post_hooks"][0](str(path))
            return {"filepath": str(path)}
        yield SimpleNamespace(extract_info=extract, process_ie_result=process)
    monkeypatch.setattr(core, "_downloader", downloader)
    entry = core.PlaylistEntry(1, VIDEO, "Fixture", f"https://youtu.be/{VIDEO}")
    result = core._download_entry(entry, tmp_path, None, lambda: None, lambda _: None)
    assert result.status == "downloaded" and len(processed) == 1
    assert calls[1][1] == {"download": False, "process": False, "ie_key": "Youtube"}
    assert core._download_entry(entry, tmp_path, None, lambda: None, lambda _: None).status == "existing"
    assert len(calls) == 2


def test_redirect_to_nested_playlist_cannot_download_outside_selection(tmp_path, monkeypatch):
    results = iter([{"_type": "url", "url": URL, "ie_key": "YoutubeTab"},
                    {"_type": "playlist", "entries": []}])
    @contextmanager
    def downloader(*args):
        yield SimpleNamespace(extract_info=lambda *a, **k: next(results))
    monkeypatch.setattr(core, "_downloader", downloader)
    entry = core.PlaylistEntry(1, VIDEO, "Fixture", f"https://youtu.be/{VIDEO}")
    with pytest.raises(ValueError, match="selection"):
        core._download_entry(entry, tmp_path, None, lambda: None, lambda _: None)
    assert not (tmp_path / "completed.json").exists()


@pytest.mark.parametrize("mode", ["loop", "limit", "unsafe", "cancel"])
def test_redirects_are_bounded_validated_and_cancellable(mode):
    calls = []
    def extract(url, **kwargs):
        calls.append(url)
        target = URL if mode == "loop" else f"https://www.youtube.com/playlist?list=PL{len(calls)}"
        if mode == "unsafe":
            target = "file:///private"
        return {"_type": "url", "url": target}
    def check():
        if mode == "cancel" and calls:
            raise core.DownloadCancelled()
    with pytest.raises(core.DownloadCancelled if mode == "cancel" else ValueError):
        core._extract_unprocessed(SimpleNamespace(extract_info=extract), URL, check)
    assert len(calls) <= 6


def test_paginated_youtube_list_retains_limit():
    def entries():
        for _ in range(2001):
            yield {"id": VIDEO, "url": f"https://www.youtube.com/watch?v={VIDEO}"}
    ydl = SimpleNamespace(extract_info=lambda *a, **k: {"_type": "playlist", "entries": entries()})
    with pytest.raises(ValueError, match="2000"):
        core._extract_list(ydl, URL, lambda: None)

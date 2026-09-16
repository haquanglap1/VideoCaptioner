"""A GUI download must return one usable media path for an anthology URL."""

from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
import yt_dlp

from videocaptioner.core.utils import installer
from videocaptioner.ui.thread import video_download_thread


@pytest.mark.parametrize("query,part", [("", 1), ("?p=2", 2)])
def test_gui_download_returns_requested_video_instead_of_an_anthology(tmp_path, monkeypatch, query, part):
    downloaded = []

    class AnthologyDownloader:
        def __init__(self, params):
            self.params = params

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def extract_info(self, url, *, download):
            assert not download
            selected = parse_qs(urlparse(url).query).get("p", [None])[0]
            if not selected and not self.params.get("noplaylist"):
                return {"_type": "playlist", "title": "Fixture anthology", "entries": [{}, {}]}
            return {"title": f"Fixture part {selected or 1}", "ext": "mp4"}

        def process_ie_result(self, info, *, download):
            assert download
            if info.get("_type") == "playlist":
                downloaded.extend(info["entries"])
            else:
                downloaded.append(info["title"])
                target = Path(self.prepare_filename(info))
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(b"synthetic video")
            return info

        def prepare_filename(self, info):
            return str(Path(self.params["paths"]["home"]) / f"{info['title']}.mp4")

    monkeypatch.setattr(yt_dlp, "YoutubeDL", AnthologyDownloader)
    monkeypatch.setattr(installer, "deno_path", lambda: tmp_path / "existing-deno.exe")
    monkeypatch.setattr(video_download_thread, "APPDATA_PATH", tmp_path / "settings")
    worker = video_download_thread.VideoDownloadThread(
        "https://www.bilibili.com/video/BVfixture/" + query, str(tmp_path / "downloads")
    )
    video, _, _, _ = worker.download(need_subtitle=False)
    assert video and Path(video).read_bytes() == b"synthetic video"
    assert downloaded == [f"Fixture part {part}"]

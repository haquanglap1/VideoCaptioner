"""A GUI download must return one usable media path for an anthology URL."""

import re
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
import yt_dlp

from videocaptioner.core.utils import installer
from videocaptioner.ui.thread import video_download_thread


def _prepared(params, info, outtmpl=None):
    # Mirrors yt-dlp: the default template under paths.home, %(ext)s from the info.
    if outtmpl:
        title = re.sub(r'[<>:"/\\|?*]', "_", info["title"])  # yt-dlp's own sanitizing, simplified
        name = outtmpl.replace("%(title).200s", title).replace("%(ext)s", info.get("ext", "mp4"))
        return str(Path(params["paths"]["home"]) / name)
    name = params["outtmpl"]["default"].replace("%(ext)s", info.get("ext", "mp4"))
    assert "%" not in name and "$" not in name
    return str(Path(params["paths"]["home"]) / name)


@pytest.mark.parametrize("query,part", [("", 1), ("?p=2", 2)])
def test_gui_download_returns_requested_video_instead_of_an_anthology(tmp_path, monkeypatch, query, part):
    downloaded = []

    class AnthologyDownloader:
        def __init__(self, params):
            self.params = params
            assert params["merge_output_format"] == "mp4"
            assert params["format"].endswith("best[ext=mp4]")

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def extract_info(self, url, *, download):
            assert not download
            selected = parse_qs(urlparse(url).query).get("p", [None])[0]
            if not selected and not self.params.get("noplaylist"):
                return {"_type": "playlist", "title": "Fixture anthology", "entries": [{}, {}]}
            return {"title": f"Fixture part {selected or 1}", "ext": "mp4", "id": f"BVfixture_p{selected or 1}"}

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

        def prepare_filename(self, info, outtmpl=None):
            return _prepared(self.params, info, outtmpl)

    monkeypatch.setattr(yt_dlp, "YoutubeDL", AnthologyDownloader)
    monkeypatch.setattr(installer, "deno_path", lambda: tmp_path / "existing-deno.exe")
    monkeypatch.setattr(video_download_thread, "APPDATA_PATH", tmp_path / "settings")
    worker = video_download_thread.VideoDownloadThread(
        "https://www.bilibili.com/video/BVfixture/" + query, str(tmp_path / "downloads")
    )
    video, _, _, _ = worker.download(need_subtitle=False)
    assert video and Path(video).read_bytes() == b"synthetic video"
    assert downloaded == [f"Fixture part {part}"]


def test_gui_download_writes_a_context_sidecar_beside_the_video(tmp_path, monkeypatch):
    from videocaptioner.core.translate.series_context import load_video_context

    class Downloader:
        def __init__(self, params):
            self.params = params

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def extract_info(self, url, *, download):
            return {"title": "Fixture PV", "ext": "mp4", "uploader": "Channel", "description": "师徒修行",
                    "webpage_url": url}

        def process_ie_result(self, info, *, download):
            target = Path(self.prepare_filename(info))
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"synthetic video")
            return info

        def prepare_filename(self, info, outtmpl=None):
            return _prepared(self.params, info, outtmpl)

    monkeypatch.setattr(yt_dlp, "YoutubeDL", Downloader)
    monkeypatch.setattr(installer, "deno_path", lambda: tmp_path / "existing-deno.exe")
    monkeypatch.setattr(video_download_thread, "APPDATA_PATH", tmp_path / "settings")
    worker = video_download_thread.VideoDownloadThread("https://www.youtube.com/watch?v=fixture", str(tmp_path / "downloads"))
    video, _, _, _ = worker.download(need_subtitle=False)
    context = load_video_context(video)
    assert context is not None and (context.title, context.uploader, context.description) == ("Fixture PV", "Channel", "师徒修行")
    assert context.url == "https://www.youtube.com/watch?v=fixture"


class _PageDownloader:
    """yt-dlp stand-in that writes the merged file at the prepared path."""

    title = ""

    def __init__(self, params):
        self.params = params

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def extract_info(self, url, *, download):
        return {"title": self.title, "ext": "mp4", "id": "BV1GFbk6LEVm", "webpage_url": url}

    downloads = 0

    def process_ie_result(self, info, *, download):
        target = Path(self.prepare_filename(info))
        if not target.exists():  # yt-dlp skips a finished file
            type(self).downloads += 1
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"synthetic video")
        return info

    def prepare_filename(self, info, outtmpl=None):
        return _prepared(self.params, info, outtmpl)


def _worker(tmp_path, monkeypatch, title, naming=None):
    monkeypatch.setattr(_PageDownloader, "title", title)
    monkeypatch.setattr(_PageDownloader, "downloads", 0)
    monkeypatch.setattr(yt_dlp, "YoutubeDL", _PageDownloader)
    monkeypatch.setattr(installer, "deno_path", lambda: tmp_path / "existing-deno.exe")
    monkeypatch.setattr(video_download_thread, "APPDATA_PATH", tmp_path / "settings")
    return video_download_thread.VideoDownloadThread(
        "https://www.bilibili.com/video/BV1GFbk6LEVm", str(tmp_path / "downloads"), naming)


@pytest.fixture
def vi_naming(monkeypatch):
    from types import SimpleNamespace

    from videocaptioner.core.llm.client import LLMCredentials
    from videocaptioner.core.translate import video_title as titles

    requests = []

    class Request:
        def __init__(self, *args, **kwargs):
            pass

        def __call__(self, messages, model):
            requests.append(messages)
            content = '{"title": "Tập 1 Sư phụ dạy kiếm"}'
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])

    monkeypatch.setattr(titles, "OwnedLLMRequest", Request)
    monkeypatch.setattr(titles, "is_cache_enabled", lambda: False)
    config = titles.VideoTitleConfig("", "", "vi", "synthetic-model",
                                     LLMCredentials("synthetic-secret", "https://synthetic.invalid/v1"))
    return SimpleNamespace(config=config, requests=requests)


def test_gui_download_is_named_by_the_llm_before_any_file_is_written(tmp_path, monkeypatch, vi_naming):
    from videocaptioner.core.translate.series_context import load_video_context

    requests, naming = vi_naming.requests, vi_naming.config
    title = "【鸣潮】第1集 师父教我练剑！！超燃 #鸣潮 #二次元 #原神 " + "很长的描述" * 40
    worker = _worker(tmp_path, monkeypatch, title, naming)
    video, _, _, _ = worker.download(need_subtitle=False)
    path = Path(video)
    assert path.name == "Tập 1 Sư phụ dạy kiếm [BV1GFbk6LEVm].mp4"
    assert path.parent == tmp_path / "downloads" / path.stem
    assert [p.name for p in (tmp_path / "downloads").iterdir()] == [path.stem]
    assert len(requests) == 1 and str(tmp_path) not in repr(requests)
    context = load_video_context(path)
    assert context is not None and context.file_title == "Tập 1 Sư phụ dạy kiếm"
    assert context.title.startswith("【鸣潮】第1集")


def test_gui_download_without_naming_clips_long_titles(tmp_path, monkeypatch):
    from videocaptioner.core.translate.series_context import load_video_context

    title = "超长的抖音描述 " * 60 + "#话题 50% $HOME"
    worker = _worker(tmp_path, monkeypatch, title)
    video, _, _, _ = worker.download(need_subtitle=False)
    path = Path(video)
    assert path.name.endswith(" [BV1GFbk6LEVm].mp4") and len(path.stem) <= 60 + 15
    assert path.parent.name == path.stem and path.read_bytes() == b"synthetic video"
    context = load_video_context(path)
    assert context is not None and context.file_title == ""


@pytest.mark.parametrize("sidecar_url", [None, "https://www.bilibili.com/video/BV1GFbk6LEVm", "https://other.test/v"])
def test_redownload_renames_an_old_long_name_download_instead_of_fetching(tmp_path, monkeypatch, vi_naming,
                                                                         sidecar_url):
    from videocaptioner.core.translate.series_context import (
        VideoContext,
        load_video_context,
        save_video_context,
        sidecar_path,
    )
    from videocaptioner.ui.thread.video_download_thread import _legacy_folder

    title = "【鸣潮】第1集 师父教我练剑: 超燃?"
    old = tmp_path / "downloads" / _legacy_folder(title) / "【鸣潮】第1集 师父教我练剑_ 超燃_.mp4"
    old.parent.mkdir(parents=True)
    old.write_bytes(b"earlier download")
    if sidecar_url:
        save_video_context(old, VideoContext.make(title=title, url=sidecar_url))
    worker = _worker(tmp_path, monkeypatch, title, vi_naming.config)
    video = Path(worker.download(need_subtitle=False)[0])
    assert video.name == "Tập 1 Sư phụ dạy kiếm [BV1GFbk6LEVm].mp4"
    if sidecar_url == "https://other.test/v":  # another video under the same title is left alone
        assert _PageDownloader.downloads == 1 and old.read_bytes() == b"earlier download"
        return
    assert _PageDownloader.downloads == 0 and video.read_bytes() == b"earlier download"
    assert not old.parent.exists() and not sidecar_path(old).exists()
    assert load_video_context(video).file_title == "Tập 1 Sư phụ dạy kiếm"


def test_redownload_keeps_other_files_in_the_old_folder(tmp_path, monkeypatch, vi_naming):
    title = "Old long title"
    old = tmp_path / "downloads" / title / f"{title}.mp4"
    (old.parent / "subtitle").mkdir(parents=True)
    old.write_bytes(b"earlier download")
    (old.parent / f"{title}_dubbed.mp4").write_bytes(b"output")
    video = Path(_worker(tmp_path, monkeypatch, title, vi_naming.config).download(need_subtitle=False)[0])
    assert video.read_bytes() == b"earlier download" and _PageDownloader.downloads == 0
    assert (old.parent / f"{title}_dubbed.mp4").read_bytes() == b"output" and not old.exists()


def test_real_ytdlp_gui_download_uses_the_short_name_and_reuses_it(tmp_path, monkeypatch, vi_naming):
    import functools
    import http.server
    import shutil
    import subprocess
    import threading

    from videocaptioner.core.translate.series_context import sidecar_path
    from videocaptioner.core.utils.subprocess_helper import child_environment

    if not shutil.which("ffmpeg"):
        pytest.skip("FFmpeg required")
    media = tmp_path / "media" / "sample.mp4"
    media.parent.mkdir()
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=blue:s=160x90:r=10:d=1",
                    "-c:v", "libx264", str(media)], env=child_environment(), capture_output=True, check=True)
    requests = []

    class Handler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            requests.append(self.path)
            super().do_GET()

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Handler, directory=str(media.parent)))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setattr(installer, "deno_path", lambda: tmp_path / "existing-deno.exe")
    monkeypatch.setattr(video_download_thread, "APPDATA_PATH", tmp_path / "settings")
    url = f"http://127.0.0.1:{server.server_port}/sample.mp4"
    try:
        worker = video_download_thread.VideoDownloadThread(url, str(tmp_path / "downloads"))
        video, _, _, _ = worker.download(need_subtitle=False)
        path = Path(video)
        assert path.read_bytes() == media.read_bytes() and path.parent.name == path.stem
        assert path.name.startswith("sample [") and path.suffix == ".mp4"
        assert requests
        written = path.stat().st_mtime_ns
        again, _, _, _ = video_download_thread.VideoDownloadThread(url, str(tmp_path / "downloads")).download(
            need_subtitle=False)
        # Same name on a repeat, so yt-dlp sees the finished file instead of downloading again.
        assert again == video and [p.name for p in (tmp_path / "downloads").iterdir()] == [path.stem]
        assert path.stat().st_mtime_ns == written
        # Turning naming on later renames that unnamed download instead of fetching it again.
        named = Path(video_download_thread.VideoDownloadThread(url, str(tmp_path / "downloads"),
                                                               vi_naming.config).download(need_subtitle=False)[0])
        assert named.name.startswith("Tập 1 Sư phụ dạy kiếm [") and named.stat().st_mtime_ns == written
        assert [p.name for p in (tmp_path / "downloads").iterdir()] == [named.stem]
        # A download from the old long-name layout is found through yt-dlp's own file naming.
        legacy = tmp_path / "downloads" / "sample" / "sample.mp4"
        legacy.parent.mkdir()
        named.rename(legacy)
        sidecar_path(named).unlink()  # downloads before 2026-10-07 had no sidecar
        named.parent.rmdir()
        adopted = Path(video_download_thread.VideoDownloadThread(url, str(tmp_path / "downloads"),
                                                                 vi_naming.config).download(need_subtitle=False)[0])
        assert adopted == named and adopted.stat().st_mtime_ns == written and not legacy.parent.exists()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(5)

"""Same-format Bilibili CDN fallback with real HTTP failures and resumable bytes."""

import hashlib
import http.server
import json
import threading
from contextlib import contextmanager
from pathlib import Path

import pytest

from videocaptioner.core import playlist as core


@pytest.mark.parametrize("failure,has_backup,backup_fails,cancel", [
    ("short", True, False, False),
    ("short", False, False, False),
    ("short", True, True, False),
    ("500", True, False, False),
    ("502", True, False, False),
    ("503", True, False, False),
    ("504", True, False, False),
    ("503", False, False, False),
    ("503", True, True, False),
    ("403", True, False, False),
    ("404", True, False, False),
    ("412", True, False, False),
    ("429", True, False, False),
    ("short", True, False, True),
    ("503", True, False, True),
])
def test_same_format_backup_resumes_only_transport_failures(
    tmp_path, monkeypatch, failure, has_backup, backup_fails, cancel,
):
    from yt_dlp.utils import DownloadError

    payload = bytes(range(256)) * 12000
    requests = []
    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            primary = self.path == "/primary.mp4"
            value = self.headers.get("Range", "bytes=0-")
            first, last = value.removeprefix("bytes=").split("-")
            start = int(first)
            end = min(int(last) if last else len(payload) - 1, len(payload) - 1)
            requests.append((self.path, start, end))
            if failure != "short" and (primary or backup_fails):
                if cancel:
                    stopped[0] = True
                self.send_error(int(failure))
                return
            self.send_response(206)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Content-Length", str(end - start + 1))
            self.send_header("Content-Range", f"bytes {start}-{end}/{len(payload)}")
            self.end_headers()
            sent_end = min(start + 65536, end + 1) if primary or backup_fails else end + 1
            try:
                self.wfile.write(payload[start:sent_end])
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass
            self.close_connection = True

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    media = {"id": 80, "baseUrl": base + "/primary.mp4", "mimeType": "video/mp4",
             "codecs": "avc1.640028", "width": 32, "height": 32}
    if has_backup:
        media["backupUrl"] = [base + "/backup.mp4", base + "/unused.mp4"]
    play_info = {"dash": {"video": [media]}, "support_formats": []}
    original = core._downloader

    @contextmanager
    def downloader(options, cookies, check):
        with original(options, cookies, check) as ydl:
            ie = ydl.get_info_extractor("BiliBili")
            monkeypatch.setattr(ydl, "extract_info", lambda *a, **k: {
                "id": "fixture", "title": "Fixture", "formats": ie.extract_formats(play_info)})
            yield ydl

    monkeypatch.setattr(core, "_downloader", downloader)
    folder = tmp_path / "entry"
    folder.mkdir()
    partial = folder / "Fixture [fixture].mp4.part"
    prefix = payload[:32768]
    partial.write_bytes(prefix)
    stopped = [False]
    def check():
        if stopped[0]:
            raise core.DownloadCancelled()
    def progress(percent):
        if cancel and percent > 0:
            stopped[0] = True
    entry = core.PlaylistEntry(1, "fixture", "Fixture", "https://www.bilibili.com/video/BVfixture")
    try:
        if cancel or failure in ("403", "404", "412", "429") or not has_backup or backup_fails:
            with pytest.raises(core.DownloadCancelled if cancel else DownloadError):
                core._download_entry(entry, folder, None, check, progress)
            assert not (folder / "completed.json").exists()
            assert partial.read_bytes().startswith(prefix)
            expected_backup_requests = 11 if backup_fails else 0
            assert sum(path == "/backup.mp4" for path, _, _ in requests) == expected_backup_requests
        else:
            result = core._download_entry(entry, folder, None, check, progress)
            assert result.status == "downloaded"
            assert Path(result.path).read_bytes() == payload
            receipt = json.loads((folder / "completed.json").read_text())
            assert receipt["sha256"] == hashlib.sha256(payload).hexdigest()
            first_backup = next(start for path, start, _ in requests if path == "/backup.mp4")
            assert first_backup > len(prefix) if failure == "short" else first_backup == len(prefix)
            count = len(requests)
            assert core._download_entry(entry, folder, None, check, progress).status == "existing"
            assert len(requests) == count
        assert all(path != "/unused.mp4" for path, _, _ in requests)
        assert requests[0][1] == len(prefix)
        primary_requests = sum(path == "/primary.mp4" for path, _, _ in requests)
        assert primary_requests <= 11
        if failure in ("500", "502", "503", "504") and not cancel:
            assert primary_requests == 11
    finally:
        server.shutdown()
        server.server_close()
        thread.join(5)


def test_backup_capture_keeps_format_identity_and_rejects_insecure_urls():
    from types import SimpleNamespace

    source = {"url": "https://media.example.test/video.mp4", "format_id": "100029"}
    extractor = SimpleNamespace(extract_formats=lambda _: [dict(source)])
    original = extractor.extract_formats
    ydl = SimpleNamespace(get_info_extractor=lambda _: extractor)
    metadata = {"dash": {"video": [{"baseUrl": source["url"], "backupUrl": [
        "file:///private", "http://media.example.test/video.mp4", "https://user:secret@example.test/",
        "https://backup.example.test/video.mp4?signature=fixture",
    ]}]}}
    with core._bilibili_media_backups(ydl, True) as backups:
        formats = extractor.extract_formats(metadata)
        assert formats == [source]
    assert extractor.extract_formats is original
    info = {"id": "fixture", "title": "Fixture", "formats": formats}
    fallback = core._media_attempt(info, backups)
    assert fallback["formats"][0]["url"] == "https://backup.example.test/video.mp4?signature=fixture"
    assert fallback["formats"][0]["format_id"] == "100029"
    assert info["formats"][0] == source
    direct = {"id": "fixture", "url": source["url"]}
    assert core._media_attempt(direct) == direct


@pytest.mark.parametrize("message", [
    "ERROR: Unable to download webpage: HTTP Error 503: Service Unavailable",
    "ERROR: [download] Got error: HTTP Error 403: Forbidden",
    "ERROR: [download] Got error: HTTP Error 429: Too Many Requests",
    "ERROR: [download] Got error: certificate verify failed",
    "ERROR: Postprocessing failed for video503.mp4",
])
def test_backup_does_not_retry_other_errors(message):
    assert not core._recoverable_media_error(Exception(message))


def test_server_error_explains_resume_without_blame_on_cookies():
    error = Exception("ERROR: [download] Got error: HTTP Error 503: Service Unavailable. Giving up after 10 retries")
    message = core.friendly_error(error)
    assert "HTTP 503" in message
    assert "Tải / Tiếp tục" in message
    assert "cookies" not in message

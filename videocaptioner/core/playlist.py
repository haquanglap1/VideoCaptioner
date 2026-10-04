"""Playlist discovery and resumable, single-entry downloads through the installed yt-dlp."""

from __future__ import annotations

import hashlib
import json
import math
import re
import shutil
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Callable, Mapping, cast
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

from videocaptioner.core.utils.download_format import mp4_format_selector, require_mp4


class DownloadCancelled(Exception):
    """Cooperative cancellation at network/progress boundaries."""


@dataclass(frozen=True)
class PlaylistEntry:
    index: int
    entry_id: str
    title: str
    url: str
    duration: float | None = None
    unavailable_reason: str = ""


@dataclass(frozen=True)
class PlaylistInfo:
    source_url: str
    title: str
    entries: tuple[PlaylistEntry, ...]
    kind: str = "playlist"


@dataclass(frozen=True)
class PlaylistItemResult:
    index: int
    status: str = "pending"
    path: str = ""
    error: str = ""


@dataclass(frozen=True)
class PlaylistResult:
    items: tuple[PlaylistItemResult, ...]
    cancelled: bool = False

    @property
    def paths(self) -> list[str]:
        return [item.path for item in self.items if item.status in ("downloaded", "existing")]


def canonical_url(url: str) -> str:
    parts = urlsplit(url.strip())
    if parts.scheme not in ("http", "https") or not parts.hostname or parts.username or parts.password:
        raise ValueError("Nhập URL video/danh sách http(s) hợp lệ.")
    if parts.hostname.lower() in ("bilibili.com", "www.bilibili.com") and parts.path.startswith("/video/"):
        query = parse_qs(parts.query)
        keep = {"p": query["p"][-1]} if query.get("p") else {}
        return urlunsplit(("https", "www.bilibili.com", parts.path.rstrip("/"), urlencode(keep), ""))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, ""))


def safe_name(value: str) -> str:
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value).strip(" .")[:65].rstrip(" .")
    if not name or re.fullmatch(r"(?i)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?", name):
        name = "playlist_" + name
    return name


def selection(info: PlaylistInfo, expression: str = "") -> tuple[PlaylistEntry, ...]:
    """Explicit 1-based indices/ranges, preserving source order and rejecting silent omissions."""
    if not expression.strip():
        return info.entries
    indexes: set[int] = set()
    for part in expression.split(","):
        match = re.fullmatch(r"\s*([1-9]\d*)(?:\s*-\s*([1-9]\d*))?\s*", part)
        if not match:
            raise ValueError("Chọn tập dạng 1,3-5 (số thứ tự bắt đầu từ 1).")
        first, last = int(match[1]), int(match[2] or match[1])
        if first > last or last > len(info.entries):
            raise ValueError("Số thứ tự tập nằm ngoài danh sách.")
        indexes.update(range(first, last + 1))
    return tuple(entry for entry in info.entries if entry.index in indexes)


def friendly_error(error: Exception) -> str:
    text = str(error)
    if "Requested format is not available" in text:
        return "Không có định dạng MP4 phù hợp để tải. Kiểm tra FFmpeg và quyền truy cập chất lượng video."
    status = re.search(r"\bHTTP(?:\s+Error)?\s+(403|412|429)\b", text, re.IGNORECASE)
    if status:
        return f"Bilibili/dịch vụ đang hạn chế truy cập (HTTP {status[1]}). Kiểm tra cookies/quyền truy cập hoặc thử lại sau."
    status = re.search(r"\bHTTP(?:\s+Error)?\s+(500|502|503|504)\b", text, re.IGNORECASE)
    if status:
        return (f"Máy chủ tải video tạm thời lỗi (HTTP {status[1]}). "
                "Lượt tải chưa hoàn tất; các video đã xong và file tải dở được giữ nguyên. "
                "Thử lại sau bằng Tải / Tiếp tục trong cùng thư mục.")
    return text[:700]


class _QuietLogger:
    def __init__(self, check):
        self.check = check

    def debug(self, message):
        self.check()

    info = warning = error = debug


@contextmanager
def _downloader(options: dict, cookies: Path | None, check: Callable[[], None]):
    import yt_dlp

    # yt-dlp saves its cookie jar on close; use a disposable snapshot of the user's file.
    with tempfile.TemporaryDirectory(prefix="vc-playlist-") as folder:
        opts = {"quiet": True, "no_warnings": True, "logger": _QuietLogger(check),
                "socket_timeout": 15, "retries": 2, "fragment_retries": 2, "extractor_retries": 1,
                "cachedir": False, "noplaylist": True, "overwrites": False, "continuedl": True,
                **options}
        if cookies and cookies.is_file():
            snapshot = Path(folder) / "cookies.txt"
            shutil.copyfile(cookies, snapshot)
            opts["cookiefile"] = str(snapshot)
        check()
        with yt_dlp.YoutubeDL(cast(Any, opts)) as ydl:
            yield ydl


def _entry(index: int, value: dict | None) -> PlaylistEntry:
    value = value or {}
    url = value.get("webpage_url") or value.get("url") or ""
    reason = ""
    try:
        url = canonical_url(url)
    except (ValueError, TypeError, AttributeError):
        url, reason = "", "Không có URL video truy cập được."
    duration = value.get("duration")
    if not isinstance(duration, (int, float)) or isinstance(duration, bool) or not math.isfinite(duration) or duration < 0:
        duration = None
    if value.get("_type") in ("playlist", "multi_video"):
        reason = "Danh sách lồng nhau; mở URL này riêng để chọn tập."
    return PlaylistEntry(index, str(value.get("id") or index), str(value.get("title") or value.get("id") or f"Tập {index}"),
                         url, duration, reason)


def _bilibili_page(ydl, url: str, scope: str, check) -> PlaylistInfo | None:
    """The Bilibili video extractor does not expose a video's ugc_season collection."""
    parts = urlsplit(url)
    if parts.hostname != "www.bilibili.com" or not re.fullmatch(r"/video/(?:BV[0-9A-Za-z]+|av\d+)", parts.path):
        return None
    video_id = parts.path.rsplit("/", 1)[-1]
    ie = ydl.get_info_extractor("BiliBili")
    page = ie._download_webpage(url, video_id)
    check()
    state = ie._search_json(r"window\.__INITIAL_STATE__\s*=", page, "initial state", video_id, default={})
    video = state.get("videoData") or state.get("videoInfo") or {}
    season = video.get("ugc_season") or {}
    if scope == "auto" and season:
        episodes = [episode for section in season.get("sections", []) for episode in section.get("episodes", [])]
        expected = season.get("ep_count")
        if isinstance(expected, int) and expected > 0 and len(episodes) == expected:
            entries = tuple(_entry(i, {"id": ep.get("bvid"), "title": ep.get("title"),
                "url": f'https://www.bilibili.com/video/{ep["bvid"]}' if ep.get("bvid") else "",
                "duration": (ep.get("arc") or {}).get("duration")}) for i, ep in enumerate(episodes, 1))
            return PlaylistInfo(url, str(season.get("title") or video_id), entries, "bilibili-collection")
        # Some pages only embed a subset. Let the installed paginated extractor fetch the collection.
        mid, sid = season.get("mid"), season.get("id")
        if not str(mid).isdigit() or not str(sid).isdigit():
            raise ValueError("Trang chỉ có một phần合集 và thiếu ID để đọc toàn bộ danh sách.")
        return _extract_list(ydl, f"https://space.bilibili.com/{mid}/lists/{sid}?type=season", check)
    pages = video.get("pages") or []
    if pages:
        bvid = video.get("bvid") or video_id
        entries = tuple(_entry(i, {"id": f'{bvid}_p{p["page"]}', "title": p.get("part"),
            "url": f'https://www.bilibili.com/video/{bvid}?p={p["page"]}', "duration": p.get("duration")})
            for i, p in enumerate(pages, 1))
        return PlaylistInfo(url, str(video.get("title") or bvid), entries, "bilibili-parts")
    return None


def _extract_list(ydl, url: str, check) -> PlaylistInfo:
    # process=False retains the generator so pagination can be cancelled and bounded.
    info = ydl.extract_info(url, download=False, process=False)
    if not isinstance(info, dict):
        raise ValueError("Không đọc được danh sách video.")
    if info.get("_type") not in ("playlist", "multi_video"):
        raise ValueError("URL này không trả danh sách. Với Bilibili, chọn link合集 hoặc video có nhiều phần.")
    entries = []
    for index, value in enumerate(info.get("entries") or [], 1):
        check()
        if index > 2000:
            raise ValueError("Danh sách vượt 2000 mục; chọn một合集 nhỏ hơn. Chưa bắt đầu tải.")
        entries.append(_entry(index, value))
    count = info.get("playlist_count")
    if isinstance(count, int) and count > len(entries):
        raise ValueError("Danh sách trả về chưa đầy đủ; chưa bắt đầu tải.")
    if not entries:
        raise ValueError("Danh sách trống hoặc không có quyền truy cập.")
    return PlaylistInfo(url, str(info.get("title") or info.get("id") or "Playlist"), tuple(entries))


def discover_playlist(url: str, *, cookies: Path | None = None, scope: str = "auto",
                      cancelled: Callable[[], bool] = lambda: False) -> PlaylistInfo:
    url = canonical_url(url)
    if scope not in ("auto", "parts"):
        raise ValueError("Unknown playlist scope")

    def check():
        if cancelled():
            raise DownloadCancelled()

    with _downloader({"noplaylist": False, "extract_flat": "in_playlist", "skip_download": True}, cookies, check) as ydl:
        result = _bilibili_page(ydl, url, scope, check)
        if result is None:
            result = _extract_list(ydl, url, check)
        check()
        if not result.entries or len(result.entries) > 2000:
            raise ValueError("Danh sách phải có từ 1 đến 2000 mục.")
        return result


def _fingerprint(path: Path, check) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            check()
            digest.update(block)
    return digest.hexdigest()


@contextmanager
def _bilibili_media_backups(ydl, enabled: bool):
    """Keep same-format backup URLs that the installed extractor otherwise discards."""
    backups: dict[str, str] = {}
    if not enabled:
        yield backups
        return
    extractor = ydl.get_info_extractor("BiliBili")
    original = extractor.extract_formats

    def extract_formats(play_info):
        formats = original(play_info)
        pending = [play_info.get("dash") or {}]
        while pending:
            value = pending.pop()
            if isinstance(value, list):
                pending.extend(value)
            elif isinstance(value, dict):
                primary = value.get("baseUrl") or value.get("base_url")
                alternatives = value.get("backupUrl") or value.get("backup_url") or []
                if isinstance(primary, str) and isinstance(alternatives, list):
                    for candidate in alternatives:
                        try:
                            candidate = canonical_url(candidate)
                        except (ValueError, TypeError, AttributeError):
                            continue
                        if candidate != primary and urlsplit(candidate).scheme == urlsplit(primary).scheme:
                            backups[primary] = candidate
                            break
                pending.extend(child for child in value.values() if isinstance(child, (dict, list)))
        return formats

    extractor.extract_formats = extract_formats
    try:
        yield backups
    finally:
        extractor.extract_formats = original


def _media_attempt(info: Mapping[str, Any], backups: dict[str, str] | None = None) -> dict[str, Any]:
    # yt-dlp mutates formats while processing. Keep IDs/names stable across the retry.
    result = dict(info)
    if "formats" in info:
        result["formats"] = [dict(fmt) for fmt in info.get("formats") or []]
    if backups and result.get("formats"):
        for fmt in result["formats"]:
            if fmt.get("url") in backups:
                fmt["url"] = backups[fmt["url"]]
    return result


def _recoverable_media_error(error: Exception) -> bool:
    message = re.search(r"\[download\]\s+Got error:\s+(.+)", str(error), re.DOTALL)
    if not message:
        return False
    text = message[1]
    status = re.search(r"\bHTTP(?:\s+Error)?\s+(\d{3})\b", text, re.IGNORECASE)
    if status:
        return status[1] in ("500", "502", "503", "504")
    # yt-dlp's exhausted retry callback flattens the transport exception into text.
    # Match known connection failures, never certificate or proxy configuration errors.
    if re.search(r"certificate|CERTIFICATE_VERIFY_FAILED|ProxyError", text, re.IGNORECASE):
        return False
    return bool(re.search(
        r"\b\d+ bytes read, \d+ more expected\b|\bRemoteDisconnected\b|"
        r"Remote end closed connection without response|\bConnection(?:Reset|Aborted)Error\b|"
        r"Connection reset by peer|\b(?:ReadTimeout|ConnectTimeout|SSLEOFError)\b|"
        r"\bUNEXPECTED_EOF_WHILE_READING\b|(?:read operation|read|connection) timed out",
        text, re.IGNORECASE))


def _download_entry(entry: PlaylistEntry, folder: Path, cookies, check, progress) -> PlaylistItemResult:
    if entry.unavailable_reason or not entry.url:
        raise ValueError(entry.unavailable_reason or "Không có URL")
    folder.mkdir(parents=True, exist_ok=True)
    receipt = folder / "completed.json"
    if receipt.is_file():
        verified = False
        try:
            saved = json.loads(receipt.read_text(encoding="utf-8"))
            target = folder / saved["filename"]
            if (target.resolve().parent == folder.resolve() and saved["url"] == entry.url
                and target.is_file() and target.stat().st_size == saved["size"]
                and _fingerprint(target, check) == saved["sha256"]):
                verified = True
        except (KeyError, TypeError, ValueError, OSError):
            pass
        if verified:
            require_mp4(target)
            return PlaylistItemResult(entry.index, "existing", str(target.resolve()))
        # Keep a user's modified completed file rather than letting yt-dlp treat it as a cache hit.
        raise ValueError("File/receipt đã thay đổi hoặc thiếu. Chọn thư mục đích mới để tải lại; bản cũ được giữ.")

    def hook(data):
        check()
        total = data.get("total_bytes") or data.get("total_bytes_estimate") or 0
        percent = min(99, int(100 * (data.get("downloaded_bytes") or 0) / total)) if total else 0
        progress(percent)

    paths = []
    def after_move(filename):
        check()
        paths.append(Path(filename))

    options = {"format": mp4_format_selector(bool(shutil.which("ffmpeg"))),
               "outtmpl": str(folder / "%(title).100s [%(id)s].%(ext)s"), "windowsfilenames": True,
               "progress_hooks": [hook], "postprocessor_hooks": [lambda _: check()],
               "post_hooks": [after_move], "merge_output_format": "mp4"}
    bilibili = urlsplit(entry.url).hostname in ("bilibili.com", "www.bilibili.com")
    if bilibili:
        # Bilibili media connections can end early. Bound each Range request and
        # retain yt-dlp's normal finite retry budget instead of the discovery cap.
        options.update(http_chunk_size=1024 * 1024, retries=10)
    with _downloader(options, cookies, check) as ydl:
        with _bilibili_media_backups(ydl, bilibili) as backups:
            info = ydl.extract_info(entry.url, download=False, process=False)
        check()
        if not isinstance(info, dict) or info.get("_type", "video") != "video":
            raise ValueError("Mục này trả danh sách lồng nhau; chưa tải để tránh tải ngoài selection.")
        from yt_dlp.utils import DownloadError

        try:
            result = ydl.process_ie_result(cast(Any, _media_attempt(info)), download=True)
        except DownloadError as exc:
            check()
            # One fallback for interrupted connections, truncated bodies or temporary server errors.
            # Access/certificate/extractor errors retain their original failure.
            if (not _recoverable_media_error(exc)
                    or not any(fmt.get("url") in backups for fmt in info.get("formats") or [])):
                raise
            paths.clear()
            result = ydl.process_ie_result(cast(Any, _media_attempt(info, backups)), download=True)
        check()
        if not paths and isinstance(result, dict):
            paths.append(Path(result.get("filepath") or ydl.prepare_filename(result)))
    if len(paths) != 1:
        raise ValueError("Không xác minh được một file video hoàn chỉnh cho mục này.")
    target = paths[0].resolve()
    require_mp4(target)
    if target.parent != folder.resolve() or not target.is_file() or target.stat().st_size <= 0 or target.suffix.lower() in (".part", ".ytdl"):
        raise ValueError("Tải chưa tạo file video hoàn chỉnh.")
    record = {"url": entry.url, "filename": target.name, "size": target.stat().st_size,
              "sha256": _fingerprint(target, check)}
    temporary = receipt.with_suffix(".tmp")
    temporary.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(receipt)
    return PlaylistItemResult(entry.index, "downloaded", str(target))


def download_playlist(info: PlaylistInfo, selected: tuple[PlaylistEntry, ...], output: Path, *,
                      cookies: Path | None = None, cancelled: Callable[[], bool] = lambda: False,
                      progress: Callable[[PlaylistItemResult, int], None] = lambda *_: None) -> PlaylistResult:
    members = {entry.index: entry for entry in info.entries}
    if not selected or len({entry.index for entry in selected}) != len(selected) or any(members.get(e.index) != e for e in selected):
        raise ValueError("Selection không hợp lệ hoặc danh sách đã đổi.")
    selected = tuple(sorted(selected, key=lambda e: e.index))
    identity = hashlib.sha256(info.source_url.encode()).hexdigest()[:10]
    directory = output / f"{safe_name(info.title)}-{identity}"
    results = [PlaylistItemResult(entry.index) for entry in selected]
    def check():
        if cancelled():
            raise DownloadCancelled()

    for offset, entry in enumerate(selected):
        try:
            check()
            progress(replace(results[offset], status="downloading"), 0)
            key = hashlib.sha256(entry.url.encode()).hexdigest()[:10]
            folder = directory / f"{entry.index:05d}-{safe_name(entry.title)}-{key}"
            results[offset] = _download_entry(entry, folder, cookies, check,
                lambda value: progress(PlaylistItemResult(entry.index, "downloading"), value))
            progress(results[offset], 100)
        except DownloadCancelled:
            results[offset] = PlaylistItemResult(entry.index, "cancelled")
            return PlaylistResult(tuple(results), cancelled=True)
        except Exception as exc:
            if cancelled():
                results[offset] = PlaylistItemResult(entry.index, "cancelled")
                return PlaylistResult(tuple(results), cancelled=True)
            results[offset] = PlaylistItemResult(entry.index, "failed", error=friendly_error(exc))
            progress(results[offset], 0)
    return PlaylistResult(tuple(results))

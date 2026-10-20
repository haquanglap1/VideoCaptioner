import os
import re
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING, Any, Mapping, cast

import requests
from PyQt5.QtCore import QThread, pyqtSignal

from videocaptioner.config import APPDATA_PATH
from videocaptioner.core.utils.logger import setup_logger

if TYPE_CHECKING:
    from videocaptioner.core.translate.video_title import VideoTitleConfig

logger = setup_logger("video_download_thread")

ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def _strip_ansi(value: str) -> str:
    return ANSI_ESCAPE_RE.sub("", value).strip()


_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}


def _legacy_folder(title: str) -> str:
    """Folder the downloader used before 2026-10-20 (whole title, applied twice), to adopt those files."""
    name = title
    for _ in range(2):
        name = re.sub(r'[<>:"/\\|?*]', "_", name)
        name = re.sub(r"[\0-\31]", "", name).rstrip(" .")
        if len(name) > 255:
            base, ext = os.path.splitext(name)
            name = base[:255 - len(ext)] + ext
        if os.path.splitext(name)[0].upper() in _RESERVED:
            name = f"{name}_"
        name = name or "default_filename"
    return name


def _format_bytes(num_bytes: float) -> str:
    if num_bytes is None:
        return "?"
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if num_bytes < 1024.0:
            return f"{num_bytes:.1f}{unit}"
        num_bytes /= 1024.0
    return f"{num_bytes:.1f}PiB"


class VideoDownloadThread(QThread):
    """Worker thread that downloads a video with yt-dlp."""

    finished = pyqtSignal(
        str
    )  # Emitted on completion: (video path, subtitle path, thumbnail path, video info)
    progress = pyqtSignal(int, str)  # Download progress
    error = pyqtSignal(str)  # Error message

    def __init__(self, url: str, work_dir: str, naming: "VideoTitleConfig | None" = None):
        super().__init__()
        self.url = url
        self.work_dir = work_dir
        # LLM snapshot taken on the Qt thread; None keeps the clipped page title.
        self.naming = naming

    def run(self):
        from yt_dlp.utils import DownloadError

        try:
            video_file_path, _subtitle_path, _thumbnail_path, _info = self.download()
            self.finished.emit(video_file_path or "")
        except DownloadError as e:
            logger.exception("下载视频失败 (DownloadError): %s", str(e))
            self.error.emit(self._friendly_error(str(e)))
        except Exception as e:
            logger.exception("下载视频失败: %s", str(e))
            self.error.emit(str(e))

    @staticmethod
    def _friendly_error(message: str) -> str:
        """Map yt-dlp errors to actionable hints (Vietnamese)."""
        lowered = message.lower()
        if "sign in to confirm" in lowered or "confirm you" in lowered or "bot" in lowered:
            return (
                "YouTube yêu cầu xác thực (chống bot). Hãy cập nhật yt-dlp lên bản mới nhất "
                "và đặt cookies.txt vào AppData, hoặc đăng nhập trên trình duyệt."
            )
        if "ffmpeg" in lowered:
            return (
                "Không tìm thấy ffmpeg để hợp nhất video/audio. Hãy cài ffmpeg và thêm vào PATH."
            )
        if "http error 403" in lowered or "forbidden" in lowered:
            return (
                "Bị YouTube từ chối (HTTP 403). Hãy cập nhật yt-dlp và thử lại sau, hoặc dùng cookies.txt."
            )
        if "unable to extract" in lowered or "no video formats" in lowered:
            return (
                "Không tách được luồng video. yt-dlp có thể đã lỗi thời với YouTube; "
                "chạy 'pip install -U yt-dlp' để cập nhật."
            )
        return message

    def progress_hook(self, d):
        """yt-dlp progress hook, robust against missing/N-A fields and ANSI noise."""
        try:
            status = d.get("status")
            if status != "downloading":
                return

            # Prefer numeric fields (stable across yt-dlp versions). Fall back to strings.
            downloaded = d.get("downloaded_bytes") or 0
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0

            percent_value = None
            if total:
                percent_value = max(0.0, min(100.0, downloaded * 100.0 / total))
            else:
                raw_percent = _strip_ansi(d.get("_percent_str", "")).rstrip("%").strip()
                if raw_percent and raw_percent.upper() not in ("N/A", "---"):
                    try:
                        percent_value = float(raw_percent)
                    except ValueError:
                        percent_value = None

            speed_value = d.get("speed")
            if speed_value:
                speed_text = f"{_format_bytes(speed_value)}/s"
            else:
                speed_text = _strip_ansi(d.get("_speed_str", "")) or "—"

            progress_label = self.tr("下载进度")
            speed_label = self.tr("速度")
            if percent_value is None:
                self.progress.emit(
                    0,
                    f"{progress_label}: {_format_bytes(downloaded)}  {speed_label}: {speed_text}",
                )
            else:
                self.progress.emit(
                    int(percent_value),
                    f"{progress_label}: {percent_value:.1f}%  {speed_label}: {speed_text}",
                )
        except Exception as exc:
            # Never let progress hook abort the download.
            logger.warning("progress_hook error: %s", exc)

    def _download_stem(self, info_dict: Mapping[str, object]) -> tuple[str, str, str]:
        """Short target-language stem (LLM) chosen before any file exists, its LLM title, and the
        clipped page-title stem an unnamed earlier download would have."""
        from videocaptioner.core.translate.video_title import (
            DOWNLOAD_TITLE_MAX,
            download_id_tag,
            download_name,
        )

        tag = download_id_tag(info_dict.get("id"), self.url)
        # Transcripts nest work_dir/<stem>/subtitle/【原始字幕】<stem>-<model>-<lang>.srt.
        room = 240 - len(os.path.abspath(self.work_dir)) - 2 * len(tag) - 60
        limit = max(16, min(DOWNLOAD_TITLE_MAX, room // 2))
        title = str(info_dict.get("title") or "")
        fallback = download_name(title, None, limit=limit)[0] + tag
        if self.naming is None:
            return fallback, "", fallback
        self.progress.emit(0, "Đang rút gọn tên video bằng LLM...")
        name, named = download_name(title, self.naming, self.isInterruptionRequested, limit)
        if not named:
            self.progress.emit(0, "Không rút gọn được tên bằng LLM; dùng tiêu đề gốc đã cắt ngắn.")
        return name + tag, name if named else "", fallback

    def _adopt_earlier_download(self, ydl, info_dict, fallback: str) -> None:
        """Rename a finished earlier download of this URL to today's name instead of fetching it again."""
        from videocaptioner.core.translate.series_context import (
            context_from_info,
            load_video_context,
            sidecar_path,
        )

        target = Path(ydl.prepare_filename(info_dict))
        if target.exists():
            return
        work_dir = Path(self.work_dir)
        title = str(info_dict.get("title") or "MyVideo")
        # The old layout put the whole title in both the folder and the file.
        legacy = work_dir / _legacy_folder(title) / os.path.basename(
            ydl.prepare_filename(info_dict, outtmpl="%(title).200s.%(ext)s"))
        unnamed = work_dir / fallback / (fallback + target.suffix)
        url = context_from_info(info_dict, self.url).url
        for earlier in (legacy, unnamed):
            if earlier == target or not earlier.is_file():
                continue
            context = load_video_context(earlier)
            if context is not None and context.url != url:
                continue
            # Pre-sidecar downloads are trusted by path, as yt-dlp's own skip did.
            if context is None and earlier != legacy:
                continue
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                earlier.rename(target)
            except OSError as exc:  # e.g. open in a player: download a fresh copy instead
                logger.warning("Could not rename the earlier download (%s); downloading again", exc)
                return
            sidecar_path(earlier).unlink(missing_ok=True)
            try:
                earlier.parent.rmdir()  # only when nothing else was left there
            except OSError:
                pass
            logger.info("Renamed earlier download to %s", target.name)
            self.progress.emit(0, "Video đã tải trước đó: đổi tên, không tải lại.")
            return

    def download(self, need_subtitle: bool = True, need_thumbnail: bool = False):
        """Download the video, subtitles and thumbnail."""
        import yt_dlp

        logger.info("开始下载视频: %s", self.url)

        # Ensure the Deno JS runtime is available so yt-dlp can solve YouTube's
        # signature/n challenges (otherwise HD formats are skipped). Auto-download
        # it on first use; a failure here is non-fatal — the download still proceeds
        # (degraded to whatever pre-signed formats remain).
        try:
            from videocaptioner.core.utils.installer import deno_path, ensure_deno

            if deno_path() is None:
                ensure_deno(progress_cb=lambda p, m: self.progress.emit(p, m))
        except Exception as exc:  # noqa: BLE001 — never block the download on this
            logger.warning("Deno auto-install skipped: %s", exc)

        # If ffmpeg is unavailable, fall back to a single-file format that doesn't need merging.
        # YouTube exposes pre-merged streams up to 720p; better than nothing.
        from shutil import which
        has_ffmpeg = bool(which("ffmpeg"))
        from videocaptioner.core.utils.download_format import mp4_format_selector, require_mp4

        format_selector = mp4_format_selector(has_ffmpeg)
        if not has_ffmpeg:
            logger.warning("FFmpeg unavailable; selecting a single MP4 stream.")

        # Base yt-dlp options
        initial_ydl_opts = {
            "outtmpl": {
                # Replaced by the short stem once the page title is known.
                "default": "%(title).60s.%(ext)s",
                "subtitle": "【下载字幕】.%(ext)s",
                "thumbnail": "thumbnail",
            },
            "format": format_selector,
            "merge_output_format": "mp4",
            "progress_hooks": [self.progress_hook],  # Progress hook
            "quiet": True,  # Silence logging
            "no_warnings": True,  # Silence warnings
            "noprogress": True,
            # The task pipeline accepts one media path, not an anthology/playlist result.
            "noplaylist": True,
            "writesubtitles": need_subtitle,  # Uploaded subtitles (preferred)
            "writeautomaticsub": need_subtitle,  # Auto-generated subtitles (fallback)
            "writethumbnail": need_thumbnail,  # Thumbnail
            "thumbnail_format": "jpg",  # Thumbnail format
            # Modern UA helps avoid some YouTube anti-bot rejections.
            "http_headers": {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0 Safari/537.36"
                )
            },
            "retries": 5,
            "fragment_retries": 5,
            # Auto-download the EJS challenge solver script so the Deno JS runtime can
            # solve YouTube signature / n-sig challenges. Without it, almost every
            # adaptive format is skipped and downloads collapse to a single 360p stream
            # (or "Requested format is not available" when 360p isn't offered).
            "remote_components": ["ejs:github"],
        }

        # Note: do NOT pin extractor_args.youtube.player_client. A hard pin
        # (android/web/ios/tv) hides formats that those clients can't serve without
        # PO tokens; yt-dlp's default client selection resolves full HD formats.

        # Cookies file
        cookiefile_path = APPDATA_PATH / "cookies.txt"
        if cookiefile_path.exists():
            logger.info(f"使用cookiefile: {cookiefile_path}")
            initial_ydl_opts["cookiefile"] = str(cookiefile_path)

        # typeshed types the params as a private TypedDict; the dict is built
        # dynamically above, so hand it over untyped.
        with yt_dlp.YoutubeDL(cast(Any, initial_ydl_opts)) as ydl:
            # Extract video info without downloading
            info_dict = ydl.extract_info(self.url, download=False)

            # The folder matches the file stem so the transcript stage reuses it.
            stem, file_title, fallback = self._download_stem(info_dict)
            video_work_dir = Path(self.work_dir) / stem
            subtitle_language = info_dict.get("language", None)
            if subtitle_language:
                subtitle_language = subtitle_language.lower().split("-")[0]

            try:
                subtitle_download_link = None
                # Prefer uploaded (manual/community) subtitles
                manual_subtitles = info_dict.get("subtitles")
                if manual_subtitles and subtitle_language:
                    for lang_code in manual_subtitles:
                        if lang_code.startswith(subtitle_language):
                            subtitle_download_link = manual_subtitles[lang_code][-1][
                                "url"
                            ]
                            logger.info("找到人工上传字幕 (lang=%s)", lang_code)
                            break
                # Fall back to auto-generated subtitles
                if not subtitle_download_link:
                    automatic_captions = info_dict.get("automatic_captions")
                    if automatic_captions and subtitle_language:
                        for lang_code in automatic_captions:
                            if lang_code.startswith(subtitle_language):
                                subtitle_download_link = automatic_captions[lang_code][-1][
                                    "url"
                                ]
                                logger.info("使用自动生成字幕 (lang=%s)", lang_code)
                                break
            except Exception:
                subtitle_download_link = None

            # yt-dlp download options
            ydl_opts = {
                "paths": {
                    "home": str(video_work_dir),
                    "subtitle": str(video_work_dir / "subtitle"),
                    "thumbnail": str(video_work_dir),
                },
            }
            # Apply the yt-dlp options
            ydl.params.update(cast(Any, ydl_opts))
            # The stem is already free of %/$, which templates and paths would expand.
            cast(Any, ydl.params)["outtmpl"]["default"] = stem + ".%(ext)s"
            self._adopt_earlier_download(ydl, info_dict, fallback)

            # Use the public extractor pipeline so format selection, post-processing,
            # and subtitle writing all run as expected.
            try:
                processed_info = ydl.process_ie_result(info_dict, download=True)
                if isinstance(processed_info, dict):
                    info_dict = processed_info
            except AttributeError:
                # Older yt-dlp builds: fall back to internal API.
                ydl.process_info(info_dict)

            # Video file path
            video_file_path = Path(ydl.prepare_filename(info_dict))
            require_mp4(video_file_path)
            if video_file_path.exists():
                try:
                    from videocaptioner.core.translate.series_context import (
                        context_from_info,
                        save_video_context,
                    )

                    context = context_from_info(info_dict, self.url)
                    save_video_context(video_file_path, replace(context, file_title=file_title))
                except Exception as exc:  # noqa: BLE001 - background for translation is optional
                    logger.warning("Video context sidecar skipped: %s", exc)
                video_file_path = str(video_file_path)
            else:
                video_file_path = None

            # Subtitle file path
            subtitle_file_path = None
            for file in video_work_dir.glob("**/【下载字幕】*"):
                file_path = str(file)
                if subtitle_language and subtitle_language not in file_path:
                    logger.info(
                        "字幕语言错误，重新下载字幕: %s", subtitle_download_link
                    )
                    os.remove(file_path)
                    if subtitle_download_link:
                        response = requests.get(subtitle_download_link, timeout=30)
                        file_path = (
                            video_work_dir
                            / "subtitle"
                            / f"【下载字幕】{subtitle_language}.vtt"
                        )
                        if res := response.text:
                            with open(file_path, "w", encoding="utf-8") as f:
                                f.write(res)
                            subtitle_file_path = file_path
                else:
                    subtitle_file_path = file_path
                break

            # Thumbnail file path
            thumbnail_file_path = None
            for file in video_work_dir.glob("**/thumbnail*"):
                thumbnail_file_path = str(file)
                break

            logger.info(f"视频下载完成: {video_file_path}")
            logger.info(f"字幕文件路径: {subtitle_file_path}")
            return video_file_path, subtitle_file_path, thumbnail_file_path, info_dict

import os
import re
from pathlib import Path

import requests
from PyQt5.QtCore import QThread, pyqtSignal

from videocaptioner.config import APPDATA_PATH
from videocaptioner.core.utils.logger import setup_logger

logger = setup_logger("video_download_thread")

ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def _strip_ansi(value: str) -> str:
    return ANSI_ESCAPE_RE.sub("", value).strip()


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

    def __init__(self, url: str, work_dir: str):
        super().__init__()
        self.url = url
        self.work_dir = work_dir

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

    def sanitize_filename(self, name: str, replacement: str = "_") -> str:
        """Strip characters that are not allowed in file names."""
        # Disallowed characters
        forbidden_chars = r'<>:"/\\|?*'

        # Replace disallowed characters
        sanitized = re.sub(f"[{re.escape(forbidden_chars)}]", replacement, name)

        # Remove control characters
        sanitized = re.sub(r"[\0-\31]", "", sanitized)

        # Trim trailing spaces and dots
        sanitized = sanitized.rstrip(" .")

        # Limit the file name length
        max_length = 255
        if len(sanitized) > max_length:
            base, ext = os.path.splitext(sanitized)
            base_max_length = max_length - len(ext)
            sanitized = base[:base_max_length] + ext

        # Handle Windows reserved names
        windows_reserved_names = {
            "CON",
            "PRN",
            "AUX",
            "NUL",
            "COM1",
            "COM2",
            "COM3",
            "COM4",
            "COM5",
            "COM6",
            "COM7",
            "COM8",
            "COM9",
            "LPT1",
            "LPT2",
            "LPT3",
            "LPT4",
            "LPT5",
            "LPT6",
            "LPT7",
            "LPT8",
            "LPT9",
        }
        name_without_ext = os.path.splitext(sanitized)[0].upper()
        if name_without_ext in windows_reserved_names:
            sanitized = f"{sanitized}_"

        # Fall back to a default name when empty
        if not sanitized:
            sanitized = "default_filename"

        return sanitized

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
        if has_ffmpeg:
            # Broad chain: prefer mp4+m4a for compatibility, but fall through to ANY best
            # video+audio combo, then any single best/worst — so logged-in/Premium accounts
            # whose top formats are AV1/Opus/WebM still resolve to a downloadable stream.
            format_selector = (
                "bestvideo[ext=mp4]+bestaudio[ext=m4a]/"
                "bestvideo*+bestaudio/"
                "best[ext=mp4]/"
                "best/"
                "worst"
            )
        else:
            format_selector = "best[ext=mp4]/best/worst"
            logger.warning("ffmpeg 未找到，使用单文件下载（最高 720p）。")

        # Base yt-dlp options
        initial_ydl_opts = {
            "outtmpl": {
                "default": "%(title).200s.%(ext)s",  # Cap the file name at 200 characters
                "subtitle": "【下载字幕】.%(ext)s",
                "thumbnail": "thumbnail",
            },
            "format": format_selector,
            "progress_hooks": [self.progress_hook],  # Progress hook
            "quiet": True,  # Silence logging
            "no_warnings": True,  # Silence warnings
            "noprogress": True,
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

        with yt_dlp.YoutubeDL(initial_ydl_opts) as ydl:
            # Extract video info without downloading
            info_dict = ydl.extract_info(self.url, download=False)

            # Download folder named after the video title
            video_title = self.sanitize_filename(info_dict.get("title") or "MyVideo")
            video_work_dir = Path(self.work_dir) / self.sanitize_filename(video_title)
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
            ydl.params.update(ydl_opts)

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
            if video_file_path.exists():
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

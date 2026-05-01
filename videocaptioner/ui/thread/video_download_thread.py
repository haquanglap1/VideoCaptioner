import os
import re
from pathlib import Path

import requests
import yt_dlp
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
    """视频下载线程类"""

    finished = pyqtSignal(
        str
    )  # 发送下载完成的信号(视频路径, 字幕路径, 缩略图路径, 视频信息)
    progress = pyqtSignal(int, str)  # 发送下载进度的信号
    error = pyqtSignal(str)  # 发送错误信息的信号

    def __init__(self, url: str, work_dir: str):
        super().__init__()
        self.url = url
        self.work_dir = work_dir

    def run(self):
        try:
            video_file_path, subtitle_file_path, thumbnail_file_path, info_dict = (
                self.download()
            )
            self.finished.emit(video_file_path or "")
        except yt_dlp.utils.DownloadError as e:
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
        """下载进度回调函数 — robust against missing/N-A fields and ANSI noise."""
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
        """清理文件名中不允许的字符"""
        # 定义不允许的字符
        forbidden_chars = r'<>:"/\\|?*'

        # 替换不允许的字符
        sanitized = re.sub(f"[{re.escape(forbidden_chars)}]", replacement, name)

        # 移除控制字符
        sanitized = re.sub(r"[\0-\31]", "", sanitized)

        # 去除文件名末尾的空格和点
        sanitized = sanitized.rstrip(" .")

        # 限制文件名长度
        max_length = 255
        if len(sanitized) > max_length:
            base, ext = os.path.splitext(sanitized)
            base_max_length = max_length - len(ext)
            sanitized = base[:base_max_length] + ext

        # 处理Windows保留名称
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

        # 如果文件名为空，返回默认名称
        if not sanitized:
            sanitized = "default_filename"

        return sanitized

    def download(self, need_subtitle: bool = True, need_thumbnail: bool = False):
        """下载视频"""
        logger.info("开始下载视频: %s", self.url)

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

        # 初始化 ydl 选项
        initial_ydl_opts = {
            "outtmpl": {
                "default": "%(title).200s.%(ext)s",  # 限制文件名最长200个字符
                "subtitle": "【下载字幕】.%(ext)s",
                "thumbnail": "thumbnail",
            },
            "format": format_selector,
            "progress_hooks": [self.progress_hook],  # 下载进度钩子
            "quiet": True,  # 禁用日志输出
            "no_warnings": True,  # 禁用警告信息
            "noprogress": True,
            "writesubtitles": need_subtitle,  # 下载人工上传的字幕（优先）
            "writeautomaticsub": need_subtitle,  # 下载自动生成的字幕（备选）
            "writethumbnail": need_thumbnail,  # 下载缩略图
            "thumbnail_format": "jpg",  # 指定缩略图的格式
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
        }

        initial_ydl_opts["extractor_args"] = {
            "youtube": {"player_client": ["android", "web", "ios", "tv"]}
        }

        # 检查 cookies 文件
        cookiefile_path = APPDATA_PATH / "cookies.txt"
        if cookiefile_path.exists():
            logger.info(f"使用cookiefile: {cookiefile_path}")
            initial_ydl_opts["cookiefile"] = str(cookiefile_path)

        with yt_dlp.YoutubeDL(initial_ydl_opts) as ydl:
            # 提取视频信息（不下载）
            info_dict = ydl.extract_info(self.url, download=False)

            # 设置动态下载文件夹为视频标题
            video_title = self.sanitize_filename(info_dict.get("title", "MyVideo"))
            video_work_dir = Path(self.work_dir) / self.sanitize_filename(video_title)
            subtitle_language = info_dict.get("language", None)
            if subtitle_language:
                subtitle_language = subtitle_language.lower().split("-")[0]

            try:
                subtitle_download_link = None
                # 优先使用人工上传的字幕（manual/community subtitles）
                manual_subtitles = info_dict.get("subtitles")
                if manual_subtitles and subtitle_language:
                    for lang_code in manual_subtitles:
                        if lang_code.startswith(subtitle_language):
                            subtitle_download_link = manual_subtitles[lang_code][-1][
                                "url"
                            ]
                            logger.info("找到人工上传字幕 (lang=%s)", lang_code)
                            break
                # 如果没有人工字幕，退回自动生成的字幕
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

            # 设置 yt-dlp 下载选项
            ydl_opts = {
                "paths": {
                    "home": str(video_work_dir),
                    "subtitle": str(video_work_dir / "subtitle"),
                    "thumbnail": str(video_work_dir),
                },
            }
            # 更新 yt-dlp 的配置
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

            # 获取视频文件路径
            video_file_path = Path(ydl.prepare_filename(info_dict))
            if video_file_path.exists():
                video_file_path = str(video_file_path)
            else:
                video_file_path = None

            # 获取字幕文件路径
            subtitle_file_path = None
            for file in video_work_dir.glob("**/【下载字幕】*"):
                file_path = str(file)
                if subtitle_language and subtitle_language not in file_path:
                    logger.info(
                        "字幕语言错误，重新下载字幕: %s", subtitle_download_link
                    )
                    os.remove(file_path)
                    if subtitle_download_link:
                        response = requests.get(subtitle_download_link)
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

            # 获取缩略图文件路径
            thumbnail_file_path = None
            for file in video_work_dir.glob("**/thumbnail*"):
                thumbnail_file_path = str(file)
                break

            logger.info(f"视频下载完成: {video_file_path}")
            logger.info(f"字幕文件路径: {subtitle_file_path}")
            return video_file_path, subtitle_file_path, thumbnail_file_path, info_dict

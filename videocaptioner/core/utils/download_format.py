"""One MP4 selection policy for single-video and playlist downloads."""

from pathlib import Path


def mp4_format_selector(has_ffmpeg: bool) -> str:
    # Force the merge container separately: yt-dlp can misclassify HEVC codec
    # tags such as hev1 and select MKV even when both source streams are MP4.
    return "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]" if has_ffmpeg else "best[ext=mp4]"


def require_mp4(path: str | Path) -> None:
    if Path(path).suffix.lower() != ".mp4":
        raise ValueError("Chỉ nhận video tải xuống MP4. File cũ được giữ nguyên; chọn thư mục mới để tải MP4.")

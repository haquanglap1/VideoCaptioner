"""Auto-update thread — tải exe mới trên background."""

import os
import tempfile
from pathlib import Path

import requests
from PyQt5.QtCore import QThread, pyqtSignal

from videocaptioner.core.utils.logger import setup_logger

logger = setup_logger("auto_update")


class AutoUpdateThread(QThread):
    """Tải file exe mới từ download_url."""

    progress = pyqtSignal(int, str)  # (percent, message)
    download_complete = pyqtSignal(str)  # temp_exe_path
    error = pyqtSignal(str)

    def __init__(self, download_url: str, parent=None):
        super().__init__(parent)
        self.download_url = download_url
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        try:
            self.progress.emit(0, self.tr("Đang kết nối..."))

            # Resolve GitHub releases page → direct .exe link if needed
            url = self._resolve_download_url(self.download_url)
            if not url:
                self.error.emit(
                    self.tr("Không tìm được link tải trực tiếp. Vui lòng tải thủ công.")
                )
                return

            logger.info("Downloading update from: %s", url)

            # Stream download
            response = requests.get(url, stream=True, timeout=30, allow_redirects=True)
            response.raise_for_status()

            total_size = int(response.headers.get("content-length", 0))
            total_mb = total_size / (1024 * 1024) if total_size else 0

            # Save to temp file
            temp_dir = Path(tempfile.mkdtemp(prefix="vc_update_"))
            temp_path = str(temp_dir / "VideoCaptioner_update.exe")

            downloaded = 0
            chunk_size = 1024 * 1024  # 1MB chunks

            with open(temp_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=chunk_size):
                    if self._cancelled:
                        logger.info("Download cancelled by user")
                        self.error.emit(self.tr("Đã huỷ tải"))
                        return

                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)

                        if total_size > 0:
                            pct = int(downloaded * 100 / total_size)
                            dl_mb = downloaded / (1024 * 1024)
                            msg = f"Đang tải... {dl_mb:.1f} MB / {total_mb:.1f} MB"
                        else:
                            pct = min(95, downloaded // (1024 * 1024))
                            dl_mb = downloaded / (1024 * 1024)
                            msg = f"Đang tải... {dl_mb:.1f} MB"

                        self.progress.emit(pct, msg)

            # Verify file exists and has content
            if not Path(temp_path).is_file() or Path(temp_path).stat().st_size < 1024 * 1024:
                self.error.emit(self.tr("File tải về không hợp lệ"))
                return

            self.progress.emit(100, self.tr("Tải xong!"))
            logger.info("Download complete: %s (%d bytes)", temp_path, downloaded)
            self.download_complete.emit(temp_path)

        except requests.ConnectionError:
            self.error.emit(self.tr("Lỗi kết nối. Kiểm tra kết nối mạng."))
        except requests.Timeout:
            self.error.emit(self.tr("Hết thời gian chờ kết nối."))
        except requests.HTTPError as e:
            self.error.emit(f"HTTP Error: {e.response.status_code}")
        except Exception as e:
            logger.exception("Auto-update download failed")
            self.error.emit(str(e))

    def _resolve_download_url(self, url: str) -> str:
        """Resolve download URL to a direct .exe link.

        If the URL is already a direct link (ends with .exe), return as-is.
        If it's a GitHub releases page, try to find the .exe asset via API.
        """
        if not url:
            return ""

        # Already a direct link
        if url.lower().endswith(".exe"):
            return url

        # Try GitHub API: /repos/{owner}/{repo}/releases/latest
        # URL pattern: https://github.com/{owner}/{repo}/releases/latest
        if "github.com" in url and "/releases" in url:
            try:
                parts = url.replace("https://github.com/", "").split("/")
                if len(parts) >= 2:
                    owner, repo = parts[0], parts[1]
                    api_url = f"https://api.github.com/repos/{owner}/{repo}/releases/latest"
                    resp = requests.get(api_url, timeout=10)
                    resp.raise_for_status()
                    data = resp.json()

                    # Find .exe asset
                    for asset in data.get("assets", []):
                        name = asset.get("name", "")
                        if name.lower().endswith(".exe"):
                            direct_url = asset.get("browser_download_url", "")
                            if direct_url:
                                logger.info("Resolved GitHub exe: %s", direct_url)
                                return direct_url
            except Exception as e:
                logger.warning("Failed to resolve GitHub URL: %s", e)

        # Fallback: return original URL (might work for direct links)
        return url

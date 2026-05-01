# coding: utf-8
import hashlib
from datetime import datetime

import requests
from PyQt5.QtCore import QObject, QVersionNumber, pyqtSignal

from videocaptioner.config import VERSION
from videocaptioner.core.utils.cache import get_version_state_cache
from videocaptioner.core.utils.logger import setup_logger

logger = setup_logger("version_checker")


class VersionChecker(QObject):
    """Version checker"""

    newVersionAvailable = pyqtSignal(str, bool, str, str)
    announcementAvailable = pyqtSignal(str)
    checkCompleted = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.current_version = VERSION
        self.latest_version = VERSION
        self.update_info = ""
        self.update_required = False
        self.download_url = ""
        self.announcement = {}

        self.cache = get_version_state_cache()

    def get_latest_version_info(self) -> dict:
        """Get latest version information"""
        from videocaptioner.config import GITHUB_OWNER, GITHUB_REPO
        url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "VideoCaptioner-Updater"
        }

        try:
            response = requests.get(url, timeout=10, headers=headers)
            response.raise_for_status()
            data = response.json()
            
            # Parse GitHub release format
            self.latest_version = data.get("tag_name", self.current_version)
            
            # Consider any new release as required if version is newer
            self.update_required = False
            
            self.update_info = data.get("body", "")
            
            # Find the first .exe asset for download url
            self.download_url = data.get("html_url", "")
            for asset in data.get("assets", []):
                if asset.get("name", "").lower().endswith(".exe"):
                    self.download_url = asset.get("browser_download_url", "")
                    break
                    
            self.announcement = {}

            logger.info("Successfully fetched version info from GitHub: %s", self.latest_version)
            return data

        except requests.RequestException as e:
            logger.warning("Failed to fetch GitHub version: %s", e)
            return {}

    def has_new_version(self) -> bool:
        """Check if new version is available"""
        try:
            latest_ver = self.latest_version.lstrip("v")
            current_ver = self.current_version.lstrip("v")

            latest_ver_num = QVersionNumber.fromString(latest_ver)
            current_ver_num = QVersionNumber.fromString(current_ver)

            if latest_ver_num > current_ver_num:
                logger.info(
                    "New version found: %s (current: %s)",
                    self.latest_version,
                    self.current_version,
                )
                self.newVersionAvailable.emit(
                    self.latest_version,
                    self.update_required,
                    self.update_info,
                    self.download_url,
                )
                return True

        except Exception as e:
            logger.error("Version comparison failed: %s", str(e))

        return False

    def perform_check(self) -> None:
        """Perform version check."""
        try:
            version_data = self.get_latest_version_info()
            if not version_data:
                return
            self.has_new_version()
            self.checkCompleted.emit()
        except Exception:
            logger.exception("Version check failed")

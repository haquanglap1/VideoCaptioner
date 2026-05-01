"""Update dialog — hiển thị thông tin phiên bản mới và tiến trình tải."""

import os
import subprocess
import sys
from pathlib import Path

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtWidgets import QVBoxLayout
from qfluentwidgets import (
    BodyLabel,
    InfoBar,
    InfoBarPosition,
    MessageBoxBase,
    ProgressBar,
    PrimaryPushButton,
    PushButton,
    StrongBodyLabel,
    SubtitleLabel,
    TextEdit,
)

from videocaptioner.core.utils.logger import setup_logger
from videocaptioner.ui.thread.auto_update_thread import AutoUpdateThread

logger = setup_logger("update_dialog")


class UpdateDialog(MessageBoxBase):
    """Dialog cập nhật phiên bản mới.

    Hiển thị thông tin cập nhật, progress bar tải, và nút cập nhật/huỷ.
    """

    def __init__(
        self,
        version: str,
        update_info: str,
        download_url: str,
        parent=None,
    ):
        super().__init__(parent)
        self.version = version
        self.update_info = update_info
        self.download_url = download_url
        self._thread = None
        self._temp_exe_path = None

        self._setup_ui()

    def _setup_ui(self):
        # Title
        self.title_label = SubtitleLabel(
            self.tr("🔄 Phiên bản mới ") + self.version
        )
        self.viewLayout.addWidget(self.title_label)

        # Update info
        if self.update_info:
            info_label = BodyLabel(self.tr("Nội dung cập nhật:"))
            self.viewLayout.addWidget(info_label)

            self.info_text = TextEdit()
            self.info_text.setReadOnly(True)
            self.info_text.setPlainText(self.update_info)
            self.info_text.setMaximumHeight(150)
            self.viewLayout.addWidget(self.info_text)

        # Progress bar (hidden initially)
        self.progress_bar = ProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)
        self.viewLayout.addWidget(self.progress_bar)

        # Status label (hidden initially)
        self.status_label = BodyLabel("")
        self.status_label.setVisible(False)
        self.viewLayout.addWidget(self.status_label)

        # Buttons
        self.yesButton.setText(self.tr("Cập nhật ngay"))
        self.cancelButton.setText(self.tr("Để sau"))

        # Min width
        self.widget.setMinimumWidth(400)

    def __onYesButtonClicked(self):
        """Override: bắt đầu tải thay vì đóng dialog."""
        self._start_download()

    def _start_download(self):
        """Bắt đầu tải exe mới."""
        self.yesButton.setEnabled(False)
        self.yesButton.setText(self.tr("Đang tải..."))
        self.cancelButton.setText(self.tr("Huỷ tải"))
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.status_label.setVisible(True)
        self.status_label.setText(self.tr("Đang kết nối..."))

        self._thread = AutoUpdateThread(self.download_url, self)
        self._thread.progress.connect(self._on_progress)
        self._thread.download_complete.connect(self._on_download_complete)
        self._thread.error.connect(self._on_error)
        self._thread.start()

    def _on_progress(self, pct: int, message: str):
        self.progress_bar.setValue(pct)
        self.status_label.setText(message)

    def _on_download_complete(self, temp_path: str):
        self._temp_exe_path = temp_path
        self.status_label.setText(self.tr("Tải xong! Đang cài đặt..."))
        self.progress_bar.setValue(100)

        # Apply update
        self._apply_update(temp_path)

    def _on_error(self, error_msg: str):
        self.yesButton.setEnabled(True)
        self.yesButton.setText(self.tr("Thử lại"))
        self.cancelButton.setText(self.tr("Đóng"))
        self.status_label.setText(self.tr("Lỗi: ") + error_msg)
        self.progress_bar.setVisible(False)

        logger.error("Auto-update failed: %s", error_msg)

    def _apply_update(self, temp_exe_path: str):
        """Tạo batch script thay thế exe và restart app."""
        try:
            # Determine current exe path
            if getattr(sys, "frozen", False):
                current_exe = sys.executable
            else:
                # Running from source — can't replace
                self.status_label.setText(
                    self.tr("Đang chạy từ source code. Vui lòng thay thế exe thủ công: ")
                    + temp_exe_path
                )
                self.yesButton.setEnabled(False)
                self.cancelButton.setText(self.tr("Đóng"))
                return

            current_exe_path = Path(current_exe)

            # Create batch script for Windows
            if os.name == "nt":
                batch_content = (
                    '@echo off\r\n'
                    'echo Dang cap nhat VideoCaptioner...\r\n'
                    'timeout /t 2 /nobreak >nul\r\n'
                    f'copy /Y "{temp_exe_path}" "{current_exe}"\r\n'
                    'if errorlevel 1 (\r\n'
                    '    echo Loi cap nhat! Vui long cap nhat thu cong.\r\n'
                    '    pause\r\n'
                    '    exit /b 1\r\n'
                    ')\r\n'
                    f'del "{temp_exe_path}"\r\n'
                    f'start "" "{current_exe}"\r\n'
                    'del "%~f0"\r\n'
                )

                batch_path = Path(temp_exe_path).parent / "vc_update.bat"
                batch_path.write_text(batch_content, encoding="utf-8")

                logger.info("Running update batch: %s", batch_path)
                subprocess.Popen(
                    [str(batch_path)],
                    shell=True,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
            else:
                # Unix: shell script
                script_content = (
                    '#!/bin/bash\n'
                    'sleep 2\n'
                    f'cp -f "{temp_exe_path}" "{current_exe}"\n'
                    f'chmod +x "{current_exe}"\n'
                    f'rm -f "{temp_exe_path}"\n'
                    f'"{current_exe}" &\n'
                    'rm -f "$0"\n'
                )

                script_path = Path(temp_exe_path).parent / "vc_update.sh"
                script_path.write_text(script_content)
                os.chmod(str(script_path), 0o755)

                logger.info("Running update script: %s", script_path)
                subprocess.Popen([str(script_path)])

            # Quit the app
            from PyQt5.QtWidgets import QApplication
            QApplication.quit()

        except Exception as e:
            logger.exception("Failed to apply update")
            self.status_label.setText(
                self.tr("Lỗi cài đặt: ") + str(e)
                + self.tr("\nFile mới tại: ") + temp_exe_path
            )
            self.yesButton.setEnabled(False)
            self.cancelButton.setText(self.tr("Đóng"))

    def reject(self):
        """Handle cancel/close."""
        if self._thread and self._thread.isRunning():
            self._thread.cancel()
            self._thread.wait(3000)
        super().reject()

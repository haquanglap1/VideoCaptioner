import atexit
import os

import psutil
from PyQt5.QtCore import QSize, Qt, QThread, QTimer, QUrl, pyqtSignal
from PyQt5.QtGui import QDesktopServices, QIcon
from PyQt5.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget
from qfluentwidgets import FluentIcon as FIF
from qfluentwidgets import (
    FluentWindow,
    InfoBar,
    InfoBarPosition,
    MessageBox,
    NavigationItemPosition,
    SplashScreen,
)

from videocaptioner.config import ASSETS_PATH, GITHUB_REPO_URL
from videocaptioner.core.constant import (
    INFOBAR_DURATION_FOREVER,
    INFOBAR_DURATION_SUCCESS,
)
from videocaptioner.ui.common.config import cfg

LOGO_PATH = ASSETS_PATH / "logo.png"


class LazyInterface(QWidget):
    """Navigation page that constructs its real widget on first display."""

    loaded = pyqtSignal(object)

    def __init__(self, route_key: str, factory, parent=None):
        super().__init__(parent)
        self.setObjectName(route_key)
        self._factory = factory
        self._content: QWidget | None = None
        self._loading = False
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._placeholder = QLabel(self.tr("正在加载界面..."), self)
        self._placeholder.setAlignment(Qt.AlignCenter)  # type: ignore
        self._layout.addWidget(self._placeholder)

    @property
    def content(self) -> QWidget | None:
        return self._content

    def load(self) -> QWidget:
        if self._content is not None:
            return self._content
        if self._loading:
            return self
        self._loading = True
        try:
            content = self._factory()
            self._content = content
            self._layout.removeWidget(self._placeholder)
            self._placeholder.deleteLater()
            self._layout.addWidget(content)
            self.loaded.emit(content)
            return content
        finally:
            self._loading = False

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self._content is None and not self._loading:
            QTimer.singleShot(0, self._load_if_needed)

    def _load_if_needed(self) -> None:
        self.load()


class MainWindow(FluentWindow):
    def __init__(self):
        super().__init__()
        self.versionChecker = None
        self.versionThread = None
        self._dubbing_interface = None
        self.initWindow()
        self._create_lazy_interfaces()
        self.initNavigation()
        self.splashScreen.finish()
        QTimer.singleShot(500, self._start_background_services)

        # 注册退出处理， 清理进程
        atexit.register(self.stop)

    def _create_lazy_interfaces(self) -> None:
        self.homeInterface = LazyInterface(
            "HomeInterface", self._create_home_interface, self
        )
        self.batchProcessInterface = LazyInterface(
            "batchProcessInterface", self._create_batch_interface, self
        )
        self.subtitleStyleInterface = LazyInterface(
            "subtitleStyleInterface", self._create_subtitle_style_interface, self
        )
        self.videoEditorInterface = LazyInterface(
            "videoEditorInterface", self._create_video_editor_interface, self
        )
        self.llmLogsInterface = LazyInterface(
            "llmLogsInterface", self._create_logs_interface, self
        )
        self.settingInterface = LazyInterface(
            "settingInterface", self._create_setting_interface, self
        )

    def _create_home_interface(self) -> QWidget:
        from videocaptioner.ui.view.home_interface import HomeInterface

        interface = HomeInterface(self.homeInterface)
        interface.openInVideoEditorRequested.connect(
            self.openInVideoEditor
        )
        interface.dubbingInterfaceReady.connect(self._start_vieneu_runtime_thread)
        return interface

    def _start_vieneu_runtime_thread(self, dubbing_interface) -> None:
        if self._dubbing_interface is not None:
            return
        self._dubbing_interface = dubbing_interface
        from videocaptioner.core.tts.vieneu.service import get_vieneu_service

        if (
            get_vieneu_service().update_prerequisite_error()
            or not cfg.vieneu_auto_update.value
        ):
            dubbing_interface._update_provider_visibility()
            return
        # Startup only asks the hub for the latest revision, through the tab's
        # queue so Start/voices cannot race it; the download is offered in the
        # tab instead of pulling 1.7 GB and restarting the sidecar silently.
        dubbing_interface.start_launch_update_check()

    def _create_batch_interface(self) -> QWidget:
        from videocaptioner.ui.view.batch_process_interface import BatchProcessInterface

        return BatchProcessInterface(self.batchProcessInterface)

    def _create_subtitle_style_interface(self) -> QWidget:
        from videocaptioner.ui.view.subtitle_style_interface import SubtitleStyleInterface

        return SubtitleStyleInterface(self.subtitleStyleInterface)

    def _create_video_editor_interface(self) -> QWidget:
        from videocaptioner.ui.view.video_editor_interface import VideoEditorInterface

        return VideoEditorInterface(self.videoEditorInterface)

    def _create_logs_interface(self) -> QWidget:
        from videocaptioner.ui.view.llm_logs_interface import LLMLogsInterface

        return LLMLogsInterface(self.llmLogsInterface)

    def _create_setting_interface(self) -> QWidget:
        from videocaptioner.ui.view.setting_interface import SettingInterface

        return SettingInterface(self.settingInterface)

    def _start_background_services(self) -> None:
        if self.versionThread is None:
            from videocaptioner.ui.thread.version_checker_thread import VersionChecker

            self.versionChecker = VersionChecker()
            self.versionChecker.newVersionAvailable.connect(self.onNewVersion)
            self.versionChecker.announcementAvailable.connect(self.onAnnouncement)
            self.versionThread = QThread(self)
            self.versionChecker.moveToThread(self.versionThread)
            self.versionThread.started.connect(self.versionChecker.perform_check)
            self.versionThread.start()
        self._check_ffmpeg()

    def initNavigation(self):
        """初始化导航栏"""
        # 添加导航项
        self.addSubInterface(self.homeInterface, FIF.HOME, self.tr("主页"))
        self.addSubInterface(self.batchProcessInterface, FIF.VIDEO, self.tr("批量处理"))
        self.addSubInterface(self.subtitleStyleInterface, FIF.FONT, self.tr("字幕样式"))
        self.addSubInterface(self.videoEditorInterface, FIF.EDIT, self.tr("Video Editor"))
        self.addSubInterface(self.llmLogsInterface, FIF.HISTORY, self.tr("请求日志"))

        self.navigationInterface.addSeparator()

        # 在底部添加设置
        self.addSubInterface(
            self.settingInterface,
            FIF.SETTING,
            self.tr("Settings"),
            NavigationItemPosition.BOTTOM,
        )

        # 设置默认界面
        self.switchTo(self.homeInterface)

    def switchTo(self, interface):
        if interface.windowTitle():
            self.setWindowTitle(interface.windowTitle())
        else:
            self.setWindowTitle(self.tr("卡卡字幕助手 -- VideoCaptioner"))
        self.stackedWidget.setCurrentWidget(interface, popOut=False)

    def openInVideoEditor(self, video_path: str, subtitle_path: str) -> None:
        editor = self.videoEditorInterface.load()
        editor.open_in_editor(video_path, subtitle_path)  # type: ignore[attr-defined]
        self.switchTo(self.videoEditorInterface)

    def initWindow(self):
        """初始化窗口"""
        self.resize(1050, 800)
        self.setMinimumWidth(700)
        self.setWindowIcon(QIcon(str(LOGO_PATH)))
        self.setWindowTitle(self.tr("卡卡字幕助手 -- VideoCaptioner"))

        self.setMicaEffectEnabled(cfg.get(cfg.micaEnabled))

        # 创建启动画面
        self.splashScreen = SplashScreen(self.windowIcon(), self)
        self.splashScreen.setIconSize(QSize(106, 106))
        self.splashScreen.raise_()

        # 设置窗口位置, 居中
        desktop = QApplication.desktop().availableGeometry()
        w, h = desktop.width(), desktop.height()
        self.move(w // 2 - self.width() // 2, h // 2 - self.height() // 2)

        self.show()
        QApplication.processEvents()

    def onGithubDialog(self):
        """打开GitHub"""
        w = MessageBox(
            self.tr("GitHub信息"),
            self.tr(
                "VideoCaptioner 由本人在课余时间独立开发完成，目前托管在GitHub上，欢迎Star和Fork。项目诚然还有很多地方需要完善，遇到软件的问题或者BUG欢迎提交Issue。\n\n https://github.com/WEIFENG2333/VideoCaptioner"
            ),
            self,
        )
        w.yesButton.setText(self.tr("打开 GitHub"))
        w.cancelButton.setText(self.tr("支持作者"))
        if w.exec():
            QDesktopServices.openUrl(QUrl(GITHUB_REPO_URL))
        else:
            # 点击"支持作者"按钮时打开捐赠对话框
            from videocaptioner.ui.components.DonateDialog import DonateDialog

            donate_dialog = DonateDialog(self)
            donate_dialog.exec_()

    def onNewVersion(self, version, update_required, update_info, download_url):
        """新版本提示 — 显示 UpdateDialog cho phép tải và cài tự động."""
        from videocaptioner.ui.components.UpdateDialog import UpdateDialog

        dialog = UpdateDialog(
            version=version,
            update_info=update_info,
            download_url=download_url,
            parent=self,
        )

        if update_required:
            # Bắt buộc cập nhật: ẩn nút cancel
            dialog.cancelButton.setVisible(False)

        result = dialog.exec()

        if update_required and result == 0:
            # User đóng dialog mà không cập nhật — tắt tính năng
            self.homeInterface.setEnabled(False)
            self.batchProcessInterface.setEnabled(False)
            InfoBar.error(
                title="Cần cập nhật",
                content=self.tr("Đã có phiên bản mới bắt buộc. Vui lòng cập nhật."),
                isClosable=False,
                position=InfoBarPosition.BOTTOM,
                duration=-1,
                parent=self,
            )

    def onAnnouncement(self, content):
        """显示公告"""
        w = MessageBox(self.tr("公告"), content, self)
        w.yesButton.setText(self.tr("我知道了"))
        w.cancelButton.hide()
        w.exec()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if hasattr(self, "splashScreen"):
            self.splashScreen.resize(self.size())

    def closeEvent(self, event):
        # Stop background QThread (version checker) cleanly so it doesn't keep
        # the network call alive after the window is gone.
        try:
            if self.versionThread is not None and self.versionThread.isRunning():
                self.versionThread.quit()
                self.versionThread.wait(2000)
        except Exception:
            pass

        try:
            from videocaptioner.core.tts.vieneu.service import get_vieneu_service

            get_vieneu_service().cancel_pending()
            if self._dubbing_interface is not None:
                # Interrupt now; the wait comes after child processes are gone
                # so a running FFmpeg mix cannot hold the job past the timeout.
                self._dubbing_interface.request_stop()
                self._dubbing_interface.shutdown_vieneu_threads(11_000)
        except Exception:
            pass

        self.videoEditorInterface.close()

        try:
            from videocaptioner.core.tts.vieneu.service import get_vieneu_service

            get_vieneu_service().shutdown()
        except Exception:
            pass

        # Kill child processes (ffmpeg, aria2c, faster-whisper, etc.) BEFORE Qt
        # tears down — atexit alone is unreliable when the user X-closes the app
        # and orphaned conhost.exe / ffmpeg.exe pile up in Task Manager.
        self.stop()

        if self._dubbing_interface is not None:
            self._dubbing_interface.wait_for_dubbing_job(10_000)

        self._detach_info_bar_managers()
        super().closeEvent(event)
        QApplication.quit()

    def _detach_info_bar_managers(self) -> None:
        """Stop InfoBar managers from filtering this window's events.

        qfluentwidgets installs its per-position InfoBarManager singletons as
        event filters on the window the first time a bar is shown and never
        removes them. At interpreter shutdown the managers die before the
        window does, and every late event then logs "wrapped C/C++ object of
        type BottomInfoBarManager has been deleted" through the excepthook.
        """
        try:
            from qfluentwidgets.components.widgets.info_bar import InfoBarManager

            for position in InfoBarPosition:
                if position in InfoBarManager.managers:
                    self.removeEventFilter(InfoBarManager.make(position))
        except Exception:
            pass

    def stop(self):
        """Terminate all child processes spawned by this app."""
        try:
            process = psutil.Process(os.getpid())
            children = process.children(recursive=True)
        except Exception:
            return

        for child in children:
            try:
                child.terminate()
            except Exception:
                pass

        # Give them a moment to exit gracefully, then hard-kill survivors.
        _gone, alive = psutil.wait_procs(children, timeout=2)
        for child in alive:
            try:
                child.kill()
            except Exception:
                pass

    def _check_ffmpeg(self):
        """Detect ffmpeg; if missing, offer one-click auto-install on Windows."""
        from videocaptioner.core.utils.installer import ffmpeg_path

        # Honor managed install dir (already prepended to PATH on import) and
        # any user-installed ffmpeg.
        if ffmpeg_path() is not None:
            return

        # On non-Windows platforms we can't auto-download portably; just warn.
        import platform
        if platform.system() != "Windows":
            InfoBar.warning(
                self.tr("FFmpeg 未安装"),
                self.tr("软件处理音视频文件时需要 FFmpeg，请先安装"),
                duration=INFOBAR_DURATION_FOREVER,
                position=InfoBarPosition.BOTTOM,
                parent=self,
            )
            return

        # Windows: prompt with a "Cài tự động" / install-now button.
        from PyQt5.QtCore import Qt
        from PyQt5.QtWidgets import QApplication, QPushButton
        from qfluentwidgets import ProgressBar

        bar = InfoBar.warning(
            self.tr("FFmpeg 未安装"),
            self.tr("Cần FFmpeg để xử lý video. Bấm để cài tự động vào AppData."),
            duration=INFOBAR_DURATION_FOREVER,
            position=InfoBarPosition.BOTTOM,
            isClosable=True,
            parent=self,
        )

        progress = ProgressBar(bar)
        progress.setFixedWidth(180)
        progress.setVisible(False)
        bar.addWidget(progress)

        install_btn = QPushButton(self.tr("Cài tự động"))
        install_btn.setCursor(Qt.PointingHandCursor)  # type: ignore
        install_btn.setStyleSheet(
            "QPushButton { padding: 4px 12px; border-radius: 4px;"
            " background: #28f08b; color: black; font-weight: 600; }"
            "QPushButton:hover { background: #4cffa5; }"
            "QPushButton:disabled { background: #555; color: #aaa; }"
        )
        bar.addWidget(install_btn)

        def _start_install():
            from videocaptioner.ui.thread.ffmpeg_install_thread import FFmpegInstallThread

            install_btn.setEnabled(False)
            install_btn.setText(self.tr("Đang tải..."))
            progress.setVisible(True)
            progress.setValue(0)

            self._ffmpeg_thread = FFmpegInstallThread(self)
            self._ffmpeg_thread.progress.connect(
                lambda p, msg: (progress.setValue(p), install_btn.setText(msg))
            )
            self._ffmpeg_thread.finished_ok.connect(_on_done)
            self._ffmpeg_thread.failed.connect(_on_fail)
            self._ffmpeg_thread.start()

        def _on_done(path: str):
            bar.close()
            InfoBar.success(
                self.tr("成功"),
                self.tr("Đã cài FFmpeg: ") + path,
                duration=INFOBAR_DURATION_SUCCESS,
                position=InfoBarPosition.BOTTOM,
                parent=self,
            )

        def _on_fail(msg: str):
            install_btn.setEnabled(True)
            install_btn.setText(self.tr("Thử lại"))
            progress.setValue(0)
            InfoBar.error(
                self.tr("下载错误"),
                msg,
                duration=8000,
                position=InfoBarPosition.BOTTOM,
                parent=self,
            )
            QApplication.beep()

        install_btn.clicked.connect(_start_install)

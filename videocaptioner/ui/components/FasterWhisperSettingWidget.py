import os
import shutil
import subprocess
from pathlib import Path

from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QShowEvent
from PyQt5.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    BodyLabel,
    ComboBox,
    ComboBoxSettingCard,
    HyperlinkButton,
    HyperlinkCard,
    InfoBar,
    InfoBarPosition,
    MessageBoxBase,
    ProgressBar,
    PushButton,
    SettingCardGroup,
    SingleDirectionScrollArea,
    SubtitleLabel,
    SwitchSettingCard,
    TableItemDelegate,
    TableWidget,
)
from qfluentwidgets import FluentIcon as FIF

from videocaptioner.config import BIN_PATH, LEGACY_BIN_PATH, MODEL_PATH
from videocaptioner.core.entities import (
    FasterWhisperModelEnum,
    TranscribeLanguageEnum,
    VadMethodEnum,
)
from videocaptioner.core.utils.logger import setup_logger
from videocaptioner.core.utils.platform_utils import open_folder
from videocaptioner.core.utils.subprocess_helper import child_environment
from videocaptioner.ui.common.config import cfg
from videocaptioner.ui.components.LineEditSettingCard import LineEditSettingCard
from videocaptioner.ui.components.SpinBoxSettingCard import DoubleSpinBoxSettingCard
from videocaptioner.ui.thread.file_download_thread import FileDownloadThread
from videocaptioner.ui.thread.modelscope_download_thread import ModelscopeDownloadThread

logger = setup_logger("faster_whisper_setting")

# Constants
FASTER_WHISPER_PROGRAMS = [
    {
        "label": "Bản GPU (CUDA) + CPU",
        "value": "faster-whisper-gpu.7z",
        "type": "GPU",
        "size": "1.35 GB",
        "downloadLink": "https://modelscope.cn/models/bkfengg/whisper-cpp/resolve/master/Faster-Whisper-XXL_r245.2_windows.7z",
    },
    {
        "label": "Bản CPU",
        "value": "faster-whisper.exe",
        "type": "CPU",
        "size": "78.7 MB",
        "downloadLink": "https://modelscope.cn/models/bkfengg/whisper-cpp/resolve/master/whisper-faster.exe",
    },
]

FASTER_WHISPER_MODELS = [
    {
        "label": "Tiny",
        "value": "faster-whisper-tiny",
        "size": "77824",
        "downloadLink": "https://huggingface.co/Systran/faster-whisper-tiny",
        "modelScopeLink": "pengzhendong/faster-whisper-tiny",
    },
    {
        "label": "Base",
        "value": "faster-whisper-base",
        "size": "148480",
        "downloadLink": "https://huggingface.co/Systran/faster-whisper-base",
        "modelScopeLink": "pengzhendong/faster-whisper-base",
    },
    {
        "label": "Small",
        "value": "faster-whisper-small",
        "size": "495616",
        "downloadLink": "https://huggingface.co/Systran/faster-whisper-small",
        "modelScopeLink": "pengzhendong/faster-whisper-small",
    },
    {
        "label": "Medium",
        "value": "faster-whisper-medium",
        "size": "1572864",
        "downloadLink": "https://huggingface.co/Systran/faster-whisper-medium",
        "modelScopeLink": "pengzhendong/faster-whisper-medium",
    },
    {
        "label": "Large-v1",
        "value": "faster-whisper-large-v1",
        "size": "3145728",
        "downloadLink": "https://huggingface.co/Systran/faster-whisper-large-v1",
        "modelScopeLink": "pengzhendong/faster-whisper-large-v1",
    },
    {
        "label": "Large-v2",
        "value": "faster-whisper-large-v2",
        "size": "3145728",
        "downloadLink": "https://huggingface.co/Systran/faster-whisper-large-v2",
        "modelScopeLink": "pengzhendong/faster-whisper-large-v2",
    },
    {
        "label": "Large-v3",
        "value": "faster-whisper-large-v3",
        "size": "3145728",
        "downloadLink": "https://huggingface.co/Systran/faster-whisper-large-v3",
        "modelScopeLink": "pengzhendong/faster-whisper-large-v3",
    },
    {
        "label": "Large-v3-turbo",
        "value": "faster-whisper-large-v3-turbo",
        "size": "1720320",
        "downloadLink": "https://huggingface.co/Systran/faster-whisper-large-v3-turbo",
        "modelScopeLink": "pengzhendong/faster-whisper-large-v3-turbo",
    },
]

MIN_PROGRAM_SIZE = 1024 * 1024
MAX_SCAN_DEPTH = 4
MAX_SCAN_ENTRIES = 4096


def _model_dir(model: dict) -> Path:
    return Path(MODEL_PATH) / model["value"]


def is_faster_whisper_model_downloaded(model: dict) -> bool:
    """Return True when a Faster Whisper model directory contains model.bin."""
    model_path = _model_dir(model)
    if not model_path.exists():
        return False
    if (model_path / "model.bin").exists():
        return True
    return _bounded_find_file(model_path, {"model.bin"}) is not None


def _model_config_for_enum(model_enum: FasterWhisperModelEnum) -> dict | None:
    return next(
        (
            model
            for model in FASTER_WHISPER_MODELS
            if model["label"].lower() == model_enum.value.lower()
        ),
        None,
    )


def available_faster_whisper_models() -> list[FasterWhisperModelEnum]:
    available = []
    for model_enum in FasterWhisperModelEnum:
        model = _model_config_for_enum(model_enum)
        if model and is_faster_whisper_model_downloaded(model):
            available.append(model_enum)
    return available


def _is_valid_program_file(path: Path) -> bool:
    """Return True when `path` looks like a usable executable."""
    return path.exists() and path.is_file() and path.stat().st_size >= MIN_PROGRAM_SIZE


def _bounded_find_file(root: Path, names: set[str]) -> Path | None:
    """Find a file without allowing a malformed install tree to freeze Qt."""
    stack = [(root, 0)]
    visited = 0
    while stack and visited < MAX_SCAN_ENTRIES:
        directory, depth = stack.pop()
        try:
            entries = list(os.scandir(directory))
        except OSError:
            continue
        for entry in entries:
            visited += 1
            if visited > MAX_SCAN_ENTRIES:
                return None
            if entry.name.startswith("._____"):
                continue
            try:
                if entry.is_file(follow_symlinks=False) and entry.name in names:
                    return Path(entry.path)
                if depth < MAX_SCAN_DEPTH and entry.is_dir(follow_symlinks=False):
                    stack.append((Path(entry.path), depth + 1))
            except OSError:
                continue
    return None


# Module-level helper
def _program_search_roots() -> list[Path]:
    roots = [Path(BIN_PATH)]
    legacy = Path(LEGACY_BIN_PATH)
    if legacy != roots[0]:
        roots.append(legacy)
    return roots


def _find_program_file(*relative_paths: str) -> Path | None:
    for root in _program_search_roots():
        for relative_path in relative_paths:
            candidate = root / relative_path
            if _is_valid_program_file(candidate):
                return candidate
        candidate = _bounded_find_file(root, {Path(p).name for p in relative_paths})
        if candidate is not None and _is_valid_program_file(candidate):
            return candidate
    return None


def _find_7z_executable() -> str | None:
    """Return a native 7-Zip executable when one is available."""
    for executable in ("7z", "7za", "7zr"):
        path = shutil.which(executable)
        if path:
            return path

    candidates = []
    for root in _program_search_roots():
        candidates.extend(
            [
                root / "7z.exe",
                root / "7za.exe",
                root / "7zr.exe",
                root / "7-Zip" / "7z.exe",
            ]
        )

    if os.name == "nt":
        program_files = [
            os.environ.get("ProgramFiles"),
            os.environ.get("ProgramFiles(x86)"),
            os.environ.get("LocalAppData"),
        ]
        for program_dir in filter(None, program_files):
            candidates.extend(
                [
                    Path(program_dir) / "7-Zip" / "7z.exe",
                    Path(program_dir) / "Programs" / "7-Zip" / "7z.exe",
                    Path(program_dir) / "Microsoft" / "WindowsApps" / "7z.exe",
                    Path(program_dir) / "Microsoft" / "WindowsApps" / "NanaZipC.exe",
                ]
            )

    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return str(candidate)
    return None


def _find_tar_executable() -> str | None:
    """Return the platform tar executable when libarchive-backed tar is available."""
    return shutil.which("tar")


def check_faster_whisper_exists() -> tuple[bool, list[str]]:
    """Check whether a faster-whisper program is installed.

    Two layouts are accepted:
    1. faster-whisper.exe directly under the bin directory
    2. Faster-Whisper-XXL/faster-whisper-xxl.exe under the bin directory

    Returns:
        tuple[bool, list[str]]: (program found, installed version labels)
    """
    installed_versions = []

    # faster-whisper.exe (CPU build)
    if _find_program_file("faster-whisper.exe", "whisper-faster.exe"):
        installed_versions.append("CPU")

    # Faster-Whisper-XXL/faster-whisper-xxl.exe (GPU build)
    if _find_program_file("Faster-Whisper-XXL/faster-whisper-xxl.exe"):
        installed_versions.extend(["GPU", "CPU"])
    installed_versions = [
        version for version in ("GPU", "CPU") if version in installed_versions
    ]

    return bool(installed_versions), installed_versions


# Extraction thread
class UnzipThread(QThread):
    """7z extraction thread."""

    finished = pyqtSignal()  # Emitted when extraction finishes
    error = pyqtSignal(str)  # Emitted on extraction error

    def __init__(self, zip_file, extract_path, remove_archive: bool = True):
        super().__init__()
        self.zip_file = zip_file
        self.extract_path = extract_path
        self.remove_archive = remove_archive

    def run(self):
        try:
            if str(self.zip_file).lower().endswith(".7z"):
                self._extract_7z()
            else:
                self._extract_with_7z()
            if self.remove_archive:
                os.remove(self.zip_file)
            self.finished.emit()
        except subprocess.CalledProcessError as e:
            stderr = (e.stderr or "").strip()
            self.error.emit(stderr or f"Extract failed: {e}")
        except Exception as e:
            msg = str(e)
            if "BCJ2 filter is not supported by py7zr" in msg:
                msg = (
                    "File .7z nay can 7-Zip de giai nen. "
                    "Vui long cai 7-Zip hoac dat 7z.exe vao thu muc chuong trinh, "
                    "sau do bam tai/cai dat lai."
                )
            self.error.emit(msg)

    def _extract_7z(self):
        seven_zip = _find_7z_executable()
        if seven_zip:
            self._extract_with_7z(seven_zip)
            return

        tar = _find_tar_executable()
        if tar:
            try:
                self._extract_with_tar(tar)
                return
            except subprocess.CalledProcessError as e:
                logger.warning(
                    "tar failed to extract %s: %s",
                    self.zip_file,
                    (e.stderr or e.stdout or str(e)).strip(),
                )

        import py7zr

        with py7zr.SevenZipFile(self.zip_file, mode="r") as archive:
            archive.extractall(path=self.extract_path)

    def _extract_with_7z(self, seven_zip: str | None = None):
        seven_zip = seven_zip or _find_7z_executable()
        if not seven_zip:
            raise RuntimeError(
                "Khong tim thay 7-Zip. Vui long cai 7-Zip hoac dat 7z.exe "
                "vao thu muc chuong trinh de giai nen goi GPU Faster Whisper."
            )

        subprocess.run(
            [seven_zip, "x", str(self.zip_file), f"-o{self.extract_path}", "-y"], env=child_environment(),
            check=True,
            capture_output=True,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )

    def _extract_with_tar(self, tar: str):
        subprocess.run(
            [tar, "-xf", str(self.zip_file), "-C", str(self.extract_path)], env=child_environment(),
            check=True,
            capture_output=True,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )


class FasterWhisperDownloadDialog(MessageBoxBase):
    """Faster Whisper download dialog."""

    # Class-level download state
    is_downloading = False

    def __init__(self, parent=None, setting_widget=None):
        super().__init__(parent)
        self.widget.setMinimumWidth(600)
        self.program_download_thread = None
        self.model_download_thread = None
        self._setup_ui()
        self._connect_signals()
        self.setting_widget = setting_widget

    def _setup_ui(self):
        """Set up the UI."""
        layout = QVBoxLayout()
        self._setup_program_section(layout)
        layout.addSpacing(20)
        self._setup_model_section(layout)
        self._setup_progress_section(layout)

        self.viewLayout.addLayout(layout)
        self.cancelButton.setText(self.tr("关闭"))
        self.yesButton.hide()

    def _setup_program_section(self, layout):
        """Set up the program download section."""
        # Title row with buttons
        title_layout = QHBoxLayout()

        # Title
        faster_whisper_title = SubtitleLabel(self.tr("Faster Whisper 下载"), self)
        title_layout.addWidget(faster_whisper_title)

        # Open-folder button
        open_folder_btn = HyperlinkButton("", self.tr("打开程序文件夹"), parent=self)
        open_folder_btn.setIcon(FIF.FOLDER)
        open_folder_btn.clicked.connect(self._open_program_folder)
        title_layout.addStretch()
        title_layout.addWidget(open_folder_btn)

        layout.addLayout(title_layout)
        layout.addSpacing(8)

        # Installed versions
        has_program, installed_versions = check_faster_whisper_exists()

        if has_program:
            # Show the installed versions
            versions_text = " + ".join(installed_versions)
            program_status = BodyLabel(self.tr(f"已安装版本: {versions_text}"), self)
            program_status.setStyleSheet("color: green")
            layout.addWidget(program_status)

            # Description label
            if len(installed_versions) == 1:
                desc_label = BodyLabel(self.tr("您可以继续下载其他版本:"), self)
                layout.addWidget(desc_label)
        else:
            desc_label = BodyLabel(self.tr("未下载Faster Whisper 程序"), self)
            layout.addWidget(desc_label)

        # Download controls
        program_layout = QHBoxLayout()
        self.program_combo = ComboBox(self)
        self.program_combo.setFixedWidth(300)
        self.program_combo.hide()

        # Only offer versions that are not installed
        for program in FASTER_WHISPER_PROGRAMS:
            version_type = program["type"]
            if version_type not in installed_versions:
                self.program_combo.addItem(
                    f"{self.tr(program['label'])} ({program['size']})",
                    userData=program,
                )

        # Show the download controls while versions remain
        if self.program_combo.count() > 0:
            self.program_combo.show()
            self.program_download_btn = PushButton(self.tr("下载程序"), self)
            self.program_download_btn.clicked.connect(self._start_download)
            program_layout.addWidget(self.program_combo)
            program_layout.addWidget(self.program_download_btn)
            program_layout.addStretch()
            layout.addLayout(program_layout)

    def _setup_model_section(self, layout):
        """Set up the model download section."""
        # Title row with buttons
        title_layout = QHBoxLayout()

        # Title
        model_title = SubtitleLabel(self.tr("模型下载"), self)
        title_layout.addWidget(model_title)

        # Open-folder button
        open_folder_btn = HyperlinkButton("", self.tr("打开模型文件夹"), parent=self)
        open_folder_btn.setIcon(FIF.FOLDER)
        open_folder_btn.clicked.connect(self._open_model_folder)
        title_layout.addStretch()
        title_layout.addWidget(open_folder_btn)

        layout.addLayout(title_layout)
        layout.addSpacing(8)

        # Model table
        self.model_table = self._create_model_table()
        self._populate_model_table()
        layout.addWidget(self.model_table)

    def _create_model_table(self):
        """Create the model table."""
        table = TableWidget(self)
        table.setEditTriggers(TableWidget.NoEditTriggers)
        table.setSelectionMode(TableWidget.NoSelection)
        table.setColumnCount(4)
        table.setHorizontalHeaderLabels(
            [self.tr("模型名称"), self.tr("大小"), self.tr("状态"), self.tr("操作")]
        )

        # Table style
        table.setBorderVisible(True)
        table.setBorderRadius(8)
        table.setItemDelegate(TableItemDelegate(table))

        # Column widths
        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.Fixed)
        header.setSectionResizeMode(2, QHeaderView.Fixed)
        header.setSectionResizeMode(3, QHeaderView.Fixed)

        table.setColumnWidth(1, 100)
        table.setColumnWidth(2, 80)
        table.setColumnWidth(3, 150)

        # Row height
        row_height = 45
        table.verticalHeader().setDefaultSectionSize(row_height)

        # Table height
        header_height = 20
        max_visible_rows = 6
        table_height = row_height * max_visible_rows + header_height + 15
        table.setFixedHeight(table_height)

        return table

    def _setup_progress_section(self, layout):
        """Set up the progress section."""
        self.progress_bar = ProgressBar(self)
        self.progress_label = BodyLabel("", self)
        self.progress_bar.hide()
        self.progress_label.hide()

        layout.addWidget(self.progress_bar)
        layout.addWidget(self.progress_label)

    def _populate_model_table(self):
        """Fill the model table."""
        self.model_table.setRowCount(len(FASTER_WHISPER_MODELS))
        for i, model in enumerate(FASTER_WHISPER_MODELS):
            self._add_model_row(i, model)

    def _add_model_row(self, row, model):
        """Add one model row."""
        # Model name
        name_item = QTableWidgetItem(model["label"])
        name_item.setTextAlignment(Qt.AlignCenter)  # type: ignore
        self.model_table.setItem(row, 0, name_item)

        # Size
        size_item = QTableWidgetItem(f"{int(model['size']) / 1024:.1f} MB")
        size_item.setTextAlignment(Qt.AlignCenter)  # type: ignore
        self.model_table.setItem(row, 1, size_item)

        # Status; ModelScope/HuggingFace may place model.bin in nested snapshots.
        is_downloaded = is_faster_whisper_model_downloaded(model)

        status_item = QTableWidgetItem(
            self.tr("已下载") if is_downloaded else self.tr("未下载")
        )
        if is_downloaded:
            status_item.setForeground(Qt.green)  # type: ignore
        status_item.setTextAlignment(Qt.AlignCenter)  # type: ignore
        self.model_table.setItem(row, 2, status_item)

        # Download button
        button_container = QWidget()
        button_layout = QHBoxLayout(button_container)
        button_layout.setContentsMargins(4, 4, 4, 4)

        download_btn = HyperlinkButton(
            "",
            self.tr("重新下载") if is_downloaded else self.tr("下载"),
            parent=self,
        )
        download_btn.setIcon(FIF.DOWNLOAD)
        download_btn.clicked.connect(lambda checked, r=row: self._download_model(r))

        button_layout.addStretch()
        button_layout.addWidget(download_btn)
        button_layout.addStretch()
        self.model_table.setCellWidget(row, 3, button_container)

    def _connect_signals(self):
        """Connect signals."""
        self.rejected.connect(self._on_dialog_reject)

    def _start_download(self):
        """Start the download."""
        if FasterWhisperDownloadDialog.is_downloading:
            InfoBar.warning(
                self.tr("下载进行中"),
                self.tr("请等待当前下载任务完成"),
                duration=3000,
                parent=self,
            )
            return

        FasterWhisperDownloadDialog.is_downloading = True
        # Disable every download button
        self._set_all_download_buttons_enabled(False)

        program = self.program_combo.currentData()

        if not program:
            InfoBar.error(
                self.tr("下载错误"),
                self.tr("未找到对应的程序配置"),
                duration=3000,
                parent=self,
            )
            FasterWhisperDownloadDialog.is_downloading = False
            self._set_all_download_buttons_enabled(True)
            return

        # Make sure BIN_PATH exists
        os.makedirs(BIN_PATH, exist_ok=True)

        self.progress_bar.show()
        self.progress_label.show()
        self.program_download_btn.setEnabled(False)
        self.program_combo.setEnabled(False)

        # Download straight into the bin directory; older dev setups used resource/bin,
        # nếu còn file cài đặt ở đó thì tái sử dụng để không tải lại 1.35 GB.
        save_path = os.path.join(BIN_PATH, program["value"])
        legacy_save_path = os.path.join(LEGACY_BIN_PATH, program["value"])

        if os.path.exists(save_path):
            if save_path.endswith(".exe") and not _is_valid_program_file(Path(save_path)):
                Path(save_path).unlink(missing_ok=True)
            elif save_path.endswith(".7z") and Path(save_path).stat().st_size < MIN_PROGRAM_SIZE:
                Path(save_path).unlink(missing_ok=True)

        if not os.path.exists(save_path) and os.path.exists(legacy_save_path):
            save_path = legacy_save_path

        if os.path.exists(save_path):
            self.progress_label.setText(self.tr("已找到下载文件，正在安装..."))
            self._on_program_download_finished(save_path)
            return

        self.program_download_thread = FileDownloadThread(
            program["downloadLink"], save_path
        )
        self.program_download_thread.progress.connect(
            self._on_program_download_progress
        )
        self.program_download_thread.finished.connect(
            lambda: self._on_program_download_finished(save_path)
        )
        self.program_download_thread.error.connect(self._on_program_download_error)
        self.program_download_thread.start()

    def _on_program_download_progress(self, value, status_msg):
        """Update the program download progress."""
        self.progress_bar.setValue(int(value))
        self.progress_label.setText(status_msg)

    def _on_program_download_finished(self, save_path):
        """Handle a finished program download."""
        try:
            # Direct download of the CPU build?
            if save_path.endswith(".exe"):
                # A bare exe is renamed to faster-whisper.exe
                target_path = os.path.join(BIN_PATH, "faster-whisper.exe")
                if os.path.abspath(save_path) != os.path.abspath(target_path):
                    os.replace(save_path, target_path)
                self._finish_program_installation()
            else:
                # The GPU build needs extraction
                self.progress_label.setText(self.tr("正在解压文件..."))

                # Create and start the extraction thread
                remove_archive = Path(save_path).parent == Path(BIN_PATH)
                self.unzip_thread = UnzipThread(
                    save_path, BIN_PATH, remove_archive=remove_archive
                )
                self.unzip_thread.finished.connect(self._finish_program_installation)
                self.unzip_thread.error.connect(self._on_unzip_error)
                self.unzip_thread.start()
                return  # Return now; extraction finishes asynchronously

        except Exception as e:
            InfoBar.error(self.tr("安装失败"), str(e), duration=3000, parent=self)
            self._cleanup_installation()

    def _on_program_download_error(self, error):
        """Handle a program download error."""
        InfoBar.error(self.tr("下载失败"), error, duration=3000, parent=self)
        FasterWhisperDownloadDialog.is_downloading = False
        self._set_all_download_buttons_enabled(True)
        self.program_download_btn.setEnabled(True)
        self.program_combo.setEnabled(True)
        self.progress_bar.hide()
        self.progress_label.hide()

    def _on_dialog_reject(self):
        """Handle the dialog closing."""
        self._cleanup_download_threads()

    def _cleanup_download_threads(self):
        if self.program_download_thread and self.program_download_thread.isRunning():
            self.program_download_thread.stop()
        if self.model_download_thread and self.model_download_thread.isRunning():
            self.model_download_thread.terminate()
        FasterWhisperDownloadDialog.is_downloading = False

    def closeEvent(self, event):
        """Handle the window close event."""
        self._cleanup_download_threads()
        super().closeEvent(event)

    def _download_model(self, row):
        """Download the selected model."""
        if FasterWhisperDownloadDialog.is_downloading:
            InfoBar.warning(
                self.tr("下载进行中"),
                self.tr("请等待当前下载任务完成"),
                duration=3000,
                parent=self,
            )
            return

        FasterWhisperDownloadDialog.is_downloading = True
        self._set_all_download_buttons_enabled(False)

        model = FASTER_WHISPER_MODELS[row]
        self.progress_bar.show()
        self.progress_label.show()
        self.progress_label.setText(self.tr(f"正在下载 {model['label']} 模型..."))

        # Disable the download button of this row
        button_container = self.model_table.cellWidget(row, 3)
        download_btn = button_container.findChild(HyperlinkButton)
        if download_btn:
            download_btn.setEnabled(False)

        # Create and start the download thread, kept on the class
        self.model_download_thread = ModelscopeDownloadThread(
            model["modelScopeLink"], os.path.join(MODEL_PATH, model["value"])
        )

        def _on_model_download_progress(value, msg):
            self.progress_bar.setValue(value)
            self.progress_label.setText(msg)

        def _on_model_download_finished():
            FasterWhisperDownloadDialog.is_downloading = False
            self._set_all_download_buttons_enabled(True)
            model = FASTER_WHISPER_MODELS[row]
            self._populate_model_table()

            # Update the model selector of the main settings dialog
            if self.setting_widget:
                self.setting_widget.refresh_model_options()

            InfoBar.success(
                self.tr("下载成功"),
                self.tr(f"{model['label']} 模型已下载完成"),
                duration=3000,
                parent=self,
            )
            self.progress_bar.hide()
            self.progress_label.hide()

        def _on_model_download_error(error):
            FasterWhisperDownloadDialog.is_downloading = False
            self._set_all_download_buttons_enabled(True)
            if download_btn:
                download_btn.setEnabled(True)

            InfoBar.error(self.tr("下载失败"), str(error), duration=3000, parent=self)
            self.progress_bar.hide()
            self.progress_label.hide()

        self.model_download_thread.progress.connect(_on_model_download_progress)
        self.model_download_thread.finished.connect(_on_model_download_finished)
        self.model_download_thread.error.connect(_on_model_download_error)
        self.model_download_thread.start()

    def _set_all_download_buttons_enabled(self, enabled: bool):
        """Enable or disable every download button."""
        # Program download button
        if hasattr(self, "program_download_btn"):
            self.program_download_btn.setEnabled(enabled)
            self.program_combo.setEnabled(enabled)

        # Model download buttons
        for row in range(self.model_table.rowCount()):
            button_container = self.model_table.cellWidget(row, 3)
            if button_container:
                download_btn = button_container.findChild(HyperlinkButton)
                if download_btn:
                    download_btn.setEnabled(enabled)

    def _open_model_folder(self):
        """Open the model folder."""
        if os.path.exists(MODEL_PATH):
            # Open the folder with the platform's file manager
            open_folder(str(MODEL_PATH))

    def _open_program_folder(self):
        """Open the program folder."""
        if os.path.exists(BIN_PATH):
            # Open the folder with the platform's file manager
            open_folder(str(BIN_PATH))

    def _finish_program_installation(self):
        """Finish the program installation."""
        has_program, _ = check_faster_whisper_exists()
        if not has_program:
            InfoBar.error(
                self.tr("安装失败"),
                self.tr(
                    "Không tìm thấy chương trình Faster Whisper hợp lệ. "
                    "Tệp tải về có thể bị hỏng, vui lòng tải lại."
                ),
                duration=5000,
                parent=self,
            )
            self._cleanup_installation()
            return

        InfoBar.success(
            self.tr("安装完成"),
            self.tr("Faster Whisper 程序已安装成功"),
            duration=3000,
            parent=self,
        )
        self.accept()
        self._cleanup_installation()

    def _on_unzip_error(self, error_msg):
        """Handle an extraction error."""
        InfoBar.error(self.tr("安装失败"), error_msg, duration=3000, parent=self)
        self._cleanup_installation()

    def _cleanup_installation(self):
        """Reset the installation state."""
        FasterWhisperDownloadDialog.is_downloading = False
        self._set_all_download_buttons_enabled(True)
        self.progress_bar.hide()
        self.progress_label.hide()

    def showEvent(self, event):
        super().showEvent(event)
        self._populate_model_table()


class FasterWhisperSettingWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._missing_program_warned = False
        self.setup_ui()
        self._connect_signals()

    def showEvent(self, a0: QShowEvent) -> None:
        super().showEvent(a0)
        self.refresh_model_options()
        # Check that the Faster Whisper model exists
        is_faster_whisper_exists, _ = check_faster_whisper_exists()
        if is_faster_whisper_exists:
            self._missing_program_warned = False
        elif not self._missing_program_warned:
            self.show_warning_info(self.tr("Faster Whisper程序不存在，请先下载程序"))
            self._missing_program_warned = True
        return

    def setup_ui(self):
        self.main_layout = QVBoxLayout(self)

        # Vertical scroll area and container
        self.scrollArea = SingleDirectionScrollArea(orient=Qt.Vertical, parent=self)  # type: ignore
        self.scrollArea.setStyleSheet(
            "QScrollArea{background: transparent; border: none}"
        )

        self.container = QWidget(self)
        self.container.setStyleSheet("QWidget{background: transparent}")
        self.containerLayout = QVBoxLayout(self.container)

        self.setting_group = SettingCardGroup(
            self.tr("Faster Whisper 设置"), self
        )

        # Model selector
        self.model_card = ComboBoxSettingCard(
            cfg.faster_whisper_model,
            FIF.ROBOT,
            self.tr("模型"),
            self.tr("选择 Faster Whisper 模型"),
            [self.tr(model.value) for model in FasterWhisperModelEnum],
            self.setting_group,
        )

        self.refresh_model_options()

        # Model management card
        self.manage_model_card = HyperlinkCard(
            "",  # No link
            self.tr("管理模型"),
            FIF.DOWNLOAD,  # Download icon
            self.tr("模型管理"),
            self.tr("下载或更新 Faster Whisper 模型"),
            self.setting_group,  # Add to the settings group
        )

        # Language selector
        self.language_card = ComboBoxSettingCard(
            cfg.transcribe_language,
            FIF.LANGUAGE,
            self.tr("源语言"),
            self.tr("音视频中说话的语言，默认根据前30秒自动识别"),
            [self.tr(lang.value) for lang in TranscribeLanguageEnum],
            self.setting_group,
        )
        self.language_card.comboBox.setMaxVisibleItems(6)

        # Device selector
        self.device_card = ComboBoxSettingCard(
            cfg.faster_whisper_device,
            FIF.IOT,
            self.tr("运行设备"),
            self.tr("模型运行设备"),
            ["cuda", "cpu"],
            self.setting_group,
        )
        # _, available_devices = check_faster_whisper_exists()
        # if "GPU" not in available_devices:
        #     self.device_card.comboBox.removeItem(0)

        # VAD group
        self.vad_group = SettingCardGroup(self.tr("VAD设置"), self)

        # VAD filter switch
        self.vad_filter_card = SwitchSettingCard(
            FIF.CHECKBOX,
            self.tr("VAD过滤"),
            self.tr("过滤无人声语音片断，减少幻觉"),
            cfg.faster_whisper_vad_filter,
            self.vad_group,
        )

        # VAD threshold
        self.vad_threshold_card = DoubleSpinBoxSettingCard(
            cfg.faster_whisper_vad_threshold,
            FIF.VOLUME,  # type: ignore
            self.tr("VAD阈值"),
            self.tr("语音概率阈值，高于此值视为语音"),
            minimum=0.00,
            maximum=1.00,
            decimals=2,
            step=0.05,
        )

        # VAD method
        self.vad_method_card = ComboBoxSettingCard(
            cfg.faster_whisper_vad_method,
            FIF.MUSIC,
            self.tr("VAD方法"),
            self.tr("选择VAD检测方法"),
            [self.tr(method.value) for method in VadMethodEnum],
            self.vad_group,
        )

        # Other settings group
        self.other_group = SettingCardGroup(self.tr("其他设置"), self)

        # Audio denoise
        self.ff_mdx_kim2_card = SwitchSettingCard(
            FIF.MUSIC,
            self.tr("人声分离"),
            self.tr("处理前使用MDX-Net降噪，分离人声和背景音乐"),
            cfg.faster_whisper_ff_mdx_kim2,
            self.other_group,
        )

        # Word timestamps
        self.one_word_card = SwitchSettingCard(
            FIF.UNIT,
            self.tr("单字时间戳"),
            self.tr("开启生成单字级时间戳；关闭后使用原始分段断句"),
            cfg.faster_whisper_one_word,
            self.other_group,
        )

        # Prompt
        self.prompt_card = LineEditSettingCard(
            cfg.faster_whisper_prompt,
            FIF.CHAT,
            self.tr("提示词"),
            self.tr("可选的提示词,默认空"),
            "",
            self.other_group,
        )

        # Cards of the model group
        self.setting_group.addSettingCard(self.model_card)
        self.setting_group.addSettingCard(self.manage_model_card)
        self.setting_group.addSettingCard(self.device_card)
        self.setting_group.addSettingCard(self.language_card)

        # Cards of the VAD group
        self.vad_group.addSettingCard(self.vad_filter_card)
        self.vad_group.addSettingCard(self.vad_threshold_card)
        self.vad_group.addSettingCard(self.vad_method_card)

        # Cards of the other settings group
        self.other_group.addSettingCard(self.ff_mdx_kim2_card)
        self.other_group.addSettingCard(self.one_word_card)
        self.other_group.addSettingCard(self.prompt_card)

        # Add every group to the container layout
        self.containerLayout.addWidget(self.setting_group)
        self.containerLayout.addWidget(self.vad_group)
        self.containerLayout.addWidget(self.other_group)
        self.containerLayout.addStretch(1)

        # Minimum widget width
        self.model_card.comboBox.setMinimumWidth(200)
        self.device_card.comboBox.setMinimumWidth(200)
        self.language_card.comboBox.setMinimumWidth(200)
        self.vad_method_card.comboBox.setMinimumWidth(200)
        self.prompt_card.lineEdit.setMinimumWidth(200)

        # Scroll area
        self.scrollArea.setWidget(self.container)
        self.scrollArea.setWidgetResizable(True)
        self.scrollArea.enableTransparentBackground()
        self.scrollArea.viewport().setAttribute(
            Qt.WA_TranslucentBackground, True  # type: ignore
        )
        self.container.setAttribute(Qt.WA_TranslucentBackground, True)  # type: ignore

        # Add the scroll area to the main layout
        self.main_layout.addWidget(self.scrollArea)

    def _connect_signals(self):
        """Connect signals."""
        self.manage_model_card.linkButton.clicked.connect(self._show_model_manager)
        self.vad_filter_card.checkedChanged.connect(self._on_vad_filter_changed)

    def _on_vad_filter_changed(self, checked: bool):
        """Handle the VAD filter switch changing."""
        self.vad_threshold_card.setEnabled(checked)
        self.vad_method_card.setEnabled(checked)

    def _show_model_manager(self):
        """Show the model management dialog."""
        dialog = FasterWhisperDownloadDialog(self.window(), self)
        dialog.exec_()
        self.refresh_model_options()
        has_program, _ = check_faster_whisper_exists()
        self._missing_program_warned = not has_program

    def refresh_model_options(self):
        """Refresh the model combo from the models that exist on disk."""
        available = available_faster_whisper_models()
        current_value = cfg.faster_whisper_model.value
        combo = self.model_card.comboBox

        combo.blockSignals(True)
        combo.clear()
        combo.setEnabled(bool(available))
        self.model_card.optionToText = {
            model: self.tr(model.value) for model in available
        }
        for model in available:
            combo.addItem(self.tr(model.value), userData=model)

        selected = current_value if current_value in available else None
        if selected:
            combo.setCurrentText(self.model_card.optionToText[selected])
        elif available:
            selected = available[0]
            combo.setCurrentIndex(0)
        combo.blockSignals(False)

        if selected and current_value != selected:
            cfg.set(cfg.faster_whisper_model, selected)
        if not selected:
            combo.setPlaceholderText(self.tr("Chưa có mô hình đã tải"))

    def show_error_info(self, error_msg):
        """Show an error message."""
        InfoBar.error(
            title=self.tr("错误"),
            content=error_msg,
            parent=self.window(),
            duration=5000,
            position=InfoBarPosition.BOTTOM,
        )

    def show_warning_info(self, warning_msg):
        """Show a non-blocking notice."""
        InfoBar.warning(
            title=self.tr("提示"),
            content=warning_msg,
            parent=self.window(),
            duration=5000,
            position=InfoBarPosition.BOTTOM,
        )

    def check_faster_whisper_model(self):
        """Check that the selected Faster Whisper model exists.

        Returns:
            bool: True when the model exists and is configured, else False
        """
        # Program present?
        has_program, _ = check_faster_whisper_exists()
        if not has_program:
            self.show_error_info(self.tr("Faster Whisper程序不存在，请先下载程序"))
            return False

        model_value = cfg.faster_whisper_model.value.value
        # Model configured?
        model_config = next(
            (
                m
                for m in FASTER_WHISPER_MODELS
                if m["label"].lower() == model_value.lower()
            ),
            None,
        )
        if not model_config:
            self.show_error_info(self.tr("模型配置不存在"))
            return False

        # Model file present?
        if not is_faster_whisper_model_downloaded(model_config):
            self.show_error_info(self.tr("模型文件不存在: ") + model_value)
            return False
        return True

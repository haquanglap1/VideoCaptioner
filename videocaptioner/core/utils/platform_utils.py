"""
Cross-platform helpers: launchers, subprocess flags and platform checks.
"""

import logging
import os
import platform
import subprocess
import sys

from videocaptioner.core.entities import TranscribeModelEnum
from videocaptioner.core.utils.subprocess_helper import child_environment

logger = logging.getLogger(__name__)


def is_onedir_frozen_build() -> bool:
    """True when running from a PyInstaller onedir bundle (exe + ``_internal/``).

    Onedir builds set ``sys._MEIPASS`` to the ``_internal`` directory beside the
    executable (PyInstaller 6) or to the executable directory itself (older
    versions); onefile builds extract to a temporary ``_MEIxxxx`` folder instead.
    Swapping only the exe of an onedir build leaves it paired with stale
    ``_internal`` files, so the updater uses this to refuse in-place replacement.
    """
    if not getattr(sys, "frozen", False):
        return False
    bundle_root = getattr(sys, "_MEIPASS", None)
    if not bundle_root:
        return False
    bundle = os.path.abspath(str(bundle_root))
    exe_dir = os.path.abspath(os.path.dirname(sys.executable))
    return bundle == exe_dir or os.path.dirname(bundle) == exe_dir


def open_folder(path):
    """
    Open a folder in the platform file manager.

    Args:
        path: folder to open
    """
    system = platform.system()

    if system == "Windows":
        if hasattr(os, "startfile"):
            getattr(os, "startfile")(path)
        else:
            subprocess.Popen(["explorer", path], env=child_environment())
    elif system == "Darwin":  # macOS
        subprocess.Popen(["open", path], env=child_environment())
    elif system == "Linux":
        subprocess.Popen(["xdg-open", path], env=child_environment())
    else:
        # Unknown platform: try the freedesktop opener
        try:
            subprocess.Popen(["xdg-open", path], env=child_environment())
        except (OSError, subprocess.SubprocessError):
            logger.warning(f"Cannot open folder on current system: {path}")


def reveal_in_explorer(file_path):
    """Show a file selected in the platform file manager."""
    system = platform.system()
    try:
        if system == "Windows":
            subprocess.Popen(["explorer", "/select,", os.path.normpath(file_path)], env=child_environment())
        elif system == "Darwin":
            subprocess.Popen(["open", "-R", file_path], env=child_environment())
        else:
            # Linux has no portable "select file" action; open the parent folder
            subprocess.Popen(["xdg-open", os.path.dirname(file_path)], env=child_environment())
    except (OSError, subprocess.SubprocessError):
        logger.warning(f"can not reveal in explorer: {file_path}")


def open_file(path):
    """
    Open a file with its default application.

    Args:
        path: file to open
    """
    system = platform.system()

    if system == "Windows":
        if hasattr(os, "startfile"):
            getattr(os, "startfile")(path)
        else:
            subprocess.Popen(["cmd", "/c", "start", "", path], env=child_environment())
    elif system == "Darwin":  # macOS
        subprocess.Popen(["open", path], env=child_environment())
    elif system == "Linux":
        subprocess.Popen(["xdg-open", path], env=child_environment())
    else:
        # Unknown platform: try the freedesktop opener
        try:
            subprocess.Popen(["xdg-open", path], env=child_environment())
        except (OSError, subprocess.SubprocessError):
            logger.warning(f"Cannot open file on current system: {path}")


def get_subprocess_kwargs():
    """
    Extra keyword arguments for subprocess calls on this platform.

    Returns:
        dict: kwargs to splat into subprocess.run/Popen
    """
    kwargs = {}

    # CREATE_NO_WINDOW only exists (and matters) on Windows
    if platform.system() == "Windows":
        if hasattr(subprocess, "CREATE_NO_WINDOW"):
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)

    return kwargs


def is_macos() -> bool:
    """
    Whether the current platform is macOS.

    Returns:
        bool: True on macOS
    """
    return platform.system() == "Darwin"


def is_windows() -> bool:
    """
    Whether the current platform is Windows.

    Returns:
        bool: True on Windows
    """
    return platform.system() == "Windows"


def is_linux() -> bool:
    """
    Whether the current platform is Linux.

    Returns:
        bool: True on Linux
    """
    return platform.system() == "Linux"


def get_available_transcribe_models() -> list[TranscribeModelEnum]:
    """
    Transcription models usable on this platform.

    FasterWhisper is unavailable on macOS because it depends on CUDA/cuDNN.

    Returns:
        list[TranscribeModelEnum]: models that can run here
    """
    all_models = list(TranscribeModelEnum)

    # FasterWhisper cannot run on macOS
    if is_macos():
        return [
            model for model in all_models if model != TranscribeModelEnum.FASTER_WHISPER
        ]

    return all_models


def is_model_available(model: TranscribeModelEnum) -> bool:
    """
    Whether a transcription model can run on this platform.

    Args:
        model: model to check

    Returns:
        bool: True when the model is usable here
    """
    # FasterWhisper is unavailable on macOS
    if is_macos() and model == TranscribeModelEnum.FASTER_WHISPER:
        return False

    return True

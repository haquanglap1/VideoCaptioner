import logging
import os
import sys
from pathlib import Path

try:
    from videocaptioner._version import __version__ as _raw_version
    # Strip dev suffix (e.g. "1.5.0.dev103+g38544177c" → "1.5.0")
    VERSION = _raw_version.split(".dev")[0]
except Exception:
    VERSION = "0.0.0-dev"
YEAR = 2026
APP_NAME = "VideoCaptioner"
AUTHOR = "Weifeng"

HELP_URL = "https://github.com/WEIFENG2333/VideoCaptioner"
GITHUB_REPO_URL = "https://github.com/WEIFENG2333/VideoCaptioner"
RELEASE_URL = "https://github.com/WEIFENG2333/VideoCaptioner/releases/latest"
FEEDBACK_URL = "https://github.com/WEIFENG2333/VideoCaptioner/issues"

# GitHub Auto-Update Configuration
GITHUB_OWNER = "haquanglap1"
GITHUB_REPO = "VideoCaptioner"

# Detect whether running from source tree or pip-installed
_PACKAGE_DIR = Path(__file__).parent
_PROJECT_ROOT = _PACKAGE_DIR.parent
_IS_FROZEN = getattr(sys, "frozen", False)

# Development mode: resource/ exists next to the package
_IS_DEV = (_PROJECT_ROOT / "resource").is_dir()

if _IS_FROZEN:
    _BUNDLE_ROOT = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    ROOT_PATH = Path(sys.executable).resolve().parent
    RESOURCE_PATH = _BUNDLE_ROOT / "resource"
    APPDATA_PATH = ROOT_PATH / "AppData"
    WORK_PATH = ROOT_PATH / "work-dir"
elif _IS_DEV:
    ROOT_PATH = _PROJECT_ROOT
    RESOURCE_PATH = ROOT_PATH / "resource"
    APPDATA_PATH = ROOT_PATH / "AppData"
    WORK_PATH = ROOT_PATH / "work-dir"
else:
    # Installed via pip — use platform-appropriate directories
    from platformdirs import user_data_dir

    ROOT_PATH = Path(user_data_dir(APP_NAME))
    RESOURCE_PATH = ROOT_PATH / "resource"
    APPDATA_PATH = ROOT_PATH
    WORK_PATH = Path.home() / "VideoCaptioner"

BIN_PATH = APPDATA_PATH / "bin"
LEGACY_BIN_PATH = RESOURCE_PATH / "bin"
ASSETS_PATH = RESOURCE_PATH / "assets"
SUBTITLE_STYLE_PATH = RESOURCE_PATH / "subtitle_style"
TRANSLATIONS_PATH = RESOURCE_PATH / "translations"
FONTS_PATH = RESOURCE_PATH / "fonts"

# Fallback: bundled fonts inside the package (for pip install)
_BUNDLED_FONTS = _PACKAGE_DIR / "resources" / "fonts"
if not FONTS_PATH.exists() and _BUNDLED_FONTS.exists():
    FONTS_PATH = _BUNDLED_FONTS

# Fallback: bundled translations inside the package (for pip install)
_BUNDLED_TRANSLATIONS = _PACKAGE_DIR / "resources" / "translations"
if not TRANSLATIONS_PATH.exists() and _BUNDLED_TRANSLATIONS.exists():
    TRANSLATIONS_PATH = _BUNDLED_TRANSLATIONS

LOG_PATH = APPDATA_PATH / "logs"
LLM_LOG_FILE = LOG_PATH / "llm_requests.jsonl"
SETTINGS_PATH = APPDATA_PATH / "settings.json"
CACHE_PATH = APPDATA_PATH / "cache"
MODEL_PATH = APPDATA_PATH / "models"

FASTER_WHISPER_PATH = BIN_PATH / "Faster-Whisper-XXL"
LEGACY_FASTER_WHISPER_PATH = LEGACY_BIN_PATH / "Faster-Whisper-XXL"

# Logging
LOG_LEVEL = logging.INFO
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

# Add bin paths to PATH (only if they exist)
for _bin_dir in (
    FASTER_WHISPER_PATH,
    BIN_PATH,
    BIN_PATH / "ffmpeg",
    LEGACY_FASTER_WHISPER_PATH,
    LEGACY_BIN_PATH,
):
    if _bin_dir.exists():
        os.environ["PATH"] = str(_bin_dir) + os.pathsep + os.environ["PATH"]

# Create data directories
for p in [CACHE_PATH, LOG_PATH, WORK_PATH, MODEL_PATH]:
    p.mkdir(parents=True, exist_ok=True)

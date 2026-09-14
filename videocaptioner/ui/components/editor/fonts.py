"""Register the existing bundled fonts once in the Qt application."""

from functools import lru_cache

from PyQt5.QtGui import QFontDatabase

from videocaptioner.config import FONTS_PATH


@lru_cache(maxsize=1)
def load_editor_fonts() -> None:
    for name in ("NotoSansSC-Regular.ttf", "LXGWWenKai-Regular.ttf"):
        path = FONTS_PATH / name
        if path.is_file():
            QFontDatabase.addApplicationFont(str(path))

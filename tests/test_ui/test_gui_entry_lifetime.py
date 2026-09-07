"""The function entry point must not collect Qt's application or translators early."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from videocaptioner.core.utils.subprocess_helper import child_environment


@pytest.mark.parametrize("locale", ["vi_VN", "en_US"])
def test_application_and_translators_outlive_main_scope(tmp_path, locale):
    repo = Path(__file__).resolve().parents[2]
    script = r'''
import gc
import json
from pathlib import Path
import sys
import weakref

repo, scratch, locale = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
sys.path.insert(0, str(repo))
sys.dont_write_bytecode = True
# Resolve all mutable app paths into this test's scratch before importing the GUI.
original_executable = sys.executable
sys.frozen, sys._MEIPASS, sys.executable = True, str(repo), str(scratch / "host.exe")
import videocaptioner.config
sys.executable = original_executable
del sys.frozen
del sys._MEIPASS

from PyQt5 import sip
from PyQt5.QtCore import QLocale, QTimer
from PyQt5.QtWidgets import QApplication, QWidget
from videocaptioner.ui.common.config import Language, cfg
import videocaptioner.ui.view.main_window as window_module
from videocaptioner.ui.main import main

cfg.set(cfg.language, Language(QLocale(locale)))
translators, windows, observations = [], [], []
install_translator = QApplication.installTranslator
def observe_install(application, translator):
    translators.append(weakref.ref(translator))
    return install_translator(translator)
QApplication.installTranslator = observe_install

class Window(QWidget):
    def __init__(self):
        super().__init__()
        # Model a callback retaining a widget after the entrypoint's frame unwinds.
        windows.append(self)

    def show(self):
        super().show()
        def leave():
            observations.append(all(ref() is not None and not sip.isdeleted(ref()) for ref in translators))
            self.close()
        QTimer.singleShot(0, leave)

window_module.MainWindow = Window
try:
    main()
except SystemExit as error:
    assert error.code == 0
gc.collect()
result = {
    "translator_count": len(translators),
    "translators_alive_in_event_loop": observations == [True],
    "application_alive_after_main": QApplication.instance() is not None,
    "retained_widget_alive_after_main": not sip.isdeleted(windows[0]),
}
print(json.dumps(result), flush=True)
assert result["translator_count"] == 2
assert all(value for key, value in result.items() if key != "translator_count")
'''
    env = child_environment({"QT_QPA_PLATFORM": "offscreen"})
    result = subprocess.run(
        [sys.executable, "-I", "-c", script, str(repo), str(tmp_path), locale],
        cwd=tmp_path, env=env, capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=30,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0,
    )
    assert result.returncode == 0, f"GUI lifecycle child exited {result.returncode}:\n{result.stdout}\n{result.stderr}"

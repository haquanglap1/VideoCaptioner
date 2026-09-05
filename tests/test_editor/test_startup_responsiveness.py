import os
import subprocess
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# The child process does not get the root conftest's cfg.file redirect, and the
# views call cfg.set() while wiring, which would rewrite the developer's real
# AppData/settings.json with whatever the script assigned to cfg items.
_ISOLATE_SETTINGS = """
from pathlib import Path as _SettingsPath
from videocaptioner.ui.common.config import cfg as _cfg
_cfg.file = _SettingsPath({settings!r})
"""


def _run_script(script: str, *, offscreen: bool = False) -> subprocess.CompletedProcess:
    environment = os.environ.copy()
    if offscreen:
        environment["QT_QPA_PLATFORM"] = "offscreen"
    settings = os.path.join(tempfile.mkdtemp(prefix="vc-settings-"), "settings.json")
    return subprocess.run(
        [sys.executable, "-c", _ISOLATE_SETTINGS.format(settings=settings) + script],
        cwd=PROJECT_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


def test_main_window_defers_heavy_navigation_pages():
    result = _run_script(
        """
from PyQt5.QtWidgets import QApplication
from videocaptioner.ui.view.main_window import MainWindow
app = QApplication([])
MainWindow._start_background_services = lambda self: None
window = MainWindow()
assert window.homeInterface.content is None
assert window.videoEditorInterface.content is None
app.processEvents()
home = window.homeInterface.content
assert home is not None
assert sorted(home._interfaces) == ['TaskCreationInterface']
assert window.videoEditorInterface.content is None
assert window.subtitleStyleInterface.content is None
assert window.settingInterface.content is None
""",
        offscreen=True,
    )
    assert result.returncode == 0, result.stderr


def test_transcription_page_does_not_eagerly_create_provider_settings():
    result = _run_script(
        """
from PyQt5.QtWidgets import QApplication
from videocaptioner.core.entities import TranscribeModelEnum
from videocaptioner.ui.common.config import cfg
from videocaptioner.ui.view.main_window import MainWindow
app = QApplication([])
cfg.transcribe_model.value = TranscribeModelEnum.BIJIAN
MainWindow._start_background_services = lambda self: None
window = MainWindow()
app.processEvents()
home = window.homeInterface.content
home._activate_interface('TranscriptionInterface')
app.processEvents()
transcription = home.transcription_interface
assert transcription.transcription_setting_card._widgets == {}
assert sorted(home._interfaces) == ['TaskCreationInterface', 'TranscriptionInterface']
""",
        offscreen=True,
    )
    assert result.returncode == 0, result.stderr


def test_segmented_click_loads_and_switches_transcription_page():
    result = _run_script(
        """
from PyQt5.QtWidgets import QApplication
from videocaptioner.ui.view.main_window import MainWindow
app = QApplication([])
MainWindow._start_background_services = lambda self: None
window = MainWindow()
app.processEvents()
home = window.homeInterface.content
home.pivot.items['TranscriptionInterface'].click()
app.processEvents()
current = home.stackedWidget.currentWidget()
assert current is home.transcription_interface
assert current.objectName() == 'TranscriptionInterface'
""",
        offscreen=True,
    )
    assert result.returncode == 0, result.stderr


def test_subtitle_style_scroll_surface_inherits_dark_background():
    result = _run_script(
        """
from PyQt5.QtWidgets import QApplication, QVBoxLayout, QWidget
from videocaptioner.ui.view.subtitle_style_interface import SubtitleStyleInterface
app = QApplication([])
root = QWidget()
root.setObjectName('DarkRoot')
root.setStyleSheet('QWidget#DarkRoot{background:#202020;}')
layout = QVBoxLayout(root)
layout.setContentsMargins(0, 0, 0, 0)
page = SubtitleStyleInterface(root)
layout.addWidget(page)
root.resize(1100, 800)
root.show()
for _ in range(4):
    app.processEvents()
color = root.grab().toImage().pixelColor(100, 100)
assert max(color.red(), color.green(), color.blue()) < 100, color.name()
""",
        offscreen=True,
    )
    assert result.returncode == 0, result.stderr


def test_settings_scroll_surface_inherits_dark_background():
    result = _run_script(
        """
from PyQt5.QtWidgets import QApplication, QVBoxLayout, QWidget
from qfluentwidgets import Theme, setTheme
from videocaptioner.ui.view.setting_interface import SettingInterface
app = QApplication([])
setTheme(Theme.DARK)
root = QWidget()
root.setObjectName('DarkRoot')
root.setStyleSheet('QWidget#DarkRoot{background:#202020;}')
layout = QVBoxLayout(root)
layout.setContentsMargins(0, 0, 0, 0)
page = SettingInterface(root)
layout.addWidget(page)
root.resize(1000, 800)
root.show()
for _ in range(4):
    app.processEvents()
image = root.grab().toImage()
for x, y in ((20, 100), (100, 220), (980, 400)):
    color = image.pixelColor(x, y)
    assert max(color.red(), color.green(), color.blue()) < 100, (x, y, color.name())
""",
        offscreen=True,
    )
    assert result.returncode == 0, result.stderr


def test_transcription_model_scroll_surfaces_are_transparent():
    result = _run_script(
        """
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication
from videocaptioner.ui.components.FasterWhisperSettingWidget import FasterWhisperSettingWidget
from videocaptioner.ui.components.WhisperCppSettingWidget import WhisperCppSettingWidget
app = QApplication([])
pages = [FasterWhisperSettingWidget(), WhisperCppSettingWidget()]
for page in pages:
    assert page.scrollArea.viewport().testAttribute(Qt.WA_TranslucentBackground)
    assert page.container.testAttribute(Qt.WA_TranslucentBackground)
""",
        offscreen=True,
    )
    assert result.returncode == 0, result.stderr


def test_settings_exposes_clickable_faster_whisper_model_manager():
    result = _run_script(
        """
from PyQt5.QtCore import Qt
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QApplication
from videocaptioner.core.entities import TranscribeModelEnum
from videocaptioner.ui.common.config import cfg
from videocaptioner.ui.view.setting_interface import SettingInterface
app = QApplication([])
cfg.transcribe_model.value = TranscribeModelEnum.FASTER_WHISPER
opened = []
SettingInterface._SettingInterface__showFasterWhisperManager = lambda self: opened.append(True)
page = SettingInterface()
page.resize(1000, 800)
page.show()
for _ in range(4):
    app.processEvents()
card = page.fasterWhisperManagerCard
assert card.isVisible()
assert card.button.isEnabled()
QTest.mouseClick(card.button, Qt.LeftButton)
app.processEvents()
assert opened == [True]
""",
        offscreen=True,
    )
    assert result.returncode == 0, result.stderr


def test_faster_whisper_download_dialog_buttons_are_clickable():
    result = _run_script(
        """
from PyQt5.QtCore import Qt
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QApplication, QWidget
from qfluentwidgets import HyperlinkButton
import videocaptioner.ui.components.FasterWhisperSettingWidget as module
app = QApplication([])
root = QWidget()
root.resize(1000, 800)
module.check_faster_whisper_exists = lambda: (False, [])
clicked = []
module.FasterWhisperDownloadDialog._start_download = lambda self: clicked.append('program')
dialog = module.FasterWhisperDownloadDialog(root)
dialog.show()
for _ in range(4):
    app.processEvents()
QTest.mouseClick(dialog.program_download_btn, Qt.LeftButton)
dialog._download_model = lambda row: clicked.append(('model', row))
model_button = dialog.model_table.cellWidget(0, 3).findChild(HyperlinkButton)
assert model_button is not None and model_button.isEnabled()
QTest.mouseClick(model_button, Qt.LeftButton)
app.processEvents()
assert clicked == ['program', ('model', 0)]
""",
        offscreen=True,
    )
    assert result.returncode == 0, result.stderr


def test_faster_whisper_probe_is_bounded_and_read_only(tmp_path, monkeypatch):
    import videocaptioner.ui.components.FasterWhisperSettingWidget as module

    bin_path = tmp_path / "bin"
    model_path = tmp_path / "models"
    bin_path.mkdir()
    model_path.mkdir()
    invalid_program = bin_path / "faster-whisper.exe"
    invalid_program.write_bytes(b"not-an-executable")

    monkeypatch.setattr(module, "BIN_PATH", bin_path)
    monkeypatch.setattr(module, "LEGACY_BIN_PATH", tmp_path / "legacy-bin")
    monkeypatch.setattr(module, "MODEL_PATH", model_path)

    has_program, versions = module.check_faster_whisper_exists()
    assert not has_program
    assert versions == []
    assert invalid_program.exists()

    model = {"value": "faster-whisper-test"}
    snapshot = model_path / model["value"] / "snapshots" / "abc123"
    snapshot.mkdir(parents=True)
    (snapshot / "model.bin").write_bytes(b"model")
    assert module.is_faster_whisper_model_downloaded(model)

    too_deep = model_path / "faster-whisper-deep"
    cursor = too_deep
    for part in ("a", "b", "c", "d", "e", "f"):
        cursor /= part
    cursor.mkdir(parents=True)
    (cursor / "model.bin").write_bytes(b"model")
    assert not module.is_faster_whisper_model_downloaded(
        {"value": "faster-whisper-deep"}
    )


def test_lightweight_config_import_does_not_load_provider_sdks():
    result = _run_script(
        "import sys; import videocaptioner.ui.common.config; "
        "blocked={'openai','yt_dlp','modelscope'}; "
        "loaded=blocked.intersection(sys.modules); "
        "assert not loaded, sorted(loaded)"
    )
    assert result.returncode == 0, result.stderr

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_video_editor_has_no_pyside6_or_mpv_dependency():
    source = "\n".join(
        path.read_text(encoding="utf-8", errors="replace")
        for path in (ROOT / "videocaptioner").rglob("*.py")
    )
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "PySide6" not in source
    assert "import mpv" not in source
    assert "pyside6" not in pyproject.casefold()
    assert "python-mpv" not in pyproject.casefold()


def test_editor_workers_do_not_import_widgets():
    for filename in ("editor_media_thread.py", "editor_voice_thread.py"):
        source = (ROOT / "videocaptioner" / "ui" / "thread" / filename).read_text(
            encoding="utf-8"
        )
        assert "QtWidgets" not in source
        assert "QWidget" not in source


def test_navigation_order_is_subtitle_style_editor_request_logs():
    source = (
        ROOT / "videocaptioner" / "ui" / "view" / "main_window.py"
    ).read_text(encoding="utf-8")
    style = source.index("self.addSubInterface(self.subtitleStyleInterface")
    editor = source.index("self.addSubInterface(self.videoEditorInterface")
    logs = source.index("self.addSubInterface(self.llmLogsInterface")
    assert style < editor < logs


def test_pyinstaller_collects_new_editor_modules_without_new_runtime_assets():
    spec = (ROOT / "VideoCaptioner.spec").read_text(encoding="utf-8")
    assert 'collect_submodules("videocaptioner")' in spec
    assert r"videocaptioner\\resources" in spec

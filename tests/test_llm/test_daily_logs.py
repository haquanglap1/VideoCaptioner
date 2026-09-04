import json
import logging
from datetime import datetime

from PyQt5.QtWidgets import QApplication

from videocaptioner.core.llm import request_logger
from videocaptioner.core.utils.log_files import (
    LEGACY_LLM_LOG_KEY,
    available_llm_log_days,
    daily_app_log_path,
    daily_llm_log_path,
    llm_log_files_for_day,
    rotate_size_limited_file,
)
from videocaptioner.core.utils.logger import DailySizeRotatingFileHandler

_QT_APP = None


def _qt_application() -> QApplication:
    # Keep a module-level reference. A QApplication held only by a local is
    # collected when the test returns and takes qfluentwidgets' global qconfig
    # with it, which breaks every Qt test that runs later in the same session.
    global _QT_APP
    _QT_APP = QApplication.instance() or QApplication([])
    return _QT_APP


def test_daily_paths_are_stable():
    moment = datetime(2026, 8, 21, 23, 59)
    assert daily_app_log_path("logs", moment.strftime("%Y-%m-%d")).name == "app-2026-08-21.log"
    assert daily_llm_log_path("logs", moment.strftime("%Y-%m-%d")).name == "llm_requests-2026-08-21.jsonl"


def test_size_rotation_is_bounded_per_day(tmp_path):
    path = daily_llm_log_path(tmp_path, "2026-08-21")
    path.write_text("first", encoding="utf-8")
    rotate_size_limited_file(path, max_bytes=1, backup_count=2)
    assert not path.exists()
    assert path.with_name(f"{path.name}.1").read_text(encoding="utf-8") == "first"

    path.write_text("second", encoding="utf-8")
    rotate_size_limited_file(path, max_bytes=1, backup_count=2)
    assert path.with_name(f"{path.name}.1").read_text(encoding="utf-8") == "second"
    assert path.with_name(f"{path.name}.2").read_text(encoding="utf-8") == "first"


def test_day_discovery_keeps_legacy_readable(tmp_path):
    daily_llm_log_path(tmp_path, "2026-08-20").write_text("{}\n", encoding="utf-8")
    (tmp_path / "llm_requests.jsonl").write_text("{}\n", encoding="utf-8")
    days = available_llm_log_days(tmp_path, include_today=False)
    assert days == ["2026-08-20", LEGACY_LLM_LOG_KEY]
    assert llm_log_files_for_day(LEGACY_LLM_LOG_KEY, tmp_path) == [
        tmp_path / "llm_requests.jsonl"
    ]


def test_request_logger_writes_daily_file_not_legacy(tmp_path, monkeypatch):
    monkeypatch.setattr(request_logger, "LOG_PATH", tmp_path)
    request_logger._write_log({"time": "2026-08-21 10:00:00", "request": {}})
    daily = daily_llm_log_path(tmp_path)
    assert daily.is_file()
    assert json.loads(daily.read_text(encoding="utf-8"))["request"] == {}
    assert not (tmp_path / "llm_requests.jsonl").exists()


def test_daily_app_handler_writes_current_date(tmp_path):
    handler = DailySizeRotatingFileHandler(tmp_path, max_bytes=1024, backup_count=1)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger = logging.Logger("daily-test")
    logger.addHandler(handler)
    logger.warning("hello")
    handler.close()
    assert daily_app_log_path(tmp_path).read_text(encoding="utf-8").strip() == "hello"


def test_log_interface_loads_only_selected_day(tmp_path, monkeypatch):
    from videocaptioner.core.utils import log_files
    from videocaptioner.ui.view import llm_logs_interface

    app = _qt_application()

    first = daily_llm_log_path(tmp_path, "2026-08-20")
    second = daily_llm_log_path(tmp_path, "2026-08-21")
    first.write_text(json.dumps({"time": "2026-08-20 10:00:00", "task_id": "old"}) + "\n", encoding="utf-8")
    second.write_text(json.dumps({"time": "2026-08-21 10:00:00", "task_id": "new"}) + "\n", encoding="utf-8")
    monkeypatch.setattr(llm_logs_interface, "LOG_PATH", tmp_path)
    # The day list always includes "today"; pin it so the test does not depend on the clock.
    monkeypatch.setattr(log_files, "local_day", lambda value=None: "2026-08-21")

    widget = llm_logs_interface.LLMLogsInterface()
    try:
        assert widget._available_days[:2] == ["2026-08-21", "2026-08-20"]
        assert [entry["task_id"] for entry in widget.all_logs] == ["new"]
        widget.date_combo.setCurrentIndex(widget._available_days.index("2026-08-20"))
        assert [entry["task_id"] for entry in widget.all_logs] == ["old"]
    finally:
        widget.close()
        app.processEvents()

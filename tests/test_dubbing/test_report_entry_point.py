# pyright: reportAttributeAccessIssue=false
"""The dubbing report must never open by itself; it blocked the pipeline behind a modal."""

import sys

import pytest
from PyQt5.QtCore import QThread
from PyQt5.QtWidgets import QApplication

from videocaptioner.core.entities import DubbingTask
from videocaptioner.ui.view import dubbing_interface as dubbing_module
from videocaptioner.ui.view.dubbing_interface import DubbingInterface


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication(sys.argv)
    yield app


@pytest.fixture
def no_dialog(monkeypatch):
    """Record every dialog construction instead of showing one."""
    opened: list[dict] = []

    class RecordingDialog:
        def __init__(self, data, parent=None):
            opened.append(data)

        def exec_(self):
            return 0

    monkeypatch.setattr(dubbing_module, "DubbingReportDialog", RecordingDialog)
    return opened


def _report(review: int = 0, failed: int = 0, warnings: int = 0) -> dict:
    groups = [{"group_id": "g0", "fit_status": "fit", "warnings": []}]
    groups += [{"group_id": f"r{i}", "fit_status": "needs-review", "needs_review": True} for i in range(review)]
    groups += [{"group_id": f"f{i}", "fit_status": "failed"} for i in range(failed)]
    groups += [{"group_id": f"w{i}", "fit_status": "fit", "warnings": ["overlap trimmed"]} for i in range(warnings)]
    return {
        "schema_version": "dubbing-report-v1",
        "summary": {"total_groups": len(groups), "review_groups": review, "failed_groups": failed},
        "groups": groups,
    }


def test_finishing_a_dub_never_opens_the_report_dialog(qapp, no_dialog):
    widget = DubbingInterface()
    try:
        widget._thread = QThread(widget)
        widget._on_report_ready(_report(review=2))
        widget._on_finished(DubbingTask(video_path="v.mp4", output_path="out.mp4"))
        widget._on_dubbing_stopped()
        assert no_dialog == []
        assert widget._pending_report_data["summary"]["review_groups"] == 2
    finally:
        widget.close()


def test_failing_a_dub_never_opens_the_report_dialog(qapp, no_dialog):
    widget = DubbingInterface()
    try:
        widget._thread = QThread(widget)
        widget._on_report_ready(_report(failed=1))
        widget._on_error("provider produced no audio")
        widget._on_dubbing_stopped()
        assert no_dialog == []
    finally:
        widget.close()


def test_pipeline_advances_without_waiting_for_a_dialog(qapp, no_dialog):
    widget = DubbingInterface()
    emitted: list[tuple] = []
    try:
        widget._thread = QThread(widget)
        widget.finished.connect(lambda video, subtitle: emitted.append((video, subtitle)))
        widget._is_pipeline_mode = True
        widget._on_report_ready(_report(review=3))
        widget._on_finished(
            DubbingTask(video_path="v.mp4", output_path="dubbed.mp4", display_subtitle_path="d.srt")
        )
        # Handoff waits for the native thread lifecycle, never a report dialog.
        assert emitted == []
        widget._on_dubbing_stopped()
        assert emitted == [("dubbed.mp4", "d.srt")]
        assert no_dialog == []
    finally:
        widget.close()


def test_report_button_is_the_only_way_in_and_shows_the_warning_count(qapp, no_dialog):
    widget = DubbingInterface()
    try:
        assert widget.report_btn.isVisible() is False
        widget._on_report_ready(_report(review=1, failed=1, warnings=2))
        widget._on_finished(DubbingTask(video_path="v.mp4", output_path="out.mp4"))
        assert widget.report_btn.isEnabled()
        assert "4" in widget.report_btn.text()
        widget.report_btn.click()
        assert len(no_dialog) == 1
        assert no_dialog[0] is widget._pending_report_data
    finally:
        widget.close()


def test_a_clean_report_still_offers_the_entry_point_without_a_warning_count(qapp, no_dialog):
    widget = DubbingInterface()
    try:
        widget._on_report_ready(_report())
        assert widget.report_warning_count(widget._pending_report_data) == 0
        assert widget.report_btn.isEnabled()
        assert "(" not in widget.report_btn.text()
    finally:
        widget.close()


def test_starting_a_new_run_drops_the_previous_report(qapp, no_dialog):
    widget = DubbingInterface()
    try:
        widget._on_report_ready(_report(review=1))
        assert widget.report_btn.isEnabled()
        widget._pending_report_data = {}
        widget._refresh_report_button()
        assert widget.report_btn.isEnabled() is False
        assert widget.report_btn.isVisible() is False
    finally:
        widget.close()

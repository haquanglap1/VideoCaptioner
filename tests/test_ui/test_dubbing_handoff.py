"""Subtitle routing and review boundaries without media or provider work."""

import pytest

from videocaptioner.core.dubbing.config import DubbingConfig
from videocaptioner.core.dubbing.models import DubbingReviewRequired
from videocaptioner.core.entities import DubbingTask
from videocaptioner.ui.thread import dubbing_thread
from videocaptioner.ui.view.dubbing_interface import DubbingInterface


@pytest.mark.parametrize("config", [None, DubbingConfig(enabled=False)])
@pytest.mark.parametrize("separate_display", [False, True])
def test_disabled_dubbing_preserves_display_subtitle(qapp, tmp_path, monkeypatch, config, separate_display):
    spoken = tmp_path / "spoken.vi.srt"
    spoken.write_text("1\n00:00:00,000 --> 00:00:01,000\nXin chào\n", encoding="utf-8")
    display = tmp_path / "display.vi-en.srt" if separate_display else spoken
    if separate_display:
        display.write_text("1\n00:00:00,000 --> 00:00:01,000\nXin chào\nHello\n", encoding="utf-8")
    before = {path: path.read_bytes() for path in {spoken, display}}
    view = DubbingInterface()
    monkeypatch.setattr(view, "_run_dubbing", lambda task: pytest.fail("Disabled dubbing must not start a worker"))
    received = []
    view.finished.connect(lambda video, subtitle: received.append((video, subtitle)))
    view.set_task(DubbingTask(
        video_path="source.mp4", subtitle_path=str(spoken),
        display_subtitle_path=str(display) if separate_display else None,
        dubbing_config=config,
    ))
    try:
        view.process()
        assert received == [("source.mp4", str(display))]
        assert all(path.read_bytes() == contents for path, contents in before.items())
    finally:
        view.close()


@pytest.mark.parametrize("needs_review", [False, True])
def test_worker_report_controls_synthesis_handoff(qapp, monkeypatch, needs_review):
    report = {
        "schema_version": "dubbing-report-v1",
        "summary": {"total_groups": 1, "review_groups": int(needs_review)},
        "groups": [{"group_id": "g-0001", "tts_text": "A shorter spoken sentence."}],
    }

    class ReportEngine:
        last_report_path = ""
        last_report = report

        def dub(self, **kwargs):
            if needs_review:
                raise DubbingReviewRequired()
            return kwargs["output_path"]

    monkeypatch.setattr(dubbing_thread, "DubbingEngine", ReportEngine)
    view = DubbingInterface()
    view.enable_switch.setChecked(True)
    shown, forwarded = [], []
    monkeypatch.setattr(view, "_show_report", lambda **_kwargs: shown.append(view._pending_report_data))
    view.finished.connect(lambda video, subtitle: forwarded.append((video, subtitle)))
    task = DubbingTask(
        video_path="source.mp4", subtitle_path="spoken.vi.srt",
        display_subtitle_path="display.vi-en.srt", output_path="dubbed.mp4",
        dubbing_config=DubbingConfig(enabled=True),
    )
    view.set_task(task)
    try:
        view.process()
        assert view._thread.wait(5000)
        qapp.processEvents()
        assert task.dubbing_report == report
        assert shown == [report]
        assert forwarded == ([] if needs_review else [("dubbed.mp4", "display.vi-en.srt")])
        assert view.manual_dub_btn.isEnabled()
    finally:
        if view._thread and view._thread.isRunning():
            view._thread.requestInterruption()
            view._thread.wait()
        view.close()

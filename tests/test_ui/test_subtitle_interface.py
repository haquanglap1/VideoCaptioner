"""Offscreen regression tests for the subtitle tab's table editing wiring."""

import pytest

from videocaptioner.ui.common import signal_bus

_SRT = (
    "1\n00:00:00,000 --> 00:00:01,000\none\n\n"
    "2\n00:00:01,000 --> 00:00:02,000\ntwo\n\n"
    "3\n00:00:02,000 --> 00:00:03,000\nthree\n"
)


@pytest.fixture
def interface(qapp, tmp_path):
    from videocaptioner.ui.view.subtitle_interface import SubtitleInterface

    subtitle = tmp_path / "clip.srt"
    subtitle.write_text(_SRT, encoding="utf-8")
    view = SubtitleInterface()
    view.load_subtitle_file(str(subtitle))
    yield view
    view.deleteLater()


def _texts(view):
    return [row["original_subtitle"] for row in view.model._data.values()]


def test_load_fills_model(interface):
    assert _texts(interface) == ["one", "two", "three"]
    assert interface.model.rowCount() == 3


def test_merge_and_delete_go_through_the_model(interface):
    interface.merge_selected_rows([0, 1])
    assert _texts(interface) == ["one two", "three"]
    assert list(interface.model._data) == ["1", "2"]
    assert interface.model._data["1"]["end_time"] == 2000

    interface.delete_selected_rows([1])
    assert _texts(interface) == ["one two"]
    assert interface.model.rowCount() == 1


def test_single_row_merge_is_ignored(interface):
    interface.merge_selected_rows([1])
    assert _texts(interface) == ["one", "two", "three"]


def test_row_click_requests_playback_before_cue_end(interface, monkeypatch):
    received = []
    monkeypatch.setattr(
        signal_bus.signalBus,
        "play_video_segment",
        lambda start, end: received.append((start, end)),
    )
    interface.on_subtitle_clicked(interface.model.index(1, 2))
    assert received == [(1000, 1950)]

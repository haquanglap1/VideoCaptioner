"""Cancellation while staging outputs must preserve every existing subtitle."""

from threading import Event, Lock

from videocaptioner.core.asr.asr_data import ASRData, ASRDataSeg
from videocaptioner.core.subtitle.publication import SubtitleOutput, publish_subtitles


def test_cancel_during_staging_preserves_all_outputs(tmp_path, monkeypatch):
    data = ASRData([ASRDataSeg("Synthetic", 0, 1000)])
    first, second = tmp_path / "first.srt", tmp_path / "second.srt"
    first.write_text("prior user output", encoding="utf-8")
    cancelled = Event()
    actual = data.save
    def render(*args, **kwargs):
        actual(*args, **kwargs)
        cancelled.set()
    monkeypatch.setattr(data, "save", render)
    assert not publish_subtitles(data, [SubtitleOutput(str(first)), SubtitleOutput(str(second))], cancelled.is_set, Lock())
    assert first.read_text(encoding="utf-8") == "prior user output"
    assert not second.exists()
    assert list(tmp_path.iterdir()) == [first]

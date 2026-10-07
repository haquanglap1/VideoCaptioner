"""Container length is a best-effort default for the OCR selection, never a timing contract."""

import pytest

from videocaptioner.core.ocr.decoder import _duration_from_probe, probe_duration_ms, probe_video
from videocaptioner.core.ocr.models import OcrError


def test_duration_prefers_container_then_first_usable_stream_value():
    assert _duration_from_probe({"format": {"duration": "12.3456"}, "streams": [{"duration": "5"}]}) == 12346
    assert _duration_from_probe({"format": {}, "streams": [{"duration": "N/A"}, {"duration": "2.5"}]}) == 2500
    assert _duration_from_probe({"streams": [{"duration": "0"}, {"duration": "-1"}, {"duration": "nan"}]}) is None
    assert _duration_from_probe({}) is None


def test_probe_duration_is_best_effort_but_keeps_cancellation(tmp_path):
    missing = tmp_path / "missing.mp4"
    assert probe_duration_ms(missing, ffprobe="not-a-real-ffprobe") is None

    def cancelled():
        raise OcrError("cancelled")

    with pytest.raises(OcrError, match="cancelled"):
        probe_duration_ms(missing, ffprobe="not-a-real-ffprobe", check=cancelled)


def test_probe_duration_matches_generated_fixture(make_video, text_image, ffmpeg_tools):
    _ffmpeg, ffprobe = ffmpeg_tools
    source = make_video([text_image(str(i)) for i in range(5)])
    duration = probe_duration_ms(source, ffprobe)
    assert duration is not None and 300 <= duration <= 1500
    # The identity-bearing probe is unchanged by the extra length lookup.
    assert probe_video(source, ffprobe).geometry.display_size == (640, 120)

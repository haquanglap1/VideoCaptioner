import hashlib
import json
import subprocess
import time
from fractions import Fraction

import pytest
from PIL import Image, ImageDraw

from videocaptioner.core.ocr.decoder import RoiDecoder, probe_video
from videocaptioner.core.ocr.geometry import Roi
from videocaptioner.core.ocr.models import OcrError, Selection
from videocaptioner.core.utils.subprocess_helper import _NO_WINDOW, child_environment


def test_vfr_pts_nonzero_origin_and_selection_hold(make_video, text_image, ffmpeg_tools):
    ffmpeg, ffprobe = ffmpeg_tools
    source = make_video([text_image(str(i)) for i in range(8)], vfr=True, offset=5)
    info = probe_video(source, ffprobe)
    assert info.timeline_origin == 5
    raw = subprocess.run([ffprobe, "-v", "error", "-show_frames", "-select_streams", "v:0",
                          "-show_entries", "frame=pts", "-of", "json", str(source)],
                         env=child_environment(), creationflags=_NO_WINDOW, timeout=10,
                         check=True, capture_output=True)
    pts = [row["pts"] for row in json.loads(raw.stdout)["frames"]]
    decoder = RoiDecoder(source, info, Roi(0, 0, 1, 1), ffmpeg=ffmpeg)
    with decoder:
        frames = list(decoder)
    assert [frame.pts for frame in frames] == pts
    assert [frame.timeline_ms for frame in frames] == [0, 100, 300, 400, 600, 700, 900, 1000]
    with RoiDecoder(source, info, Roi(0, 0, 1, 1), ffmpeg=ffmpeg) as selected:
        spans = list(selected.spans(Selection(150, 850)))
    assert spans[0].frame.pts == pts[1]
    assert spans[0].start_ms == 150 and spans[0].clipped_start
    assert spans[-1].end_ms == 850 and spans[-1].clipped_end
    assert [(s.start_ms, s.end_ms) for s in spans] == [(150, 300), (300, 400), (400, 600), (600, 700), (700, 850)]
    assert all(not reader.is_alive() for reader in decoder.readers + selected.readers)
    measured = decoder.metrics.process_wall_s
    decoder.close()
    assert decoder.metrics.process_wall_s == measured


@pytest.mark.parametrize("offset", [0, 5])
@pytest.mark.parametrize("vfr", [False, True])
def test_seek_replays_exact_source_pts_and_spans(make_video, text_image, ffmpeg_tools, offset, vfr):
    ffmpeg, ffprobe = ffmpeg_tools
    source = make_video([text_image(str(i)) for i in range(30)], vfr=vfr, offset=offset)
    info = probe_video(source, ffprobe)
    selection = Selection(50, 2800)
    with RoiDecoder(source, info, Roi(0, 0, 1, 1), ffmpeg=ffmpeg) as full:
        expected = list(full.spans(selection))
    anchor = expected[12]
    with RoiDecoder(source, info, Roi(0, 0, 1, 1), ffmpeg=ffmpeg,
                    seek_pts=anchor.frame.pts) as resumed:
        actual = list(resumed.spans(selection, start_ms=anchor.start_ms))
    def values(spans):
        return [(s.frame.pts, hashlib.sha256(s.frame.rgb).hexdigest(), s.start_ms, s.end_ms, s.clipped_start,
                 s.clipped_end, s.uncertain_end) for s in spans]
    assert values(actual) == values(expected[12:])
    assert resumed.metrics.frames < full.metrics.frames
    assert resumed.process.poll() is not None and all(not t.is_alive() for t in resumed.readers)


@pytest.mark.parametrize("offset", [0, 5])
def test_seek_preserves_fractional_pts_with_interframe_codec(
        make_video, text_image, ffmpeg_tools, tmp_path, offset):
    ffmpeg, ffprobe = ffmpeg_tools
    original = make_video([text_image(str(i)) for i in range(60)], offset=offset, frame_rate="30000/1001")
    source = tmp_path / "interframe.mov"
    subprocess.run([ffmpeg, "-v", "error", "-nostdin", "-n", "-copyts", "-i", str(original),
                    "-c:v", "libx264", "-g", "12", "-bf", "3", "-threads", "1", "-fps_mode", "passthrough", str(source)],
                   env=child_environment(), creationflags=_NO_WINDOW, check=True, timeout=30,
                   stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    info = probe_video(source, ffprobe)
    with RoiDecoder(source, info, Roi(0, 0, 1, 1), ffmpeg=ffmpeg) as full:
        expected = list(full.spans(Selection(10, 1800)))
    anchor = expected[39]
    assert anchor.start_ms.denominator != 1
    with RoiDecoder(source, info, Roi(0, 0, 1, 1), ffmpeg=ffmpeg, seek_pts=anchor.frame.pts) as resumed:
        actual = list(resumed.spans(Selection(10, 1800), start_ms=anchor.start_ms))
    def values(spans):
        return [(s.frame.pts, hashlib.sha256(s.frame.rgb).hexdigest(), s.start_ms, s.end_ms,
                 s.clipped_start, s.clipped_end, s.uncertain_end) for s in spans]
    assert values(actual) == values(expected[39:])
    assert resumed.metrics.frames < full.metrics.frames


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
def test_decode_sar_rotation_and_odd_roi(make_video, ffmpeg_tools, rotation):
    ffmpeg, ffprobe = ffmpeg_tools
    image = Image.new("RGB", (80, 40), "black")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 39, 19), fill="red")
    draw.rectangle((40, 0, 79, 19), fill="green")
    draw.rectangle((0, 20, 39, 39), fill="blue")
    draw.rectangle((40, 20, 79, 39), fill="yellow")
    source = make_video([image, image], sar="2/1", rotation=rotation)
    info = probe_video(source, ffprobe)
    assert info.geometry.sar == 2 and info.geometry.rotation == rotation
    roi = Roi(0.1, 0.1, 0.2, 0.2)
    with RoiDecoder(source, info, roi, ffmpeg=ffmpeg) as decoder:
        frame = next(iter(decoder))
    expected = {0: (255, 0, 0), 90: (0, 128, 0), 180: (255, 255, 0), 270: (0, 0, 255)}[rotation]
    assert tuple(frame.rgb[:3]) == expected
    rect = roi.pixels(*info.geometry.display_size)
    assert (frame.width, frame.height) == (rect.width, rect.height)


def test_backpressure_cancel_and_early_close(make_video, text_image, ffmpeg_tools):
    ffmpeg, ffprobe = ffmpeg_tools
    source = make_video([text_image(str(i)) for i in range(24)])
    info = probe_video(source, ffprobe)
    cancelled = False

    def check():
        if cancelled:
            raise RuntimeError("test cancelled")

    decoder = RoiDecoder(source, info, Roi(0, 0, 1, 1), ffmpeg=ffmpeg, check=check)
    with pytest.raises(RuntimeError, match="test cancelled"), decoder:
        next(iter(decoder))
        deadline = time.monotonic() + 3
        while decoder.frames.qsize() < 4 and time.monotonic() < deadline:
            time.sleep(0.01)
        assert decoder.frames.qsize() == 4
        assert decoder.metrics.queue_peak <= 4 and decoder.metrics.roi_buffer_bound == 8
        cancelled = True
        next(iter(decoder))
    assert decoder.process.poll() is not None
    assert all(not reader.is_alive() for reader in decoder.readers)


def test_last_frame_duration_stays_uncertain(make_video, text_image, ffmpeg_tools):
    ffmpeg, ffprobe = ffmpeg_tools
    source = make_video([text_image(), text_image()])
    with RoiDecoder(source, probe_video(source, ffprobe), Roi(0, 0, 1, 1), ffmpeg=ffmpeg) as decoder:
        spans = list(decoder.spans(Selection(0, 400)))
    assert spans[-1].uncertain_end
    assert spans[-1].frame.timeline_ms == Fraction(100)


def test_empty_selection_is_not_a_success(make_video, text_image, ffmpeg_tools):
    from videocaptioner.core.ocr.consensus import CacheScope, ReadCache
    from videocaptioner.core.ocr.pipeline import OcrPipeline

    ffmpeg, ffprobe = ffmpeg_tools
    source = make_video([text_image("")] * 4)
    decoder = RoiDecoder(source, probe_video(source, ffprobe), Roi(0, 0, 1, 1), ffmpeg=ffmpeg)
    pipeline = OcrPipeline(lambda *_: pytest.fail("empty ROI must not call recognition"),
                           ReadCache(CacheScope("a" * 64, "b" * 64, "c" * 64)))
    with pytest.raises(OcrError, match="No subtitle region"):
        list(pipeline.run(decoder, Selection(0, 250)))

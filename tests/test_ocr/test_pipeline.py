from contextlib import closing

import pytest

from videocaptioner.core.ocr.consensus import CacheScope, ReadCache
from videocaptioner.core.ocr.decoder import RoiDecoder, probe_video
from videocaptioner.core.ocr.geometry import Roi
from videocaptioner.core.ocr.models import Selection
from videocaptioner.core.ocr.pipeline import OcrPipeline

from .test_consensus import read


def test_streaming_groups_cache_and_raw_review(make_video, text_image, ffmpeg_tools):
    ffmpeg, ffprobe = ffmpeg_tools
    images = [text_image(""), text_image(), text_image(), text_image("学生五人"),
              text_image("学生五人"), text_image(""), text_image(), text_image(), text_image("")]
    source = make_video(images, vfr=True, offset=3)
    decoder = RoiDecoder(source, probe_video(source, ffprobe), Roi(0, 0, 1, 1), ffmpeg=ffmpeg)
    observed = []

    def recognize(frame, check):
        check()
        observed.append(frame.pts)
        # Deliberately a fake engine: integration tests here verify orchestration, not OCR quality.
        return read("fixture-read")

    pipeline = OcrPipeline(recognize, ReadCache(CacheScope("a" * 64, "b" * 64, "c" * 64)))
    output = list(pipeline.run(decoder, Selection(0, 1200)))
    assert [(r.start_ms, r.end_ms) for r in output] == [(100, 400), (400, 700), (900, 1200)]
    assert all(r.needs_review for r in output)
    assert len(observed) == 2
    assert pipeline.metrics.candidate_crops == 6
    assert pipeline.metrics.fresh_calls == 2 and pipeline.metrics.cache_hits == 4
    assert all(r.consensus.text == "fixture-read" for r in output)


def test_cancel_during_recognition_closes_decoder(make_video, text_image, ffmpeg_tools):
    ffmpeg, ffprobe = ffmpeg_tools
    source = make_video([text_image(), text_image(""), text_image()] * 3)
    decoder = RoiDecoder(source, probe_video(source, ffprobe), Roi(0, 0, 1, 1), ffmpeg=ffmpeg)
    cancelled = False

    def check():
        if cancelled:
            raise RuntimeError("cancelled")

    def recognize(_frame, check):
        nonlocal cancelled
        cancelled = True
        check()
        return read("unreachable")

    pipeline = OcrPipeline(recognize, ReadCache(CacheScope("a" * 64, "b" * 64, "c" * 64)), check=check)
    with pytest.raises(RuntimeError, match="cancelled"):
        list(pipeline.run(decoder, Selection(0, 800)))
    assert decoder.process.poll() is not None
    assert all(not thread.is_alive() for thread in decoder.readers)


def test_early_consumer_exit_closes_iterator(make_video, text_image, ffmpeg_tools):
    ffmpeg, ffprobe = ffmpeg_tools
    source = make_video([text_image(), text_image("")] * 5)
    decoder = RoiDecoder(source, probe_video(source, ffprobe), Roi(0, 0, 1, 1), ffmpeg=ffmpeg)
    pipeline = OcrPipeline(lambda *_: read("fixture"), ReadCache(CacheScope("a" * 64, "b" * 64, "c" * 64)))
    with closing(pipeline.run(decoder, Selection(0, 900))) as stream:
        next(stream)
    assert decoder.process.poll() is not None
    assert all(not thread.is_alive() for thread in decoder.readers)

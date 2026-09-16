from fractions import Fraction

from PIL import Image

from videocaptioner.core.ocr.models import FrameSpan, RoiFrame
from videocaptioner.core.ocr.tracking import RegionTracker


def frame(image, index):
    return RoiFrame(index, index * 100, Fraction(1, 1000), Fraction(index * 100),
                    image.width, image.height, image.tobytes())


def regions(images):
    tracker, output = RegionTracker(), []
    for index, image in enumerate(images):
        result = tracker.feed(FrameSpan(frame(image, index), Fraction(index * 100), Fraction((index + 1) * 100)))
        if result:
            output.append(result)
    result = tracker.finish()
    if result:
        output.append(result)
    assert tracker.peak_candidates <= 3
    return output


def test_one_character_two_lines_repeat_after_blank(text_image):
    first = text_image("学生三人，2026年。\n玄青带来12件礼物")
    second = text_image("学生五人，2026年。\n玄青带来12件礼物")
    blank = text_image("")
    result = regions([blank, first, first, second, second, blank, first, first, blank])
    assert [(r.start_ms, r.end_ms) for r in result] == [(100, 300), (300, 500), (600, 800)]
    assert all(len(r.candidates) <= 3 for r in result)


def test_fade_preserves_uncertainty_and_sharpest_real_frame(text_image):
    images = [text_image("", level=0)] + [text_image(level=level) for level in (30, 90, 180, 255, 180, 90, 30)] + [text_image("")]
    result = regions(images)
    assert len(result) == 1
    assert "fade_or_contrast_change" in result[0].issues
    assert result[0].start_window_ms == (100, 800)
    assert frame(images[4], 4) in result[0].candidates


def test_long_track_flushes_with_review(text_image):
    tracker = RegionTracker(max_hold_ms=200)
    outputs = []
    image = text_image()
    for index in range(6):
        result = tracker.feed(FrameSpan(frame(image, index), Fraction(index * 100), Fraction((index + 1) * 100)))
        if result:
            outputs.append(result)
    outputs.append(tracker.finish())
    assert len(outputs) == 3
    assert all("track_holding_limit" in r.issues for r in outputs)


def test_unknown_eof_has_nonzero_boundary_window(text_image):
    tracker = RegionTracker()
    image = text_image()
    tracker.feed(FrameSpan(frame(image, 0), Fraction(0), Fraction(100)))
    tracker.feed(FrameSpan(frame(image, 1), Fraction(100), Fraction(400), uncertain_end=True))
    result = tracker.finish()
    assert "unknown_last_frame_duration" in result.issues
    assert result.end_window_ms == (100, 400)


def test_codec_noise_on_black_does_not_create_false_subtitle_tracks(text_image):
    noise = Image.new("RGB", (640, 120), "black")
    for y in range(5, 80, 7):
        for x in range(10, 600, 11):
            noise.putpixel((x, y), (1, 1, 1))
    result = regions([noise, text_image(), text_image(), noise, noise])
    assert [(r.start_ms, r.end_ms) for r in result] == [(100, 300)]

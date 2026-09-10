from fractions import Fraction

import pytest

from videocaptioner.core.ocr.geometry import Roi, VideoGeometry, widget_roi


def test_letterbox_drag_and_pixel_roundtrip():
    geometry = VideoGeometry(1920, 1080)
    roi = widget_roi((1000, 812.5, 0, 687.5), (1000, 1000), geometry)
    assert (roi.x, roi.y, roi.width, roi.height) == pytest.approx((0, 5 / 6, 1, 1 / 6))


def test_letterbox_clips_to_actual_video():
    geometry = VideoGeometry(1920, 1080)
    roi = widget_roi((-50, 0, 1100, 1000), (1000, 1000), geometry)
    assert (roi.x, roi.y, roi.width, roi.height) == pytest.approx((0, 0, 1, 1))
    with pytest.raises(ValueError):
        widget_roi((0, 0, 100, 100), (1000, 1000), geometry)


@pytest.mark.parametrize("rotation,size,source", [
    (0, (400, 100), (0, 0)), (90, (100, 400), (200, 0)),
    (180, (400, 100), (200, 100)), (270, (100, 400), (0, 100)),
])
def test_sar_rotation_inverse(rotation, size, source):
    geometry = VideoGeometry(200, 100, Fraction(2), rotation)
    assert geometry.display_size == size
    assert geometry.source_point(0, 0) == source


@pytest.mark.parametrize("roi", [(0, 0, 0, 1), (-0.1, 0, 1, 1), (0, 0, float("nan"), 1), (0, 0, 2, 1)])
def test_invalid_roi(roi):
    with pytest.raises(ValueError):
        Roi(*roi)

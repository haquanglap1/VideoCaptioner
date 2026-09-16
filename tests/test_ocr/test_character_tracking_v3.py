"""Synthetic line and presence regressions; private frames remain in the local audit."""

import importlib
import os

import pytest


def worker():
    return importlib.import_module(os.environ.get('VC_TRACKING_TEST_MODULE', 'scripts.ocr_tracking_worker_v3'))


def box(x, y, width, height):
    return [[x, y], [x + width, y], [x + width, y + height], [x, y + height]]


def test_box_crossing_only_edge_of_anchor_is_not_the_selected_line():
    assert worker().foreground_boxes([box(100, 42, 53, 46)], 600, 90, .5) == []


def test_nearby_tall_background_must_share_primary_line_center():
    line = box(100, 21, 70, 39)
    background = box(260, 2, 52, 52)
    assert worker().foreground_boxes([background, line], 600, 90, .5) == [line]


def test_real_same_line_and_single_glyph_keep_geometry():
    line, mark = box(100, 25, 175, 40), box(290, 27, 25, 38)
    assert worker().foreground_boxes([line, mark], 600, 90, .5) == [line, mark]
    assert worker().foreground_boxes([mark], 600, 90, .5) == [mark]


@pytest.mark.integration
def test_local_presence_rejects_gradient_but_retains_punctuation_and_fade(tmp_path):
    """Model-based presence regression includes the punctuation failure of the old threshold trial."""
    from fractions import Fraction
    from pathlib import Path

    from PIL import Image, ImageDraw, ImageFont

    from videocaptioner.core.ocr.installation import inspect_installation
    from videocaptioner.core.ocr.models import EngineRead, ReadLine, RoiFrame
    from videocaptioner.core.ocr.runtime import CpuOcrRuntime

    runtime = os.environ.get('VC_OCR_TEST_RUNTIME')
    if not runtime:
        pytest.skip('Requires the explicitly selected PP-OCRv6 medium runtime')
    root = Path(__file__).parents[2]
    installation = inspect_installation(Path(runtime))
    module = worker()
    bridge = Path(module.__file__)
    font = ImageFont.truetype(str(root / 'resource/fonts/NotoSansSC-Regular.ttf'), 32)
    labels = ['', '……', '……', '。', '学生三人。', '学生三人。', '', '学生五人。', '学生三人。']
    decisions = []
    with CpuOcrRuntime(installation.root, bridge, tmp_path / 'jobs', installation.profile_sha256,
                       expected_profile=installation.profile, max_requests=1) as runtime_worker:
        for index, label in enumerate(labels):
            image = Image.new('RGB', (600, 90), 'black')
            draw = ImageDraw.Draw(image)
            if not label:
                for y in range(90):
                    shade = y * 2
                    draw.line((0, y, 599, y), fill=(shade, shade, shade))
            else:
                draw.text((200, 20), label, font=font, fill=(80, 80, 80) if index == 5 else 'white')
            frame = RoiFrame(index, index * 100, Fraction(1, 1000), Fraction(index * 100),
                             600, 90, image.tobytes())
            geometry = EngineRead((ReadLine('synthetic geometry', .99, tuple(map(tuple, box(195, 25, 175, 40)))),),
                                  installation.profile_sha256)
            decisions.append(runtime_worker.track(frame, .5, geometry))
    assert [d.present for d in decisions] == [False, True, True, True, True, True, False, True, True]
    assert not decisions[2].changed and not decisions[5].changed
    assert decisions[3].changed and decisions[4].changed
    assert decisions[7].changed and decisions[8].changed
    assert decisions[5].quality < decisions[4].quality

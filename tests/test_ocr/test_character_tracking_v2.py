"""Synthetic geometry regressions; no private media or recognition labels."""

import hashlib
import os
from dataclasses import replace
from fractions import Fraction
from pathlib import Path

import pytest
from PIL import Image, ImageDraw, ImageFont

from scripts.ocr_tracking_worker_v2 import foreground_ranges


def test_character_drift_requires_matching_visual_features_and_one_to_one_runs():
    from scripts.ocr_tracking_worker_v2 import stable_characters

    # One glyph can move one encoder position without changing its visual feature.
    left = ([[1., 0.], [0., 1.], [1., 0.]], [11, 0, 12], [.99] * 3, [True] * 3)
    right = ([[1., 0.], [0., 1.], [1., 0.], [1., 0.]], [0, 11, 0, 12], [.99] * 4, [True] * 4)
    # Keep the first glyph's vector identical while shifting its encoder slot.
    right[0][1] = [1., 0.]
    assert stable_characters(left, right, 99)
    changed_shape = ([[0., 1.], [0., 1.], [1., 0.]], left[1], left[2], left[3])
    assert not stable_characters(left, changed_shape, 99)
    duplicate = ([[1., 0.]] * 3, [11, 0, 11], [.99] * 3, [True] * 3)
    removed = ([[1., 0.]] * 3, [11, 0, 0], [.99] * 3, [True] * 3)
    assert not stable_characters(duplicate, removed, 99)


def box(x, y, width, height):
    return [[x, y], [x + width, y], [x + width, y + height], [x, y + height]]


@pytest.mark.parametrize("roi_height", [80, 90, 120])
def test_selected_line_height_is_independent_of_roi_padding(roi_height):
    line = box(100, roi_height / 2 - 16, 320, 32)
    assert foreground_ranges([line], 600, roi_height, .5) == [(84, 436)]


def test_tall_isolated_mark_cannot_hide_wide_anchor_line():
    line = box(100, 25, 320, 32)
    mark = box(500, 20, 20, 49)
    assert foreground_ranges([line, mark], 600, 90, .5) == [(84, 436)]


def test_small_separate_mark_does_not_create_a_subtitle_region():
    assert foreground_ranges([box(100, 44, 3, 2)], 600, 90, .5) == []


def test_blank_and_off_anchor_geometry_stay_absent():
    assert foreground_ranges([], 600, 90, .5) == []
    assert foreground_ranges([box(100, 3, 320, 20)], 600, 90, .5) == []


def test_single_glyph_and_punctuation_support_are_retained():
    assert foreground_ranges([box(100, 29, 28, 32)], 600, 90, .5)


def test_clipped_or_tilted_background_is_not_a_horizontal_subtitle():
    assert foreground_ranges([box(0, 0, 300, 90)], 600, 90, .5) == []
    assert foreground_ranges([box(400, 0, 90, 68)], 600, 90, .5) == []
    tilted = [[100, 23], [158, 41], [144, 83], [86, 66]]
    assert foreground_ranges([tilted], 600, 90, .5) == []
    # Tight ROI padding is valid when the detected horizontal line is fully inside it.
    assert foreground_ranges([box(100, 4, 320, 32)], 600, 40, .5)


def test_worker_v2_has_independent_identity_and_keeps_v1_bytes():
    from tests.test_ocr.test_character_tracking import character_config
    from videocaptioner.core.ocr.codec import digest

    root = Path(__file__).parents[2]
    for name in ('ocr_tracking_worker.py', 'ocr_tracking_worker_v2.py'):
        assert (root / 'scripts' / name).read_bytes() == (root / 'videocaptioner/resources/ocr' / name).read_bytes()
    legacy = character_config()
    current = replace(legacy, tracking_policy='character-features-v2')
    assert digest(current) != digest(legacy)
    assert legacy.tracking_policy == 'character-features-v1'
    assert hashlib.sha256((root / 'scripts/ocr_tracking_worker_v2.py').read_bytes()).hexdigest() != legacy.bridge_sha256


@pytest.mark.parametrize('policy,worker_name', [
    ('character-features-v1', 'ocr_tracking_worker.py'),
    ('character-features-v2', 'ocr_tracking_worker_v2.py'),
])
def test_cli_resume_uses_saved_worker_without_migrating_policy(tmp_path, monkeypatch, policy, worker_name):
    from tests.test_ocr.test_character_tracking import character_config
    from tests.test_ocr.test_document import make_document
    from videocaptioner.cli.main import main
    from videocaptioner.core.ocr.document import OcrDocument, document_id

    config = replace(character_config(), tracking_policy=policy)
    source = replace(make_document().visual_source, selection=config.selection)
    document = OcrDocument(document_id(source, config), source, config, (), False)
    checkpoint = tmp_path / 'partial.json'
    document.save(checkpoint)
    before = checkpoint.read_bytes()
    media = tmp_path / 'synthetic.mov'
    media.write_bytes(b'configuration routing only; decoding is stubbed')
    captured = []
    monkeypatch.setattr('videocaptioner.cli.commands.ocr.resources', lambda: tmp_path)
    monkeypatch.setattr('videocaptioner.cli.commands.ocr._scan',
                        lambda _a, _s, cfg, _r, bridge, doc: captured.append((cfg, bridge, doc)) or 0)
    assert main(['ocr-resume', str(checkpoint), '--source', str(media),
                 '--checkpoint', str(tmp_path / 'continued.json')]) == 0
    assert captured == [(config, tmp_path / worker_name, document)]
    assert checkpoint.read_bytes() == before


@pytest.mark.integration
def test_local_worker_retains_blank_fade_and_one_frame_changes(tmp_path):
    """Real CPU features on synthetic glyphs; explicitly opt in to the installed runtime."""
    from videocaptioner.core.ocr.installation import inspect_installation, resources
    from videocaptioner.core.ocr.models import EngineRead, ReadLine, RoiFrame
    from videocaptioner.core.ocr.runtime import CpuOcrRuntime

    runtime = os.environ.get('VC_OCR_TEST_RUNTIME')
    if not runtime:
        pytest.skip('Requires the explicitly selected PP-OCRv6 medium runtime')
    installation = inspect_installation(Path(runtime))
    font = ImageFont.truetype(str(Path(__file__).parents[2] / 'resource/fonts/NotoSansSC-Regular.ttf'), 32)
    labels = ['', '学生三人。', '学生三人。', '学生五人。', '学生三人。',
              '学生三人！', '学生三人。', '', '学生三人。', '学生三人。', '', '……', '']
    decisions = []
    worker = CpuOcrRuntime(installation.root, resources() / 'ocr_tracking_worker_v2.py', tmp_path / 'jobs',
                          installation.profile_sha256, expected_profile=installation.profile, max_requests=1)
    with worker:
        for index, label in enumerate(labels):
            image = Image.new('RGB', (600, 90), 'black')
            draw = ImageDraw.Draw(image)
            # Deliberately move a bright background object outside the selected line.
            draw.rectangle((index * 7, 0, index * 7 + 10, 20), fill='white')
            draw.text((200, 20), label, font=font, fill=(110, 110, 110) if index == 9 else 'white')
            frame = RoiFrame(index, index * 100, Fraction(1, 1000), Fraction(index * 100), 600, 90, image.tobytes())
            geometry = EngineRead((ReadLine(label, .99, tuple(map(tuple, box(195, 25, 175, 40)))),),
                                  installation.profile_sha256)
            decisions.append(worker.track(frame, .5, geometry))
    assert [d.present for d in decisions] == [False, True, True, True, True, True, True, False, True, True,
                                            False, True, False]
    assert [d.changed for d in decisions[1:7]] == [True, False, True, True, True, True]
    assert decisions[8].changed and not decisions[9].changed
    assert decisions[9].quality < decisions[8].quality


@pytest.mark.integration
def test_local_worker_box_width_jitter_does_not_hide_punctuation(tmp_path):
    from videocaptioner.core.ocr.installation import inspect_installation, resources
    from videocaptioner.core.ocr.models import EngineRead, ReadLine, RoiFrame
    from videocaptioner.core.ocr.runtime import CpuOcrRuntime

    runtime = os.environ.get('VC_OCR_TEST_RUNTIME')
    if not runtime:
        pytest.skip('Requires the explicitly selected PP-OCRv6 medium runtime')
    installation = inspect_installation(Path(runtime))
    font = ImageFont.truetype(str(Path(__file__).parents[2] / 'resource/fonts/NotoSansSC-Regular.ttf'), 32)
    image = Image.new('RGB', (600, 90), 'black')
    ImageDraw.Draw(image).text((200, 20), '学生三人……', font=font, fill='white')
    frame = RoiFrame(0, 0, Fraction(1, 1000), Fraction(0), 600, 90, image.tobytes())
    worker = CpuOcrRuntime(installation.root, resources() / 'ocr_tracking_worker_v2.py', tmp_path / 'jobs',
                          installation.profile_sha256, expected_profile=installation.profile, max_requests=1)
    decisions = []
    with worker:
        for width in (128, 192, 128):
            geometry = EngineRead((ReadLine('synthetic geometry', .99, tuple(map(tuple, box(200, 25, width, 40)))),),
                                  installation.profile_sha256)
            decisions.append(worker.track(frame, .5, geometry))
    assert [d.changed for d in decisions] == [True, False, False]


@pytest.mark.integration
def test_local_worker_nearby_moving_text_is_outside_selected_band(tmp_path):
    from videocaptioner.core.ocr.installation import inspect_installation, resources
    from videocaptioner.core.ocr.models import EngineRead, ReadLine, RoiFrame
    from videocaptioner.core.ocr.runtime import CpuOcrRuntime

    runtime = os.environ.get('VC_OCR_TEST_RUNTIME')
    if not runtime:
        pytest.skip('Requires the explicitly selected PP-OCRv6 medium runtime')
    installation = inspect_installation(Path(runtime))
    font = ImageFont.truetype(str(Path(__file__).parents[2] / 'resource/fonts/NotoSansSC-Regular.ttf'), 32)
    worker = CpuOcrRuntime(installation.root, resources() / 'ocr_tracking_worker_v2.py', tmp_path / 'jobs',
                          installation.profile_sha256, expected_profile=installation.profile, max_requests=1)
    decisions = []
    with worker:
        for index, background in enumerate(['天', '地', '天']):
            image = Image.new('RGB', (600, 90), 'black')
            draw = ImageDraw.Draw(image)
            draw.text((160, 20), background, font=font, fill='white')
            draw.text((200, 20), '学生三人。', font=font, fill='white')
            frame = RoiFrame(index, index * 100, Fraction(1, 1000), Fraction(index * 100), 600, 90, image.tobytes())
            geometry = EngineRead((ReadLine('synthetic geometry', .99, tuple(map(tuple, box(200, 25, 165, 40)))),),
                                  installation.profile_sha256)
            decisions.append(worker.track(frame, .5, geometry))
    assert [d.changed for d in decisions] == [True, False, False]

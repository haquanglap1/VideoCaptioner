"""Tracking policy, uncertainty and compatibility without loading local models."""

import hashlib
from dataclasses import replace
from fractions import Fraction
from pathlib import Path

import pytest
from PIL import Image

from scripts.ocr_tracking_worker import (
    BASE_WORKER_SHA256,
    FEATURE_NAME,
    _field,
    _fields,
    feature_model,
)
from videocaptioner.core.ocr.document import OcrConfig
from videocaptioner.core.ocr.geometry import Roi
from videocaptioner.core.ocr.line_selection import LineSelectionPolicy
from videocaptioner.core.ocr.models import FrameSpan, OcrError, RoiFrame, Selection, VisualDecision
from videocaptioner.core.ocr.profile import OcrProfileSnapshot
from videocaptioner.core.ocr.tracking import RegionTracker


def character_config():
    path = Path(__file__).parents[2] / "videocaptioner/resources/ocr/profile-v6-medium.json"
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    return OcrConfig(Roi(0, 0, 1, 1), Selection(0, 1000), digest, "c" * 64,
                     tracking_policy="character-features-v1", line_selection=LineSelectionPolicy(),
                     profile_snapshot=OcrProfileSnapshot.from_bytes(raw, digest))


def test_character_policy_requires_one_line_and_a_supported_profile():
    config = character_config()
    legacy = replace(config, line_selection=LineSelectionPolicy(policy="horizontal-anchors-punctuation-v2"))
    assert legacy.line_selection.policy == "horizontal-anchors-punctuation-v2"
    for changed in (dict(line_selection=None), dict(line_selection=LineSelectionPolicy((.25, .75))),
                    dict(line_selection=LineSelectionPolicy(policy="horizontal-anchors-punctuation-v1")),
                    dict(profile_snapshot=None)):
        with pytest.raises(OcrError):
            replace(config, **changed)
    assert replace(config, tracking_policy="edge-tiles-ocr2-v1", line_selection=None).tracking_policy == "edge-tiles-ocr2-v1"


def test_visual_decisions_keep_short_changes_blank_repeat_and_uncertainty():
    tracker = RegionTracker()
    # Changing background pixels must not override the selected visual policy.
    states = [(False, False, False), (True, True, False), (True, False, True),
              (True, True, False), (True, True, False), (False, True, False), (True, True, False)]
    output = []
    for index, (present, changed, uncertain) in enumerate(states):
        image = Image.new("RGB", (120, 40), "white" if index % 2 else "black")
        frame = RoiFrame(index, index * 100, Fraction(1, 1000), Fraction(index * 100), 120, 40, image.tobytes())
        region = tracker.feed(FrameSpan(frame, Fraction(index * 100), Fraction((index + 1) * 100)),
                              VisualDecision(present, changed, uncertain, .95))
        if region:
            output.append(region)
    output.append(tracker.finish())
    assert [(r.start_ms, r.end_ms) for r in output] == [(100, 300), (300, 400), (400, 500), (600, 700)]
    assert "uncertain_boundary" in output[0].issues
    assert output[0].start_window_ms == output[0].end_window_ms == (100, 300)
    assert all(len(r.candidates) <= 3 for r in output)


def test_visual_holding_limit_remains_a_resume_boundary():
    tracker = RegionTracker(max_hold_ms=200)
    output = []
    for index in range(5):
        frame = RoiFrame(index, index * 100, Fraction(1, 1000), Fraction(index * 100), 16, 16, b"\0" * 768)
        region = tracker.feed(FrameSpan(frame, Fraction(index * 100), Fraction((index + 1) * 100)),
                              VisualDecision(True, index == 0, False, .9))
        if region:
            output.append(region)
    output.append(tracker.finish())
    assert [(r.start_ms, r.end_ms) for r in output] == [(0, 200), (200, 400), (400, 500)]
    assert all("track_holding_limit" in r.issues for r in output)


def test_feature_graph_adds_an_output_without_changing_nodes_or_weights():
    info = _field(1, FEATURE_NAME) + _field(2, b"type fixture")
    node, weights = _field(1, b"node fixture"), _field(5, b"weights fixture")
    graph = node + weights + _field(12, _field(1, b"existing-output")) + _field(13, info)
    original = _field(7, graph) + _field(14, b"metadata fixture")
    result = feature_model(original)
    updated = next(v for n, _, v, _ in _fields(result) if n == 7)
    assert updated == graph + _field(12, info)
    assert result.endswith(_field(14, b"metadata fixture"))
    with pytest.raises(ValueError):
        list(_fields(b"\x0a\xff"))


def test_companion_is_bundled_and_keeps_legacy_bridge_pinned():
    root = Path(__file__).parents[2]
    for name in ("ocr_stream_worker.py", "ocr_tracking_worker.py"):
        assert (root / "scripts" / name).read_bytes() == (root / "videocaptioner/resources/ocr" / name).read_bytes()
    assert hashlib.sha256((root / "scripts/ocr_stream_worker.py").read_bytes()).hexdigest() == BASE_WORKER_SHA256


def test_cli_character_mode_selects_the_companion_before_scan(tmp_path, monkeypatch):
    from videocaptioner.cli import exit_codes as EXIT
    from videocaptioner.cli.main import main

    bundle = tmp_path / "bundle"
    bundle.mkdir()
    companion = bundle / "ocr_tracking_worker.py"
    companion.write_text("# synthetic tracking worker")
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    profile = Path(__file__).parents[2] / "videocaptioner/resources/ocr/profile-v6-medium.json"
    (runtime / "profile.json").write_bytes(profile.read_bytes())
    source = tmp_path / "synthetic.mov"
    source.write_bytes(b"not decoded; configuration routing test")
    captured = []
    monkeypatch.setattr("videocaptioner.cli.commands.ocr.resources", lambda: bundle)
    monkeypatch.setattr("videocaptioner.cli.commands.ocr._scan",
                        lambda _a, _s, cfg, _r, bridge: captured.append((cfg, bridge)) or EXIT.SUCCESS)
    args = ["ocr", str(source), "--roi", "0,0,1,1", "--start-ms", "0", "--end-ms", "1000",
            "--ocr-runtime", str(runtime), "--profile-sha256", hashlib.sha256(profile.read_bytes()).hexdigest(),
            "--tracking", "characters", "-o", str(tmp_path / "output.srt")]
    assert main(args) == EXIT.USAGE_ERROR
    assert main([*args, "--line-anchors", "0.25,0.75"]) == EXIT.USAGE_ERROR
    assert not captured
    assert main([*args, "--line-anchors", "0.5"]) == EXIT.SUCCESS
    cfg, bridge = captured[0]
    assert cfg.tracking_policy == "character-features-v1" and bridge == companion
    assert cfg.bridge_sha256 == hashlib.sha256(companion.read_bytes()).hexdigest()

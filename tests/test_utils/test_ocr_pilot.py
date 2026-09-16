"""Pilot provenance/metrics guards, using only synthetic data and no model downloads."""

import json
from fractions import Fraction
from types import SimpleNamespace

import pytest

from scripts.ocr_pilot import edit_distance, execute, letters_numbers, nearest_frame, score
from scripts.package_test_models import package


def test_nearest_uses_actual_pts_and_earlier_tie():
    frames = [{"pts": 1001}, {"pts": 1019}, {"pts": 1062}]
    assert nearest_frame(frames, 1010, Fraction(1, 1000))["pts"] == 1001
    assert nearest_frame(frames, 1045, Fraction(1, 1000))["pts"] == 1062
    assert nearest_frame([{"pts": 208533}, {"pts": 209066}], 13040, Fraction(1, 16000))["pts"] == 208533


def test_metrics_preserve_script_numbers_and_punctuation():
    assert edit_distance("學生三人，2026。", "学生五人,2026。") == 3
    assert edit_distance(letters_numbers("學生三人，2026。"), letters_numbers("学生五人,2026。")) == 2
    assert edit_distance("123", "13") == 1
    assert edit_distance("", "abc") == 3


def test_score_rejects_reordered_crops(tmp_path):
    reference, raw = tmp_path / "ref.json", tmp_path / "raw.jsonl"
    reference.write_text(json.dumps({"cues": [{"source_text": "x"}]}))
    raw.write_text(json.dumps({"id": "crop-02", "texts": ["x"], "scores": [1], "error": None}))
    args = SimpleNamespace(reference=reference, raw=raw, output=tmp_path / "score.json")
    with pytest.raises(ValueError, match="mapping mismatch"):
        score(args)
    assert not args.output.exists()


def test_run_preserves_previous_measurement(tmp_path):
    marker = tmp_path / "process.json"
    marker.write_text("original receipt")
    with pytest.raises(ValueError, match="preserved"):
        execute(SimpleNamespace(output=tmp_path))
    assert marker.read_text() == "original receipt"


def test_package_ocr_carries_python_weights_and_profile_without_venv_home(tmp_path):
    source, base = tmp_path / "installed", tmp_path / "python"
    (source / "env/Lib/site-packages").mkdir(parents=True)
    (source / "env/Lib/site-packages/example.py").write_text("value = 1")
    (source / "env/pyvenv.cfg").write_text("home = original-installation")
    (source / "weights").mkdir()
    (source / "weights/model.onnx").write_bytes(b"synthetic model")
    (source / "profile.json").write_text("{}")
    (source / "setup-0.log").write_text("not part of the payload")
    (base / "Lib").mkdir(parents=True)
    (base / "python.exe").write_bytes(b"synthetic interpreter")
    (base / "Lib/os.py").write_text("stdlib")
    app = tmp_path / "relocated-app"
    result = package(SimpleNamespace(app_dir=app, python_base=base, ocr_runtime=source,
                                    faster_whisper=None, qwen_runtime=None, diarization_runtime=None,
                                    omnivoice_runtime=None, vieneu_runtime=None, weights_dir=None))
    assert result["components"] == ["ocr"]
    assert result["downloads"] == 0
    assert (app / "models/ocr/env/python.exe").is_file()
    assert (app / "models/ocr/weights/model.onnx").read_bytes() == b"synthetic model"
    assert not (app / "models/ocr/env/pyvenv.cfg").exists()
    assert not (app / "models/ocr/setup-0.log").exists()
    assert (source / "env/pyvenv.cfg").is_file()

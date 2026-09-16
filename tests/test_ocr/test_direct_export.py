"""Completed OCR exports its observed readings without a manual approval step."""

from dataclasses import replace

import pytest

from videocaptioner.cli import exit_codes as EXIT
from videocaptioner.cli.commands.ocr import _export
from videocaptioner.cli.main import main
from videocaptioner.core.asr.asr_data import ASRData
from videocaptioner.core.ocr.models import OcrError

from .test_document import make_document


@pytest.mark.parametrize("texts", [("学生三人\n2026年。",), ("学生三人", "學生三人")])
def test_export_keeps_original_observations_without_approval(texts, tmp_path):
    doc = make_document(texts, timing_issues=("selection_clipped_start", "fade_or_contrast_change"))
    original = doc.to_dict()
    target = tmp_path / "captions.json"
    assert _export(doc, doc.visual_source, str(target)) == EXIT.SUCCESS
    data = ASRData.from_subtitle_file(str(target))
    cue = data.segments[0]
    assert cue.text == doc.cues[0].raw_text
    assert (cue.start_time, cue.end_time, cue.cue_id) == (200, 500, doc.cues[0].id)
    assert cue.ocr_metadata.observations == doc.cues
    assert cue.ocr_metadata.observations[0].pending_issues
    assert cue.ocr_metadata.observations[0].selected_candidate_id is None
    assert doc.to_dict() == original


@pytest.mark.parametrize("command", ["ocr-export", "ocr-review"])
def test_old_checkpoint_exports_locally_without_candidate_selection(tmp_path, monkeypatch, command):
    doc = make_document()
    saved, source, output = (tmp_path / name for name in ("old.json", "source.mov", "captions.srt"))
    doc.save(saved)
    source.write_bytes(b"synthetic source, verification is injected")
    original = saved.read_bytes()
    monkeypatch.setattr("videocaptioner.cli.commands.ocr.verify_visual_file", lambda *_a, **_k: doc.visual_source)
    monkeypatch.setattr("videocaptioner.cli.commands.ocr.run_cpu_ocr",
                        lambda *_a, **_k: pytest.fail("Saved OCR must not run inference again"))
    assert main([command, str(saved), "--source", str(source), "-o", str(output)]) == EXIT.SUCCESS
    assert doc.cues[0].raw_text in output.read_text(encoding="utf-8")
    assert saved.read_bytes() == original


def test_scan_accepts_output_without_a_review_file(tmp_path):
    # Reaching the input check proves the parser no longer requires --review.
    assert main(["ocr", str(tmp_path / "missing.mov"), "--start-ms", "0", "--end-ms", "1000",
                 "--roi", "0,0,1,1", "-o", str(tmp_path / "captions.srt")]) == EXIT.FILE_NOT_FOUND


def test_incomplete_scan_and_wrong_source_still_fail():
    doc = make_document()
    with pytest.raises(OcrError):
        replace(doc, complete=False).resume(doc.visual_source)
    with pytest.raises(OcrError, match="mismatch"):
        doc.resume(replace(doc.visual_source, snapshot_sha256="f" * 64))

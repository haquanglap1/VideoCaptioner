"""Review contracts use synthetic readings; no OCR model, private media or API calls."""

import hashlib
import json
from dataclasses import replace
from fractions import Fraction
from pathlib import Path

import pytest

from videocaptioner.core.ocr.consensus import CandidateRead, choose_read
from videocaptioner.core.ocr.document import OcrConfig, OcrDocument, cue_from_region, document_id
from videocaptioner.core.ocr.geometry import Roi, VideoGeometry
from videocaptioner.core.ocr.identity import VisualSourceIdentity
from videocaptioner.core.ocr.models import EngineRead, OcrError, ReadLine, Selection, VideoInfo
from videocaptioner.core.ocr.pipeline import RegionResult
from videocaptioner.core.ocr.profile import OcrProfileSnapshot


def make_document(texts=("学生三人\n2026年。", "学生三人\n2026年。"), *, approved=False, timing_issues=()):
    profile = OcrProfileSnapshot("synthetic", (("fixture", "1.0"),),
                                 tuple((name, "d" * 64) for name in ("det", "rec", "cls")), "e" * 64, 10,
                                 (("synthetic", True),), (("input", "fixture"),))
    config = OcrConfig(Roi(0, 0, 1, 1), Selection(100, 1500), "b" * 64, "c" * 64, profile_snapshot=profile)
    source = VisualSourceIdentity("a" * 64, 1000, VideoInfo(0, VideoGeometry(640, 120),
                                                         Fraction(1, 1000), Fraction(3)), config.selection)
    identifier = document_id(source, config)
    reads = tuple(CandidateRead(3200 + index * 100, str(index + 1) * 64,
                                EngineRead(tuple(ReadLine(line, .98, ((0., 0.), (600., 0.),
                                                                     (600., 100.), (0., 100.)))
                                                 for line in text.split("\n")), "b" * 64), False)
                  for index, text in enumerate(texts))
    region = RegionResult(Fraction(200), Fraction(500), reads, choose_read(reads), timing_issues,
                          (Fraction(200), Fraction(200)), (Fraction(500), Fraction(500)), 3200, 3400)
    cue = cue_from_region(identifier, region)
    if approved:
        cue = cue.select_candidate(cue.candidates[0].id, "Reviewed synthetic fixture against its known text")
    return OcrDocument(identifier, source, config, (cue,), True)


def test_raw_candidates_ids_and_exact_timing_round_trip(tmp_path):
    document = make_document()
    path = tmp_path / "pending.json"
    document.save(path)
    loaded = OcrDocument.load(path)
    assert loaded == document
    assert loaded.cues[0].raw_text == "学生三人\n2026年。"
    assert "uncalibrated_profile" in loaded.cues[0].pending_issues
    data = loaded.resume(loaded.visual_source)
    assert data.segments[0].ocr_metadata.observations == document.cues
    assert "audio" not in json.dumps(loaded.to_dict())


@pytest.mark.parametrize("mutation", [
    lambda d: d.update(schema="ocr-document-v2"),
    lambda d: d.pop("complete"),
    lambda d: d.update(complete=1),
    lambda d: d["visual_source"].update(size_bytes=True),
    lambda d: d["visual_source"]["video"].update(time_base=[1, 0]),
    lambda d: d["cues"][0].update(measured_start_ms=200.0),
    lambda d: d["cues"][0].update(raw_text="invented correction"),
    lambda d: d["cues"][0].update(raw_candidate_id="candidate-" + "f" * 32),
    lambda d: d["cues"][0]["candidates"][0].update(crop_reference="../private.png"),
    lambda d: d["cues"][0]["candidates"][0]["raw"]["lines"][0].update(score=float("nan")),
    lambda d: d["cues"].append(d["cues"][0]),
    lambda d: d["config"].update(profile_sha256="e" * 64),
    lambda d: d["cues"][0].update(resolved_issues=["uncalibrated_profile"]),
])
def test_load_rejects_corruption_and_fake_review(mutation):
    payload = make_document().to_dict()
    mutation(payload)
    with pytest.raises(OcrError):
        OcrDocument.from_dict(payload)


def test_duplicate_json_keys_rejected(tmp_path):
    path = tmp_path / "duplicate.json"
    path.write_text('{"schema":"ocr-document-v1","schema":"ocr-document-v1"}')
    with pytest.raises(OcrError, match="Duplicate"):
        OcrDocument.load(path)


def test_whole_read_selection_keeps_original_disagreement():
    doc = make_document(("学生三人", "學生三人"))
    cue = doc.cues[0]
    edited = cue.select_candidate(cue.candidates[1].id, "Explicit fixture evidence")
    assert edited.raw_text == "学生三人" and edited.text == "學生三人"
    assert edited.candidates == cue.candidates and edited.id == cue.id
    assert "engine_disagreement" in edited.all_issues and not edited.pending_issues
    with pytest.raises(OcrError):
        replace(edited, edited_text="学生三个人")
    data = doc.replace_cue(edited).resume(doc.visual_source)
    assert data.segments[0].text == "學生三人"
    assert data.segments[0].metadata is None and data.segments[0].speaker is None


@pytest.mark.parametrize("texts", [("", "text"), ("", ""), ()])
def test_missing_empty_reads_never_become_success(texts):
    doc = make_document(texts)
    with pytest.raises(OcrError):
        doc.resume(doc.visual_source)
    if any(c.raw.text.strip() for c in doc.cues[0].candidates):
        selected = next(c for c in doc.cues[0].candidates if c.raw.text.strip())
        reviewed = doc.replace_cue(doc.cues[0].select_candidate(selected.id, "Checked fixture"))
        with pytest.raises(OcrError):
            reviewed.resume(doc.visual_source)


def test_timing_edit_keeps_measured_pts_clipping_and_uncertainty():
    doc = make_document(approved=True, timing_issues=("selection_clipped_start", "unknown_last_frame_duration"))
    cue = doc.cues[0]
    original = doc.resume(doc.visual_source)
    assert (original.segments[0].start_time, original.segments[0].end_time) == (200, 500)
    revised = cue.review_timing(210, 480, "Explicit known fixture boundaries")
    result = doc.replace_cue(revised).resume(doc.visual_source)
    assert (result.segments[0].start_time, result.segments[0].end_time) == (210, 480)
    assert (revised.measured_start_ms, revised.measured_end_ms, revised.first_pts) == (200, 500, 3200)
    assert revised.issues == cue.issues and revised.start_window_ms == cue.start_window_ms


def test_incomplete_and_empty_scans_cannot_resume():
    doc = make_document(approved=True)
    for changed in (replace(doc, complete=False), replace(doc, cues=())):
        with pytest.raises(OcrError):
            changed.resume(doc.visual_source)


def test_identity_compares_entire_visual_context():
    doc = make_document(approved=True)
    source = doc.visual_source
    variants = [replace(source, snapshot_sha256="f" * 64), replace(source, size_bytes=1001),
                replace(source, selection=Selection(100, 1400))]
    for field, value in (("stream_index", 1), ("time_base", Fraction(1, 16000)),
                         ("timeline_origin", Fraction(4)), ("geometry", VideoGeometry(640, 120, Fraction(2), 90))):
        variants.append(replace(source, video=replace(source.video, **{field: value})))
    for changed in variants:
        with pytest.raises(OcrError, match="mismatch"):
            doc.resume(changed)


def test_atomic_save_preserves_previous_document_on_replace_failure(tmp_path, monkeypatch):
    doc = make_document()
    destination = tmp_path / "review.json"
    doc.save(destination)
    original = destination.read_bytes()

    def fail(*_):
        raise OSError("synthetic replace failure")

    monkeypatch.setattr("videocaptioner.core.ocr.codec.os.replace", fail)
    with pytest.raises(OSError):
        make_document(approved=True).save(destination)
    assert destination.read_bytes() == original
    assert list(tmp_path.iterdir()) == [destination]


def test_profile_snapshot_keeps_pins_parameters_and_preprocessing():
    path = Path(__file__).parents[2] / "scripts/ocr_pilot_data/profile.json"
    raw = path.read_bytes()
    profile = OcrProfileSnapshot.from_bytes(raw, hashlib.sha256(raw).hexdigest())
    assert dict(profile.packages)["rapidocr"] == "3.9.2"
    assert dict(profile.parameters)["Global.use_cls"] is False
    assert dict(profile.parameters)["Rec.rec_img_shape"] == (3., 48., 320.)
    assert profile.dictionary_count == 18383
    assert dict(profile.preprocessing)["score"]
    with pytest.raises(OcrError, match="SHA"):
        OcrProfileSnapshot.from_bytes(raw + b" ", hashlib.sha256(raw).hexdigest())


def test_unresolved_and_edited_submillisecond_measurements_are_not_clamped():
    doc = make_document()
    cue = doc.cues[0]
    from videocaptioner.core.ocr.document import cue_id

    start, end = Fraction(200), Fraction(1001, 5)
    revised = replace(cue, id=cue_id(doc.id, start, end, 3200, 3200), exact_end_ms=end,
                       measured_end_ms=round(end), last_pts=3200, candidates=(cue.candidates[0],),
                       end_window_ms=(end, end))
    clipped = replace(doc, cues=(revised,))
    assert revised.measured_end_ms == revised.measured_start_ms == 200
    assert "submillisecond_span" in revised.pending_issues
    with pytest.raises(OcrError):
        clipped.resume(clipped.visual_source)

"""Source/CLI tests decode generated video, with recognition injected and no model/API."""

import hashlib
import json
import subprocess
from dataclasses import replace
from types import SimpleNamespace

import pytest

from videocaptioner.cli import exit_codes as EXIT
from videocaptioner.cli.main import main
from videocaptioner.core.asr.asr_data import ASRData
from videocaptioner.core.ocr.document import OcrDocument
from videocaptioner.core.ocr.identity import verify_visual_file
from videocaptioner.core.ocr.line_selection import LineSelectionPolicy
from videocaptioner.core.ocr.models import EngineRead, OcrError, Selection
from videocaptioner.core.ocr.runtime import RuntimeMetrics
from videocaptioner.core.ocr.service import scan_video
from videocaptioner.core.utils.subprocess_helper import _NO_WINDOW, child_environment

from .test_document import make_document


def fixture_config(end=700):
    return replace(make_document().config, selection=Selection(0, end))


def test_same_audio_and_duration_different_visual_text_must_mismatch(make_video, text_image, ffmpeg_tools, tmp_path):
    ffmpeg, ffprobe = ffmpeg_tools
    videos = [make_video([text_image(text)] * 3) for text in ("学生三人", "学生五人")]
    muxed = []
    for index, video in enumerate(videos):
        target = tmp_path / f"with-audio-{index}.mov"
        subprocess.run([ffmpeg, "-v", "error", "-nostdin", "-n", "-i", str(video), "-f", "lavfi",
                        "-i", "anullsrc=r=16000:cl=mono", "-t", "0.3", "-c:v", "copy", "-c:a", "pcm_s16le",
                        str(target)], env=child_environment(), creationflags=_NO_WINDOW, check=True,
                       timeout=30, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        muxed.append(target)
    raw = make_document().cues[0].candidates[0].raw
    docs = [scan_video(p, fixture_config(300), lambda *_: raw, jobs_root=tmp_path / "jobs",
                       ffmpeg=ffmpeg, ffprobe=ffprobe) for p in muxed]
    assert docs[0].visual_source.video == docs[1].visual_source.video
    assert docs[0].visual_source.selection == docs[1].visual_source.selection
    with pytest.raises(OcrError, match="mismatch"):
        verify_visual_file(docs[0].visual_source, muxed[1], tmp_path / "jobs", ffprobe=ffprobe)
    assert verify_visual_file(docs[0].visual_source, muxed[0], tmp_path / "jobs", ffprobe=ffprobe) == docs[0].visual_source
    assert not list((tmp_path / "jobs").iterdir())


def test_source_scan_pts_offset_checkpoint_and_no_audio(make_video, text_image, ffmpeg_tools, tmp_path):
    ffmpeg, ffprobe = ffmpeg_tools
    source = make_video([text_image(""), text_image(), text_image(), text_image(""), text_image()], vfr=True, offset=3)
    config = replace(fixture_config(650), selection=Selection(150, 650))
    raw = make_document().cues[0].candidates[0].raw
    saved = tmp_path / "review.json"
    doc = scan_video(source, config, lambda *_: raw, jobs_root=tmp_path / "jobs", ffmpeg=ffmpeg,
                     ffprobe=ffprobe, checkpoint=lambda d: d.save(saved))
    assert OcrDocument.load(saved) == doc and doc.complete
    assert doc.cues[0].measured_start_ms == 150
    assert "selection_clipped_start" in doc.cues[0].pending_issues
    assert doc.visual_source.video.timeline_origin == 3
    for cue in doc.cues:
        assert cue.first_pts <= cue.last_pts
        assert all(cue.first_pts <= c.frame_pts <= cue.last_pts for c in cue.candidates)
    assert not list((tmp_path / "jobs").iterdir())


def test_failed_scan_keeps_incomplete_checkpoint(make_video, text_image, ffmpeg_tools, tmp_path):
    ffmpeg, ffprobe = ffmpeg_tools
    source = make_video([text_image(), text_image(""), text_image("学生五人"), text_image("")])
    count = 0
    raw = make_document().cues[0].candidates[0].raw

    def recognize(*_):
        nonlocal count
        count += 1
        if count == 2:
            raise RuntimeError("synthetic cancellation")
        return raw

    saved = tmp_path / "incomplete.json"
    with pytest.raises(RuntimeError, match="cancellation"):
        scan_video(source, fixture_config(400), recognize, jobs_root=tmp_path / "jobs", ffmpeg=ffmpeg,
                   ffprobe=ffprobe, checkpoint=lambda d: d.save(saved))
    doc = OcrDocument.load(saved)
    assert not doc.complete and len(doc.cues) == 1 and "incomplete_scan" in doc.pending_issues
    with pytest.raises(OcrError):
        doc.resume(doc.visual_source)
    assert not list((tmp_path / "jobs").iterdir())


@pytest.mark.parametrize("explicit_sha", [True, False])
@pytest.mark.parametrize("checkpoint_flag", ["--checkpoint", "--review", None])
def test_cli_scan_review_resume_export_no_recognition_on_resume(make_video, text_image, ffmpeg_tools, tmp_path, monkeypatch,
                                                              explicit_sha, checkpoint_flag):
    ffmpeg, ffprobe = ffmpeg_tools
    source = make_video([text_image(""), text_image(), text_image(), text_image("")])
    root = tmp_path / "runtime"
    root.mkdir()
    profile = root / "profile.json"
    profile.write_text(json.dumps({"schema": "ocr-pilot-profile-v1", "id": "fixture",
                                  "packages": {"fixture": "1.0"},
                                  "models": {name: {"sha256": "d" * 64} for name in ("det", "rec", "cls")},
                                  "dictionary_sha256": "e" * 64, "dictionary_count": 10,
                                  "params": {"fixture": True}, "preprocessing": {"input": "fixture"}}))
    profile_sha = hashlib.sha256(profile.read_bytes()).hexdigest()
    def inspect(selected):
        assert selected == root
        return SimpleNamespace(profile_sha256=profile_sha)
    monkeypatch.setattr("videocaptioner.cli.commands.ocr.inspect_installation", inspect)
    bridge = tmp_path / "worker.py"
    bridge.write_text("# synthetic worker, never executed")
    calls = []
    raw = make_document().cues[0].candidates[0].raw

    class Runtime:
        def __init__(self, *_args, **_kwargs):
            self.bridge_sha256 = hashlib.sha256(bridge.read_bytes()).hexdigest()
            self.metrics = RuntimeMetrics()

        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def __call__(self, frame, check):
            check()
            calls.append(frame.pts)
            return EngineRead(raw.lines, profile_sha)

    monkeypatch.setattr("videocaptioner.core.ocr.service.CpuOcrRuntime", Runtime)
    monkeypatch.setattr("videocaptioner.core.ocr.service.jobs_directory", lambda: tmp_path / "jobs")
    monkeypatch.setattr("videocaptioner.cli.commands.ocr.jobs_directory", lambda: tmp_path / "jobs")
    review_path, output_path = tmp_path / "pending.json", tmp_path / "captions.json"
    arguments = ["ocr", str(source), "--roi", "0,0,1,1", "--start-ms", "0", "--end-ms", "400",
                 "--ocr-runtime", str(root), "--ocr-bridge", str(bridge), "--profile-sha256", profile_sha,
                 "--ffmpeg", ffmpeg, "--ffprobe", ffprobe, "-o", str(output_path)]
    if explicit_sha:
        arguments += ["--line-anchors", "0.5"]
    if checkpoint_flag:
        arguments += [checkpoint_flag, str(review_path)]
    if not explicit_sha:
        index = arguments.index("--profile-sha256")
        del arguments[index:index + 2]
    assert main(arguments) == EXIT.SUCCESS
    assert calls and output_path.is_file()
    data = ASRData.from_subtitle_file(str(output_path))
    assert data.segments[0].text == raw.text
    assert data.segments[0].ocr_metadata.observations[0].selected_candidate_id is None
    assert data.segments[0].ocr_metadata.config.line_selection == (LineSelectionPolicy() if explicit_sha else None)
    assert review_path.is_file() == bool(checkpoint_flag)
    # OCR defaults keep measured cues/text without approval or optimize/split.
    srt = tmp_path / "captions.srt"
    assert main(["subtitle", str(output_path), "-o", str(srt)]) == EXIT.SUCCESS
    assert raw.text in srt.read_text(encoding="utf-8")
    if not checkpoint_flag:
        return
    before = len(calls)
    doc = OcrDocument.load(review_path)
    cue = doc.cues[0]
    revised = tmp_path / "reviewed.json"
    args = ["ocr-review", str(review_path), "--source", str(source), "--ffprobe", ffprobe,
            "--select-candidate", f"{cue.id}:{cue.candidates[0].id}", "--note", "Synthetic text verified",
            "--save-review", str(revised), "-o", str(output_path)]
    assert main(args) == EXIT.SUCCESS
    assert len(calls) == before
    data = ASRData.from_subtitle_file(str(output_path))
    assert data.segments[0].text == raw.text and data.visual_source == doc.visual_source
    assert OcrDocument.load(review_path) == doc


def test_cli_blocks_overwriting_inputs_before_processing(tmp_path, monkeypatch):
    source = tmp_path / "source.json"
    source.write_text("preserve input")
    monkeypatch.setattr("videocaptioner.cli.commands.ocr.run_cpu_ocr", lambda *_a, **_k: pytest.fail("must not run"))
    assert main(["ocr", str(source), "--roi", "0,0,1,1", "--start-ms", "0", "--end-ms", "100",
                 "--ocr-runtime", str(tmp_path / "missing"), "--ocr-bridge", str(tmp_path / "worker.py"),
                 "--profile-sha256", "b" * 64, "--review", str(source)]) == EXIT.USAGE_ERROR
    assert source.read_text() == "preserve input"


def test_repeat_scan_reuses_disk_raw_preserves_ids_and_exports(make_video, text_image, ffmpeg_tools, tmp_path):
    ffmpeg, ffprobe = ffmpeg_tools
    source = make_video([text_image(""), text_image(), text_image(), text_image("")])
    raw = make_document().cues[0].candidates[0].raw
    calls = []

    def recognize(frame, check):
        calls.append(frame.pts)
        return raw

    def scan(config, cache_mib=64):
        return scan_video(source, config, recognize, jobs_root=tmp_path / "jobs", ffmpeg=ffmpeg,
                          ffprobe=ffprobe, cache_root=tmp_path / "cache", cache_mib=cache_mib)

    config = fixture_config(400)
    first = scan(config)
    before = len(calls)
    second = scan(config)
    assert len(calls) == before and second.metrics.fresh_calls == 0
    assert second.metrics.cache_hits == second.metrics.candidate_crops
    assert second.id == first.id and second.visual_source == first.visual_source
    assert second.pending_issues == first.pending_issues
    assert second.cues[0].id == first.cues[0].id
    assert [c.id for c in second.cues[0].candidates] == [c.id for c in first.cues[0].candidates]
    assert all(c.cache_hit and c.raw == raw for c in second.cues[0].candidates)
    data = second.resume(second.visual_source)
    assert tuple(c for segment in data.segments for c in segment.ocr_metadata.observations) == second.cues
    assert scan(config, cache_mib=0).metrics.fresh_calls > 0
    assert scan(replace(config, bridge_sha256="f" * 64)).metrics.fresh_calls > 0
    assert not list((tmp_path / "jobs").iterdir())


def test_retry_cancelled_scan_reuses_only_completed_reads(make_video, text_image, ffmpeg_tools, tmp_path):
    ffmpeg, ffprobe = ffmpeg_tools
    source = make_video([text_image(), text_image(""), text_image("学生五人"), text_image("")])
    raw = make_document().cues[0].candidates[0].raw
    calls, checkpoints = [], []
    fail_second = True

    def recognize(frame, check):
        calls.append(frame.pts)
        if fail_second and len(calls) == 2:
            raise OcrError("synthetic cancellation")
        return raw

    def scan():
        return scan_video(source, fixture_config(400), recognize, jobs_root=tmp_path / "jobs", ffmpeg=ffmpeg,
                          ffprobe=ffprobe, cache_root=tmp_path / "cache", checkpoint=checkpoints.append)

    with pytest.raises(OcrError, match="cancellation"):
        scan()
    partial = checkpoints[0]
    assert not partial.complete and "incomplete_scan" in partial.pending_issues
    fail_second = False
    final = scan()
    assert len(calls) == 3 and final.metrics.fresh_calls == 1 and final.complete
    assert final.cues[0].id == partial.cues[0].id
    assert final.cues[0].candidates[0].cache_hit
    assert final.pending_issues and not list((tmp_path / "jobs").iterdir())

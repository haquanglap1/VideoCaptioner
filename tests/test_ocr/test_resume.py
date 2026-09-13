"""Resume generated video from saved OCR evidence without rewriting reviewed cues."""

import hashlib
import subprocess
from dataclasses import replace

import pytest

from videocaptioner.core.ocr.document import OcrDocument, candidate_id
from videocaptioner.core.ocr.models import OcrError, Selection
from videocaptioner.core.ocr.service import scan_video
from videocaptioner.core.utils.subprocess_helper import _NO_WINDOW, child_environment

from .test_document import make_document
from .test_service import fixture_config


def without_hits(cues):
    return tuple(replace(cue, candidates=tuple(replace(c, cache_hit=False) for c in cue.candidates)) for cue in cues)


@pytest.mark.parametrize("offset,vfr", [(0, False), (5, False), (0, True), (5, True)])
@pytest.mark.parametrize("gap", [False, True])
def test_resume_keeps_reviewed_prefix_and_replays_only_boundary(
        make_video, text_image, ffmpeg_tools, tmp_path, offset, vfr, gap):
    ffmpeg, ffprobe = ffmpeg_tools
    blank, first, second = text_image(""), text_image(), text_image("学生五人")
    frames = [blank] + [first] * 3 + ([blank] if gap else []) + [second] * 4 + [blank] + [first] * 3 + [blank]
    source = make_video(frames, offset=offset, vfr=vfr)
    config = replace(fixture_config(2500), selection=Selection(50, 1900 if vfr else 1300))
    raw = make_document().cues[0].candidates[0].raw
    calls = []

    def recognize(frame, _check):
        calls.append(frame.pts)
        return raw

    def scan(resume=None, check=lambda: None, checkpoint=lambda _: None):
        return scan_video(source, config, recognize, jobs_root=tmp_path / "jobs", ffmpeg=ffmpeg,
                          ffprobe=ffprobe, cache_mib=0, resume_document=resume, check=check, checkpoint=checkpoint)

    full = scan()
    assert len(full.cues) == 3
    cues = tuple(c.select_candidate(c.candidates[0].id, "Synthetic text verified")
                 .review_timing(c.start_ms + 1, c.end_ms - 1, "Synthetic timing reviewed") for c in full.cues[:2])
    partial = replace(full, cues=cues, complete=False)
    path = tmp_path / "saved.json"
    partial.save(path)
    saved_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    calls.clear()
    continued = scan(OcrDocument.load(path))
    assert continued.complete and continued.id == full.id
    assert continued.cues[:2] == partial.cues
    assert without_hits(continued.cues[2:]) == without_hits(full.cues[2:])
    assert calls and min(calls) >= full.cues[2].first_pts
    assert continued.metrics.frames < full.metrics.frames
    assert continued.pending_issues and not list((tmp_path / "jobs").iterdir())
    assert hashlib.sha256(path.read_bytes()).hexdigest() == saved_hash


def test_real_cancel_save_resume_and_cancel_again_keep_checkpoint(
        make_video, text_image, ffmpeg_tools, tmp_path):
    ffmpeg, ffprobe = ffmpeg_tools
    source = make_video([text_image(), text_image(""), text_image("学生五人"),
                         text_image(""), text_image("学生七人"), text_image("")])
    raw = make_document().cues[0].candidates[0].raw
    saved, calls = [], []

    def fail_later(frame, _check):
        calls.append(frame.pts)
        if len(calls) == 3:
            raise OcrError("synthetic cancellation")
        return raw

    def scan(recognizer, resume=None, progress=lambda *_: None, check=lambda: None):
        return scan_video(source, fixture_config(600), recognizer, jobs_root=tmp_path / "jobs",
                          ffmpeg=ffmpeg, ffprobe=ffprobe, checkpoint=saved.append,
                          resume_document=resume, cache_mib=0, progress=progress, check=check)

    with pytest.raises(OcrError, match="cancellation"):
        scan(fail_later)
    partial = saved[-1]
    assert not partial.complete and len(partial.cues) == 2
    path = tmp_path / "partial.json"
    partial.save(path)
    stop = False

    def progress(*_):
        nonlocal stop
        stop = True

    def check():
        if stop:
            raise OcrError("cancel replay")

    with pytest.raises(OcrError, match="cancel replay"):
        scan(lambda *_: pytest.fail("no OCR during anchor replay"), partial, progress, check)
    assert saved[-1].cues == partial.cues and not saved[-1].complete
    continued = scan(lambda *_: raw, OcrDocument.load(path))
    assert continued.complete and continued.cues[:2] == partial.cues
    assert continued.metrics.fresh_calls == 1
    assert not list((tmp_path / "jobs").iterdir())


def test_resume_missing_anchor_or_changed_scope_never_advances(
        make_video, text_image, ffmpeg_tools, tmp_path):
    ffmpeg, ffprobe = ffmpeg_tools
    source = make_video([text_image(), text_image(""), text_image("学生五人"), text_image("")])
    raw = make_document().cues[0].candidates[0].raw
    config = fixture_config(400)
    saved = []

    def scan(config=config, resume=None, video=source, recognize=lambda *_: raw):
        return scan_video(video, config, recognize, jobs_root=tmp_path / "jobs", ffmpeg=ffmpeg,
                          ffprobe=ffprobe, cache_mib=0, resume_document=resume, checkpoint=saved.append)

    full = scan()
    partial = replace(full, cues=full.cues[:1], complete=False)
    with pytest.raises(OcrError, match="quét xong"):
        scan(resume=full)
    for changed in (replace(config, selection=Selection(10, 400)), replace(config, bridge_sha256="f" * 64)):
        with pytest.raises(OcrError, match="giữ nguyên"):
            scan(changed, partial)
    other = make_video([text_image("学生七人")] * 4)
    with pytest.raises(OcrError, match="mismatch"):
        scan(resume=partial, video=other, recognize=lambda *_: pytest.fail("source mismatch must precede inference"))
    cue = partial.cues[0]
    candidates = tuple(replace(c, crop_sha256="f" * 64,
                               id=candidate_id(partial.id, c.frame_pts, "f" * 64, c.raw)) for c in cue.candidates)
    damaged = replace(partial, cues=(replace(cue, candidates=candidates, raw_candidate_id=candidates[0].id),))
    with pytest.raises(OcrError, match="điểm nối"):
        scan(resume=damaged, recognize=lambda *_: pytest.fail("anchor mismatch must precede inference"))
    assert saved[-1].cues == damaged.cues and not saved[-1].complete


def test_resume_holding_limit_and_final_cue_do_not_change_boundaries(
        make_video, text_image, ffmpeg_tools, tmp_path):
    ffmpeg, ffprobe = ffmpeg_tools
    short = make_video([text_image()] * 10)
    source = tmp_path / "long-hold.mov"
    subprocess.run([ffmpeg, "-v", "error", "-nostdin", "-n", "-i", str(short),
                    "-vf", "setpts=PTS*100", "-fps_mode", "passthrough", "-c:v", "png", "-threads", "1", str(source)],
                   env=child_environment(), creationflags=_NO_WINDOW, check=True, timeout=30,
                   stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    raw = make_document().cues[0].candidates[0].raw

    def scan(resume=None):
        return scan_video(source, fixture_config(85000), lambda *_: raw, jobs_root=tmp_path / "jobs",
                          ffmpeg=ffmpeg, ffprobe=ffprobe, cache_mib=0, resume_document=resume)

    full = scan()
    assert len(full.cues) == 3 and all("track_holding_limit" in c.issues for c in full.cues)
    for count in (1, 2, 3):
        partial = replace(full, cues=full.cues[:count], complete=False)
        resumed = scan(partial)
        assert resumed.complete and without_hits(resumed.cues) == without_hits(full.cues)
        assert resumed.cues[:count] == partial.cues
        if count == 3:
            assert resumed.metrics.fresh_calls == 0


def test_cli_resumes_saved_config_and_preserves_checkpoint_input(
        make_video, text_image, ffmpeg_tools, tmp_path, monkeypatch):
    from videocaptioner.cli import exit_codes as EXIT
    from videocaptioner.cli.main import main

    ffmpeg, ffprobe = ffmpeg_tools
    source = make_video([text_image(), text_image(""), text_image("学生五人"), text_image("")])
    raw = make_document().cues[0].candidates[0].raw
    full = scan_video(source, fixture_config(400), lambda *_: raw, jobs_root=tmp_path / "jobs",
                      ffmpeg=ffmpeg, ffprobe=ffprobe, cache_mib=0)
    partial = replace(full, cues=full.cues[:1], complete=False)
    saved, result, output = tmp_path / "partial.json", tmp_path / "continued.json", tmp_path / "captions.srt"
    partial.save(saved)
    original = saved.read_bytes()
    called = []

    def run(source, config, _root, _bridge, **options):
        assert options["resume_document"] == partial and config == partial.config
        called.append(True)
        return scan_video(source, config, lambda *_: raw, jobs_root=tmp_path / "jobs",
                          ffmpeg=options["ffmpeg"], ffprobe=options["ffprobe"],
                          cache_mib=options["cache_mib"], checkpoint=options["checkpoint"],
                          resume_document=options["resume_document"])

    monkeypatch.setattr("videocaptioner.cli.commands.ocr.run_cpu_ocr", run)
    arguments = ["ocr-resume", str(saved), "--source", str(source), "--review", str(result),
                 "--ffmpeg", ffmpeg, "--ffprobe", ffprobe, "--cache-mib", "0", "-o", str(output)]
    assert main(arguments) == EXIT.SUCCESS
    assert called == [True] and output.is_file() and saved.read_bytes() == original
    continued = OcrDocument.load(result)
    assert continued.complete and continued.cues[0] == partial.cues[0]
    assert without_hits(continued.cues) == without_hits(full.cues)
    called.clear()
    for protected in (saved, source):
        args = arguments.copy()
        args[args.index("--review") + 1] = str(protected)
        assert main(args) == EXIT.USAGE_ERROR
        assert not called and saved.read_bytes() == original


def test_resume_fade_and_empty_checkpoint_keep_original_selection(
        make_video, text_image, ffmpeg_tools, tmp_path):
    ffmpeg, ffprobe = ffmpeg_tools
    frames = [text_image(level=level) for level in (30, 90, 180, 255, 180, 90, 30)]
    frames += [text_image(""), text_image("学生五人"), text_image("")]
    source = make_video(frames, vfr=True, offset=3)
    config = replace(fixture_config(1400), selection=Selection(50, 1400))
    raw = make_document().cues[0].candidates[0].raw

    def scan(resume=None):
        return scan_video(source, config, lambda *_: raw, jobs_root=tmp_path / "jobs", ffmpeg=ffmpeg,
                          ffprobe=ffprobe, resume_document=resume, cache_mib=0)

    full = scan()
    assert "selection_clipped_start" in full.cues[0].issues and "fade_or_contrast_change" in full.cues[0].issues
    for cues in ((), full.cues[:1]):
        result = scan(replace(full, complete=False, cues=cues))
        assert result.complete and without_hits(result.cues) == without_hits(full.cues)

import ast
import hashlib
from dataclasses import replace
from pathlib import Path

import pytest

from videocaptioner.core.ocr.installation import inspect_installation, resources
from videocaptioner.core.ocr.models import OcrError
from videocaptioner.core.ocr.preview import preview_candidate, preview_video
from videocaptioner.core.ocr.service import scan_video

from .test_document import make_document
from .test_service import fixture_config


def test_bundled_worker_keeps_pilot_program_and_profile():
    root = Path(__file__).parents[2]
    source = root / "scripts/ocr_stream_worker.py"
    bundled = resources() / "ocr_stream_worker.py"
    assert ast.dump(ast.parse(source.read_text(encoding="utf-8"))) == ast.dump(ast.parse(bundled.read_text(encoding="utf-8")))
    assert (resources() / "profile.json").read_bytes() == (root / "scripts/ocr_pilot_data/profile.json").read_bytes()


def test_missing_installation_never_loads_or_installs(tmp_path):
    with pytest.raises(OcrError, match="runtime"):
        inspect_installation(tmp_path)
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("rotation,sar", [(0, "1/1"), (90, "2/1"), (180, "1/1"), (270, "1/1")])
def test_exact_candidate_preview_matches_pts_transform_and_sha(make_video, text_image, ffmpeg_tools, tmp_path, rotation, sar):
    ffmpeg, ffprobe = ffmpeg_tools
    video = make_video([text_image(""), text_image("学生三人\n2026年"), text_image("学生三人\n2026年"), text_image("")],
                       offset=3, vfr=True, rotation=rotation, sar=sar)
    jobs = tmp_path / "jobs"
    raw = make_document().cues[0].candidates[0].raw
    doc = scan_video(video, fixture_config(500), lambda *_: raw, jobs_root=jobs, ffmpeg=ffmpeg, ffprobe=ffprobe)
    candidate = doc.cues[0].candidates[0]
    preview = preview_candidate(video, doc, candidate, jobs, ffmpeg=ffmpeg, ffprobe=ffprobe)
    assert preview.png.startswith(b"\x89PNG")
    assert preview.source_sha256 == doc.visual_source.snapshot_sha256
    assert preview.video == doc.visual_source.video
    positioned = preview_video(video, 100, jobs, ffmpeg=ffmpeg, ffprobe=ffprobe)
    assert positioned.png == preview.png
    assert not list(jobs.iterdir())
    with pytest.raises(OcrError, match="không thuộc"):
        preview_candidate(video, doc, replace(candidate, crop_sha256="a" * 64), jobs, ffmpeg=ffmpeg, ffprobe=ffprobe)


def test_preview_source_mutation_blocks_scan_before_recognizer(make_video, text_image, ffmpeg_tools, tmp_path):
    ffmpeg, ffprobe = ffmpeg_tools
    video = make_video([text_image()] * 3)
    with pytest.raises(OcrError, match="thay đổi"):
        scan_video(video, fixture_config(300), lambda *_: pytest.fail("must not recognize"),
                   jobs_root=tmp_path / "jobs", ffmpeg=ffmpeg, ffprobe=ffprobe,
                   expected_source_sha256=hashlib.sha256(b"different video").hexdigest())

import hashlib
from types import SimpleNamespace

import pytest

from videocaptioner.core.ocr.models import OcrError
from videocaptioner.core.ocr.source import video_snapshot


def test_snapshot_hash_in_single_copy_and_cleanup(tmp_path):
    source = tmp_path / "synthetic.mp4"
    source.write_bytes(b"synthetic video bytes")
    before = source.stat().st_mtime_ns
    jobs = tmp_path / "jobs"
    with video_snapshot(source, jobs) as snapshot:
        assert snapshot.path.read_bytes() == source.read_bytes()
        assert snapshot.sha256 == hashlib.sha256(source.read_bytes()).hexdigest()
        assert snapshot.size_bytes == source.stat().st_size
        source.write_bytes(b"changed after snapshot")
        assert snapshot.path.read_bytes() == b"synthetic video bytes"
    assert not snapshot.path.exists() and list(jobs.iterdir()) == []
    assert source.exists() and source.stat().st_mtime_ns >= before


def test_snapshot_cancel_cleans_only_job(tmp_path):
    source = tmp_path / "synthetic.mp4"
    source.write_bytes(b"x" * (2 * 1024 * 1024))
    jobs = tmp_path / "jobs"
    jobs.mkdir()
    keep = jobs / "keep.bin"
    keep.write_bytes(b"preserve")
    checks = 0

    def check():
        nonlocal checks
        checks += 1
        if checks == 3:
            raise RuntimeError("cancelled")

    with pytest.raises(RuntimeError, match="cancelled"), video_snapshot(source, jobs, check):
        pytest.fail("cancelled snapshot must not yield")
    assert list(jobs.iterdir()) == [keep]
    assert source.stat().st_size == 2 * 1024 * 1024


def test_snapshot_rejects_disk_shortage(tmp_path, monkeypatch):
    source = tmp_path / "synthetic.mp4"
    source.write_bytes(b"fixture")
    monkeypatch.setattr("videocaptioner.core.ocr.source.shutil.disk_usage", lambda _: SimpleNamespace(free=0))
    with pytest.raises(OcrError, match="disk space"), video_snapshot(source, tmp_path / "jobs"):
        pytest.fail("disk shortage must not yield")

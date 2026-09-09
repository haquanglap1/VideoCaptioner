"""Real loopback HTTP interruption/Range and isolated disk failures, without weights."""

import errno
import hashlib
import socket
import urllib.error
from pathlib import Path
from types import SimpleNamespace

import pytest

from videocaptioner.core.tts.omnivoice import config, prepare


def test_http_interruption_retains_partial_and_resumes_exact_offset(tmp_path, loopback_download):
    path = tmp_path / "weights.bin"
    part = path.with_suffix(".bin.part")
    expected = hashlib.sha256(loopback_download.payload).hexdigest()
    loopback_download.mode = "interrupt"
    with pytest.raises(RuntimeError, match="interrupted"):
        prepare.download(loopback_download.url, path, expected)
    assert part.read_bytes() == loopback_download.payload[:1024 * 1024 + 137]
    assert not path.exists() and not path.with_suffix(".bin.rejected").exists()
    offset = part.stat().st_size
    loopback_download.mode = "complete"
    prepare.download(loopback_download.url, path, expected)
    assert loopback_download.requests[-1] == {
        "range": f"bytes={offset}-", "status": 206,
        "content_range": f"bytes {offset}-{len(loopback_download.payload) - 1}/{len(loopback_download.payload)}",
    }
    assert path.read_bytes() == loopback_download.payload and not part.exists()


def test_completed_partial_is_verified_without_http_416(tmp_path, loopback_download):
    path = tmp_path / "weights.bin"
    path.with_suffix(".bin.part").write_bytes(loopback_download.payload)
    prepare.download(loopback_download.url, path, hashlib.sha256(loopback_download.payload).hexdigest())
    assert path.read_bytes() == loopback_download.payload
    assert not loopback_download.requests


def test_corrupt_completed_partial_recovers_from_http_416(tmp_path, loopback_download):
    path = tmp_path / "source.zip"
    part = path.with_suffix(".zip.part")
    damaged = b"x" * len(loopback_download.payload)
    part.write_bytes(damaged)
    prepare.download(loopback_download.url, path, hashlib.sha256(loopback_download.payload).hexdigest())
    assert [request["status"] for request in loopback_download.requests] == [416, 200]
    assert loopback_download.requests[-1]["range"] is None
    assert path.with_suffix(".zip.rejected").read_bytes() == damaged
    assert path.read_bytes() == loopback_download.payload


def test_unreachable_socket_keeps_partial_for_resume(tmp_path, loopback_download):
    path = tmp_path / "weights.bin"
    part = path.with_suffix(".bin.part")
    partial = loopback_download.payload[:12345]
    part.write_bytes(partial)
    expected = hashlib.sha256(loopback_download.payload).hexdigest()
    # A bound but non-listening local socket reliably refuses the connection.
    with socket.socket() as unavailable:
        unavailable.bind(("127.0.0.1", 0))
        url = f"http://127.0.0.1:{unavailable.getsockname()[1]}/model"
        with pytest.raises(urllib.error.URLError):
            prepare.download(url, path, expected)
    assert part.read_bytes() == partial and not path.exists()
    prepare.download(loopback_download.url, path, expected)
    assert loopback_download.requests[-1]["range"] == f"bytes={len(partial)}-"
    assert path.read_bytes() == loopback_download.payload


@pytest.mark.parametrize("mode", ["ignore-range", "bad-range", "bad-range-end", "bad-range-length"])
def test_http_range_policy_keeps_partial_on_bad_headers(tmp_path, loopback_download, mode):
    path = tmp_path / "weights.bin"
    part = path.with_suffix(".bin.part")
    partial = loopback_download.payload[:12345]
    part.write_bytes(partial)
    loopback_download.mode = mode
    expected = hashlib.sha256(loopback_download.payload).hexdigest()
    if mode.startswith("bad-range"):
        with pytest.raises(RuntimeError, match="range mismatch"):
            prepare.download(loopback_download.url, path, expected)
        assert part.read_bytes() == partial and not path.exists()
    else:
        prepare.download(loopback_download.url, path, expected)
        assert path.read_bytes() == loopback_download.payload and not part.exists()


def test_disk_preflight_keeps_existing_partial(staged_runtime, loopback_download, monkeypatch):
    part = staged_runtime / "model/weights.bin.part"
    part.parent.mkdir()
    part.write_bytes(loopback_download.payload[:12345])
    monkeypatch.setattr(prepare.shutil, "disk_usage", lambda path: SimpleNamespace(free=0))
    with pytest.raises(OSError, match="space"):
        prepare.prepare_runtime(str(staged_runtime))
    assert part.read_bytes() == loopback_download.payload[:12345]
    assert not (staged_runtime / "ready.json").exists()


def test_disk_write_failure_preserves_offset_for_next_attempt(staged_runtime, loopback_download, monkeypatch):
    original_open = Path.open
    part = staged_runtime / "model/weights.bin.part"

    class FullDisk:
        def __init__(self, file):
            self.file = file
            self.writes = 0

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.file.close()

        def write(self, block):
            if self.writes:
                raise OSError(errno.ENOSPC, "fixture disk full")
            self.writes += 1
            return self.file.write(block)

    def disk_open(path, mode="r", *args, **kwargs):
        file = original_open(path, mode, *args, **kwargs)
        return FullDisk(file) if path == part and mode in ("wb", "ab") else file

    with monkeypatch.context() as patch:
        patch.setattr(Path, "open", disk_open)
        with pytest.raises(OSError, match="disk full"):
            prepare.prepare_runtime(str(staged_runtime))
    offset = part.stat().st_size
    assert 0 < offset < len(loopback_download.payload)
    assert not (staged_runtime / "ready.json").exists()
    prepare.prepare_runtime(str(staged_runtime))
    assert loopback_download.requests[-1]["range"] == f"bytes={offset}-"
    prepare.verify(staged_runtime)


def test_failed_repair_clears_stale_ready_marker(staged_runtime, loopback_download):
    prepare.prepare_runtime(str(staged_runtime))
    (staged_runtime / "model/weights.bin").write_bytes(b"altered")
    loopback_download.mode = "corrupt"
    with pytest.raises(RuntimeError, match="checksum"):
        prepare.prepare_runtime(str(staged_runtime))
    assert not (staged_runtime / "ready.json").exists()
    assert config.status(str(staged_runtime)) == "Not prepared"
    assert (staged_runtime / "model/weights.bin.rejected").is_file()


def test_lazy_status_does_not_claim_checksum_verification(staged_runtime, loopback_download):
    prepare.prepare_runtime(str(staged_runtime))
    (staged_runtime / "model/weights.bin").write_bytes(b"x" * len(loopback_download.payload))
    assert "Ready" not in config.status(str(staged_runtime))
    with pytest.raises(RuntimeError, match="not ready"):
        prepare.verify(staged_runtime)

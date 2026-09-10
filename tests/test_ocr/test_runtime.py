"""Supervise real test processes without loading OCR models or touching user data."""

import hashlib
import io
import json
import subprocess
import sys
import time
from fractions import Fraction

import pytest

from videocaptioner.core.ocr.models import OcrError, RoiFrame
from videocaptioner.core.ocr.runtime import CpuOcrRuntime


@pytest.fixture
def runtime_factory(tmp_path, monkeypatch):
    root = tmp_path / "runtime"
    (root / "env").mkdir(parents=True)
    (root / "env/python.exe").write_bytes(b"test executable marker")
    profile = root / "profile.json"
    profile.write_text("{}")
    bridge = tmp_path / "worker.py"
    bridge.write_text('''
import argparse,hashlib,json,sys,time
from pathlib import Path
p=argparse.ArgumentParser()
p.add_argument('--root',type=Path); p.add_argument('--job-dir',type=Path); p.add_argument('--profile-sha256')
a=p.parse_args()
mode=(a.root/'mode.txt').read_text()
metrics={'network_attempts':0,'inference_calls':{'det':0,'rec':0,'cls':0}}
def emit(x): print(json.dumps(x),flush=True)
if mode=='startup-stall': time.sleep(20)
if mode=='exit': sys.exit(7)
if mode=='flood':
 sys.stderr.buffer.write(b'x'*1048576); sys.stderr.flush()
if mode=='oversized': print('x'*1048577,flush=True); sys.exit(0)
emit({'status':'ready','protocol':'ocr-stream-v1','profile_sha256':a.profile_sha256,
      'bridge_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
      'provider':'wrong' if mode=='identity' else 'CPUExecutionProvider','metrics':metrics})
for line in sys.stdin:
 r=json.loads(line)
 if mode=='malformed': print('not-json',flush=True); break
 if mode in ('timeout','cancel'):
  emit({'status':'inference','request_id':r['request_id'],'stage':'det',
        'inference_calls':{'det':1,'rec':0,'cls':0}})
  time.sleep(20)
 raw=(a.job_dir/'frame.rgb').read_bytes()
 sha=hashlib.sha256(raw).hexdigest()
 assert sha==r['crop_sha256'] and len(raw)==r['width']*r['height']*3
 score=2 if mode=='score' else 0.9
 result={'revision':a.profile_sha256,'inference_s':0.01,
         'lines':[{'text':'fixture','score':score,'box':[[0,0],[2,0],[2,2],[0,2]]}]}
 emit({'status':'result','request_id':99 if mode=='request-id' else r['request_id'],
       'crop_sha256':sha,'result':result,'metrics':metrics})
''', encoding="utf-8")
    popen = subprocess.Popen

    def launch(command, **kwargs):
        if command[0] == str(root / "env/python.exe"):
            command = [sys.executable, *command[1:]]
        return popen(command, **kwargs)

    monkeypatch.setattr("videocaptioner.core.ocr.runtime.subprocess.Popen", launch)

    def make(mode="good"):
        (root / "mode.txt").write_text(mode)
        return CpuOcrRuntime(root, bridge, tmp_path / "jobs", hashlib.sha256(profile.read_bytes()).hexdigest(),
                             timeout=0.4, startup_timeout=0.7)
    return make


def sample_frame():
    return RoiFrame(0, 0, Fraction(1, 1000), Fraction(0), 2, 2, b"\0" * 12)


def assert_closed(runtime):
    assert runtime.state == "closed" and runtime.process.poll() is not None
    assert all(not reader.is_alive() for reader in runtime.readers)
    assert runtime.directory is not None and not runtime.directory.exists()


@pytest.mark.parametrize("mode", ["good", "flood"])
def test_runtime_reuses_worker_and_drains_stderr(runtime_factory, mode):
    runtime = runtime_factory(mode)
    with runtime:
        pid = runtime.process.pid
        assert runtime(sample_frame()).text == "fixture"
        assert runtime(sample_frame()).text == "fixture"
        assert runtime.process.pid == pid and runtime.metrics.completed == 2
    assert_closed(runtime)
    if mode == "flood":
        assert runtime.metrics.stderr_bytes == 1048576


@pytest.mark.parametrize("mode,match", [
    ("startup-stall", "timed out"), ("exit", "exited"), ("identity", "identity"),
    ("oversized", "Oversized"), ("malformed", "protocol"), ("score", "Invalid CPU"),
    ("request-id", "request/request|response/request"), ("timeout", "timed out"),
])
def test_runtime_faults_kill_owned_process_join_and_cleanup(runtime_factory, mode, match):
    runtime = runtime_factory(mode)
    start = time.monotonic()
    with pytest.raises(OcrError, match=match), runtime:
        runtime(sample_frame())
    assert_closed(runtime)
    assert time.monotonic() - start < 6


def test_cancel_during_inference_preserves_attempt_counter(runtime_factory):
    runtime = runtime_factory("cancel")

    def check():
        if runtime.state == "inference":
            raise RuntimeError("cancelled")

    with pytest.raises(RuntimeError, match="cancelled"), runtime:
        runtime(sample_frame(), check)
    assert_closed(runtime)
    assert runtime.metrics.requests == 1 and runtime.metrics.completed == 0
    assert runtime.metrics.started_inference_calls == {"det": 1, "rec": 0, "cls": 0}


def test_invalid_profile_rejected_before_process(runtime_factory):
    runtime = runtime_factory()
    (runtime.root / "profile.json").write_text(json.dumps({"changed": True}))
    with pytest.raises(OcrError, match="hash mismatch"):
        runtime.start()
    assert runtime.process is None


def test_worker_transport_is_utf8_even_with_windows_ansi_stdout(monkeypatch):
    from scripts.ocr_stream_worker import emit

    buffer = io.BytesIO()
    stream = io.TextIOWrapper(buffer, encoding="cp1252")
    monkeypatch.setattr("scripts.ocr_stream_worker.sys.stdout", stream)
    emit({"text": "學生三人，2026年。"})
    assert json.loads(buffer.getvalue().decode("utf-8")) == {"text": "學生三人，2026年。"}


def test_request_budget_does_not_silently_restart_worker(runtime_factory):
    runtime = runtime_factory()
    runtime.max_requests = 1
    with runtime:
        runtime(sample_frame())
        with pytest.raises(OcrError, match="budget exhausted"):
            runtime(sample_frame())
    assert_closed(runtime)
    assert runtime.metrics.requests == runtime.metrics.completed == 1

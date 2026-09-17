"""Synthetic recognizer routing and compatibility contracts; no model inference."""

import hashlib
from dataclasses import replace
from fractions import Fraction
from pathlib import Path

import pytest

from videocaptioner.core.ocr.codec import decode, digest, encode
from videocaptioner.core.ocr.consensus import CacheScope
from videocaptioner.core.ocr.document import OcrConfig
from videocaptioner.core.ocr.geometry import Roi
from videocaptioner.core.ocr.line_selection import LineSelectionPolicy
from videocaptioner.core.ocr.models import EngineRead, OcrError, ReadLine, RoiFrame, Selection
from videocaptioner.core.ocr.vl import VlProfile, crop_line, parse_generation


def profile():
    return VlProfile("paddleocr-vl-1.5-anchor-v1", "a" * 64, "b" * 64)


def frame():
    return RoiFrame(0, 100, Fraction(1, 1000), Fraction(100), 100, 40, bytes(range(200)) * 60)


def test_legacy_config_encoding_and_identity_are_unchanged():
    config = OcrConfig(Roi(0, 0, 1, 1), Selection(0, 1000), "c" * 64, "d" * 64)
    payload = encode(config)
    assert "recognizer" not in payload
    assert config.read_revision == config.profile_sha256
    assert decode(OcrConfig, payload) == config
    assert digest(payload) == digest(config)
    raw = EngineRead((), "c" * 64)
    assert encode(raw) == {"lines": [], "revision": "c" * 64}


def test_recognizer_identity_changes_cache_and_roundtrips():
    base = OcrConfig(Roi(0, 0, 1, 1), Selection(0, 1000), "c" * 64, "d" * 64,
                     line_selection=LineSelectionPolicy())
    config = replace(base, recognizer=profile())
    other = replace(config, recognizer=replace(profile(), worker_sha256="e" * 64))
    assert len({digest(base), digest(config), digest(other)}) == 3
    assert config.read_revision != base.read_revision
    assert CacheScope("f" * 64, config.read_revision, digest(config)) != CacheScope(
        "f" * 64, other.read_revision, digest(other))
    assert decode(OcrConfig, encode(config)) == config


def test_crop_uses_geometry_and_original_rgb_only():
    source = frame()
    raw = EngineRead((ReadLine("untrusted old CTC text", .9, ((20, 12), (70, 12), (70, 28), (20, 28))),), "c" * 64)
    crop, bounds = crop_line(source, raw, LineSelectionPolicy())
    assert bounds == (12, 8, 78, 32)
    assert (crop.width, crop.height, crop.pts) == (66, 24, source.pts)
    assert crop.rgb[:198] == source.rgb[(8 * 100 + 12) * 3:(8 * 100 + 78) * 3]
    changed = replace(raw, lines=(replace(raw.lines[0], text="different answer"),))
    assert crop_line(source, changed, LineSelectionPolicy()) == (crop, bounds)


def test_blank_does_not_call_generator_and_selection_is_required():
    assert crop_line(frame(), EngineRead((), "c" * 64), LineSelectionPolicy()) is None
    with pytest.raises(OcrError):
        replace(OcrConfig(Roi(0, 0, 1, 1), Selection(0, 1000), "c" * 64, "d" * 64), recognizer=profile())


def test_generation_keeps_exact_raw_tokens_and_provenance():
    crop = frame()
    payload = {"text": "Example...", "raw_decode": "Example...<eos>", "token_ids": [42, 2],
               "eos": True, "eos_token_id": 2, "inference_s": .1}
    raw = parse_generation(payload, crop, (0, 0, 100, 40), "e" * 64, ())
    assert raw.text == payload["text"]
    assert raw.generation.token_ids == (42, 2)
    assert raw.generation.crop_sha256 == hashlib.sha256(crop.rgb).hexdigest()
    assert raw.lines[0].score == 0  # No invented confidence for autoregressive text.
    assert decode(EngineRead, encode(raw)) == raw


@pytest.mark.parametrize("change", [
    {"eos": False}, {"token_ids": []}, {"token_ids": [103424, 2]},
    {"token_ids": [42, 3]}, {"token_ids": [42] * 97 + [2]},
    {"text": 12}, {"inference_s": float("nan")},
])
def test_invalid_or_truncated_generation_never_becomes_success(change):
    payload = {"text": "Example", "raw_decode": "Example<eos>", "token_ids": [42, 2],
               "eos": True, "eos_token_id": 2, "inference_s": .1, **change}
    with pytest.raises(OcrError):
        parse_generation(payload, frame(), (0, 0, 100, 40), "e" * 64, ())


def test_routing_counts_both_engines_and_never_passes_ctc_text():
    from types import SimpleNamespace

    from videocaptioner.core.ocr.vl import VlRecognizer

    class Cpu:
        metrics = SimpleNamespace(requests=0)

        def __call__(self, source, check):
            check()
            self.metrics.requests += 1
            return EngineRead((ReadLine("CTC answer", .9, ((20, 12), (70, 12), (70, 28), (20, 28))),), "c" * 64)

    class Gpu:
        metrics = SimpleNamespace(requests=0)

        def generate(self, crop, bounds, revision, geometry, check):
            self.metrics.requests += 1
            # Geometry text is retained as provenance only; generation gets a pixel frame.
            assert isinstance(crop, RoiFrame) and crop.width == 66
            return parse_generation({"text": "GPU raw", "raw_decode": "GPU raw<eos>",
                "token_ids": [42, 2], "eos": True, "eos_token_id": 2, "inference_s": .1},
                crop, bounds, revision, geometry)

    cpu, gpu = Cpu(), Gpu()
    recognizer = VlRecognizer(cpu, gpu, LineSelectionPolicy(), "e" * 64, 2)
    assert recognizer(frame(), lambda: None).text == "GPU raw"
    with pytest.raises(OcrError, match="budget"):
        recognizer(frame(), lambda: None)
    assert cpu.metrics.requests == gpu.metrics.requests == 1


def test_generated_read_disk_cache_keeps_evidence_and_rejects_other_recipe(tmp_path):
    from videocaptioner.core.ocr.cache import RawReadStore

    payload = {"text": "Example", "raw_decode": "Example<eos>", "token_ids": [42, 2],
               "eos": True, "eos_token_id": 2, "inference_s": .1}
    raw = parse_generation(payload, frame(), (0, 0, 100, 40), "e" * 64, ())
    store = RawReadStore(tmp_path / "cache", 4096)
    try:
        store.open()
        store.put("f" * 64, raw)
        assert store.get("f" * 64, "e" * 64) == raw
        assert store.get("f" * 64, "b" * 64) is None
    finally:
        store.close()


@pytest.fixture
def gpu_runtime(tmp_path, monkeypatch):
    import sys

    from videocaptioner.core.ocr.vl import PaddleVlRuntime, VlInstallation

    bridge = tmp_path / "paddle_vl_worker.py"
    bridge.write_text('''
import argparse, hashlib, json, sys, time
from pathlib import Path
p=argparse.ArgumentParser()
p.add_argument('--root',type=Path); p.add_argument('--job-dir',type=Path); p.add_argument('--profile-sha256')
a=p.parse_args()
mode=(a.root/'mode').read_text()
def emit(x): print(json.dumps(x),flush=True)
metrics={'network_attempts':0,'inference_calls':{'det':0,'rec':0,'cls':0}}
emit({'status':'ready','protocol':'ocr-stream-v1','profile_sha256':a.profile_sha256,
      'bridge_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
      'provider':'CPUExecutionProvider' if mode=='wrong-provider' else 'CUDAExecutionProvider','metrics':metrics})
for line in sys.stdin:
 r=json.loads(line)
 metrics['inference_calls']['rec']+=1
 emit({'status':'inference','request_id':r['request_id'],'inference_calls':metrics['inference_calls']})
 if mode in ('cancel','timeout'): time.sleep(20)
 emit({'status':'result','request_id':r['request_id'],'crop_sha256':r['crop_sha256'],'metrics':metrics,
       'result':{'text':'Raw fixture','raw_decode':'Raw fixture<eos>','token_ids':[42,2],
                 'eos':mode!='no-eos','eos_token_id':2,'inference_s':.01}})
''', encoding="utf-8")
    spec = replace(profile(), worker_sha256=hashlib.sha256(bridge.read_bytes()).hexdigest())
    installation = VlInstallation(tmp_path, Path(sys.executable), tmp_path, tmp_path, spec)
    monkeypatch.setattr("videocaptioner.core.ocr.vl.resources", lambda: tmp_path)
    monkeypatch.setattr("videocaptioner.core.ocr.vl.inspect_vl", lambda *_args: installation)

    def make(mode):
        (tmp_path / "mode").write_text(mode)
        return PaddleVlRuntime(installation, tmp_path / "jobs", timeout=.3)
    return make


@pytest.mark.parametrize("mode", ["cancel", "timeout", "no-eos", "wrong-provider"])
def test_gpu_failure_closes_real_process_readers_and_lease(gpu_runtime, mode):
    import time

    runtime = gpu_runtime(mode)

    def check():
        if mode == "cancel" and runtime.state == "inference":
            raise OcrError("cancelled")

    begun = time.monotonic()
    with pytest.raises(OcrError), runtime:
        runtime.generate(frame(), (0, 0, 100, 40), "e" * 64, (), check)
    assert runtime.process.poll() is not None
    assert not any(t.is_alive() for t in runtime.readers)
    assert not runtime.directory.exists()
    assert runtime.lease.handle is None
    assert runtime.metrics.requests == (0 if mode == "wrong-provider" else 1)
    assert runtime.metrics.completed == 0
    assert time.monotonic() - begun < 5


def test_gpu_raw_generation_through_supervised_process(gpu_runtime):
    runtime = gpu_runtime("good")
    with runtime:
        raw = runtime.generate(frame(), (0, 0, 100, 40), "e" * 64, (), lambda: None)
    assert raw.text == "Raw fixture" and raw.generation.token_ids == (42, 2)
    assert runtime.metrics.requests == runtime.metrics.completed == 1
    assert runtime.metrics.started_inference_calls["rec"] == 1


def test_resume_refuses_missing_recognizer_before_starting_cpu(tmp_path, monkeypatch):
    from videocaptioner.core.ocr.service import run_cpu_ocr

    config = OcrConfig(Roi(0, 0, 1, 1), Selection(0, 1000), "c" * 64, "d" * 64,
                       line_selection=LineSelectionPolicy(), recognizer=profile())
    monkeypatch.setattr("videocaptioner.core.ocr.service.CpuOcrRuntime", lambda *_a, **_kw: pytest.fail("CPU started"))
    with pytest.raises(OcrError, match="recognizer runtime"):
        run_cpu_ocr(tmp_path / "source", config, tmp_path, tmp_path / "bridge")


@pytest.mark.parametrize("target", ["model/config.json", "deps/package.json", "python/Lib/package.json"])
def test_cli_output_cannot_overwrite_payload_outside_manifest_root(tmp_path, monkeypatch, target):
    from videocaptioner.cli.commands.ocr import _recognizer_profile
    from videocaptioner.core.ocr.vl import VlInstallation

    installation = VlInstallation(tmp_path / "manifest", tmp_path / "python/Scripts/python.exe",
                                  tmp_path / "model", tmp_path / "deps", profile())
    monkeypatch.setattr("videocaptioner.core.ocr.vl.inspect_vl", lambda _: installation)
    with pytest.raises(OcrError, match="must not replace"):
        _recognizer_profile(installation.root, [], [str(tmp_path / target)])

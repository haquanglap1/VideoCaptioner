"""S5.1 offline regressions; fake providers do not establish model/API acceptance."""

import importlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydub.generators import Sine

from videocaptioner.core.asr.asr_data import ASRData, ASRDataSeg
from videocaptioner.core.asr.local import pipeline
from videocaptioner.core.asr.local.profiles import MODELS, PROTOCOL, LocalASRConfig
from videocaptioner.core.asr.local.runtime import LocalLayout, LocalRuntime, LocalRuntimeError
from videocaptioner.core.asr.metadata import ASRMetadata
from videocaptioner.core.entities import TranscribeConfig, TranscribeModelEnum


@pytest.mark.parametrize("engine", [TranscribeModelEnum.QWEN_LOCAL, TranscribeModelEnum.WHISPER_API])
@pytest.mark.parametrize("failure", [False, True])
def test_hybrid_uses_one_owned_source_after_original_changes(tmp_path, monkeypatch, engine, failure):
    module = importlib.import_module("videocaptioner.core.asr.transcribe")
    original = tmp_path / "input.wav"
    original.write_bytes(b"original recording")
    paths = []
    data = ASRData([ASRDataSeg("synthetic", 0, 1000)])

    def create(path, config):
        paths.append(Path(path))
        assert Path(path).read_bytes() == b"original recording"

        def run(callback):
            original.write_bytes(b"different recording")
            if failure:
                raise LocalRuntimeError("cancelled")
            return data

        return SimpleNamespace(run=run)

    def diarize(path, source, *a, **k):
        assert source is data
        assert Path(path).read_bytes() == b"original recording"
        assert Path(path) == paths[0]
        return source

    monkeypatch.setattr(module, "_create_asr_instance", create)
    monkeypatch.setattr(module, "add_local_speakers", diarize)
    config = TranscribeConfig(transcribe_model=engine, local_asr=LocalASRConfig(diarize=True))
    if failure:
        with pytest.raises(LocalRuntimeError, match="cancelled"):
            module.transcribe(str(original), config)
    else:
        assert module.transcribe(str(original), config) is data
    assert original.read_bytes() == b"different recording"
    assert paths[0] != original and not paths[0].exists()


@pytest.mark.parametrize("metadata,end", [(None, 1001), (ASRMetadata("soniox", "job", "A"), 1000)])
def test_invalid_diarization_input_rejected_before_model_load(monkeypatch, metadata, end):
    audio = Sine(400).to_audio_segment(1000).set_frame_rate(16000).set_channels(1)
    monkeypatch.setattr(pipeline, "decode_audio", lambda *a: audio)
    monkeypatch.setattr(pipeline, "diarization_preflight", lambda *a, **k: "layout")
    monkeypatch.setattr(pipeline, "LocalRuntime", lambda *a: pytest.fail("Invalid source must not load a GPU model"))
    data = ASRData([ASRDataSeg("synthetic", 0, end, metadata=metadata)])
    with pytest.raises(ValueError, match="timing|Existing diarization"):
        pipeline.add_local_speakers("unused", data, TranscribeConfig(), aligned=False)


@pytest.mark.parametrize("field,value", [("revision", "wrong"), ("model", "community-1"), ("protocol", "wrong")])
def test_request_identity_mismatch_stops_owned_runtime(tmp_path, field, value):
    model = MODELS["qwen-0.6b"]
    ready = {"status": "ready", "protocol": PROTOCOL, "model": model.id, "revision": model.revision}
    changed = {**ready, field: value}
    bridge = tmp_path / "bridge.py"
    bridge.write_text(
        "import json,sys\nfrom pathlib import Path\n"
        f"print({json.dumps(ready)!r}, flush=True)\n"
        "for line in sys.stdin:\n"
        " root = Path(json.loads(line)['directory'])\n"
        " (root/'result.json').write_text('{}')\n"
        f" print({json.dumps(changed)!r}, flush=True)\n", encoding="utf-8")
    runtime = LocalRuntime(LocalLayout(tmp_path, Path(sys.executable), bridge, tmp_path, model), 5)
    runtime.start()
    process, reader = runtime.process, runtime.reader
    try:
        with pytest.raises(LocalRuntimeError, match="identity"):
            runtime.request(b"synthetic")
    finally:
        runtime.close()
    assert process.poll() is not None and not reader.is_alive()
    assert runtime.lease.handle is None


@pytest.mark.parametrize("mode", ["cancel", "changed", "missing", "timeout"])
def test_snapshot_rejection_cleans_only_owned_scratch(tmp_path, monkeypatch, mode):
    from videocaptioner.core.asr.local import audio

    monkeypatch.setattr(audio.tempfile, "tempdir", str(tmp_path))
    original = tmp_path / "original.wav"
    original.write_bytes(b"a" * (2 * 1024 * 1024))
    calls = 0

    def check():
        nonlocal calls
        calls += 1
        if calls == 3:
            if mode == "cancel":
                raise LocalRuntimeError("cancelled")
            if mode == "changed":
                with original.open("ab") as stream:
                    stream.write(b"changed")

    if mode == "missing":
        path = tmp_path / "missing.wav"
    else:
        path = original
    if mode == "timeout":
        clock = iter([0, 601])
        monkeypatch.setattr(audio.time, "monotonic", lambda: next(clock))
    with pytest.raises(LocalRuntimeError):
        with audio.source_snapshot(str(path), check):
            pytest.fail("Invalid snapshot must not reach inference")
    assert list(tmp_path.iterdir()) == [original]
    assert original.read_bytes().startswith(b"a" * 1024)


def test_runtime_hash_verification_can_cancel_between_blocks(tmp_path):
    from videocaptioner.core.asr.local.runtime import file_hash

    path = tmp_path / "weights.bin"
    path.write_bytes(b"a" * (3 * 1024 * 1024))
    calls = 0

    def check():
        nonlocal calls
        calls += 1
        if calls == 2:
            raise LocalRuntimeError("cancelled")

    with pytest.raises(LocalRuntimeError, match="cancelled"):
        file_hash(path, check=check)


def test_transcribe_freezes_options_before_callbacks(monkeypatch):
    module = importlib.import_module("videocaptioner.core.asr.transcribe")
    config = TranscribeConfig(transcribe_model=TranscribeModelEnum.QWEN_LOCAL)
    seen = []
    data = ASRData([ASRDataSeg("synthetic", 0, 1000)])

    def create(path, snapshot):
        def run(callback):
            callback(10, "recognition")
            seen.append(snapshot.local_asr)
            return data
        return SimpleNamespace(run=run)

    monkeypatch.setattr(module, "_create_asr_instance", create)

    def changed(*args):
        config.local_asr = LocalASRConfig(model="qwen-0.6b", diarize=True)

    assert module.transcribe("unused", config, changed) is data
    assert seen == [LocalASRConfig()]


def test_snapshot_accepts_different_windows_handle_and_path_ctime(tmp_path, monkeypatch):
    from videocaptioner.core.asr.local import audio

    source = tmp_path / "stable.wav"
    source.write_bytes(b"stable recording")
    fstat = audio.os.fstat

    def handle_stat(fd):
        stat = fstat(fd)
        fields = {name: getattr(stat, name) for name in ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")}
        fields["st_ctime_ns"] += 1000
        return SimpleNamespace(**fields)

    monkeypatch.setattr(audio.os, "fstat", handle_stat)
    with audio.source_snapshot(str(source), lambda: None) as snapshot:
        assert Path(snapshot).read_bytes() == source.read_bytes()
    assert not Path(snapshot).exists() and source.exists()

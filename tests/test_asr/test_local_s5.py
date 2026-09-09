"""Offline S5 contracts, lifecycle and compatibility. No real model inference here."""

import json
import os
import sys
from dataclasses import replace
from pathlib import Path

import pytest
from pydub import AudioSegment
from pydub.generators import Sine

from videocaptioner.core.asr.asr_data import ASRData, ASRDataSeg
from videocaptioner.core.asr.local import pipeline
from videocaptioner.core.asr.local.diarization import associate, diarization_key, validate_spans
from videocaptioner.core.asr.local.profiles import MODELS, PROTOCOL, LocalASRConfig
from videocaptioner.core.asr.local.review import LocalReview
from videocaptioner.core.asr.local.runtime import (
    LocalLayout,
    LocalRuntime,
    LocalRuntimeError,
    locate,
    offline_environment,
)
from videocaptioner.core.asr.metadata import ASRMetadata, StageProvenance
from videocaptioner.core.asr.review import (
    EditReviewTimingCommand,
    NativeReview,
    NativeReviewRequired,
    ReviewSession,
)
from videocaptioner.core.editor.commands import CommandStack
from videocaptioner.core.entities import TranscribeConfig, TranscribeModelEnum
from videocaptioner.core.utils.gpu_lease import GPUBusyError, GPULease

STAGE = StageProvenance("qwen-local", MODELS["qwen-0.6b"].repository, MODELS["qwen-0.6b"].revision, "qwen-text-v1")


def raw(text="你", start=100, end=400):
    return {"text": text, "start_ms": start, "end_ms": end}


def review(items=None, text="你", scope="scope"):
    return LocalReview.capture_chunks(stage=STAGE, scope=scope, durations=[(0, 1000)], texts=[text],
                                     raw=[items if items is not None else [raw()]], word_timing=True)


@pytest.mark.parametrize("options", [{"model": "main"}, {"diarize": "true"}, {"chunk_ms": 0},
    {"chunk_ms": 240001}, {"chunk_ms": True}, {"timeout": 0}, {"timeout": 3601}, {"timeout": float("nan")}])
def test_explicit_options_reject_invalid_values(options):
    with pytest.raises(ValueError):
        LocalASRConfig(**options)


def test_pins_are_distinct_and_aligner_matches_s2():
    from videocaptioner.core.asr.alignment.contract import MODEL_REVISION
    assert MODELS["aligner"].revision == MODEL_REVISION
    assert len({m.revision for m in MODELS.values()}) == 4
    assert all(len(m.revision) == 40 and int(m.revision, 16) for m in MODELS.values())
    assert MODELS["community-1"].gated


@pytest.mark.parametrize("text,tokens", [("張三有12元。", ["張", "三", "有", "12", "元"]),
                                         ("张三有１２元。", ["张", "三", "有", "１２", "元"])])
def test_review_preserves_script_full_text_offset_and_ids(text, tokens, tmp_path):
    items = [raw(t, i * 100, i * 100 + 80) for i, t in enumerate(tokens)]
    value = LocalReview.capture_chunks(stage=STAGE, scope="job", durations=[(0, 1000), (1000, 1000)],
                                       texts=[text, text], raw=[items, items], word_timing=True)
    value.save(tmp_path / "review.json")
    loaded = NativeReview.load(tmp_path / "review.json")
    data = loaded.resume()
    assert "".join(s.text for s in data) == text * 2
    assert data.segments[len(tokens)].start_time == 1000
    assert all(s.metadata.timing == "aligned" and s.metadata.recognition == STAGE for s in data)
    assert [s.cue_id for s in data] == [s.cue_id for s in loaded.resume()]
    assert [s.cue_id for s in review(scope="other").resume()] != [s.cue_id for s in review().resume()]
    data.save(str(tmp_path / "asr.json"))
    reopened = ASRData.from_subtitle_file(str(tmp_path / "asr.json"))
    assert [s.metadata for s in data] == [s.metadata for s in reopened]


@pytest.mark.parametrize("items,text", [([raw(start=0, end=0)], "你"), ([raw(start=-1)], "你"),
    ([raw(end=1001)], "你"), ([raw(start=float("nan"))], "你"), ([raw(start=1.5)], "你"),
    ([raw(start=True)], "你"), ([raw(start=400, end=100)], "你"), ([raw()], "你好"),
    ([raw("张")], "張"), ([raw(), raw("好", 300, 500)], "你好"), ([], "。")])
def test_review_does_not_repair_invalid_predictions(items, text):
    value = review(items, text)
    loaded = NativeReview.from_dict(value.to_dict())
    with pytest.raises(ValueError):
        loaded.resume()


def test_pending_alignment_requires_explicit_override_undo_redo():
    value = review([], "你好。")
    session = ReviewSession(value)
    stack = CommandStack()
    stack.execute(EditReviewTimingCommand(session, "token-000001", 100, 800))
    data = session.review.resume()
    assert data.segments[0].metadata.timing == "edited"
    assert session.review.tokens[0].start is None
    assert NativeReview.from_dict(session.review.to_dict()).resume().segments[0].end_time == 800
    stack.undo()
    with pytest.raises(ValueError):
        session.review.resume()
    stack.redo()
    assert session.review.resume().segments[0].start_time == 100


@pytest.mark.parametrize("field,value", [("scope", "bad"), ("duration_ms", 2000), ("text", "改"),
                                       ("acoustic_rejected", ["unknown-token"]), ("chunks", [])])
def test_review_rejects_tampered_raw_or_association(field, value):
    payload = review().to_dict()
    payload[field] = value
    with pytest.raises(ValueError):
        NativeReview.from_dict(payload)


def test_acoustic_rejection_cannot_be_resumed_without_review():
    value = replace(review(), acoustic_rejected=("token-000001",))
    with pytest.raises(ValueError):
        NativeReview.from_dict(value.to_dict()).resume()
    assert value.edit_timing("token-000001", 120, 450).resume().segments[0].metadata.timing == "edited"


@pytest.mark.parametrize("spans,status,speaker", [([], "unknown", None),
    ([(0, 1000, "A")], "assigned", "A"), ([(0, 799, "A")], "unknown", None),
    ([(0, 800, "A")], "assigned", "A"), ([(0, 600, "A"), (600, 1000, "B")], "ambiguous", None),
    ([(0, 900, "A"), (500, 600, "B")], "overlap", None),
    ([(0, 500, "A"), (100, 500, "A")], "unknown", None)])
def test_diarization_conservative_confidence(spans, status, speaker):
    source = ASRData([ASRDataSeg("你好", 0, 1000)])
    parsed = validate_spans([dict(start_ms=a, end_ms=b, speaker=c) for a, b, c in spans], 1000)
    result = associate(source, parsed, 1000, "job", STAGE)
    cue = result.segments[0]
    assert (cue.text, cue.start_time, cue.end_time, cue.cue_id) == ("你好", 0, 1000, source.segments[0].cue_id)
    assert cue.metadata.diarization.status == status
    assert cue.metadata.speaker == speaker
    assert ASRMetadata.from_dict(cue.metadata.to_dict()) == cue.metadata


def test_returning_speaker_global_scope_and_manual_override_survive_editor(tmp_path):
    from videocaptioner.core.editor.adapters import cues_from_asr
    from videocaptioner.core.editor.models import EditorProject
    data = ASRData([ASRDataSeg(t, i * 1000, (i + 1) * 1000) for i, t in enumerate("你好嗎")])
    spans = validate_spans([dict(start_ms=i * 1000, end_ms=(i + 1) * 1000, speaker=s) for i, s in enumerate("ABA")], 3000)
    result = associate(data, spans, 3000, "one-job", STAGE)
    assert result.segments[0].speaker == result.segments[2].speaker != result.segments[1].speaker
    other = associate(data, spans, 3000, "next-job", STAGE)
    assert other.segments[0].speaker != result.segments[0].speaker
    project = EditorProject("id", "title", "", "", 3000, cues=cues_from_asr(result))
    restored = EditorProject.from_dict(project.to_dict())
    assert [c.asr_metadata for c in restored.cues] == [c.asr_metadata for c in project.cues]
    result.segments[0].metadata = replace(result.segments[0].metadata, speaker_override="user-label")
    result.save(str(tmp_path / "output.json"))
    restored_data = ASRData.from_subtitle_file(str(tmp_path / "output.json"))
    assert restored_data.segments[0].speaker == "user-label"
    assert restored_data.segments[0].metadata.diarization.stage.provider == "pyannote"


@pytest.mark.parametrize("item", [{"start_ms": 0, "end_ms": 0, "speaker": "A"},
    {"start_ms": -1, "end_ms": 100, "speaker": "A"}, {"start_ms": 0.2, "end_ms": 100, "speaker": "A"},
    {"start_ms": True, "end_ms": 100, "speaker": "A"}, {"start_ms": 0, "end_ms": 1001, "speaker": "A"}])
def test_invalid_diarization_timing_is_rejected(item):
    with pytest.raises(ValueError):
        validate_spans([item], 1000)


def test_native_speakers_are_never_replaced():
    data = ASRData([ASRDataSeg("你好", 0, 1000, metadata=ASRMetadata("soniox", "scope", "1"))])
    with pytest.raises(ValueError, match="Existing diarization"):
        associate(data, (), 1000, "new", STAGE)


def test_stage_keys_are_separate_sensitive_content_not_in_key():
    a = pipeline.stage_key("recognition", b"audio", "qwen-0.6b", {"policy": "v1"})
    for stage, audio, model, options in [("alignment", b"audio", "qwen-0.6b", {"policy": "v1"}),
        ("recognition", b"changed", "qwen-0.6b", {"policy": "v1"}),
        ("recognition", b"audio", "qwen-1.7b", {"policy": "v1"}),
        ("recognition", b"audio", "qwen-0.6b", {"policy": "v2"})]:
        assert pipeline.stage_key(stage, audio, model, options) != a
    data = review().resume()
    key = diarization_key("audio-hash", data)
    other = data.with_segments([data.segments[0].clone()])
    other.segments[0].text = "private-transcript"
    assert key != diarization_key("audio-hash", other)
    assert "private-transcript" not in diarization_key("audio-hash", other)


def test_gpu_busy_cleanup_and_reacquisition():
    first, second = GPULease(), GPULease()
    try:
        first.acquire()
        with pytest.raises(GPUBusyError):
            second.acquire()
    finally:
        first.close()
    second.acquire()
    second.close()


def test_offline_environment_does_not_leak_credentials(monkeypatch):
    for key in ("OPENAI_API_KEY", "VIDEOCAPTIONER_OTHER", "HF_TOKEN", "HUGGING_FACE_HUB_TOKEN", "PYANNOTE_API_KEY"):
        monkeypatch.setenv(key, "secret")
    env = offline_environment()
    assert "secret" not in env.values()
    assert env["HF_HUB_OFFLINE"] == "1" and env["PYANNOTE_METRICS_ENABLED"] == "0"
    assert os.environ["HF_TOKEN"] == "secret"


def fake_layout(tmp_path, code):
    bridge = tmp_path / "bridge.py"
    bridge.write_text(code, encoding="utf-8")
    return LocalLayout(tmp_path, Path(sys.executable), bridge, tmp_path, MODELS["qwen-0.6b"])


def test_sidecar_health_restart_and_protocol_does_not_import_gpu(tmp_path):
    model = MODELS["qwen-0.6b"]
    health = json.dumps({"status": "ready", "protocol": PROTOCOL, "revision": model.revision, "model": model.id})
    layout = fake_layout(tmp_path, f"import json,sys\nprint({health!r}, flush=True)\nfor line in sys.stdin: pass\n")
    runtime = LocalRuntime(layout, 3)
    for _ in range(2):
        runtime.start()
        assert runtime.state == "ready"
        process, reader = runtime.process, runtime.reader
        runtime.close()
        assert process.poll() is not None and not reader.is_alive()
    assert not {"torch", "qwen_asr", "pyannote.audio"}.intersection(sys.modules)


@pytest.mark.parametrize("code,reason", [("import time; time.sleep(20)", "timed out"),
    ('print(\'{"status":"error","reason":"oom"}\', flush=True)', "out of memory"),
    ('print(\'{"status":"ready","protocol":"bad"}\', flush=True)', "identity")])
def test_startup_timeout_oom_and_identity_cleanup(tmp_path, code, reason):
    runtime = LocalRuntime(fake_layout(tmp_path, code), 0.5)
    with pytest.raises(LocalRuntimeError, match=reason):
        runtime.start()
    assert runtime.state == "error" and runtime.process is None and runtime.lease.handle is None


def test_missing_incomplete_failed_and_manifest_integrity(tmp_path):
    with pytest.raises(LocalRuntimeError, match="missing"):
        locate("qwen-0.6b", tmp_path)
    (tmp_path / ".installing").touch()
    with pytest.raises(LocalRuntimeError, match="incomplete"):
        locate("qwen-0.6b", tmp_path)
    (tmp_path / ".failed").touch()
    with pytest.raises(LocalRuntimeError, match="failed"):
        locate("qwen-0.6b", tmp_path)


def test_qwen_full_recognition_precedes_alignment_and_releases_gpu(monkeypatch):
    audio = (Sine(400).to_audio_segment(duration=600) + AudioSegment.silent(600) + Sine(400).to_audio_segment(duration=603)).set_frame_rate(16000).set_channels(1)
    calls = []
    monkeypatch.setattr(pipeline, "locate", lambda model, root, **kwargs: model)
    monkeypatch.setattr(pipeline, "decode_audio", lambda *args: audio)

    class Runtime:
        def __init__(self, layout, timeout):
            self.layout, self.state = layout, "stopped"
        def start(self, check):
            check()
            calls.append((self.layout, "start"))
            self.state = "ready"
        def request(self, audio, text="", check=lambda: None):
            check()
            calls.append((self.layout, "request"))
            return [raw()] if self.layout == "aligner" else {"text": "你"}
        def close(self):
            calls.append((self.layout, "close"))
            self.state = "stopped"
    monkeypatch.setattr(pipeline, "LocalRuntime", Runtime)
    config = TranscribeConfig(transcribe_model=TranscribeModelEnum.QWEN_LOCAL, transcribe_language="zh",
                local_asr=LocalASRConfig(model="qwen-0.6b", chunk_ms=1300))
    data = pipeline.QwenLocalASR("unused", config).run()
    assert "".join(s.text for s in data) == "你你"
    assert calls.index(("qwen-0.6b", "close")) < calls.index(("aligner", "start"))
    assert data.segments[1].start_time > 1000


def test_alignment_failure_retains_all_recognized_chunks(monkeypatch):
    monkeypatch.setattr(pipeline, "locate", lambda model, root, **kwargs: model)
    monkeypatch.setattr(pipeline, "decode_audio", lambda *args: Sine(400).to_audio_segment(1000).set_frame_rate(16000).set_channels(1))
    class Runtime:
        def __init__(self, layout, timeout):
            self.layout, self.state = layout, "stopped"
        def start(self, check):
            self.state = "ready"
        def request(self, audio, text="", check=lambda: None):
            return [raw(end=100)] if self.layout == "aligner" else {"text": "你"}
        def close(self):
            self.state = "stopped"
    monkeypatch.setattr(pipeline, "LocalRuntime", Runtime)
    config = TranscribeConfig(transcribe_model=TranscribeModelEnum.QWEN_LOCAL, transcribe_language="zh")
    with pytest.raises(NativeReviewRequired) as error:
        pipeline.QwenLocalASR("unused", config).run()
    assert error.value.path.is_file()
    value = NativeReview.load(error.value.path)
    assert value.text == "你" and value.tokens[0].end == 100
    with pytest.raises(ValueError):
        value.resume()


@pytest.mark.parametrize("phase", ["recognition", "alignment", "diarization"])
def test_cancel_at_each_stage_closes_runtime_without_publication(monkeypatch, phase):
    monkeypatch.setattr(pipeline, "locate", lambda model, root, **kwargs: model)
    monkeypatch.setattr(pipeline, "decode_audio", lambda *args: Sine(400).to_audio_segment(1000).set_frame_rate(16000).set_channels(1))
    closed = []
    class Cancelled(Exception):
        pass
    class Runtime:
        def __init__(self, layout, timeout):
            self.layout, self.state = layout, "stopped"
        def start(self, check):
            self.state = "ready"
        def request(self, audio, text="", check=lambda: None):
            if self.layout == {"recognition": "qwen-1.7b", "alignment": "aligner", "diarization": "community-1"}[phase]:
                raise Cancelled
            return [raw()] if self.layout == "aligner" else {"text": "你"}
        def close(self):
            closed.append(self.layout)
    monkeypatch.setattr(pipeline, "LocalRuntime", Runtime)
    monkeypatch.setattr(pipeline, "retain_review", lambda *args: pytest.fail("Cancel must not publish review"))
    config = TranscribeConfig(transcribe_model=TranscribeModelEnum.QWEN_LOCAL, transcribe_language="zh")
    with pytest.raises(Cancelled):
        if phase == "diarization":
            pipeline.add_local_speakers("unused", review().resume(), config, aligned=False)
        else:
            pipeline.QwenLocalASR("unused", config).run()
    assert {"recognition": "qwen-1.7b", "alignment": "aligner", "diarization": "community-1"}[phase] in closed


@pytest.mark.parametrize("cancel", [True, False])
def test_request_timeout_or_cancel_closes_child_and_scratch(tmp_path, cancel):
    import threading
    model = MODELS["qwen-0.6b"]
    health = json.dumps({"status": "ready", "protocol": PROTOCOL, "revision": model.revision, "model": model.id})
    marker = tmp_path / "request-location"
    code = (f"import json,sys,time\nfrom pathlib import Path\nprint({health!r},flush=True)\n"
            f"for line in sys.stdin:\n Path({str(marker)!r}).write_text(json.loads(line)['directory'])\n time.sleep(20)\n")
    runtime = LocalRuntime(fake_layout(tmp_path, code), 1)
    runtime.start()
    process, reader = runtime.process, runtime.reader
    event = threading.Event()
    timer = threading.Timer(0.15, event.set)
    timer.start()
    def check():
        if cancel and event.is_set():
            raise LocalRuntimeError("cancelled")
    try:
        with pytest.raises(LocalRuntimeError, match="cancelled" if cancel else "timed out"):
            runtime.request(b"synthetic", check=check)
    finally:
        timer.cancel()
        runtime.close()
    assert process.poll() is not None and not reader.is_alive()
    assert marker.exists() and not Path(marker.read_text()).exists()


@pytest.mark.skipif(os.name != "nt", reason="Windows installation recipe")
def test_installer_refuses_existing_destination_or_missing_access_before_subprocess(tmp_path, monkeypatch):
    from videocaptioner.core.asr.local import installer
    monkeypatch.setattr(installer, "_run", lambda *args, **kwargs: pytest.fail("Unexpected install"))
    with pytest.raises(FileExistsError):
        installer.install(tmp_path, ("qwen-0.6b",))
    with pytest.raises(LocalRuntimeError, match="read token"):
        installer.install(tmp_path / "new", ("community-1",))
    assert not (tmp_path / "new").exists()


@pytest.mark.skipif(os.name != "nt", reason="Windows installation recipe")
def test_installer_cancel_marks_owned_destination_failed(tmp_path, monkeypatch):
    from videocaptioner.core.asr.local import installer
    destination = tmp_path / "new"
    def cancelled(*args, **kwargs):
        raise LocalRuntimeError("cancelled")
    monkeypatch.setattr(installer, "_run", cancelled)
    with pytest.raises(LocalRuntimeError):
        installer.install(destination, ("qwen-0.6b",))
    assert (destination / ".failed").exists() and not (destination / ".installing").exists()


def test_generation_completion_uses_qwen_result_sequences():
    import runpy
    from types import SimpleNamespace

    from videocaptioner.core.asr.local.runtime import recipe_directory
    bridge = runpy.run_path(str(recipe_directory() / "bridge.py"))
    bridge["require_completed_generation"](SimpleNamespace(sequences=[[4, 9]]), 9)
    with pytest.raises(RuntimeError):
        bridge["require_completed_generation"](SimpleNamespace(sequences=[[4, 8]]), 9)


def test_optional_speaker_failure_retains_measured_transcript(monkeypatch, tmp_path):
    from importlib import import_module
    module = import_module("videocaptioner.core.asr.transcribe")
    data = ASRData([ASRDataSeg("你好", 0, 1000)])
    class Recognizer:
        def run(self, callback):
            return data
    def speakers(*args, **kwargs):
        raise LocalRuntimeError("missing model")
    monkeypatch.setattr(module, "add_local_speakers", speakers)
    monkeypatch.setattr(module, "_create_asr_instance", lambda *a: Recognizer())
    source = tmp_path / "audio.wav"
    source.write_bytes(b"snapshot fixture")
    result = module.transcribe(str(source), TranscribeConfig(transcribe_model=TranscribeModelEnum.WHISPER_API,
                                                           local_asr=LocalASRConfig(diarize=True)))
    assert result is data and result.pending_diarization
    assert result.segments[0].text == "你好" and result.segments[0].speaker is None


def test_manifest_inventory_checks_missing_files_revision_and_hash(tmp_path):
    from videocaptioner.core.asr.local.runtime import file_hash, recipe_directory
    recipe = recipe_directory()
    python = tmp_path / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    python.parent.mkdir()
    python.write_bytes(b"stub")
    (tmp_path / "bridge.py").write_bytes((recipe / "bridge.py").read_bytes())
    (tmp_path / "requirements.lock").write_bytes((recipe / "qwen.lock").read_bytes())
    model = MODELS["qwen-0.6b"]
    folder = tmp_path / "models" / model.id
    folder.mkdir(parents=True)
    files = {}
    for name in ["config.json", "preprocessor_config.json", "tokenizer_config.json", "vocab.json", "merges.txt", "model.safetensors"]:
        path = folder / name
        path.write_bytes(b"{}")
        files[name] = {"size": 2, "sha256": file_hash(path)}
    manifest = {"protocol": PROTOCOL, "recipe": json.loads((recipe / "qwen.json").read_text()),
                "lock_sha256": file_hash(recipe / "qwen.lock"),
                "models": {model.id: {"repository": model.repository, "revision": model.revision, "files": files}}}
    target = tmp_path / "runtime-manifest.json"
    target.write_text(json.dumps(manifest))
    assert locate(model.id, tmp_path, verify=True).model.revision == model.revision
    (folder / "model.safetensors").write_bytes(b"xx")
    with pytest.raises(LocalRuntimeError):
        locate(model.id, tmp_path, verify=True)
    del manifest["models"][model.id]["files"]["model.safetensors"]
    target.write_text(json.dumps(manifest))
    with pytest.raises(LocalRuntimeError):
        locate(model.id, tmp_path)
    manifest["models"][model.id]["revision"] = "main"
    target.write_text(json.dumps(manifest))
    with pytest.raises(LocalRuntimeError):
        locate(model.id, tmp_path)


def test_gateway_alignment_provenance_and_unknown_not_cached(monkeypatch):
    from types import SimpleNamespace
    source = ASRData([ASRDataSeg("你好", 100, 900)])
    audio = Sine(400).to_audio_segment(1000).set_frame_rate(16000).set_channels(1)
    monkeypatch.setattr(pipeline, "decode_audio", lambda *a: audio)
    monkeypatch.setattr(pipeline, "diarization_preflight", lambda *a, **k: "layout")
    monkeypatch.setattr(pipeline, "is_cache_enabled", lambda: True)
    writes = []
    cache = SimpleNamespace(get=lambda key: None, set=lambda *a, **k: writes.append(a))
    monkeypatch.setattr(pipeline, "get_asr_cache", lambda: cache)
    class Runtime:
        def __init__(self, *a):
            pass
        def start(self, check):
            check()
        def request(self, audio, check):
            return [{"start_ms": 0, "end_ms": 1000, "speaker": "A"}, {"start_ms": 500, "end_ms": 700, "speaker": "B"}]
        def close(self):
            pass
    monkeypatch.setattr(pipeline, "LocalRuntime", Runtime)
    config = TranscribeConfig(whisper_api_model="gpt-4o-transcribe", local_asr=LocalASRConfig(diarize=True))
    result = pipeline.add_local_speakers("unused", source, config, aligned=True)
    cue = result.segments[0]
    assert cue.metadata.timing == "aligned"
    assert cue.metadata.recognition.model == "gpt-4o-transcribe"
    assert cue.metadata.alignment.provider == "qwen-aligner"
    assert cue.metadata.diarization.status == "overlap" and cue.speaker is None
    assert not writes and cue.cue_id == source.segments[0].cue_id

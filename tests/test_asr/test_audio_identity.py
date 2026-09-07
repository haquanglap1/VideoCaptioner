"""S5.2 source association regressions, using synthetic PCM and offline transports."""

import importlib
import json
import shutil
from argparse import Namespace
from dataclasses import replace

import pytest
from pydub import AudioSegment
from pydub.generators import Sine

from videocaptioner.core.asr import aligned_api
from videocaptioner.core.asr.asr_data import ASRData, ASRDataSeg
from videocaptioner.core.asr.audio_identity import (
    identify_audio,
    require_audio_match,
    verify_audio_file,
)
from videocaptioner.core.asr.local import pipeline
from videocaptioner.core.asr.local.diarization import diarization_key
from videocaptioner.core.asr.local.profiles import LocalASRConfig
from videocaptioner.core.asr.local.review import LocalReview
from videocaptioner.core.asr.metadata import StageProvenance
from videocaptioner.core.asr.review import (
    EditReviewTimingCommand,
    NativeReview,
    NativeReviewRequired,
    ReviewSession,
)
from videocaptioner.core.editor.adapters import project_to_asr
from videocaptioner.core.editor.commands import CommandStack, EditCueSpeakerCommand
from videocaptioner.core.editor.project_store import EditorProjectStore
from videocaptioner.core.entities import SubtitleLayoutEnum, TranscribeConfig
from videocaptioner.core.subtitle import editing


def audio(hz=400, duration=1000):
    return Sine(hz).to_audio_segment(duration).set_frame_rate(16000).set_channels(1).set_sample_width(2)


def review(*, identity=True, pending=True):
    value = LocalReview.capture_chunks(
        stage=StageProvenance("qwen-local", "test-model", "revision", "strict-test"), scope="job",
        durations=[(0, 1000)], texts=["王明2026。"],
        raw=[[{"text": "王明2026", "start_ms": 100, "end_ms": 800}]], word_timing=True,
        audio_identity=identify_audio(audio()) if identity else None)
    return replace(value, pending_diarization=pending)


def test_same_duration_different_content_and_tail_have_distinct_identity():
    first, other = audio(), audio(800)
    assert len(first) == len(other)
    with pytest.raises(ValueError, match="does not match"):
        require_audio_match(identify_audio(first), identify_audio(other))
    tail = AudioSegment(first.raw_data + b"\x01\x00", frame_rate=16000, sample_width=2, channels=1)
    assert len(first) == len(tail)
    assert identify_audio(tail).samples == identify_audio(first).samples + 1
    assert identify_audio(tail) != identify_audio(first)


@pytest.mark.parametrize("field,value", [("policy", "future"), ("sha256", "bad"), ("samples", True),
                                         ("samples", 0), ("samples", 1.0), ("path", "secret.wav")])
def test_malformed_identity_is_rejected_not_downgraded_to_legacy(field, value):
    data = review().resume().to_document()
    data["audio_identity"][field] = value
    with pytest.raises(ValueError, match="audio identity"):
        ASRData.from_json(data)


def test_hash_can_cancel_between_blocks():
    checks = []
    def cancel():
        checks.append(True)
        if len(checks) == 2:
            raise RuntimeError("cancelled")
    with pytest.raises(RuntimeError, match="cancelled"):
        identify_audio(audio(duration=70000), cancel)


@pytest.mark.parametrize("legacy", [False, True])
def test_review_roundtrip_undo_and_resume_preserve_identity_and_pending(legacy):
    source = review(identity=not legacy)
    restored = NativeReview.from_dict(json.loads(json.dumps(source.to_dict())))
    assert restored == source
    session = ReviewSession(restored)
    stack = CommandStack()
    stack.execute(EditReviewTimingCommand(session, restored.tokens[0].id, 150, 850))
    assert session.review.audio_identity == source.audio_identity
    assert session.review.tokens == source.tokens
    stack.undo()
    assert session.review == restored
    stack.redo()
    data = NativeReview.from_dict(session.review.to_dict()).resume()
    assert data.audio_identity == source.audio_identity and data.pending_diarization
    assert data.segments[0].metadata.timing == "edited"
    assert data.segments[0].metadata.token_ids == restored.chunks[0].token_ids
    assert data.with_segments([data.segments[0].clone()]).to_document() == data.to_document()
    assert ASRData.from_json(data.to_document()).to_document() == data.to_document()
    assert ASRData.from_srt(data.to_srt()).audio_identity is None


def test_legacy_native_review_checksum_remains_compatible():
    import hashlib
    value = {"provider": "soniox", "model": "stt-async-v5", "scope": "old-job", "duration_ms": 1000,
             "text": "好", "tokens": [{"id": "token-000001", "text": "好", "start": 100, "end": 800,
             "speaker": "1", "kind": "word", "translation_status": None}], "diarize": True,
             "word_timing": True, "language": "zh", "overrides": []}
    fingerprint = {k: v for k, v in value.items() if k != "overrides"}
    wire = {"schema": "asr-review-v1", "recognition_sha256": hashlib.sha256(
        json.dumps(fingerprint, ensure_ascii=False, sort_keys=True).encode()).hexdigest(), **value}
    assert json.loads(json.dumps(NativeReview.from_dict(wire).to_dict())) == wire


def test_identity_is_bound_to_raw_review_checksum():
    wire = review().to_dict()
    wire["audio_identity"] = identify_audio(audio(800)).to_dict()
    with pytest.raises(ValueError, match="Invalid local ASR review"):
        NativeReview.from_dict(wire)


def test_mismatch_stops_before_cache_preflight_or_inference(monkeypatch):
    monkeypatch.setattr(pipeline, "decode_audio", lambda *a: audio(800))
    for name in ("get_asr_cache", "diarization_preflight", "LocalRuntime"):
        monkeypatch.setattr(pipeline, name, lambda *a, **k: pytest.fail("Mismatch must stop before cache/model"))
    data = review().resume()
    with pytest.raises(ValueError, match="does not match"):
        pipeline.add_local_speakers("unused", data, TranscribeConfig(), aligned=False)
    assert data.pending_diarization


@pytest.mark.parametrize("legacy", [False, True])
def test_diarization_preserves_binding_and_does_not_verify_legacy(monkeypatch, legacy):
    monkeypatch.setattr(pipeline, "decode_audio", lambda *a: audio())
    monkeypatch.setattr(pipeline, "diarization_preflight", lambda *a, **k: "layout")
    calls = []
    class Runtime:
        def __init__(self, *a): pass
        def start(self, check): calls.append("start")
        def request(self, binary, check): return [{"start_ms": 0, "end_ms": 1000, "speaker": "A"}]
        def close(self): calls.append("close")
    monkeypatch.setattr(pipeline, "LocalRuntime", Runtime)
    source = review(identity=not legacy).resume()
    result = pipeline.add_local_speakers("unused", source, TranscribeConfig(need_word_time_stamp=True), aligned=False)
    assert result.audio_identity == source.audio_identity
    assert not result.pending_diarization and source.pending_diarization
    assert result.segments[0].cue_id == source.segments[0].cue_id
    assert result.segments[0].metadata.token_ids == source.segments[0].metadata.token_ids
    assert calls == ["start", "close"]


def test_cache_association_distinguishes_identity_and_pending():
    data = review().resume()
    key = diarization_key("pcm", data)
    other = ASRData.from_json(data.to_document())
    other.audio_identity = None
    assert key != diarization_key("pcm", other)
    other.audio_identity = data.audio_identity
    other.pending_diarization = False
    assert key != diarization_key("pcm", other)


def test_editor_and_table_handoffs_keep_identity_override_and_pending(tmp_path):
    data = review().resume()
    subtitle = tmp_path / "source.json"
    data.save(str(subtitle))
    store = EditorProjectStore()
    project = store.create_from_media(str(tmp_path / "video.mp4"), str(subtitle), duration_ms=1000)
    stack = CommandStack()
    stack.execute(EditCueSpeakerCommand(project, project.cues[0].id, "confirmed"))
    saved, _ = store.save(project, tmp_path / "review.vceditor.json")
    restored = project_to_asr(store.load(saved))
    assert restored.audio_identity == data.audio_identity and restored.pending_diarization
    assert restored.segments[0].speaker == "confirmed"
    stack.undo()
    assert project_to_asr(project).segments[0].metadata == data.segments[0].metadata
    stack.redo()
    target = editing.write_editor_handoff(restored.to_json(), tmp_path / "handoff", "job", "video.mp4",
              audio_identity=restored.audio_identity, pending_diarization=restored.pending_diarization)
    assert ASRData.from_subtitle_file(str(target)).audio_identity == data.audio_identity
    editing.reexport_pipeline_outputs(restored.to_json(), str(target), None, SubtitleLayoutEnum.ORIGINAL_ON_TOP,
                                       document=restored)
    assert ASRData.from_subtitle_file(str(target)).pending_diarization


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="FFmpeg required for canonical container test")
def test_reencoded_container_renamed_source_and_replaced_source(tmp_path):
    first, lossless = tmp_path / "first.wav", tmp_path / "same.flac"
    audio().export(first, format="wav").close()
    audio().export(lossless, format="flac").close()
    identity = identify_audio(audio())
    assert verify_audio_file(identity, str(first))
    assert verify_audio_file(identity, str(lossless))
    first.rename(tmp_path / "renamed.wav")
    assert verify_audio_file(identity, str(tmp_path / "renamed.wav"))
    audio(800).export(first, format="wav").close()
    with pytest.raises(ValueError, match="does not match"):
        verify_audio_file(identity, str(first))


def fake_aligner(monkeypatch, *, invalid=False, cancel=False):
    calls = []
    class Cache(dict):
        def set(self, key, value, **kwargs): self[key] = value
    # S2 can retain stage values even when cache reads are disabled.
    monkeypatch.setattr(aligned_api, "get_asr_cache", lambda: Cache())
    monkeypatch.setattr(aligned_api, "locate_runtime", lambda: None)
    whole = audio(duration=2000)
    monkeypatch.setattr(aligned_api, "decode_audio", lambda *a: whole)
    monkeypatch.setattr(aligned_api, "split_audio", lambda *a: [(whole[:1000], 0), (whole[1000:], 1000)])
    class Runtime:
        def __init__(self, *_): pass
        def start(self, language, check): calls.append("health")
        def align(self, binary, text, check):
            calls.append("align")
            if cancel:
                raise RuntimeError("cancelled")
            return [{"text": "你", "start_ms": 100, "end_ms": 100 if invalid else 800}]
        def close(self): calls.append("close")
    monkeypatch.setattr(aligned_api, "AlignmentRuntime", Runtime)
    def submit(*a):
        calls.append("upload")
        return {"text": "你"}
    monkeypatch.setattr(aligned_api, "submit_cancellable", submit)
    config = TranscribeConfig(whisper_api_key="test-key", whisper_api_base="https://asr.invalid/v1",
        whisper_api_model="gpt-4o-transcribe", transcribe_language="zh", local_asr=LocalASRConfig(diarize=True))
    return aligned_api.AlignedAPI("unused", config), calls, whole


@pytest.mark.parametrize("invalid", [False, True])
def test_gateway_alignment_whole_job_review_identity_and_pending(monkeypatch, invalid):
    job, calls, whole = fake_aligner(monkeypatch, invalid=invalid)
    if invalid:
        with pytest.raises(NativeReviewRequired) as error:
            job.run()
        retained = NativeReview.load(error.value.path)
        assert retained.text == "你你" and len(retained.chunks) == 2
        assert retained.chunks[1].offset_ms == 1000
        assert retained.tokens[1].start is None
        assert retained.audio_identity == identify_audio(whole) and retained.pending_diarization
        with pytest.raises(ValueError):
            retained.resume()
    else:
        data = job.run()
        assert len(data) == 2 and data.audio_identity == identify_audio(whole) and data.pending_diarization
        assert data.segments[1].start_time == 1100
        assert all(s.metadata.recognition.model == "gpt-4o-transcribe" for s in data)
    assert calls[:3] == ["health", "upload", "upload"]
    assert calls[-1] == "close"


def test_gateway_alignment_cancel_does_not_publish_review(monkeypatch):
    job, calls, _ = fake_aligner(monkeypatch, cancel=True)
    monkeypatch.setattr(aligned_api, "retain_review", lambda *a: pytest.fail("cancel cannot publish"))
    with pytest.raises(RuntimeError, match="cancelled"):
        job.run()
    assert calls[-1] == "close"


def test_empty_gateway_text_on_audible_audio_cannot_resume_as_success(monkeypatch):
    job, _, _ = fake_aligner(monkeypatch)
    monkeypatch.setattr(aligned_api, "submit_cancellable", lambda *a: {"text": ""})
    with pytest.raises(NativeReviewRequired) as error:
        job.run()
    retained = NativeReview.load(error.value.path)
    assert not retained.recognition_complete and len(retained.chunks) == 2
    with pytest.raises(ValueError, match="requires review"):
        retained.resume()


def test_cli_review_mismatch_writes_no_output(tmp_path, monkeypatch):
    from videocaptioner.cli.commands import asr_review
    source, output = tmp_path / "source.json", tmp_path / "out.json"
    review().save(source)
    monkeypatch.setattr("videocaptioner.core.asr.alignment.audio.decode_audio", lambda *a: audio(800))
    assert asr_review.run(Namespace(input=str(source), audio="wrong.wav", output=str(output),
                                    set_timing=None, save_review=None), {}) == 5
    assert not output.exists()


def test_whisper_snapshot_identity_is_bound_before_recognition(tmp_path, monkeypatch):
    module = importlib.import_module("videocaptioner.core.asr.transcribe")
    from videocaptioner.core.entities import TranscribeModelEnum
    path = tmp_path / "original.wav"
    path.write_bytes(b"synthetic-container")
    monkeypatch.setattr(module, "decode_audio", lambda *a: audio())
    class Chunked(module.ChunkedASR):
        def __init__(self, path): self.path = path
        def run(self, callback):
            path.write_bytes(b"replaced-container")
            return ASRData([ASRDataSeg("synthetic", 100, 800)])
    monkeypatch.setattr(module, "_create_asr_instance", lambda path, config: Chunked(path))
    config = TranscribeConfig(transcribe_model=TranscribeModelEnum.WHISPER_API, need_word_time_stamp=True)
    result = module.transcribe(str(path), config)
    assert result.audio_identity == identify_audio(audio())

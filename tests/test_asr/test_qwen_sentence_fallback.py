"""Practical timing and selective Whisper replacement preserve source ownership."""

import sys
from dataclasses import replace
from types import SimpleNamespace

import pytest
from pydub.generators import Sine

from videocaptioner.core.asr.alignment.contract import AlignmentError
from videocaptioner.core.asr.asr_data import ASRData, ASRDataSeg
from videocaptioner.core.asr.audio_identity import identify_audio
from videocaptioner.core.asr.local import sentence_fallback as fallback
from videocaptioner.core.asr.local.review import LocalReview
from videocaptioner.core.asr.local.sentence_timing import PRACTICAL_SENTENCE_POLICY, sentence_cues
from videocaptioner.core.asr.metadata import StageProvenance
from videocaptioner.core.asr.review import NativeReview
from videocaptioner.core.entities import TranscribeConfig


def fixture():
    audio = Sine(400, sample_rate=16000).to_audio_segment(9000)
    stage = StageProvenance("qwen-local", "qwen-1.7b", "pin", "text")
    raw = [[dict(text="你好", start_ms=100, end_ms=800)],
           [dict(text="原文", start_ms=0, end_ms=0)],
           [dict(text="结束", start_ms=100, end_ms=900)]]
    review = LocalReview.capture_chunks(stage=stage, scope="fixture", durations=[(0, 3000), (3000, 3000), (6000, 3000)],
        texts=["你好。", "原文。", "结束。"], raw=raw, word_timing=False, audio_identity=identify_audio(audio))
    return audio, replace(review, alignment_policy=PRACTICAL_SENTENCE_POLICY)


def test_zero_duration_boundary_tokens_are_usable_only_in_practical_sentence_mode():
    raw = [dict(text="你", start_ms=100, end_ms=100), dict(text="好", start_ms=800, end_ms=800)]
    with pytest.raises(AlignmentError):
        sentence_cues("你好。", raw, 1000)
    cue, = sentence_cues("你好。", raw, 1000, policy=PRACTICAL_SENTENCE_POLICY)
    assert (cue.span.start_ms, cue.span.end_ms, cue.span.text) == (100, 800, "你好。")
    assert raw[0]["start_ms"] == raw[0]["end_ms"] == 100


@pytest.mark.parametrize("start,end", [(0, 0), (-1, 800), (800, 100), (100, 1001)])
def test_practical_mode_still_rejects_unusable_cue_boundaries(start, end):
    with pytest.raises(AlignmentError):
        sentence_cues("你好", [dict(text="你好", start_ms=start, end_ms=end)], 1000, policy=PRACTICAL_SENTENCE_POLICY)


def test_fallback_replaces_only_bad_region_with_its_own_text_timing_and_provenance(monkeypatch, tmp_path):
    audio, review = fixture()
    original = review.to_dict()
    requests = []

    def recognize(self, region, check):
        check()
        requests.append(len(region))
        return ASRData([ASRDataSeg("Whisper文字。", 200, 2000)]), StageProvenance("faster-whisper", "large-v3", "hash", fallback.FALLBACK_POLICY)

    monkeypatch.setattr(fallback.WhisperSentenceFallback, "__call__", recognize)
    messages = []
    data = fallback.sentence_subtitles(audio, review, TranscribeConfig(), lambda p, m: messages.append(m))
    assert requests == [3000]
    assert [(s.text, s.start_time, s.end_time) for s in data] == [("你好。", 100, 800), ("Whisper文字。", 3200, 5000), ("结束。", 6100, 6900)]
    assert fallback.fallback_cue_count(data) == 1
    assert data.segments[1].metadata.provider == "faster-whisper"
    assert data.segments[1].metadata.alignment is None and not data.segments[1].metadata.token_ids
    assert data.segments[0].metadata.recognition == review.recognition
    assert review.to_dict() == original
    saved, = (tmp_path / "asr-review").glob("*.json")
    assert NativeReview.load(saved).text == review.text
    data.save(str(tmp_path / "hybrid.json"))
    assert fallback.fallback_cue_count(ASRData.from_subtitle_file(str(tmp_path / "hybrid.json"))) == 1
    assert any("1 chunks use Whisper" in m for m in messages)


def test_short_failed_tail_uses_preceding_region_without_splicing_transcripts(monkeypatch):
    audio, review = fixture()
    short = audio[:6500]
    review = replace(review, duration_ms=6500, audio_identity=identify_audio(short),
        chunks=(*review.chunks[:2], replace(review.chunks[2], duration_ms=500)))
    sizes = []
    def recognize(self, region, check):
        sizes.append(len(region))
        return ASRData([ASRDataSeg("完整替代", 100, 3400)]), StageProvenance("faster-whisper", "large-v3", "hash", fallback.FALLBACK_POLICY)
    monkeypatch.setattr(fallback.WhisperSentenceFallback, "__call__", recognize)
    data = fallback.sentence_subtitles(short, review, TranscribeConfig())
    assert sizes == [3500]
    assert [s.text for s in data] == ["你好。", "完整替代"]


def test_incomplete_or_wrong_audio_never_calls_whisper(monkeypatch):
    audio, review = fixture()
    monkeypatch.setattr(fallback.WhisperSentenceFallback, "__call__", lambda *a: pytest.fail("unexpected inference"))
    with pytest.raises(AlignmentError):
        fallback.sentence_subtitles(audio, replace(review, recognition_complete=False), TranscribeConfig())
    with pytest.raises(ValueError):
        fallback.sentence_subtitles(audio - 20, review, TranscribeConfig())


def test_cancelled_fallback_does_not_publish_result_or_review(monkeypatch, tmp_path):
    audio, review = fixture()
    class Cancelled(Exception):
        pass
    def recognize(*args):
        raise Cancelled
    monkeypatch.setattr(fallback.WhisperSentenceFallback, "__call__", recognize)
    with pytest.raises(Cancelled):
        fallback.sentence_subtitles(audio, review, TranscribeConfig())
    assert not (tmp_path / "asr-review").exists()


def test_silent_whisper_process_obeys_deadline_and_is_reaped(monkeypatch):
    owner = fallback.WhisperSentenceFallback(SimpleNamespace(local_asr=SimpleNamespace(timeout=0.1)))
    engine = SimpleNamespace(device="cpu", _build_command=lambda path: [sys.executable, "-c", "import time; time.sleep(30)"])
    processes = []
    popen = fallback.subprocess.Popen
    def capture(*args, **kwargs):
        process = popen(*args, **kwargs)
        processes.append(process)
        return process
    monkeypatch.setattr(fallback.subprocess, "Popen", capture)
    with pytest.raises(AlignmentError, match="timed out"):
        owner._request(engine, b"fixture", lambda: None)
    assert processes and all(p.poll() is not None for p in processes)


@pytest.mark.parametrize("response,valid", [("1\n00:00:00,100 --> 00:00:00,800\n你好\n", True),
    ("1\n00:00:00,100 --> 00:00:01,800\n你好\n", False), ("", False)])
def test_installed_model_name_and_directory_and_only_valid_results_are_cached(monkeypatch, tmp_path, response, valid):
    root = tmp_path / "models"
    model = root / "faster-whisper-large-v3"
    model.mkdir(parents=True)
    for name in ("model.bin", "config.json", "tokenizer.json"):
        (model / name).write_bytes(b"fixture")
    program = tmp_path / "whisper.exe"
    program.write_bytes(b"fixture")
    class Engine:
        def __init__(self, binary, selected, whisper_model, model_dir, **kwargs):
            assert whisper_model == "large-v3" and model_dir == str(root.resolve())
            self.faster_whisper_program = str(program)
        def _build_command(self, audio):
            return [str(program), "-m", "large-v3", "--model_dir", str(root)]
    class Cache(dict):
        def set(self, key, value, **kwargs):
            self[key] = value
    cache, requests = Cache(), []
    monkeypatch.setattr(fallback, "FasterWhisperASR", Engine)
    monkeypatch.setattr(fallback, "is_cache_enabled", lambda: True)
    monkeypatch.setattr(fallback, "get_asr_cache", lambda: cache)
    def request(*args):
        requests.append(True)
        return response
    monkeypatch.setattr(fallback.WhisperSentenceFallback, "_request", request)
    owner = fallback.WhisperSentenceFallback(TranscribeConfig(faster_whisper_model_dir=str(root)))
    audio = Sine(400, sample_rate=16000).to_audio_segment(1000)
    if valid:
        first, stage = owner(audio, lambda: None)
        second, same = owner(audio, lambda: None)
        assert first.to_srt() == second.to_srt() and stage == same
        assert len(requests) == len(cache) == 1
    else:
        with pytest.raises(AlignmentError):
            owner(audio, lambda: None)
        assert not cache

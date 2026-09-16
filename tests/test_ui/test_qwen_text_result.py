"""GUI workers return text while preserving the separate subtitle failure."""

from dataclasses import replace
from pathlib import Path

import pytest

from videocaptioner.core.asr.api_transcription import TranscriptionResult
from videocaptioner.core.asr.asr_data import ASRData, ASRDataSeg
from videocaptioner.core.asr.local.review import LocalReview
from videocaptioner.core.asr.metadata import StageProvenance
from videocaptioner.core.asr.review import NativeReviewRequired
from videocaptioner.core.entities import (
    TranscribeConfig,
    TranscribeModelEnum,
    TranscribeOutputFormatEnum,
    TranscribeTask,
)
from videocaptioner.ui.thread import transcript_thread as module


@pytest.fixture
def task(tmp_path, monkeypatch, qapp):
    source = tmp_path / "input.wav"
    source.write_bytes(b"media conversion mocked")
    monkeypatch.setattr(module, "video2audio", lambda *a, **kw: True)
    return TranscribeTask(file_path=str(source), output_path=str(tmp_path / "output.srt"),
        transcribe_config=TranscribeConfig(transcribe_model=TranscribeModelEnum.QWEN_LOCAL,
            transcribe_language="zh", output_format=TranscribeOutputFormatEnum.SRT))


def run_worker(task):
    worker = module.TranscriptThread(task)
    finished, errors, reviews = [], [], []
    worker.finished.connect(finished.append)
    worker.error.connect(errors.append)
    worker.review_required.connect(reviews.append)
    # Run synchronously: this tests result routing, without creating a QThread race.
    worker.run()
    return finished, errors, reviews


def test_gui_txt_returns_recognition_without_alignment(task, monkeypatch):
    task.transcribe_config.output_format = TranscribeOutputFormatEnum.TXT
    task.asr_data = ASRData([ASRDataSeg("stale result", 0, 1000)])
    task.transcript_path = "stale.txt"
    monkeypatch.setattr(module, "recognize_text", lambda *a, **kw: TranscriptionResult("语音文字。"))
    monkeypatch.setattr(module, "transcribe", lambda *a, **kw: pytest.fail("No aligner for TXT"))
    finished, errors, reviews = run_worker(task)
    assert finished == [task] and not errors and not reviews
    assert task.asr_data is None
    assert Path(task.transcript_path).read_text(encoding="utf-8") == "语音文字。"


@pytest.mark.parametrize("pipeline", [False, True])
def test_gui_keeps_text_but_never_starts_subtitle_pipeline_after_bad_timing(task, monkeypatch, pipeline):
    task.need_next_task = pipeline
    original_output = task.output_path
    review = LocalReview.capture_chunks(stage=StageProvenance("qwen-local", "synthetic", "revision", "policy"),
        scope="test", durations=[(0, 1000)], texts=["完整文字。"], raw=[], word_timing=True)

    def fail(*a, **kw):
        raise NativeReviewRequired(review, "alignment unavailable", None)

    monkeypatch.setattr(module, "transcribe", fail)
    finished, errors, reviews = run_worker(task)
    assert bool(finished) is not pipeline and bool(errors) is pipeline
    assert bool(reviews) is pipeline  # Standalone speech recognition must not open a timing editor.
    assert not Path(original_output).exists() and task.asr_data is None
    assert Path(task.transcript_path).read_text(encoding="utf-8") == "完整文字。"
    assert task.output_path == (original_output if pipeline else task.transcript_path)


@pytest.mark.parametrize("cancelled", [False, True])
def test_incomplete_or_cancelled_recognition_is_not_reported_as_complete(task, monkeypatch, cancelled):
    review = LocalReview.capture_chunks(stage=StageProvenance("qwen-local", "synthetic", "revision", "policy"),
        scope="test", durations=[(0, 1000)], texts=["部分文字"], raw=[], word_timing=True)
    if not cancelled:
        review = replace(review, recognition_complete=False)
    worker = module.TranscriptThread(task)
    if cancelled:
        monkeypatch.setattr(worker, "isInterruptionRequested", lambda: True)
    assert not worker._recover_transcript(NativeReviewRequired(review, "not complete", None))
    assert task.transcript_path is None
    assert not Path(task.output_path).with_suffix(".txt").exists()

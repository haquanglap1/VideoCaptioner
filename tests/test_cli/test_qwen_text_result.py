"""CLI text success is independent from the requested subtitle export status."""

import importlib

import pytest

from videocaptioner.cli.main import main
from videocaptioner.core.asr.api_transcription import TranscriptionResult
from videocaptioner.core.asr.local.review import LocalReview
from videocaptioner.core.asr.metadata import StageProvenance
from videocaptioner.core.asr.review import NativeReviewRequired


def failed_timing():
    review = LocalReview.capture_chunks(stage=StageProvenance("qwen-local", "synthetic", "revision", "policy"),
        scope="test", durations=[(0, 1000)], texts=["完整的文字。"],
        raw=[[{"text": "完整的文字。", "start_ms": 200, "end_ms": 200}]], word_timing=True)
    return NativeReviewRequired(review, "invalid alignment", None)


@pytest.fixture
def source(tmp_path, monkeypatch):
    source = tmp_path / "input.wav"
    source.write_bytes(b"media preflight mocked")
    monkeypatch.setattr("videocaptioner.cli.validators.validate_media_input", lambda *a: None)
    return source


def test_cli_txt_does_not_enter_subtitle_pipeline(source, tmp_path, monkeypatch):
    module = importlib.import_module("videocaptioner.core.asr.transcribe")
    monkeypatch.setattr(module, "transcribe", lambda *a, **kw: pytest.fail("TXT must not request alignment"))
    monkeypatch.setattr(module, "recognize_text", lambda *a, **kw: TranscriptionResult("识别成功。"))
    output = tmp_path / "result.txt"
    assert main(["transcribe", str(source), "--asr", "qwen-local", "--language", "zh", "-o", str(output)]) == 0
    assert output.read_text(encoding="utf-8") == "识别成功。"
    assert not output.with_suffix(".srt").exists()


def test_cli_subtitle_failure_still_exports_full_text(source, tmp_path, monkeypatch):
    module = importlib.import_module("videocaptioner.core.asr.transcribe")

    def fail(*a, **kw):
        raise failed_timing()

    monkeypatch.setattr(module, "transcribe", fail)
    output = tmp_path / "result.srt"
    existing = output.with_suffix(".txt")
    existing.write_text("preserve", encoding="utf-8")
    assert main(["transcribe", str(source), "--asr", "qwen-local", "--language", "zh", "-o", str(output)]) == 5
    assert not output.exists()
    assert existing.read_text(encoding="utf-8") == "preserve"
    assert (tmp_path / "result-2.txt").read_text(encoding="utf-8") == "完整的文字。"


def test_process_does_not_translate_or_render_a_text_recovery(source, tmp_path, monkeypatch):
    module = importlib.import_module("videocaptioner.core.asr.transcribe")
    monkeypatch.setattr("videocaptioner.cli.validators.validate_process", lambda *a, **kw: True)
    monkeypatch.setattr("videocaptioner.cli.commands.subtitle.run", lambda *a, **kw: pytest.fail("No timed subtitles"))

    def fail(*a, **kw):
        raise failed_timing()

    monkeypatch.setattr(module, "transcribe", fail)
    assert main(["process", str(source), "--asr", "qwen-local", "--language", "zh", "--no-synthesize"]) == 5
    assert source.with_suffix(".txt").read_text(encoding="utf-8") == "完整的文字。"
    assert not source.with_suffix(".srt").exists()

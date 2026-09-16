"""Text recognition survives an unavailable aligner without inventing timings."""

import importlib

import pytest
from pydub.generators import Sine

from videocaptioner.core.asr.api_transcription import TranscriptionResult
from videocaptioner.core.asr.local import pipeline
from videocaptioner.core.asr.local.profiles import LocalASRConfig
from videocaptioner.core.asr.local.runtime import LocalRuntimeError
from videocaptioner.core.asr.review import NativeReviewRequired
from videocaptioner.core.entities import TranscribeConfig, TranscribeModelEnum


@pytest.fixture
def recognition(monkeypatch):
    calls = []
    audio = Sine(400).to_audio_segment(duration=1000).set_frame_rate(16000).set_channels(1)
    monkeypatch.setattr(pipeline, "decode_audio", lambda *a: audio)

    def locate(model, *a, **kw):
        calls.append((model, "locate"))
        if model == "aligner":
            raise LocalRuntimeError("aligner unavailable")
        return model

    class Runtime:
        def __init__(self, layout, timeout):
            self.layout, self.state = layout, "stopped"

        def start(self, check):
            check()
            self.state = "ready"

        def request(self, audio, check):
            check()
            calls.append((self.layout, "recognize"))
            return {"text": "你好，世界！"}

        def close(self):
            calls.append((self.layout, "close"))
            self.state = "stopped"

    monkeypatch.setattr(pipeline, "locate", locate)
    monkeypatch.setattr(pipeline, "ensure_model", locate)
    monkeypatch.setattr(pipeline, "LocalRuntime", Runtime)
    return calls


@pytest.mark.parametrize("model", ["qwen-0.6b", "qwen-1.7b"])
def test_text_export_never_checks_aligner_or_optional_speaker_runtime(recognition, model):
    module = importlib.import_module("videocaptioner.core.asr.transcribe")
    config = TranscribeConfig(transcribe_model=TranscribeModelEnum.QWEN_LOCAL,
        transcribe_language="zh", local_asr=LocalASRConfig(model=model, diarize=True))
    result = module.recognize_text("synthetic.wav", config)
    assert result.text == "你好，世界！" and result.timing_level == "none"
    assert all(name == model for name, _ in recognition)
    assert recognition[-1] == (model, "close")
    assert config.local_asr.diarize is True


def test_missing_aligner_retains_completed_text_for_timed_export(recognition):
    config = TranscribeConfig(transcribe_model=TranscribeModelEnum.QWEN_LOCAL, transcribe_language="zh")
    with pytest.raises(NativeReviewRequired) as caught:
        pipeline.QwenLocalASR("synthetic.wav", config).run()
    review = caught.value.review
    assert review.text == "你好，世界！" and review.recognition_complete
    assert all(token.start is None and token.end is None for token in review.tokens)
    assert recognition.index(("qwen-1.7b", "close")) < recognition.index(("aligner", "locate"))
    with pytest.raises(ValueError):
        review.resume()


def test_cancel_after_recognition_does_not_return_success(recognition):
    class Cancelled(Exception):
        pass

    def progress(percent, stage):
        if percent == 100:
            raise Cancelled

    config = TranscribeConfig(transcribe_language="zh")
    with pytest.raises(Cancelled):
        pipeline.QwenLocalASR("synthetic.wav", config).recognize(progress)
    assert recognition[-1] == ("qwen-1.7b", "close")
    assert not any(name == "aligner" for name, _ in recognition)


def test_recovery_does_not_overwrite_existing_user_transcripts(tmp_path):
    original = tmp_path / "recording.txt"
    next_file = tmp_path / "recording-2.txt"
    original.write_text("existing transcript", encoding="utf-8")
    next_file.write_text("another transcript", encoding="utf-8")
    result = TranscriptionResult("保持原文。\nSecond line")
    saved = result.save_text(original, unique=True)
    assert saved.name == "recording-3.txt"
    assert saved.read_text(encoding="utf-8") == result.text
    assert original.read_text(encoding="utf-8") == "existing transcript"
    assert next_file.read_text(encoding="utf-8") == "another transcript"

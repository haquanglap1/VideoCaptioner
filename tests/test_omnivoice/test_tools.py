"""Local utility data paths, cancellation and recording storage without live devices."""

import wave
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace

import pytest

from videocaptioner.core.dubbing.config import DubbingConfig, TTSProviderEnum
from videocaptioner.core.dubbing.engine import DubbingEngine
from videocaptioner.core.tts import TTSConfig
from videocaptioner.core.tts.omnivoice.reference import ReferenceASROptions, transcribe_reference
from videocaptioner.core.tts.omnivoice.text_audio import export_text_audio


@pytest.fixture(scope="session")
def retained_application():
    from PyQt5.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


def wav(path, duration=0.2):
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(24000)
        audio.writeframes(b"\0\1" * round(24000 * duration))


@pytest.fixture
def speech(tmp_path, monkeypatch):
    calls = []
    class Provider:
        def synthesize(self, data, output_dir, callback=None, max_workers=1):
            for i, segment in enumerate(data.segments):
                calls.append(segment.text)
                if segment.text != "FAIL":
                    path = Path(output_dir) / f"{i}.wav"
                    wav(path, 0.3 if segment.text == "Second" else 0.2)
                    segment.audio_path = str(path)
                else:
                    segment.error = "Injected item failure"
                if callback:
                    callback(50, "synthesizing")
            return data
    engine = DubbingEngine(tts_provider_factory=lambda _: Provider(), cache_root=tmp_path / "cache")
    monkeypatch.setattr(engine, "_managed_runtime_context", lambda *args: nullcontext())
    config = DubbingConfig(tts_provider=TTSProviderEnum.OMNIVOICE_LOCAL,
        tts_config=TTSConfig("fake", "", "", voice="vi-female-1", sample_rate=24000, speed=1, response_format="wav"))
    return engine, config, calls


def test_text_export_preserves_repetitions_full_pcm_and_measured_srt(tmp_path, speech):
    from videocaptioner.core.asr.asr_data import ASRData
    engine, config, calls = speech
    result = export_text_audio("First\nSecond\nFirst", tmp_path / "speech.wav", config, engine=engine)
    assert calls == ["First", "Second"]
    data = ASRData.from_srt(Path(result.subtitle_path).read_text(encoding="utf-8"), detect_bilingual=False)
    assert [s.text for s in data] == ["First", "Second", "First"]
    assert [(s.start_time, s.end_time) for s in data] == [(0, 200), (280, 580), (660, 860)]
    with wave.open(result.audio_path) as output:
        assert output.getnframes() == 20640
        samples = output.readframes(output.getnframes())
        assert samples[:9600] == b"\0\1" * 4800
        assert samples[9600:13440] == b"\0\0" * 1920
        assert samples[-9600:] == b"\0\1" * 4800
    assert result.segments == 3 and result.duration_ms == 860
    export_text_audio("First\nSecond\nFirst", tmp_path / "cached.wav", config, engine=engine)
    assert calls == ["First", "Second"]


def test_export_refuses_existing_srt_before_inference(tmp_path, speech):
    engine, config, calls = speech
    protected = tmp_path / "speech.srt"
    protected.write_text("Original", encoding="utf-8")
    with pytest.raises(ValueError, match="không ghi đè"):
        export_text_audio("First", tmp_path / "speech.wav", config, engine=engine)
    assert not calls and protected.read_text() == "Original"


@pytest.mark.parametrize("cancel", [False, True])
def test_incomplete_export_keeps_parts_without_publishing_partial_files(tmp_path, speech, cancel):
    engine, config, calls = speech
    def callback(progress, message):
        if cancel and message == "synthesizing":
            raise RuntimeError("cancelled")
    with pytest.raises(RuntimeError):
        export_text_audio("First\nFAIL", tmp_path / "incomplete.wav", config, callback, engine=engine)
    assert not (tmp_path / "incomplete.wav").exists() and not (tmp_path / "incomplete.srt").exists()
    assert list(tmp_path.glob("incomplete-parts-*/*.wav"))


def test_reference_asr_uses_installed_path_and_preserves_source(tmp_path, monkeypatch):
    from videocaptioner.core.asr import faster_whisper
    from videocaptioner.core.asr.local.sentence_fallback import WhisperSentenceFallback

    root = tmp_path / "models"
    model = root / "faster-whisper-tiny"
    model.mkdir(parents=True)
    for name in ("model.bin", "config.json", "tokenizer.json"):
        (model / name).write_text("fixture")
    reference = tmp_path / "reference.wav"
    wav(reference, 4)
    before = reference.read_bytes()
    def adapter(binary, program, model_path, model_dir, **kwargs):
        assert model_path == "tiny" and model_dir == str(root.resolve()) and kwargs["vad_filter"] is False
        assert binary[:4] == b"RIFF"
        return SimpleNamespace(_make_segments=lambda _: [SimpleNamespace(text="Lời nói đầy đủ.")])
    monkeypatch.setattr(faster_whisper, "FasterWhisperASR", adapter)
    monkeypatch.setattr(WhisperSentenceFallback, "_request", lambda *args: "fixture SRT")
    result = transcribe_reference(str(reference), ReferenceASROptions(model_dir=str(root)))
    assert result.text == "Lời nói đầy đủ." and reference.read_bytes() == before
    assert "Lời nói" not in repr(result)


def test_reference_asr_does_not_download_missing_model(tmp_path):
    reference = tmp_path / "reference.wav"
    wav(reference, 4)
    with pytest.raises(ValueError, match="không tự tải"):
        transcribe_reference(str(reference), ReferenceASROptions(model_dir=str(tmp_path)))


def test_recorder_writes_only_explicit_valid_capture(tmp_path, retained_application):
    from videocaptioner.ui.components.omnivoice_recorder import ReferenceRecorder
    recorder = ReferenceRecorder()
    paths, errors = [], []
    recorder.recorded.connect(paths.append)
    recorder.failed.connect(errors.append)
    assert not recorder.active
    recorder.active = True
    recorder.buffer = bytearray(b"\0\1" * 24000 * 4)
    recorder.stop()
    assert not errors and len(paths) == 1
    assert Path(paths[0]).is_relative_to(tmp_path)
    with wave.open(paths[0]) as audio:
        assert audio.getnframes() == 96000
    recorder.active = True
    recorder.buffer = bytearray(b"\0\1" * 24000)
    recorder.stop()
    assert errors and len(paths) == 1
    recorder.active = True
    recorder.buffer = bytearray(b"\0\1" * 24000 * 4)
    recorder.cancel()
    assert len(paths) == 1 and not recorder.buffer


def test_panel_does_not_open_microphone_and_rejects_stale_asr(tmp_path, retained_application, monkeypatch):
    from videocaptioner.core.tts.omnivoice.reference import ReferenceTranscript
    from videocaptioner.ui.components import omnivoice_recorder
    from videocaptioner.ui.components.omnivoice_panel import OmniVoicePanel

    monkeypatch.setattr(omnivoice_recorder, "QAudioDeviceInfo", SimpleNamespace(
        defaultInputDevice=lambda: pytest.fail("Opening panel must not activate a microphone")))
    panel = OmniVoicePanel()
    source = tmp_path / "ref.wav"
    wav(source, 4)
    panel.reference_audio.setText(str(source))
    panel.reference_text.setText("Current words")
    panel._tools_result(ReferenceTranscript(str(source.resolve()), "Stale", (0, 0)))
    assert panel.reference_text.text() == "Current words"
    stamp = source.stat()
    panel._tools_result(ReferenceTranscript(str(source.resolve()), "Draft for review", (stamp.st_size, stamp.st_mtime_ns)))
    assert panel.reference_text.text() == "Draft for review"
    panel.stop()
    panel.close()


def test_utility_cli_routes_without_changing_dubbing_defaults():
    from videocaptioner.cli.main import _build_cli_overrides, build_parser

    parser = build_parser()
    args = parser.parse_args(["omnivoice", "speak", "approved.txt", "-o", "speech.wav"])
    config = _build_cli_overrides(args)
    assert config["dubbing"]["tts_provider"] == "omnivoice-local"
    assert config["dubbing"]["tts_speed"] == 1
    args = parser.parse_args(["omnivoice", "transcribe-reference", "reference.wav", "-o", "draft.txt", "--model", "large-v3"])
    assert args.model == "large-v3" and args.action == "transcribe-reference"


def test_tools_thread_runs_off_main_thread_and_joins(retained_application, monkeypatch):
    from PyQt5.QtCore import QEventLoop, QThread, QTimer

    from videocaptioner.ui.thread import omnivoice_tools_thread

    def transcribe(*args):
        assert QThread.currentThread() != retained_application.thread()
        return "draft"
    monkeypatch.setattr(omnivoice_tools_thread, "transcribe_reference", transcribe)
    worker = omnivoice_tools_thread.OmniVoiceToolsThread("transcribe", audio="reference.wav", asr_options=ReferenceASROptions())
    values, errors = [], []
    worker.completed.connect(values.append)
    worker.failed.connect(errors.append)
    loop = QEventLoop()
    worker.finished.connect(loop.quit)
    QTimer.singleShot(5000, loop.quit)
    worker.start()
    loop.exec_()
    worker.wait()
    assert not errors and values == ["draft"]


@pytest.mark.parametrize("action", ["speak", "transcribe-reference"])
def test_cli_main_dispatches_the_new_utilities(action, monkeypatch):
    import importlib
    cli = importlib.import_module("videocaptioner.cli.main")
    calls = []
    monkeypatch.setattr(cli, "_load_config", lambda _: {"fixture": True})
    monkeypatch.setattr("videocaptioner.cli.commands.omnivoice.run", lambda args, config: calls.append((args.action, config)) or 0)
    assert cli.main(["omnivoice", action, "synthetic-input", "-o", "new-output"]) == 0
    assert calls == [(action, {"fixture": True} if action == "speak" else {})]

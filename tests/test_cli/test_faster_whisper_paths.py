"""Explicit installed binaries/models must reach the real ASR configuration."""

import importlib
from argparse import Namespace

import pytest

from videocaptioner.cli.main import _build_cli_overrides, build_parser, main
from videocaptioner.cli.validators import validate_faster_whisper
from videocaptioner.core.asr import faster_whisper
from videocaptioner.core.asr.asr_data import ASRData, ASRDataSeg


def program_file(tmp_path, name="custom-whisper.exe"):
    path = tmp_path / name
    with path.open("wb") as handle:
        handle.truncate(faster_whisper.MIN_PROGRAM_SIZE)
    return path


@pytest.mark.parametrize("command", ["transcribe", "process"])
def test_cli_exposes_installed_faster_whisper_paths(command, tmp_path):
    args = build_parser().parse_args([command, "synthetic.wav", "--asr", "faster-whisper",
        "--fw-program", str(tmp_path / "engine.exe"), "--fw-model-dir", str(tmp_path / "models"),
        "--fw-model", "large-v3", "--fw-device", "cuda"])
    options = _build_cli_overrides(args)["transcribe"]
    assert options["asr"] == "faster-whisper"
    assert options["faster_whisper"] == {"program": str(tmp_path / "engine.exe"),
        "model_dir": str(tmp_path / "models"), "model": "large-v3", "device": "cuda"}


@pytest.mark.parametrize("device", ["cpu", "cuda", "auto"])
def test_explicit_valid_program_does_not_require_path_lookup(tmp_path, monkeypatch, device):
    program = program_file(tmp_path)
    monkeypatch.setattr(faster_whisper, "_which_valid", lambda *a: pytest.fail("Explicit executable must win"))
    monkeypatch.setattr(faster_whisper.BaseASR, "__init__", lambda *a, **k: None)
    monkeypatch.setattr(faster_whisper, "is_rtx_50_series", lambda: False)
    engine = faster_whisper.FasterWhisperASR(b"", str(program), "large-v3", str(tmp_path), device=device)
    command = engine._build_command("input.wav")
    assert command[0] == str(program)
    assert command[command.index("--model_dir") + 1] == str(tmp_path)
    assert command[command.index("-d") + 1] == device


def test_invalid_selected_program_does_not_silently_use_another_binary(tmp_path, monkeypatch):
    installed = program_file(tmp_path)
    missing = str(tmp_path / "missing.exe")
    monkeypatch.setattr(faster_whisper, "_which_valid", lambda name: str(installed) if name == "faster-whisper-xxl" else None)
    with pytest.raises(EnvironmentError):
        faster_whisper.resolve_program(missing, "cuda")
    assert not validate_faster_whisper({"transcribe": {"faster_whisper": {"program": missing}}})


def test_auto_device_resolves_default_binary(tmp_path, monkeypatch):
    program = program_file(tmp_path, "faster-whisper-xxl.exe")
    monkeypatch.setattr(faster_whisper, "_which_valid", lambda name: str(program) if name == "faster-whisper-xxl" else None)
    assert faster_whisper.resolve_program("", "auto") == str(program)


def test_selected_model_directory_must_exist(tmp_path):
    program = program_file(tmp_path)
    assert not validate_faster_whisper({"transcribe": {"faster_whisper": {
        "program": str(program), "model_dir": str(tmp_path / "missing")}}})


def test_transcribe_command_passes_paths_to_core_without_mutating_environment(tmp_path, monkeypatch):
    import os
    program = program_file(tmp_path)
    models = tmp_path / "models"
    models.mkdir()
    source = tmp_path / "input.wav"
    source.write_bytes(b"preflight is mocked")
    destination = tmp_path / "output.json"
    monkeypatch.setattr("videocaptioner.cli.validators.validate_media_input", lambda *a: None)
    captured = []
    module = importlib.import_module("videocaptioner.core.asr.transcribe")

    def transcribe(audio, config, callback=None):
        captured.append(config)
        return ASRData([ASRDataSeg("测试字幕", 100, 900)])

    monkeypatch.setattr(module, "transcribe", transcribe)
    original_path = os.environ.get("PATH")
    assert main(["transcribe", str(source), "--asr", "faster-whisper", "--fw-program", str(program),
        "--fw-model-dir", str(models), "--fw-device", "cuda", "--language", "zh", "-o", str(destination)]) == 0
    assert len(captured) == 1
    assert captured[0].faster_whisper_program == str(program)
    assert captured[0].faster_whisper_model_dir == str(models)
    assert captured[0].faster_whisper_model.value == "large-v3"
    assert captured[0].need_word_time_stamp is False
    assert os.environ.get("PATH") == original_path
    assert ASRData.from_subtitle_file(str(destination)).segments[0].text == "测试字幕"


@pytest.mark.parametrize("optimize,translate,split,expected_words", [
    (False, True, False, False), (True, False, False, False), (True, True, False, False),
    (False, True, True, True), (True, False, True, True), (False, False, True, False),
])
def test_process_requests_words_only_when_a_split_step_will_run(tmp_path, monkeypatch, optimize, translate, split, expected_words):
    from videocaptioner.cli.commands.process import run
    source = tmp_path / "input.wav"
    source.write_bytes(b"no media inference in this routing test")
    monkeypatch.setattr("videocaptioner.cli.validators.validate_process", lambda *a, **k: True)
    captured = []

    def transcribe(args, config):
        captured.append(args.word_timestamps)
        return 0

    monkeypatch.setattr("videocaptioner.cli.commands.transcribe.run", transcribe)
    monkeypatch.setattr("videocaptioner.cli.commands.subtitle.run", lambda *a: 0)
    args = Namespace(input=str(source), quiet=True, no_synthesize=True)
    config = {"subtitle": {"optimize": optimize, "translate": translate, "split": split}}
    assert run(args, config) == 0
    assert captured == [expected_words]


@pytest.mark.parametrize("engine,expected", [("FASTER_WHISPER", [(100, 400), (600, 900)]),
                                            ("BIJIAN", [(100, 550), (550, 900)])])
def test_native_faster_sentences_keep_measured_boundaries(monkeypatch, engine, expected):
    from types import SimpleNamespace

    from videocaptioner.core.entities import TranscribeConfig, TranscribeModelEnum
    module = importlib.import_module("videocaptioner.core.asr.transcribe")
    data = ASRData([ASRDataSeg("第一句", 100, 400), ASRDataSeg("第二句", 600, 900)])
    monkeypatch.setattr(module, "_create_asr_instance", lambda *a: SimpleNamespace(run=lambda **k: data))
    result = module.transcribe("unused.wav", TranscribeConfig(
        transcribe_model=getattr(TranscribeModelEnum, engine), need_word_time_stamp=False))
    assert [(s.start_time, s.end_time) for s in result] == expected

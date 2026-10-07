"""Explicit S5 CLI configuration and local review, with no API/model calls."""

import pytest

from videocaptioner.cli.config import DEFAULTS, build_config, load_config_file, save_config_value
from videocaptioner.cli.main import _build_cli_overrides, build_parser


@pytest.mark.parametrize("command", ["transcribe", "process"])
def test_qwen_and_hybrid_cli_options(command, tmp_path):
    args = build_parser().parse_args([command, "input.wav", "--asr", "qwen-local", "--qwen-model", "qwen-0.6b",
        "--language", "zh", "--local-diarize", "--qwen-runtime", "installed-qwen", "--diarization-runtime", "installed-pyannote",
        "--local-timeout", "300", "--local-chunk-ms", "60000"])
    config = build_config(_build_cli_overrides(args), gui_settings_path=tmp_path / "none")
    assert config["transcribe"]["asr"] == "qwen-local"
    assert config["local_asr"] == {"model": "qwen-0.6b", "diarize": True, "runtime_root": "installed-qwen",
                                    "diarization_root": "installed-pyannote", "timeout": 300, "chunk_ms": 60000,
                                    "name_speakers": False}
    assert DEFAULTS["transcribe"]["asr"] == "bijian"
    assert not DEFAULTS["local_asr"]["diarize"]


@pytest.mark.parametrize("key,value", [("model", "unknown"), ("timeout", "0"), ("timeout", "3601"),
                                      ("chunk_ms", "240001"), ("diarize", "sometimes")])
def test_bad_local_config_does_not_write(key, value, tmp_path):
    target = tmp_path / "config.toml"
    with pytest.raises(ValueError):
        save_config_value(f"local_asr.{key}", value, target)
    assert not target.exists()


def test_local_config_roundtrip_and_no_gui_behavior_mirroring(tmp_path):
    target = tmp_path / "config.toml"
    save_config_value("local_asr.diarize", "true", target)
    save_config_value("local_asr.model", "qwen-0.6b", target)
    assert load_config_file(target)["local_asr"] == {"diarize": True, "model": "qwen-0.6b"}
    gui = tmp_path / "gui.json"
    gui.write_text('{"LocalASR":{"Diarize":true,"Model":"qwen-0.6b"}}')
    assert build_config(config_path=tmp_path / "missing.toml", gui_settings_path=gui)["local_asr"]["diarize"] is False


def test_model_manager_has_no_token_argument_and_status_is_light(monkeypatch):
    from videocaptioner.cli.commands.local_asr import run
    args = build_parser().parse_args(["local-asr", "status", "--models", "qwen-0.6b"])
    monkeypatch.setattr("videocaptioner.cli.commands.local_asr.locate", lambda *a, **k: object())
    monkeypatch.setattr("videocaptioner.cli.commands.local_asr.LocalRuntime", lambda *a, **k: pytest.fail("Heavy status"))
    assert run(args) == 0
    with pytest.raises(SystemExit):
        build_parser().parse_args(["local-asr", "install", "--token", "fake"])


def test_mixed_install_fails_before_requesting_token(tmp_path, monkeypatch):
    from videocaptioner.cli.commands.local_asr import run
    monkeypatch.setattr("getpass.getpass", lambda *a: pytest.fail("Do not ask for credentials for an invalid install"))
    args = build_parser().parse_args(["local-asr", "install", "--root", str(tmp_path / "new")])
    assert run(args) == 2
    assert not (tmp_path / "new").exists()


def test_local_diarize_rejects_text_only_before_inference(tmp_path, monkeypatch):
    from videocaptioner.cli.commands.local_diarize import run
    monkeypatch.setattr("videocaptioner.cli.commands.local_diarize.add_local_speakers", lambda *a, **k: pytest.fail("Needs alignment"))
    args = build_parser().parse_args(["local-diarize", str(tmp_path / "text.txt"), "--audio", "audio.wav", "-o", "result.json"])
    assert run(args) == 2


def _diarized_document():
    from videocaptioner.core.asr.asr_data import ASRData, ASRDataSeg
    from videocaptioner.core.asr.metadata import ASRMetadata, SpeakerAssociation, StageProvenance
    stage = StageProvenance("pyannote", "repo", "rev", "policy")
    recognition = StageProvenance("imported", "timed-subtitles", "", "user-supplied-timing-v1")

    def cue(text, start, end, label, cue_id):
        association = SpeakerAssociation(stage, "scope", "assigned", (label,), 900_000)
        return ASRDataSeg(text, start, end, cue_id=cue_id, metadata=ASRMetadata(
            "imported", "scope", label, recognition=recognition, diarization=association))
    return ASRData([cue("师父，弟子知错了。", 0, 1000, "SPEAKER_00", "c1"), cue("清宵，起来吧。", 1000, 2000, "SPEAKER_01", "c2")])


def _naming_reply(*names):
    import json
    return json.dumps({"speakers": [
        {"label": label, "name": name, "role": "", "gender": "unknown", "age_group": "unknown",
         "confidence": 0.9, "evidence_cue_ids": [2]} for label, name in zip(("SPEAKER_00", "SPEAKER_01"), names)]},
        ensure_ascii=False)


@pytest.fixture
def diarize_inputs(tmp_path):
    source = tmp_path / "timed.srt"
    source.write_text("1\n00:00:00,000 --> 00:00:01,000\n师父，弟子知错了。\n\n2\n00:00:01,000 --> 00:00:02,000\n清宵，起来吧。\n",
                      encoding="utf-8")
    audio = tmp_path / "episode.mp4"
    audio.write_bytes(b"not decoded: add_local_speakers is faked")
    return source, audio, tmp_path / "speakers.json"


def test_name_speakers_cli_option_maps_to_config_and_defaults_off(tmp_path):
    args = build_parser().parse_args(["transcribe", "input.wav", "--asr", "qwen-local", "--language", "zh",
                                      "--local-diarize", "--name-speakers"])
    config = build_config(_build_cli_overrides(args), gui_settings_path=tmp_path / "none")
    assert config["local_asr"]["name_speakers"] is True and config["local_asr"]["diarize"] is True
    assert DEFAULTS["local_asr"]["name_speakers"] is False
    target = tmp_path / "config.toml"
    save_config_value("local_asr.name_speakers", "true", target)
    assert load_config_file(target)["local_asr"] == {"name_speakers": True}
    with pytest.raises(ValueError):
        save_config_value("local_asr.name_speakers", "sometimes", target)


def test_local_diarize_name_speakers_sends_text_only_and_saves_the_map(diarize_inputs, tmp_path, monkeypatch):
    from types import SimpleNamespace

    from videocaptioner.cli.commands.local_diarize import run
    from videocaptioner.core.asr.asr_data import ASRData
    from videocaptioner.core.translate.series_context import VideoContext, save_video_context

    source, audio, destination = diarize_inputs
    save_video_context(audio, VideoContext.make(title="PV 修行", uploader="鸣潮"))
    notes = tmp_path / "series.txt"
    notes.write_text("清宵 = đệ tử của 老道", encoding="utf-8")
    monkeypatch.setattr("videocaptioner.cli.commands.local_diarize.add_local_speakers", lambda *a, **k: _diarized_document())
    seen = []

    def fake_call(self, messages, model, **kwargs):
        seen.append((self.credentials, self.timeout, model, messages, kwargs))
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=_naming_reply("清宵", "老道")),
                                                        finish_reason="stop")], usage=None)
    monkeypatch.setattr("videocaptioner.core.llm.owned_request.OwnedLLMRequest.__call__", fake_call)
    args = build_parser().parse_args(["local-diarize", str(source), "--audio", str(audio), "-o", str(destination),
                                      "--name-speakers", "--series-context", str(notes)])
    config = {"llm": {"api_key": "sk-fixture-only", "api_base": "https://fixture.invalid/v1", "model": "fixture-model",
                      "request_timeout": 45}, "translate": {"series_context": "ignored when a file is given"}}
    assert run(args, config) == 0
    credentials, timeout, model, messages, kwargs = seen[0]
    assert credentials.api_key == "sk-fixture-only" and timeout == 45 and model == "fixture-model"
    user = messages[1]["content"]
    assert "Title: PV 修行" in user and "清宵 = đệ tử của 老道" in user and "ignored when" not in user
    assert str(audio) not in user and str(tmp_path) not in user and "sk-fixture-only" not in user
    assert kwargs["max_completion_tokens"] == 2400
    saved = ASRData.from_subtitle_file(str(destination))
    assert saved.speaker_naming is not None and [p.name for p in saved.speaker_naming.profiles] == ["清宵", "老道"]
    assert sorted(c.label for c in saved.conversation_context.characters) == ["清宵", "老道"]
    assert all(m.evidence.source == "text" and m.evidence.status == "confirmed" for m in saved.conversation_context.mappings)
    assert saved.to_srt() == _diarized_document().to_srt()  # names never reach SRT text


def test_local_diarize_naming_failure_keeps_the_diarized_json(diarize_inputs, monkeypatch):
    from videocaptioner.cli.commands.local_diarize import run
    from videocaptioner.core.asr.asr_data import ASRData

    source, audio, destination = diarize_inputs
    monkeypatch.setattr("videocaptioner.cli.commands.local_diarize.add_local_speakers", lambda *a, **k: _diarized_document())

    def fake_call(self, messages, model, **kwargs):
        raise RuntimeError("Translation HTTP 500; review or retry explicitly.")
    monkeypatch.setattr("videocaptioner.core.llm.owned_request.OwnedLLMRequest.__call__", fake_call)
    args = build_parser().parse_args(["local-diarize", str(source), "--audio", str(audio), "-o", str(destination),
                                      "--name-speakers"])
    config = {"llm": {"api_key": "sk-fixture-only", "api_base": "https://fixture.invalid/v1", "model": "fixture-model"}}
    assert run(args, config) == 0
    saved = ASRData.from_subtitle_file(str(destination))
    assert saved.speaker_naming is None and saved.segments[0].speaker == "pyannote:scope:SPEAKER_00"


def test_local_diarize_name_speakers_without_llm_config_stops_before_the_model(diarize_inputs, monkeypatch):
    from videocaptioner.cli.commands.local_diarize import run

    source, audio, destination = diarize_inputs
    monkeypatch.setattr("videocaptioner.cli.commands.local_diarize.add_local_speakers",
                        lambda *a, **k: pytest.fail("LLM configuration is checked before diarization"))
    args = build_parser().parse_args(["local-diarize", str(source), "--audio", str(audio), "-o", str(destination),
                                      "--name-speakers"])
    assert run(args, {"llm": {"api_key": "", "api_base": "", "model": ""}}) == 2
    assert not destination.exists()
    without = build_parser().parse_args(["local-diarize", str(source), "--audio", str(audio), "-o", str(destination)])
    assert without.name_speakers is False

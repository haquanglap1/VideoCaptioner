"""CLI S4 context uses the same persisted schema and keeps old defaults."""

import json

import pytest

from videocaptioner.cli.config import build_config
from videocaptioner.cli.main import _build_cli_overrides, build_parser
from videocaptioner.core.asr.asr_data import ASRData, ASRDataSeg
from videocaptioner.core.translate.conversation import Character, ConversationContext


@pytest.mark.parametrize("command", ["transcribe", "process", "subtitle"])
def test_context_flag_shared_config(command):
    args = build_parser().parse_args([command, "input.json", "--conversation-context", "context.json"])
    config = build_config(_build_cli_overrides(args))
    assert config["translate"]["conversation_context"] == "context.json"
    assert config["transcribe"]["asr"] == "bijian"


def test_context_json_cli_noop_preserves_metadata_and_context(tmp_path):
    from videocaptioner.cli.commands.subtitle import run
    data = ASRData([ASRDataSeg("你好。", 0, 1000)])
    source = tmp_path / "input.json"
    target = tmp_path / "output.json"
    context_file = tmp_path / "context.json"
    data.save(str(source))
    context = ConversationContext(characters=(Character("A", "Minh"),))
    context_file.write_text(json.dumps(context.to_dict()), encoding="utf-8")
    args = build_parser().parse_args(["subtitle", str(source), "-o", str(target), "--no-optimize", "--no-split",
                                     "--no-translate", "--conversation-context", str(context_file)])
    config = build_config(_build_cli_overrides(args))
    assert run(args, config) == 0
    loaded = ASRData.from_subtitle_file(str(target))
    assert loaded.conversation_context == context
    assert loaded.segments[0].cue_id == data.segments[0].cue_id


def test_malformed_context_cli_keeps_runtime_exit_code(tmp_path):
    from videocaptioner.cli.commands.subtitle import run
    source = tmp_path / "input.srt"
    source.write_text("1\n00:00:00,000 --> 00:00:01,000\n你好。\n", encoding="utf-8")
    bad = tmp_path / "bad.json"
    bad.write_text('{"policy":"unrecognized"}', encoding="utf-8")
    args = build_parser().parse_args(["subtitle", str(source), "--no-optimize", "--no-split", "--no-translate",
                                     "--conversation-context", str(bad)])
    assert run(args, build_config(_build_cli_overrides(args))) == 5


def test_context_document_keeps_its_cues_when_split_is_enabled(tmp_path, monkeypatch):
    """Speaker/character evidence points at the saved cues, so the CLI skips splitting instead of failing."""
    from videocaptioner.cli.commands.subtitle import run
    from videocaptioner.core.translate.conversation import Evidence, SpeakerMapping

    data = ASRData([ASRDataSeg("师父，弟子知错了。", 0, 1000, cue_id="c1"), ASRDataSeg("起来吧。", 1000, 2000, cue_id="c2")])
    data.conversation_context = ConversationContext(
        characters=(Character("ai-char-1", "清宵", Evidence("text", "confirmed", ("c1",))),),
        mappings=(SpeakerMapping("ai-map-1", "pyannote:scope:SPEAKER_00", "ai-char-1",
                                 evidence=Evidence("text", "confirmed", ("c1",))),))
    source, target = tmp_path / "named.json", tmp_path / "out.json"
    data.save(str(source))
    monkeypatch.setattr("videocaptioner.core.split.split.SubtitleSplitter.split_subtitle",
                        lambda *a, **k: pytest.fail("split must be skipped for a context document"))
    args = build_parser().parse_args(["subtitle", str(source), "-o", str(target), "--no-optimize", "--no-translate"])
    config = build_config(_build_cli_overrides(args))
    assert config["subtitle"]["split"] is True
    assert run(args, config) == 0
    loaded = ASRData.from_subtitle_file(str(target))
    assert [s.cue_id for s in loaded] == ["c1", "c2"]
    assert loaded.conversation_context == data.conversation_context

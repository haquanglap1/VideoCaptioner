"""Empty complete jobs stop before LLM, publication or speaker enrichment."""

import importlib
from pathlib import Path
from types import SimpleNamespace

import pytest

from videocaptioner.core.asr.asr_data import ASRData, ASRDataSeg, EmptyTranscriptError
from videocaptioner.core.entities import TranscribeConfig, TranscribeModelEnum


def test_complete_empty_asr_stops_before_export(monkeypatch):
    module = importlib.import_module("videocaptioner.core.asr.transcribe")
    monkeypatch.setattr(module, "_create_asr_instance", lambda *a: SimpleNamespace(run=lambda **kw: ASRData([])))
    with pytest.raises(EmptyTranscriptError, match="Không nhận diện được lời nói"):
        module.transcribe("synthetic.wav", TranscribeConfig(transcribe_model=TranscribeModelEnum.FASTER_WHISPER))


def test_empty_chunk_is_still_valid_data():
    assert ASRData([]).segments == []
    ASRData([ASRDataSeg("Speech", 0, 1000)]).require_speech()


def test_gui_empty_subtitle_stops_before_configuration_or_workers():
    from videocaptioner.ui.thread.subtitle_thread import SubtitleThread

    with pytest.raises(EmptyTranscriptError, match="phụ đề nguồn rỗng"):
        SubtitleThread._process_subtitles(SimpleNamespace(), ASRData([]), None, None, Path("synthetic.srt"))


def test_cli_empty_srt_reports_no_speech_without_llm_or_output(tmp_path, capsys):
    from videocaptioner.cli.commands import subtitle
    from videocaptioner.cli.main import build_parser

    source = tmp_path / "empty.srt"
    source.write_text("", encoding="utf-8")
    target = tmp_path / "translated.srt"
    args = build_parser().parse_args(["subtitle", str(source), "--dialogue", "--target-language", "vi", "-o", str(target)])
    assert subtitle.run(args, {}) == 5
    output = capsys.readouterr()
    assert "phụ đề nguồn rỗng" in output.out + output.err
    assert not target.exists() and source.read_bytes() == b""

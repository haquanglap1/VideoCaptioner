"""Pipeline display layout survives hard rendering; standalone CLI stays raw."""

from argparse import Namespace
from pathlib import Path

import pytest

from videocaptioner.cli.commands import process, synthesize
from videocaptioner.cli.validators import resolve_layout
from videocaptioner.core.asr.asr_data import ASRData, ASRDataSeg
from videocaptioner.core.entities import SubtitleLayoutEnum


@pytest.fixture
def source(monkeypatch):
    monkeypatch.setattr("videocaptioner.core.asr.asr_data.detect", lambda text: "en" if text.startswith("Original") else "vi")
    return ASRData([ASRDataSeg("Original source sentence", 125, 2450, "Bản dịch đầy đủ")])


@pytest.mark.parametrize("layout_name", ["target-above", "source-above", "target-only", "source-only"])
@pytest.mark.parametrize("mode", ["ass", "rounded"])
@pytest.mark.parametrize("pipeline", [False, True])
def test_cli_hard_layout_once_for_process_and_standalone(source, tmp_path, monkeypatch, layout_name, mode, pipeline):
    video = tmp_path / "input.mp4"
    video.write_bytes(b"fixture video")
    layout = resolve_layout(layout_name)
    rendered, producer_files = [], []
    monkeypatch.setattr("videocaptioner.cli.validators.validate_process", lambda *a, **k: True)
    monkeypatch.setattr(synthesize, "validate_synthesize", lambda *a: True)
    monkeypatch.setattr(synthesize, "_resolve_style", lambda *a: (mode, "fixture style", {"font_size": 31}, None, None))

    def render(**kwargs):
        assert kwargs["layout"] == layout
        if mode == "ass":
            assert kwargs["style_str"] == "fixture style"
        else:
            assert kwargs["rounded_style"] == {"font_size": 31}
        data = kwargs["asr_data"]
        rendered.append(data.to_srt(layout=kwargs["layout"]))
        assert data.segments[0].start_time == 125 and data.segments[0].end_time == 2450

    monkeypatch.setattr("videocaptioner.core.subtitle.ass_renderer.render_ass_video", render)
    monkeypatch.setattr("videocaptioner.core.subtitle.rounded_renderer.render_rounded_video", render)
    config = {"synthesize": {"subtitle_mode": "hard", "layout": layout_name},
              "subtitle": {"optimize": True, "translate": False, "split": False}}
    if pipeline:
        def transcribe(args, _config):
            source.to_srt(save_path=args.output)
            return 0

        def subtitle(args, _config):
            source.to_srt(save_path=args.output, layout=layout)
            producer_files.append((Path(args.output), Path(args.output).read_bytes()))
            return 0

        monkeypatch.setattr("videocaptioner.cli.commands.transcribe.run", transcribe)
        monkeypatch.setattr("videocaptioner.cli.commands.subtitle.run", subtitle)
        args = Namespace(input=str(video), output=None, quiet=True, layout=layout_name)
        result = process.run(args, config)
    else:
        path = tmp_path / "raw.srt"
        source.to_srt(save_path=str(path))
        producer_files.append((path, path.read_bytes()))
        args = Namespace(video=str(video), subtitle=str(path), output=None, quiet=True, layout=layout_name)
        assert not hasattr(args, "input_subtitle_layout")
        result = synthesize.run(args, config)
    assert result == 0
    expected = {
        "target-above": ["Bản dịch đầy đủ", "Original source sentence"],
        "source-above": ["Original source sentence", "Bản dịch đầy đủ"],
        "target-only": ["Bản dịch đầy đủ"],
        "source-only": ["Original source sentence"],
    }[layout_name]
    assert len(rendered) == 1 and rendered[0].splitlines()[2:] == expected
    assert all(path.read_bytes() == before for path, before in producer_files)
    assert source.segments[0].text == "Original source sentence"


def test_cli_skipped_subtitle_stage_keeps_raw_input_marker(source, tmp_path, monkeypatch):
    video = tmp_path / "input.mp4"
    video.write_bytes(b"fixture video")
    seen = []
    monkeypatch.setattr("videocaptioner.cli.validators.validate_process", lambda *a, **k: True)

    def transcribe(args, _config):
        source.to_srt(save_path=args.output)
        return 0

    def render(args, _config):
        seen.append(args.input_subtitle_layout)
        return 0

    monkeypatch.setattr("videocaptioner.cli.commands.transcribe.run", transcribe)
    monkeypatch.setattr(synthesize, "run", render)
    config = {"subtitle": {"optimize": False, "translate": False, "split": False}}
    assert process.run(Namespace(input=str(video), quiet=True), config) == 0
    assert seen == [None]


def test_cli_soft_preserves_display_file_as_is(source, tmp_path, monkeypatch):
    video, subtitle = tmp_path / "input.mp4", tmp_path / "display.srt"
    video.write_bytes(b"fixture video")
    source.to_srt(save_path=str(subtitle), layout=SubtitleLayoutEnum.TRANSLATE_ON_TOP)
    seen = []
    before = subtitle.read_bytes()
    monkeypatch.setattr(synthesize, "validate_synthesize", lambda *a: True)
    monkeypatch.setattr("videocaptioner.core.utils.video_utils.add_subtitles",
                        lambda **kwargs: seen.append(Path(kwargs["subtitle_file"]).read_bytes()))
    args = Namespace(video=str(video), subtitle=str(subtitle), output=None, quiet=True,
                     input_subtitle_layout=SubtitleLayoutEnum.TRANSLATE_ON_TOP)
    assert synthesize.run(args, {"synthesize": {"subtitle_mode": "soft"}}) == 0
    assert seen == [before] and subtitle.read_bytes() == before

"""Display SRT handoff through real QThreads without FFmpeg or provider calls."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from videocaptioner.core.asr.asr_data import ASRData, ASRDataSeg
from videocaptioner.core.entities import (
    SubtitleConfig,
    SubtitleTask,
    SynthesisConfig,
    SynthesisTask,
)
from videocaptioner.core.entities import (
    SubtitleLayoutEnum as Layout,
)
from videocaptioner.core.entities import (
    SubtitleRenderModeEnum as Render,
)
from videocaptioner.core.subtitle.synthesis import load_synthesis_subtitles
from videocaptioner.ui.common.config import cfg
from videocaptioner.ui.thread import video_synthesis_thread
from videocaptioner.ui.view.home_interface import HomeInterface
from videocaptioner.ui.view.subtitle_interface import SubtitleInterface
from videocaptioner.ui.view.video_synthesis_interface import VideoSynthesisInterface


@pytest.fixture
def source(monkeypatch):
    # This suite controls bilingual detection to test layout provenance alone.
    monkeypatch.setattr("videocaptioner.core.asr.asr_data.detect", lambda text: "en" if text.startswith("Original") else "vi")
    return ASRData([
        ASRDataSeg("Original source sentence", 125, 2450, "Bản dịch thứ nhất"),
        ASRDataSeg("Original second sentence", 3500, 5678, "Bản dịch thứ hai"),
    ])


def expected_lines(layout, original, translated):
    return {
        Layout.TRANSLATE_ON_TOP: [translated, original],
        Layout.ORIGINAL_ON_TOP: [original, translated],
        Layout.ONLY_ORIGINAL: [original],
        Layout.ONLY_TRANSLATE: [translated],
    }[layout]


@pytest.mark.parametrize("layout", list(Layout))
@pytest.mark.parametrize("mode", ["soft", "ass", "rounded"])
@pytest.mark.parametrize("formatted", [False, True])
def test_gui_synthesis_applies_layout_once(source, tmp_path, qapp, monkeypatch, layout, mode, formatted):
    subtitle = tmp_path / "input.srt"
    source.to_srt(save_path=str(subtitle), layout=layout if formatted else Layout.ORIGINAL_ON_TOP)
    original_bytes = subtitle.read_bytes()
    seen, errors, finished = [], [], []
    config = SynthesisConfig(need_video=True, soft_subtitle=mode == "soft", subtitle_layout=layout,
                             render_mode=Render.ROUNDED_BG if mode == "rounded" else Render.ASS_STYLE,
                             ass_style="fixture styles", rounded_style={"font_size": 31})

    def soft(_video, srt, *_args, **kwargs):
        seen.append(Path(srt).read_text(encoding="utf-8"))
        assert kwargs["soft_subtitle"] is True

    def hard(**kwargs):
        assert kwargs["subtitle_layout"] == layout
        assert kwargs["render_mode"] == config.render_mode
        assert kwargs["ass_style"] == "fixture styles" and kwargs["rounded_style"] == {"font_size": 31}
        data = kwargs["asr_data"]
        seen.append(data.to_srt(layout=layout))
        ass = data.to_ass(layout=layout)
        for cue in source.segments:
            primary = expected_lines(layout, cue.text, cue.translated_text)[0]
            assert f"Default,,0,0,0,,{primary}\n" in ass

    monkeypatch.setattr(video_synthesis_thread, "add_subtitles", soft)
    monkeypatch.setattr(video_synthesis_thread, "add_subtitles_with_style", hard)
    task = SynthesisTask(video_path="fixture.mp4", subtitle_path=str(subtitle), output_path=str(tmp_path / "out.mp4"),
                         synthesis_config=config, input_subtitle_layout=layout if formatted else None)
    worker = video_synthesis_thread.VideoSynthesisThread(task)
    worker.error.connect(errors.append)
    worker.finished.connect(finished.append)
    worker.start()
    try:
        assert worker.wait(5000)
        qapp.processEvents()
        assert not errors and finished == [task]
        assert len(seen) == 1
        blocks = seen[0].strip().split("\n\n")
        for block, cue in zip(blocks, source.segments):
            assert block.splitlines()[1] == cue.to_srt_ts()
            assert block.splitlines()[2:] == expected_lines(layout, cue.text, cue.translated_text)
        assert subtitle.read_bytes() == original_bytes
        assert source.segments[0].text == "Original source sentence"
    finally:
        worker.wait()


@pytest.mark.parametrize("layout", [Layout.ONLY_ORIGINAL, Layout.ONLY_TRANSLATE])
def test_monolingual_display_keeps_every_line_and_default_ass_style(source, tmp_path, layout):
    path = tmp_path / "multiline.srt"
    path.write_text("1\n00:00:00,125 --> 00:00:02,450\nOriginal first line\nDòng tiếp theo\n", encoding="utf-8")
    before = path.read_bytes()
    data = load_synthesis_subtitles(str(path), input_layout=layout)
    assert data.to_srt(layout=layout) == path.read_text(encoding="utf-8")
    assert "Default,,0,0,0,,Original first line\\NDòng tiếp theo\n" in data.to_ass(layout=layout)
    assert data.segments[0].start_time == 125 and data.segments[0].end_time == 2450
    assert path.read_bytes() == before


def test_input_layout_is_independent_from_new_output_layout(source, tmp_path):
    path = tmp_path / "display.srt"
    source.to_srt(save_path=str(path), layout=Layout.TRANSLATE_ON_TOP)
    loaded = load_synthesis_subtitles(str(path), input_layout=Layout.TRANSLATE_ON_TOP)
    assert loaded.to_srt(layout=Layout.ORIGINAL_ON_TOP) == source.to_srt(layout=Layout.ORIGINAL_ON_TOP)


@pytest.mark.parametrize("layout", list(Layout))
def test_home_captures_producer_layout_across_dubbing_before_cfg_changes(monkeypatch, layout):
    subtitle = SubtitleTask(output_path="display.srt", subtitle_config=SubtitleConfig(subtitle_layout=layout))
    received = []
    interface = SimpleNamespace(set_task=received.append, process=lambda: None)
    home = SimpleNamespace(
        _current_task_id="pipeline-task", _display_subtitle_handoff=None,
        subtitle_optimization_interface=SimpleNamespace(task=subtitle),
        dubbing_interface=interface, video_synthesis_interface=interface,
        stackedWidget=SimpleNamespace(setCurrentWidget=lambda _: None),
        pivot=SimpleNamespace(setCurrentItem=lambda _: None),
    )
    monkeypatch.setattr(cfg.use_subtitle_style, "value", False)
    HomeInterface.switch_to_dubbing(home, "video.mp4", "tts.srt")
    monkeypatch.setattr(cfg.subtitle_layout, "value", Layout.ONLY_ORIGINAL)
    HomeInterface.switch_to_video_synthesis(home, "dubbed.mp4", "display.srt")
    task = received[-1]
    assert task.input_subtitle_layout == layout
    assert task.synthesis_config.subtitle_layout == Layout.ONLY_ORIGINAL
    assert task.subtitle_path == "display.srt"
    subtitle.subtitle_config.subtitle_layout = Layout.ONLY_TRANSLATE
    HomeInterface.switch_to_video_synthesis(home, "dubbed.mp4", "display.srt")
    assert received[-1].input_subtitle_layout == Layout.ONLY_TRANSLATE
    HomeInterface.switch_to_video_synthesis(home, "video.mp4", "raw.srt")
    assert received[-1].input_subtitle_layout is None


@pytest.mark.parametrize("written", [False, True])
def test_reexport_updates_input_layout_only_after_display_write(source, monkeypatch, written):
    task = SubtitleTask(output_path="display.srt", subtitle_config=SubtitleConfig(subtitle_layout=Layout.TRANSLATE_ON_TOP))
    interface = SimpleNamespace(task=task, model=SimpleNamespace(_data=source.to_json()),
                                _current_ass_style=lambda: "", _context_data=source)
    monkeypatch.setattr("videocaptioner.ui.view.subtitle_interface.editing.reexport_pipeline_outputs",
                        lambda *a, **k: ["display.srt"] if written else [])
    SubtitleInterface._reexport_pipeline_outputs(interface, Layout.ORIGINAL_ON_TOP)
    assert task.subtitle_config.subtitle_layout == (Layout.ORIGINAL_ON_TOP if written else Layout.TRANSLATE_ON_TOP)


@pytest.mark.parametrize("mode", ["same", "changed", "raw"])
def test_manual_synthesis_retry_keeps_marker_only_for_same_pipeline_file(monkeypatch, mode):
    existing = SynthesisTask(subtitle_path="display.srt",
                             input_subtitle_layout=None if mode == "raw" else Layout.TRANSLATE_ON_TOP)
    selected = "other.srt" if mode == "changed" else "display.srt"
    view = SimpleNamespace(task=existing, subtitle_input=SimpleNamespace(text=lambda: selected),
                           video_input=SimpleNamespace(text=lambda: "video.mp4"))
    monkeypatch.setattr(cfg.use_subtitle_style, "value", False)
    task = VideoSynthesisInterface.create_task(view)
    assert task.input_subtitle_layout == (Layout.TRANSLATE_ON_TOP if mode == "same" else None)

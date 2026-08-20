from pathlib import Path

from videocaptioner.core.entities import (
    OutputSubtitleFormatEnum,
    SubtitleConfig,
    SubtitleLayoutEnum,
    SubtitleTask,
)
from videocaptioner.ui.task_factory import TaskFactory
from videocaptioner.ui.thread.subtitle_thread import SubtitleThread


def test_full_pipeline_subtitle_task_defaults_to_srt(tmp_path):
    source = tmp_path / "source.srt"
    source.write_text("1\n00:00:00,000 --> 00:00:01,000\nHello world\n", encoding="utf-8")
    task = TaskFactory.create_subtitle_task(
        str(source), str(tmp_path / "clip.mp4"), need_next_task=True
    )
    assert Path(task.output_path or "").suffix == ".srt"


def test_full_pipeline_writes_srt_only_and_ass_remains_explicit_export(tmp_path, qapp):
    source = tmp_path / "source.srt"
    video = tmp_path / "clip.mp4"
    output = tmp_path / "processed.srt"
    source.write_text("1\n00:00:00,000 --> 00:00:01,000\nHello world\n", encoding="utf-8")
    video.write_bytes(b"placeholder")
    task = SubtitleTask(
        subtitle_path=str(source),
        video_path=str(video),
        output_path=str(output),
        need_next_task=True,
        subtitle_config=SubtitleConfig(
            need_split=False,
            need_optimize=False,
            need_translate=False,
            subtitle_layout=SubtitleLayoutEnum.ONLY_ORIGINAL,
        ),
    )
    errors = []
    thread = SubtitleThread(task)
    thread.error.connect(errors.append)
    thread.run()

    assert errors == []
    assert output.is_file()
    assert (tmp_path / "clip.srt").is_file()
    assert Path(task.dubbing_subtitle_path or "").is_file()
    assert not (tmp_path / "clip.ass").exists()
    assert list(tmp_path.glob("*.ass")) == []
    assert OutputSubtitleFormatEnum.ASS.value == "ass"

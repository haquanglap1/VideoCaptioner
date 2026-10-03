"""Completed video identity and worker reuse, without a real TTS provider."""

from dataclasses import replace

import pytest
from PyQt5.QtWidgets import QApplication

from videocaptioner.core.dubbing.completed import (
    CompletedVideo,
    load_video,
    receipt_path,
    save_video,
    video_identity,
)
from videocaptioner.core.dubbing.config import DubbingConfig
from videocaptioner.core.entities import DubbingTask
from videocaptioner.ui.thread import dubbing_thread


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def files(tmp_path):
    video, subtitle, output, captions = [tmp_path / name for name in ("source.mp4", "source.srt", "translated_dubbed.mp4", "playback.srt")]
    for file in (video, subtitle, output, captions):
        file.write_bytes(file.name.encode())
    return video, subtitle, output, captions


def test_receipt_reuses_translated_filename_and_checks_every_file(files):
    video, subtitle, output, captions = files
    config = DubbingConfig()
    key = video_identity(str(video), str(subtitle), config)
    receipt = receipt_path(str(output.parent / "source_dubbed.mp4"))
    save_video(receipt, key, CompletedVideo(str(output), str(captions)))
    assert load_video(receipt, key).output == str(output)
    assert video_identity(str(video), str(subtitle), replace(config, tts_concurrency=48, rewrite_model="other", rewrite_api_key="SECRET")) == key
    for changed in (replace(config, voice_tempo=1.2), replace(config, output_resolution=720), replace(config, voice_volume=.4)):
        assert load_video(receipt, video_identity(str(video), str(subtitle), changed)) is None
    captions.write_bytes(b"modified")
    assert load_video(receipt, key) is None
    captions.write_bytes(captions.name.encode())
    output.write_bytes(b"damaged")
    assert load_video(receipt, key) is None
    video.write_bytes(b"different source")
    assert video_identity(str(video), str(subtitle), config) != key


def test_worker_skips_title_tts_and_render_and_force_runs(files, monkeypatch, qapp):
    video, subtitle, output, captions = files
    config = DubbingConfig()
    expected = str(output.parent / "source_dubbed.mp4")
    key = video_identity(str(video), str(subtitle), config)
    save_video(receipt_path(expected), key, CompletedVideo(str(output), str(captions)))
    calls = []
    def engine(_):
        calls.append("engine")
        raise RuntimeError("Forced engine reached")
    monkeypatch.setattr(dubbing_thread, "_engine_for_task", engine)
    monkeypatch.setattr("videocaptioner.ui.thread.video_title.prepare_video_title", lambda *args: calls.append("title"))
    task = DubbingTask(video_path=str(video), subtitle_path=str(subtitle), output_path=expected, dubbing_config=config)
    worker = dubbing_thread.DubbingThread(task)
    errors, results = [], []
    worker.error.connect(errors.append)
    worker.finished.connect(results.append)
    worker._run()
    assert not errors and results == [task] and calls == []
    assert task.output_path == str(output) and task.playback_subtitle_path == str(captions)
    task.output_path = expected
    config.reuse_completed = False
    worker._run()
    assert calls == ["title", "engine"] and errors == ["Forced engine reached"]


def test_receipt_never_follows_paths_outside_output_folder(files):
    import json
    _, _, output, _ = files
    receipt = receipt_path(str(output))
    save_video(receipt, "identity", CompletedVideo(str(output)))
    data = json.loads(receipt.read_text())
    data["output"] = "../outside.mp4"
    receipt.write_text(json.dumps(data))
    assert load_video(receipt, "identity") is None


def test_legacy_rejects_wrong_text_missing_audio_and_short_video(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from videocaptioner.core.dubbing import completed
    from videocaptioner.core.translate.dialogue import DialogueCue, DialogueDocument, SpeechBlock

    source = tmp_path / "source [BV123456].mp4"
    source.write_bytes(b"source")
    subtitle = tmp_path / "spoken.dialogue.json"
    DialogueDocument((DialogueCue("c1", "source", "Xin chào", 0, 1000),),
                     (SpeechBlock(("c1",), "Xin chào"),), "vi").save(subtitle)
    output = tmp_path / "Tiêu đề [BV123456]_dubbed.mp4"
    output.write_bytes(b"completed video")
    captions = tmp_path / (output.stem + "-subtitles") / "playback.srt"
    captions.parent.mkdir()
    captions.write_text("1\n00:00:00,000 --> 00:00:01,000\nSai lời đọc\n", encoding="utf-8")
    source_info = SimpleNamespace(width=1280, height=720, audio_codec="aac", duration_seconds=2)
    result_info = SimpleNamespace(**source_info.__dict__)
    monkeypatch.setattr(completed, "get_video_info", lambda path: source_info if path == str(source) else result_info)
    expected = str(tmp_path / (source.stem + "_dubbed.mp4"))
    config = DubbingConfig()
    def load():
        return completed.load_legacy_video(str(source), str(subtitle), expected, config)
    assert load() is None
    captions.write_text("1\n00:00:00,000 --> 00:00:01,000\nXin chào\n", encoding="utf-8")
    result_info.audio_codec = ""
    assert load() is None
    result_info.audio_codec = "aac"
    result_info.duration_seconds = .5
    assert load() is None
    result_info.duration_seconds = 2
    assert load().output == str(output)
    # A mismatched new receipt may never fall back to weaker legacy matching.
    receipt_path(expected).write_text("{}")
    assert load() is None

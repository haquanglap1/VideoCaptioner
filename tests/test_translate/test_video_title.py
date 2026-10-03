"""Video naming uses only the basename, survives failure and never renames inputs."""

import json
import shutil
import subprocess
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from videocaptioner.core.entities import DubbingTask, SynthesisConfig, SynthesisTask
from videocaptioner.core.llm.client import LLMCredentials
from videocaptioner.core.translate import video_title as titles
from videocaptioner.ui.common.config import cfg
from videocaptioner.ui.task_factory import TaskFactory
from videocaptioner.ui.thread.video_title import prepare_video_title


@pytest.fixture(scope="session")
def qapp():
    from PyQt5.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def silent_video(tmp_path):
    from videocaptioner.core.utils.subprocess_helper import _NO_WINDOW, child_environment
    if not shutil.which("ffmpeg"):
        pytest.skip("FFmpeg unavailable")
    path = tmp_path / "source.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=s=64x64:d=1", "-c:v", "libx264", str(path)],
                   env=child_environment(), creationflags=_NO_WINDOW, capture_output=True, check=True)
    return path


@pytest.fixture
def title_service(monkeypatch):
    calls, stored = [], {}
    response = {"title": "Hướng dẫn ánh sáng UE5"}
    class Request:
        def __init__(self, credentials, timeout, cancelled, log_content):
            assert credentials.api_key == "synthetic-secret" and timeout <= 60 and not log_content
            self.cancelled = cancelled
        def __call__(self, messages, model):
            calls.append((messages, model))
            if isinstance(response.get("error"), Exception):
                raise response["error"]
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(response)))])
    monkeypatch.setattr(titles, "OwnedLLMRequest", Request)
    monkeypatch.setattr(titles, "is_cache_enabled", lambda: True)
    monkeypatch.setattr(titles, "get_translate_cache", lambda: SimpleNamespace(
        get=lambda key, default=None: stored.get(key, default),
        set=lambda key, value, **kwargs: stored.update({key: value})))
    config = titles.VideoTitleConfig("UE5 灯光 [BVfixture01]", "_dubbed", "vi", "synthetic-model",
                                    LLMCredentials("synthetic-secret", "https://synthetic.invalid/v1"))
    return SimpleNamespace(config=config, calls=calls, stored=stored, response=response)


def test_title_request_contains_no_path_or_video_id_and_reuses_cache(title_service, tmp_path):
    s = title_service
    config = replace(s.config, source_stem=r"C:\private\folder\UE5 灯光 [BVfixture01]")
    source = tmp_path / "source.mp4"
    source.write_bytes(b"original-video")
    result = titles.translated_output_path(str(tmp_path / "original_dubbed.mp4"), config)
    assert Path(result).name == "Hướng dẫn ánh sáng UE5 [BVfixture01]_dubbed.mp4"
    assert Path(result).parent == tmp_path and source.read_bytes() == b"original-video"
    request = json.loads(s.calls[0][0][1]["content"])
    assert request == {"title": "UE5 灯光", "language": "vi"}
    assert "private" not in repr(s.calls) and "BVfixture01" not in repr(s.calls)
    assert "synthetic-secret" not in repr(config)
    assert titles.translated_output_path(str(tmp_path / "another.mp4"), config) == result
    assert len(s.calls) == 1
    titles.translated_output_path(str(tmp_path / "another.mp4"), replace(config, target_language="en"))
    assert len(s.calls) == 2


def test_collision_retains_existing_file_and_extension(title_service, tmp_path):
    s = title_service
    original = tmp_path / "original.mkv"
    proposed = Path(titles.translated_output_path(str(original), s.config))
    proposed.write_bytes(b"keep-existing")
    result = Path(titles.translated_output_path(str(original), s.config))
    assert result.stem.endswith("(2)") and result.suffix == ".mkv"
    assert proposed.read_bytes() == b"keep-existing" and not result.exists()


@pytest.mark.parametrize("title", ['../../wrong:folder?\\name*', 'CON', 'NUL.txt', 'A' * 700, 'Tên hợp lệ'])
def test_windows_names_stay_in_output_directory(title_service, tmp_path, title):
    title_service.response["title"] = title
    result = Path(titles.translated_output_path(str(tmp_path / "out.mp4"), title_service.config))
    assert result.parent == tmp_path and result.suffix == ".mp4"
    assert not any(ch in result.name for ch in '<>:"/\\|?*')
    assert len(result.name.encode("utf-16-le")) // 2 < 200


@pytest.mark.parametrize("title", ["", "one\ntwo", 12, None, "///"])
def test_bad_translation_falls_back_without_failing_video(title_service, tmp_path, title):
    s = title_service
    s.response["title"] = title
    path = str(tmp_path / "original.mp4")
    task = DubbingTask(output_path=path, title_translation=s.config)
    progress = []
    prepare_video_title(task, lambda: None, lambda *args: progress.append(args))
    assert task.output_path == path and task.title_translation is None
    assert "tên gốc" in progress[-1][1] and not s.stored


def test_request_failure_is_one_attempt_and_cancel_is_not_swallowed(title_service, tmp_path):
    s = title_service
    s.response["error"] = TimeoutError()
    task = SynthesisTask(output_path=str(tmp_path / "out.mp4"), title_translation=s.config)
    prepare_video_title(task, lambda: None, lambda *_: None)
    prepare_video_title(task, lambda: None, lambda *_: None)
    assert len(s.calls) == 1 and not s.stored
    task.title_translation = s.config
    def check():
        raise RuntimeError("cancelled")
    with pytest.raises(RuntimeError, match="cancelled"):
        prepare_video_title(task, check, lambda *_: None)
    assert len(s.calls) == 1


def test_setting_is_captured_without_network_and_disabled_preserves_names(monkeypatch, title_service, tmp_path):
    monkeypatch.setattr(cfg.translate_video_title, "value", True)
    source = str(tmp_path / "中文 [BVfixture01].mp4")
    task = TaskFactory.create_synthesis_task(source, "input.srt")
    assert task.title_translation.source_stem == "中文 [BVfixture01]"
    assert task.title_translation.output_suffix == "_captioned"
    assert not title_service.calls
    monkeypatch.setattr(cfg.translate_video_title, "value", False)
    assert TaskFactory.create_synthesis_task(source, "input.srt").title_translation is None


def test_real_synthesis_publishes_translated_name(qapp, silent_video, tmp_path, title_service):
    from PyQt5.QtCore import QEventLoop, QThread, QTimer

    from videocaptioner.ui.thread.video_synthesis_thread import VideoSynthesisThread
    subtitle = tmp_path / "sub.srt"
    subtitle.write_text("1\n00:00:00,000 --> 00:00:01,000\nKiểm tra\n", encoding="utf-8")
    task = SynthesisTask(video_path=str(silent_video), subtitle_path=str(subtitle),
                         output_path=str(tmp_path / "original.mp4"),
                         synthesis_config=SynthesisConfig(need_video=True, soft_subtitle=True),
                         title_translation=title_service.config)
    worker = VideoSynthesisThread(task)
    loop = QEventLoop()
    errors, results = [], []
    worker.error.connect(errors.append)
    worker.finished.connect(results.append)
    QThread.finished.__get__(worker).connect(loop.quit)
    timer = QTimer()
    timer.setSingleShot(True)
    timer.timeout.connect(worker.stop)
    timer.start(15000)
    worker.start()
    loop.exec_()
    worker.wait()
    timer.stop()
    assert not errors and results == [task]
    assert "Hướng dẫn" in Path(task.output_path).name and Path(task.output_path).is_file()
    assert silent_video.is_file() and not (tmp_path / "original.mp4").exists()

"""Optional centralized exports retain every source and completed result."""

from pathlib import Path
from threading import Barrier

import pytest
from PyQt5.QtWidgets import QApplication

from tests.test_thread.test_batch_lifecycle import until
from videocaptioner.core.dubbing.config import DubbingConfig
from videocaptioner.core.dubbing.output import OutputClaim, video_destination
from videocaptioner.core.entities import BatchTaskType, DubbingTask
from videocaptioner.ui.batch_plan import BatchPlan
from videocaptioner.ui.common.config import cfg
from videocaptioner.ui.components.dubbing_output_folder import DubbingOutputFolder
from videocaptioner.ui.task_factory import TaskFactory
from videocaptioner.ui.thread import dubbing_thread


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


def make_task(tmp_path, name, directory=""):
    source = tmp_path / name / "episode.mp4"
    source.parent.mkdir(exist_ok=True)
    source.write_bytes(name.encode())
    subtitle = source.with_suffix(".srt")
    subtitle.write_text("1\n00:00:00,000 --> 00:00:02,000\nXin chào.\n", encoding="utf-8")
    return DubbingTask(video_path=str(source), subtitle_path=str(subtitle),
                       output_path=str(source.with_name("episode_dubbed.mp4")),
                       output_directory=directory, dubbing_config=DubbingConfig())


def test_default_remains_beside_source_and_central_config_is_snapshotted(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg.dubbing_output_dir, "value", "")
    monkeypatch.setattr(cfg.dubbing_enabled, "value", True)
    source = tmp_path / "source" / "video.mp4"
    original = TaskFactory.create_dubbing_task(str(source), "input.srt")
    assert Path(original.output_path).parent == source.parent and not original.output_directory
    chosen = tmp_path / "collected"
    monkeypatch.setattr(cfg.dubbing_output_dir, "value", str(chosen))
    monkeypatch.setattr(cfg.work_dir, "value", str(tmp_path / "work"))
    plan = BatchPlan.capture(str(source), BatchTaskType.FULL_PROCESS, TaskFactory(), dub=True, task_id="fixture")
    assert plan.dubbing.output_directory == plan.synthesis.output_directory == str(chosen)
    assert Path(plan.dubbing.output_path).parent == Path(plan.synthesis.output_path).parent == chosen
    monkeypatch.setattr(cfg.dubbing_output_dir, "value", "")
    assert plan.dubbing.output_directory == str(chosen) and not chosen.exists()


def test_claim_never_overwrites_and_removes_only_its_unused_placeholder(tmp_path):
    target = tmp_path / "same.mp4"
    target.write_bytes(b"keep")
    first, second = OutputClaim(str(target)), OutputClaim(str(target))
    assert first.path != second.path and first.path != target
    first.path.write_bytes(b"completed")
    first.close()
    second.close()
    assert target.read_bytes() == b"keep" and first.path.read_bytes() == b"completed"
    assert not second.path.exists()


def test_receipt_keys_distinguish_same_named_sources(tmp_path):
    root = str(tmp_path / "collected")
    first = video_destination("episode_dubbed.mp4", root, str(tmp_path / "a/episode.mp4"))
    second = video_destination("episode_dubbed.mp4", root, str(tmp_path / "b/episode.mp4"))
    assert first.output == second.output and first.receipt != second.receipt
    assert first.receipt.parent.name == ".videocaptioner"


def test_two_workers_export_same_names_and_reuse_their_own_receipts(tmp_path, monkeypatch, qapp):
    root = tmp_path / "collected"
    root.mkdir()
    protected = root / "episode_dubbed.mp4"
    protected.write_bytes(b"existing user video")
    tasks = [make_task(tmp_path, name, str(root)) for name in ("a", "b")]
    barrier, calls = Barrier(2), []

    class Engine:
        last_report_path = ""
        last_report = {}
        last_review = None
        def dub(self, **kwargs):
            source, output = Path(kwargs["video_path"]), Path(kwargs["output_path"])
            calls.append(str(source))
            barrier.wait(5)
            output.write_bytes(source.read_bytes())
            captions = output.parent / (output.stem + "-subtitles") / "playback.srt"
            captions.parent.mkdir()
            captions.write_bytes(Path(kwargs["subtitle_path"]).read_bytes())
            self.last_subtitle_path = str(captions)

    monkeypatch.setattr(dubbing_thread, "_engine_for_task", lambda _: Engine())
    workers = [dubbing_thread.DubbingThread(task) for task in tasks]
    errors = []
    for worker in workers:
        worker.error.connect(errors.append)
        worker.start()
    try:
        until(qapp, lambda: all(worker.isFinished() for worker in workers))
    finally:
        for worker in workers:
            worker.wait()
    assert not errors and len(calls) == 2
    assert tasks[0].output_path != tasks[1].output_path
    for task in tasks:
        assert Path(task.output_path).parent == root
        assert Path(task.output_path).read_bytes() == Path(task.video_path).read_bytes()
        assert Path(task.playback_subtitle_path).is_relative_to(root)
    assert protected.read_bytes() == b"existing user video"
    for original, name in zip(tasks, ("a", "b")):
        rerun = make_task(tmp_path, name, str(root))
        worker = dubbing_thread.DubbingThread(rerun)
        worker.error.connect(errors.append)
        worker.run()
        assert rerun.output_path == original.output_path
    assert not errors and len(calls) == 2 and len(list(root.glob("*.mp4"))) == 3


def test_bad_destination_fails_without_falling_back_to_source(tmp_path, monkeypatch, qapp):
    invalid = tmp_path / "not-a-folder"
    invalid.write_bytes(b"keep")
    task = make_task(tmp_path, "a", str(invalid))
    monkeypatch.setattr(dubbing_thread, "_engine_for_task", lambda _: pytest.fail("Do not call TTS for an invalid folder"))
    worker = dubbing_thread.DubbingThread(task)
    errors = []
    worker.error.connect(errors.append)
    worker.run()
    assert errors and not Path(task.output_path).exists() and invalid.read_bytes() == b"keep"


def test_failed_job_releases_unused_output_name(tmp_path, monkeypatch, qapp):
    root = tmp_path / "collected"
    task = make_task(tmp_path, "a", str(root))
    def fail(_):
        raise RuntimeError("fixture TTS failure")
    monkeypatch.setattr(dubbing_thread, "_engine_for_task", fail)
    worker = dubbing_thread.DubbingThread(task)
    errors = []
    worker.error.connect(errors.append)
    worker.run()
    assert errors == ["fixture TTS failure"] and not list(root.glob("*.mp4"))


def test_folder_controls_stay_in_sync_and_clear_to_default(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(cfg.dubbing_output_dir, "value", "")
    first, second = DubbingOutputFolder(), DubbingOutputFolder()
    first.edit.setText(str(tmp_path / "collected"))
    assert second.edit.text() == cfg.dubbing_output_dir.value == first.edit.text()
    second.clear_btn.click()
    assert not first.edit.text() and not cfg.dubbing_output_dir.value
    first.close()
    second.close()

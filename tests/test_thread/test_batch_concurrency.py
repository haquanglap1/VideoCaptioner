"""Exercise overlap, resource ownership and cancellation through native QThreads."""

import time
from collections import Counter
from pathlib import Path
from threading import Event

import pytest
from PyQt5.QtCore import QThread, pyqtSignal

from tests.test_thread.test_batch_lifecycle import until
from videocaptioner.core.asr.asr_data import ASRData, ASRDataSeg
from videocaptioner.core.batch import BatchLimits, asr_uses_gpu
from videocaptioner.core.entities import BatchTaskStatus as Status
from videocaptioner.core.entities import BatchTaskType as Kind
from videocaptioner.core.entities import TranscribeConfig, TranscribeModelEnum
from videocaptioner.ui.common.config import cfg
from videocaptioner.ui.thread import batch_process_thread as batch


@pytest.fixture
def parallel(qapp, monkeypatch, tmp_path):
    for item, value in ((cfg.work_dir, str(tmp_path / "work")), (cfg.dubbing_enabled, True),
                        (cfg.dubbing_tts_provider, "openai"), (cfg.need_video, True),
                        (cfg.transcribe_model, TranscribeModelEnum.WHISPER_API),
                        (cfg.local_asr_diarize, False), (cfg.translate_video_title, False)):
        monkeypatch.setattr(item, "value", value)
    coordinator = batch.BatchProcessThread(BatchLimits(3, 2, 2, 2, 1))
    workers, events, gates, failures = [], [], {}, {}

    class Worker(QThread):
        finished = pyqtSignal(object)
        error = pyqtSignal(str)
        progress = pyqtSignal(int, str)
        stage = "asr"

        def __init__(self, task, **_):
            super().__init__()
            self.task = task
            self.source = Path(getattr(task, "file_path", None) or getattr(task, "video_path", "")).name
            workers.append(self)

        def run(self):
            key = self.source, self.stage
            events.append(("start", *key, time.monotonic()))
            gate = gates.get(key)
            while gate and not gate.is_set() and not self.isInterruptionRequested():
                self.msleep(5)
            if key in failures:
                self.failure = failures[key]
                self.error.emit(str(self.failure))
                self.msleep(40)
                events.append(("exit", *key, time.monotonic()))
                return
            self.progress.emit(50, "halfway")
            if self.stage == "asr":
                self.task.asr_data = ASRData([ASRDataSeg(self.source, 0, 1000)])
                self.finished.emit(self.task)
            elif self.stage == "subtitle":
                self.finished.emit(self.task.video_path, self.task.output_path)
            else:
                if self.stage == "tts":
                    self.task.playback_subtitle_path = str(Path(self.task.output_path).with_suffix(".srt"))
                self.finished.emit(self.task)
            # Results are deliberately early; resource slots must remain held.
            self.msleep(40)
            events.append(("exit", *key, time.monotonic()))

    class Subtitle(Worker):
        finished = pyqtSignal(str, str)
        stage = "subtitle"

    class Dub(Worker):
        stage = "tts"

    class Render(Worker):
        stage = "render"

    for name, cls in (("TranscriptThread", Worker), ("SubtitleThread", Subtitle),
                      ("DubbingThread", Dub), ("VideoSynthesisThread", Render)):
        monkeypatch.setattr(batch, name, cls)
    from types import SimpleNamespace
    state = SimpleNamespace(c=coordinator, workers=workers, events=events, gates=gates, root=tmp_path,
                            failures=failures)
    yield state
    coordinator.shutdown()
    until(qapp, lambda: not coordinator.isRunning())
    for worker in workers:
        assert worker.wait(1000)


def enqueue(state, count=3, kind=Kind.FULL_PROCESS):
    tasks = [batch.BatchTask(str(state.root / f"{i}.mp4"), kind) for i in range(count)]
    for task in tasks:
        state.c.add_task(task)
    return tasks


def test_cpu_asr_overlaps_and_respects_stage_cap(parallel, qapp):
    parallel.gates.update({(f"{i}.mp4", "asr"): Event() for i in range(3)})
    tasks = enqueue(parallel)
    until(qapp, lambda: len(parallel.events) >= 2)
    assert {e[1] for e in parallel.events} == {"0.mp4", "1.mp4"}
    assert len(parallel.c.threads) == 2
    parallel.gates[("0.mp4", "asr")].set()
    until(qapp, lambda: any(e[:3] == ("start", "0.mp4", "subtitle") for e in parallel.events))
    assert not any(e[:3] == ("exit", "1.mp4", "asr") for e in parallel.events)
    for gate in parallel.gates.values():
        gate.set()
    until(qapp, lambda: not parallel.c.isRunning())
    assert all(task.status == Status.COMPLETED for task in tasks)
    active, peak = Counter(), Counter()
    for action, _, stage, _ in parallel.events:
        active[stage] += 1 if action == "start" else -1
        peak[stage] = max(peak[stage], active[stage])
    assert peak["asr"] == 2 and peak["render"] == 1
    assert all(active[stage] == 0 for stage in active)
    assert len({w.llm_gate for w in parallel.workers}) == 1


def test_gpu_asr_and_tts_share_one_slot_but_translation_overlaps(parallel, qapp, monkeypatch):
    monkeypatch.setattr(cfg.transcribe_model, "value", TranscribeModelEnum.FASTER_WHISPER)
    monkeypatch.setattr(cfg.faster_whisper_device, "value", "cuda")
    monkeypatch.setattr(cfg.dubbing_tts_provider, "value", "omnivoice-local")
    parallel.gates[("0.mp4", "subtitle")] = Event()
    tasks = enqueue(parallel)
    until(qapp, lambda: any(e[:3] == ("start", "1.mp4", "asr") for e in parallel.events))
    assert not any(e[:3] == ("exit", "0.mp4", "subtitle") for e in parallel.events)
    parallel.gates[("0.mp4", "subtitle")].set()
    until(qapp, lambda: not parallel.c.isRunning())
    active = peak = 0
    for action, _, stage, _ in parallel.events:
        if stage in ("asr", "tts"):
            active += 1 if action == "start" else -1
            peak = max(peak, active)
            assert active <= 1
    assert peak == 1 and active == 0 and all(t.status == Status.COMPLETED for t in tasks)


def test_cancel_one_running_job_keeps_other_jobs_and_retry_waits_for_cleanup(parallel, qapp):
    parallel.gates.update({(f"{i}.mp4", "asr"): Event() for i in range(3)})
    tasks = enqueue(parallel)
    until(qapp, lambda: len(parallel.events) == 2)
    parallel.c.stop_task(tasks[0].file_path)
    parallel.c.add_task(batch.BatchTask(tasks[0].file_path, Kind.FULL_PROCESS))
    assert parallel.c.current_tasks[tasks[0].file_path] is tasks[0]
    until(qapp, lambda: tasks[0].status == Status.CANCELLED)
    assert tasks[1].status == Status.RUNNING
    for gate in parallel.gates.values():
        gate.set()
    until(qapp, lambda: not parallel.c.isRunning())
    assert all(t.status == Status.COMPLETED for t in tasks[1:])
    assert not any(e[1:3] == ("0.mp4", "subtitle") for e in parallel.events)
    retry = batch.BatchTask(tasks[0].file_path, Kind.FULL_PROCESS)
    parallel.c.add_task(retry)
    until(qapp, lambda: not parallel.c.isRunning())
    assert retry.status == Status.COMPLETED


def test_stop_all_cancels_waiting_stages_and_preserves_responsiveness(parallel, qapp):
    parallel.gates.update({(f"{i}.mp4", "asr"): Event() for i in range(5)})
    tasks = enqueue(parallel, 5)
    until(qapp, lambda: len(parallel.events) == 2)
    started = time.monotonic()
    parallel.c.stop_all()
    assert time.monotonic() - started < .1
    until(qapp, lambda: not parallel.c.isRunning())
    assert all(t.status == Status.CANCELLED for t in tasks)
    assert len(parallel.events) == 4 and not parallel.c.admission.active


def test_same_name_sources_capture_distinct_paths_and_settings(parallel, qapp, monkeypatch):
    tasks = [batch.BatchTask(str(parallel.root / folder / "same.mp4"), Kind.FULL_PROCESS) for folder in ("a", "b")]
    for task in tasks:
        parallel.c.add_task(task)
    plans = [t.plan for t in tasks]
    assert plans[0].transcribe.output_path != plans[1].transcribe.output_path
    assert plans[0].subtitle.output_path != plans[1].subtitle.output_path
    before = plans[0].dubbing.dubbing_config.tts_config.voice
    monkeypatch.setattr(cfg.dubbing_tts_voice, "value", "changed after queueing")
    monkeypatch.setattr(cfg.dubbing_enabled, "value", False)
    until(qapp, lambda: not parallel.c.isRunning())
    assert all(t.status == Status.COMPLETED for t in tasks)
    assert all(w.task.dubbing_config.tts_config.voice == before for w in parallel.workers if w.stage == "tts")
    assert len([w for w in parallel.workers if w.stage == "tts"]) == 2


def test_concurrency_one_preserves_serial_mode(parallel, qapp):
    parallel.c.configure(BatchLimits(videos=1))
    tasks = enqueue(parallel, 2)
    until(qapp, lambda: not parallel.c.isRunning())
    assert all(t.status == Status.COMPLETED for t in tasks)
    assert [e[2] for e in parallel.events if e[0] == "start"] == ["asr", "subtitle", "tts", "render"] * 2


def test_quota_failure_stops_other_running_and_waiting_jobs(parallel, qapp):
    from videocaptioner.core.llm.rate_limit import LLMRateLimitError
    parallel.failures[("0.mp4", "subtitle")] = LLMRateLimitError("quota")
    parallel.gates[("1.mp4", "asr")] = Event()
    parallel.gates[("2.mp4", "asr")] = Event()
    tasks = enqueue(parallel, 5)
    until(qapp, lambda: not parallel.c.isRunning())
    assert tasks[0].status == Status.FAILED
    assert all(task.status == Status.CANCELLED for task in tasks[1:])
    assert not any(event[2] in ("tts", "render") for event in parallel.events)
    assert not parallel.c.admission.active


def test_sources_sharing_same_output_basename_are_rejected_before_workers(parallel, qapp):
    first = batch.BatchTask(str(parallel.root / "same.mp4"), Kind.FULL_PROCESS)
    second = batch.BatchTask(str(parallel.root / "same.mkv"), Kind.FULL_PROCESS)
    parallel.c.add_task(first)
    parallel.c.add_task(second)
    assert second.status == Status.FAILED and "tên đầu ra" in second.error_message
    until(qapp, lambda: not parallel.c.isRunning())
    assert first.status == Status.COMPLETED


@pytest.mark.parametrize("model,expected", [("whisper-1", False), ("gpt-4o-transcribe", True)])
def test_cloud_asr_with_local_alignment_reserves_gpu(model, expected):
    config = TranscribeConfig(transcribe_model=TranscribeModelEnum.WHISPER_API, whisper_api_model=model)
    assert asr_uses_gpu(config) is expected


def test_two_gpu_slots_overlap_asr_and_omnivoice(parallel, qapp, monkeypatch):
    monkeypatch.setattr(cfg.transcribe_model, "value", TranscribeModelEnum.FASTER_WHISPER)
    monkeypatch.setattr(cfg.faster_whisper_device, "value", "cuda")
    monkeypatch.setattr(cfg.dubbing_tts_provider, "value", "omnivoice-local")
    parallel.c.configure(BatchLimits(gpu=2))
    parallel.gates[("1.mp4", "asr")] = Event()
    tasks = enqueue(parallel, 3)
    until(qapp, lambda: any(e[:3] == ("start", "0.mp4", "tts") for e in parallel.events))
    assert not any(e[:3] == ("exit", "1.mp4", "asr") for e in parallel.events)
    parallel.gates[("1.mp4", "asr")].set()
    until(qapp, lambda: not parallel.c.isRunning())
    active = peak = 0
    for action, _, stage, _ in parallel.events:
        if stage in ("asr", "tts"):
            active += 1 if action == "start" else -1
            peak = max(peak, active)
            assert active <= 2
    assert peak == 2 and all(task.status == Status.COMPLETED for task in tasks)


def test_other_managed_gpu_runtimes_remain_exclusive():
    from videocaptioner.core.batch import BatchAdmission, BatchStage
    admission = BatchAdmission(BatchLimits(gpu=2))
    assert admission.acquire("first", BatchStage.ASR, True)
    assert not admission.acquire("vieneu", BatchStage.DUBBING, True, exclusive=True)
    admission.release("first")
    assert admission.acquire("vieneu", BatchStage.DUBBING, True, exclusive=True)
    assert not admission.acquire("second", BatchStage.ASR, True)
    assert admission.acquire("translate", BatchStage.SUBTITLE, False)

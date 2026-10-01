"""Selecting another video must export its own speech in the same Qt session."""

import io
import wave
import zlib
from pathlib import Path

from PyQt5.QtCore import QEventLoop, QTimer

from videocaptioner.core.asr import base, faster_whisper
from videocaptioner.core.asr.asr_data import ASRData
from videocaptioner.core.asr.chunked_asr import ChunkedASR
from videocaptioner.core.entities import (
    FasterWhisperModelEnum,
    TranscribeModelEnum,
    TranscribeOutputFormatEnum,
    VideoInfo,
)
from videocaptioner.ui.common.config import cfg
from videocaptioner.ui.view import transcription_interface as view


class MemoryCache(dict):
    def get(self, key, default=None):
        return super().get(key, default)

    def set(self, key, value, **kwargs):
        self[key] = value


def join_worker(qapp, worker):
    loop = QEventLoop()
    poll = QTimer()
    poll.timeout.connect(lambda: loop.quit() if not worker.isRunning() else None)
    poll.start(5)
    deadline = QTimer()
    deadline.setSingleShot(True)
    deadline.timeout.connect(loop.quit)
    deadline.start(5000)
    loop.exec_()
    poll.stop()
    deadline.stop()
    assert worker.wait(5000)
    qapp.processEvents()


def test_two_videos_cache_hit_and_failure_then_next_job(qapp, monkeypatch, tmp_path):
    monkeypatch.setattr(cfg.transcribe_model, "value", TranscribeModelEnum.FASTER_WHISPER)
    monkeypatch.setattr(cfg.transcribe_output_format, "value", TranscribeOutputFormatEnum.SRT)
    monkeypatch.setattr(cfg.faster_whisper_model, "value", FasterWhisperModelEnum.LARGE_V3)
    monkeypatch.setattr(faster_whisper, "resolve_program", lambda *_: "fake-whisper")
    monkeypatch.setattr(faster_whisper, "is_rtx_50_series", lambda: False)
    monkeypatch.setattr(base, "is_cache_enabled", lambda: True)
    memory = MemoryCache()
    monkeypatch.setattr(base, "get_asr_cache", lambda: memory)
    monkeypatch.setattr(ChunkedASR, "_split_audio", lambda self: [(self.file_binary, 0)])
    raws = [
        "1\n00:00:00,125 --> 00:00:01,900\nAlpha begins\n\n"
        "2\n00:00:01,900 --> 00:00:02,950\nAlpha ends\n",
        "1\n00:00:00,250 --> 00:00:01,800\nBeta now\nAgain\n\n"
        "2\n00:00:01,800 --> 00:00:01,800\nnow\n\n"
        "3\n00:00:01,800 --> 00:00:02,975\nBeta ends\n",
        "1\n00:00:00,900 --> 00:00:00,800\nInvalid timing\n",
    ]
    videos, audio, responses, calls, errors, done = [], {}, {}, [], [], []
    for i, raw in enumerate(raws):
        video = tmp_path / f"video {i} tiếng Việt.mp4"
        video.write_bytes(f"synthetic input {i}".encode())
        stream = io.BytesIO()
        with wave.open(stream, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(16000)
            wav.writeframes((i+1).to_bytes(2, "little") * 48000)
        videos.append(video)
        audio[str(video)] = stream.getvalue()
        responses[f"{zlib.crc32(stream.getvalue()) & 0xffffffff:08x}"] = raw

    def extract(path, output, **kwargs):
        Path(output).write_bytes(audio[path])
        return True

    def request(engine, *args, **kwargs):
        calls.append(engine.crc32_hex)
        return responses[engine.crc32_hex]

    def info(path, **kwargs):
        return VideoInfo(Path(path).name, path, 1920, 1080, 30, 3, 1000,
                         "h264", "aac", 16000, "")

    monkeypatch.setattr("videocaptioner.ui.thread.transcript_thread.video2audio", extract)
    monkeypatch.setattr("videocaptioner.ui.thread.video_info_thread.get_video_info", info)
    monkeypatch.setattr(faster_whisper.FasterWhisperASR, "_run", request)
    monkeypatch.setattr(view.InfoBar, "error", lambda *args, **kwargs: errors.append(args))
    page = view.TranscriptionInterface()
    card = page.video_info_card
    monkeypatch.setattr(card, "_validate_transcription_runtime", lambda task: True)
    card.finished.connect(done.append)

    def select_and_run(index):
        monkeypatch.setattr(view.QFileDialog, "getOpenFileName", lambda *args: (str(videos[index]), ""))
        page._on_file_select()
        join_worker(qapp, page.video_info_thread)
        assert card.video_info.file_path == str(videos[index])
        card.start_button.click()
        task = card.task
        join_worker(qapp, card.transcript_thread)
        assert not page.is_processing
        assert card.start_button.isEnabled()
        assert task.file_path == str(videos[index])
        assert Path(task.output_path) == videos[index].with_suffix(".srt")
        return task

    try:
        first = select_and_run(0)
        second = select_and_run(1)
        assert not errors
        assert first is not second
        assert done == [first, second]
        expected = [
            [("Alpha begins", 125, 1900), ("Alpha ends", 1900, 2950)],
            [("Beta now\nAgain\nnow", 250, 1800), ("Beta ends", 1800, 2975)],
        ]
        snapshots = [Path(task.output_path).read_bytes() for task in (first, second)]
        assert snapshots[0] != snapshots[1]
        for task, rows in zip((first, second), expected):
            data = ASRData.from_srt(Path(task.output_path).read_text("utf-8"), detect_bilingual=False)
            assert [(s.text, s.start_time, s.end_time) for s in data] == rows
        assert len(calls) == 2
        cached = dict(memory)
        assert sorted(memory.values()) == sorted(raws[:2])
        for i in (1, 0):
            hit = select_and_run(i)
            assert Path(hit.output_path).read_bytes() == snapshots[i]
        assert memory == cached and len(calls) == 2
        failed = select_and_run(2)
        assert errors and not Path(failed.output_path).exists()
        assert failed not in done
        recovered = select_and_run(0)
        assert Path(recovered.output_path).read_bytes() == snapshots[0]
        assert len(calls) == 3 and len(done) == 5
    finally:
        page.close()

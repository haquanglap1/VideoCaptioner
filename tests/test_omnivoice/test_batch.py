"""Actual model batching contracts, without a GPU or external service."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from videocaptioner.core.tts import TTSConfig, TTSData, TTSDataSeg
from videocaptioner.core.tts.omnivoice.config import OmniVoiceOptions
from videocaptioner.core.tts.omnivoice.provider import OmniVoiceTTS, plan_batches
from videocaptioner.resources.omnivoice.worker import generate_batch


def test_batch_planner_bounds_padding_and_preserves_full_long_text():
    texts = ["a" * 30, "b" * 35, "c" * 100, "d" * 200, "e" * 10]
    segments = [TTSDataSeg(text) for text in texts]
    batches = list(plan_batches(segments, OmniVoiceOptions(batch_size=4, batch_max_chars=100), "female"))
    assert [[i for i, _ in batch] for _, batch in batches] == [[0, 1], [2], [3], [4]]
    assert [segment.text for _, batch in batches for _, segment in batch] == texts
    assert all(voice == "vi-female-1" for voice, _ in batches)
    segments[1].voice = "male"
    assert len(list(plan_batches(segments[:2], OmniVoiceOptions(batch_size=4), "female"))) == 2


@pytest.mark.parametrize("size", [0, 3, 8, True])
def test_batch_options_reject_invalid_size(size):
    with pytest.raises(ValueError):
        OmniVoiceOptions(batch_size=size)


@pytest.mark.parametrize("failure", ["oom", "one-error", "count", "invalid-audio"])
def test_worker_maps_every_item_and_bounds_fallback(tmp_path, failure):
    events, calls, writes, seeds = [], [], [], []

    class OutOfMemoryError(RuntimeError):
        pass

    class Model:
        sampling_rate = 24000

        def generate(self, **kwargs):
            texts = kwargs["text"]
            calls.append(texts)
            assert kwargs["speed"] == 1 and kwargs["voice_clone_prompt"] is prompt
            if failure == "oom" and len(texts) > 1:
                raise OutOfMemoryError()
            if failure == "one-error" and "third" in texts:
                raise ValueError("private transcript must never be exposed")
            if failure == "count" and len(texts) > 1:
                return []
            return [[float("nan") if failure == "invalid-audio" and text == "third" else index + 0.1]
                    for index, text in enumerate(texts)]

    import math
    np = SimpleNamespace(isfinite=lambda audio: SimpleNamespace(all=lambda: all(math.isfinite(x) for x in audio)))
    torch = SimpleNamespace(manual_seed=seeds.append)
    sf = SimpleNamespace(write=lambda output, *args, **kwargs: writes.append(Path(output).stem))
    prompt = object()
    request = dict(items=[dict(id=str(i), text=text, output=str(tmp_path / f"{i}.wav"))
                         for i, text in enumerate(("first", "second", "third", "fourth"))],
        request_id="job-1", seed=9, language="vi", speed=1.0, steps=32, voice="vi-female-1")
    generate_batch(Model(), prompt, request, tmp_path, events.append, torch, np, sf)
    results = [e for e in events if e["status"] == "item"]
    assert [e["id"] for e in results] == ["0", "1", "2", "3"]
    assert len(calls) <= 7 and seeds == [9] * len(calls)
    assert events[-1] == {"status": "complete", "count": 4, "request_id": "job-1"}
    assert all(e["request_id"] == "job-1" for e in events)
    assert "private transcript" not in str(events)
    expected = ["0", "1", "3"] if failure in ("one-error", "invalid-audio") else ["0", "1", "2", "3"]
    assert writes == expected
    if failure == "one-error":
        assert calls.count(["first", "second"]) == 1
        assert results[2]["error_type"] == "ValueError"
    if failure == "invalid-audio":
        assert len(calls) == 1 and results[2]["error_type"] == "ValueError"
    if failure == "oom":
        assert all(e["actual_batch_size"] == 1 for e in results)


def test_provider_uses_model_batch_size_not_request_threads(tmp_path, monkeypatch):
    calls = []
    service = SimpleNamespace(options=OmniVoiceOptions(batch_size=2), check=lambda: None)

    def synthesize(items, on_result, **kwargs):
        calls.append(items)
        for item_id, _text, output in reversed(items):
            Path(output).write_bytes(item_id.encode())
            on_result(item_id, int(item_id) + 1, "", [])

    service.synthesize_batch = synthesize
    monkeypatch.setattr("videocaptioner.core.tts.omnivoice.provider.get_omnivoice_service", lambda: service)
    segments = [TTSDataSeg(f"Full text {i}", i * 5, i * 5 + 4) for i in range(5)]
    data = TTSData(segments)
    provider = OmniVoiceTTS(TTSConfig("", "", "", voice="vi-female-1", speed=1.0))
    provider.synthesize(data, str(tmp_path), max_workers=48)
    assert [len(items) for items in calls] == [2, 2, 1]
    assert [item[1] for items in calls for item in items] == [segment.text for segment in segments]
    assert [Path(segment.audio_path).read_text() for segment in segments] == [str(i) for i in range(5)]
    assert [(s.start_time, s.end_time) for s in segments] == [(i * 5, i * 5 + 4) for i in range(5)]


def test_existing_backoff_can_reduce_again_without_skipping_items(tmp_path):
    events = []
    class OutOfMemoryError(RuntimeError):
        pass
    class Model:
        sampling_rate = 24000
        def generate(self, **kwargs):
            if len(kwargs["text"]) > 1:
                raise OutOfMemoryError()
            return [[0.1]]
    request = dict(items=[dict(id=str(i), text=f"text {i}", output=str(tmp_path / f"{i}.wav")) for i in range(4)],
        request_id="reduced", seed=0, language="vi", speed=1.0, steps=32)
    limit = generate_batch(Model(), None, request, tmp_path, events.append,
        SimpleNamespace(manual_seed=lambda _: None),
        SimpleNamespace(isfinite=lambda _: SimpleNamespace(all=lambda: True)),
        SimpleNamespace(write=lambda *a, **kw: None), max_batch=2)
    assert limit == 1
    assert [e["id"] for e in events if e["status"] == "item"] == ["0", "1", "2", "3"]


def test_cli_distinguishes_threads_and_model_batch():
    from videocaptioner.cli.commands.dub import build_dubbing_config
    from videocaptioner.cli.main import _build_cli_overrides, build_parser

    args = build_parser().parse_args(["dub", "synthetic.mp4", "--subtitle", "synthetic.srt",
        "--tts-provider", "omnivoice-local", "--tts-concurrency", "12", "--omnivoice-batch-size", "4",
        "--omnivoice-batch-max-chars", "300", "--omnivoice-quality-preset", "more-steps"])
    config = build_dubbing_config(_build_cli_overrides(args))
    assert config.tts_concurrency == 12 and config.omnivoice.batch_size == 4
    assert config.omnivoice.batch_max_chars == 300 and config.omnivoice.effective_steps == 64

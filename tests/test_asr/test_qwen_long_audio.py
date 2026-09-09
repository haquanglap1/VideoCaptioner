"""Continuous audio, timeout retry and complete-only publication contracts."""

from types import SimpleNamespace

import pytest
from pydub import AudioSegment
from pydub.generators import Sine

from videocaptioner.core.asr.local import pipeline
from videocaptioner.core.asr.local.audio import split_recognition_audio
from videocaptioner.core.asr.local.profiles import LocalASRConfig
from videocaptioner.core.asr.local.runtime import (
    LocalRuntimeError,
    LocalRuntimeGenerationLimit,
    LocalRuntimeTimeout,
)
from videocaptioner.core.asr.review import NativeReviewRequired
from videocaptioner.core.entities import TranscribeConfig


def sound(ms):
    return Sine(400, sample_rate=16000).to_audio_segment(duration=ms)


def test_continuous_audio_keeps_every_sample_and_bounds_requests():
    audio = sound(62000) + AudioSegment(b"\x01\x02" * 7, sample_width=2, frame_rate=16000, channels=1)
    chunks = split_recognition_audio(audio, lambda: None, 120000)
    assert len(chunks) == 3
    assert b"".join(part.raw_data for part, _ in chunks) == audio.raw_data
    assert all(len(part) <= 30000 for part, _ in chunks)
    assert [offset for _, offset in chunks] == [0, len(chunks[0][0]), len(chunks[0][0]) + len(chunks[1][0])]


def test_existing_silence_cuts_stay_compatible():
    from videocaptioner.core.asr.alignment.audio import split_audio
    audio = sound(29000) + AudioSegment.silent(1000, frame_rate=16000) + sound(4000)
    old = split_audio(audio, lambda: None, 30000)
    new = split_recognition_audio(audio, lambda: None, 30000)
    assert [(part.raw_data, offset) for part, offset in old] == [(part.raw_data, offset) for part, offset in new]


@pytest.mark.parametrize("complete_retry", [True, False])
@pytest.mark.parametrize("failure", [LocalRuntimeTimeout, LocalRuntimeGenerationLimit])
def test_timeout_retries_only_failed_chunk_and_never_publishes_partial(monkeypatch, complete_retry, failure):
    audio = sound(32000)
    monkeypatch.setattr(pipeline, "decode_audio", lambda *a: audio)
    monkeypatch.setattr(pipeline, "locate", lambda *a, **k: "layout")
    calls = []

    class Runtime:
        def __init__(self, *a):
            self.state = "stopped"
        def start(self, check):
            self.state = "ready"
        def request(self, binary, check):
            duration = (len(binary) - 44) // 32
            calls.append(duration)
            if duration > 15000:
                if failure is LocalRuntimeTimeout:
                    self.close()
                raise failure("incomplete")
            if not complete_retry and len(calls) == 3:
                raise LocalRuntimeError("inference failed")
            return {"text": "你好。"}
        def close(self):
            self.state = "stopped"

    monkeypatch.setattr(pipeline, "LocalRuntime", Runtime)
    engine = pipeline.QwenLocalASR("fixture.wav", TranscribeConfig(transcribe_language="zh", local_asr=LocalASRConfig()))
    if complete_retry:
        result = engine.recognize()
        assert result.text == "你好。" * 3
        assert sum(calls[1:]) == len(audio)
    else:
        with pytest.raises(NativeReviewRequired) as error:
            engine.recognize()
        assert not error.value.review.recognition_complete
        assert error.value.review.text == "你好。"
        with pytest.raises(ValueError):
            error.value.review.resume()
    assert calls[0] > 15000 and all(n <= 15000 for n in calls[1:])


def test_completed_recognition_chunks_are_reused_after_failure(monkeypatch):
    monkeypatch.setattr(pipeline, "decode_audio", lambda *a: sound(2000))
    monkeypatch.setattr(pipeline, "locate", lambda *a, **k: "layout")
    cache = {}
    monkeypatch.setattr(pipeline, "is_cache_enabled", lambda: True)
    monkeypatch.setattr(pipeline, "get_asr_cache", lambda: SimpleNamespace(get=cache.get,
        set=lambda key, value, **kw: cache.__setitem__(key, value)))
    calls = []
    fail = True

    class Runtime:
        def __init__(self, *a):
            self.state = "stopped"
        def start(self, check):
            self.state = "ready"
        def request(self, binary, check):
            calls.append(binary)
            if fail and len(calls) == 2:
                raise LocalRuntimeError("failed")
            return {"text": "句。"}
        def close(self):
            self.state = "stopped"

    monkeypatch.setattr(pipeline, "LocalRuntime", Runtime)
    config = TranscribeConfig(transcribe_language="zh", local_asr=LocalASRConfig(chunk_ms=1000))
    with pytest.raises(NativeReviewRequired):
        pipeline.QwenLocalASR("fixture.wav", config).recognize()
    fail = False
    count = len(calls)
    result = pipeline.QwenLocalASR("fixture.wav", config).recognize()
    assert result.text == "句。" * 3
    assert len(calls) == count + 1


def test_audio_sized_budget_exhaustion_requires_eos_and_never_truncates_text():
    import runpy

    from videocaptioner.core.asr.local.runtime import recipe_directory

    bridge = runpy.run_path(str(recipe_directory() / "bridge.py"))
    limit = bridge["recognition_token_limit"]
    assert limit(30 * 16000) == 1216
    assert limit(15 * 16000) == 736
    assert limit(240 * 16000) == 7936
    assert limit(300 * 16000) == 8192
    bridge["require_completed_generation"](SimpleNamespace(sequences=[[1, 2, 9]]), [9, 10])
    with pytest.raises(bridge["IncompleteGeneration"]):
        bridge["require_completed_generation"](SimpleNamespace(sequences=[[1, 2, 3]]), 9)


def test_generation_limit_protocol_reuses_process_and_releases_request_files(tmp_path):
    import sys
    from pathlib import Path

    from videocaptioner.core.asr.local.profiles import MODELS, PROTOCOL
    from videocaptioner.core.asr.local.runtime import LocalLayout, LocalRuntime

    model = MODELS["qwen-0.6b"]
    identity = {"status": "ready", "protocol": PROTOCOL, "model": model.id, "revision": model.revision}
    bridge = tmp_path / "bridge.py"
    receipt = tmp_path / "request-path.txt"
    bridge.write_text(f'''import json,sys
from pathlib import Path
identity = {identity!r}
print(json.dumps(identity), flush=True)
for i, line in enumerate(sys.stdin):
    root = Path(json.loads(line)["directory"])
    Path({str(receipt)!r}).write_text(str(root))
    if i == 0:
        print(json.dumps(dict(identity, status="incomplete", reason="generation-limit")), flush=True)
    else:
        (root / "result.json").write_text(json.dumps({{"text": "complete"}}))
        print(json.dumps(identity), flush=True)
''', encoding="utf-8")
    runtime = LocalRuntime(LocalLayout(tmp_path, Path(sys.executable), bridge, tmp_path, model), 3)
    try:
        runtime.start()
        process = runtime.process
        with pytest.raises(LocalRuntimeGenerationLimit):
            runtime.request(b"audio")
        assert runtime.process is process and process.poll() is None and runtime.state == "ready"
        assert not Path(receipt.read_text()).exists()
        assert runtime.request(b"shorter audio") == {"text": "complete"}
        assert runtime.process is process
        assert not Path(receipt.read_text()).exists()
    finally:
        runtime.close()
    assert process.poll() is not None and runtime.lease.handle is None

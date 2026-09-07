"""Offline alignment contracts and lifecycle; synthetic audio, no cloud/model inference."""

import json
import sys
from contextvars import ContextVar
from dataclasses import replace
from pathlib import Path

import httpx
import openai
import pytest
from pydub import AudioSegment
from pydub.generators import Sine

from videocaptioner.core.asr import aligned_api
from videocaptioner.core.asr.alignment.audio import split_audio, verify_acoustic_support, wav_bytes
from videocaptioner.core.asr.alignment.contract import (
    MODEL_REVISION,
    POLICY,
    AlignmentError,
    alignment_key,
    chinese_language,
    merge_chunks,
    validate_alignment,
)
from videocaptioner.core.asr.alignment.runtime import (
    AlignmentRuntime,
    RuntimeLayout,
    locate_runtime,
)
from videocaptioner.core.entities import TranscribeConfig, TranscribeModelEnum


def item(text="你", start=100, end=300):
    return {"text": text, "start_ms": start, "end_ms": end}


@pytest.mark.parametrize("text,tokens", [
    ("“你好！”", ["你", "好"]), ("張三有12元。", ["張", "三", "有", "12", "元"]),
    ("张三有１２元。", ["张", "三", "有", "１２", "元"]), ("你好，OpenAI!", ["你", "好", "OpenAI"]),
    (" 你 好。 ", ["你", "好"]),
])
def test_text_preserved_exactly_and_seconds_are_not_invented(text, tokens):
    spans = [item(t, 100 + i * 200, 250 + i * 200) for i, t in enumerate(tokens)]
    result = validate_alignment(text, spans, 2000, 7000)
    for word in (True, False):
        data = result.asr_data(word)
        assert "".join(s.text for s in data) == text
        assert data.segments[0].start_time == 7100
        assert data.segments[-1].end_time == 7250 + (len(tokens) - 1) * 200
    assert "00:00:07,100" in result.asr_data().segments[0].to_srt_ts()


@pytest.mark.parametrize("items", [
    [item(start=-1)], [item(start=float("nan"))], [item(end=float("inf"))],
    [item(start=True)], [item(end=None)], [item(start=300, end=100)],
    [item(start=100, end=100)], [item(end=1001)], [item(start=100.5)],
    [item("我")], [item(), item()], [], {}, [{"text": "你"}],
])
def test_invalid_unmatched_and_silence_require_review(items):
    with pytest.raises(AlignmentError):
        validate_alignment("你", items, 1000)


def test_overlap_missing_text_and_script_changes_are_not_repaired():
    for text, items in [("你好", [item(), item("好", 200, 400)]),
                        ("你好", [item()]), ("張", [item("张")])]:
        with pytest.raises(AlignmentError):
            validate_alignment(text, items, 1000)
    assert not validate_alignment("", [], 1000).spans
    with pytest.raises(AlignmentError):
        validate_alignment("。", [], 1000)
    with pytest.raises(AlignmentError, match="silence"):
        verify_acoustic_support(AudioSegment.silent(1000), validate_alignment("你", [item()], 1000).spans)


@pytest.mark.parametrize("language", ["auto", "", "vi", "yue", "en"])
def test_language_preflight(language):
    with pytest.raises(AlignmentError):
        chinese_language(language)


def test_chunk_offset_and_boundary_reject_gaps_overlap():
    a = validate_alignment("你", [item()], 1000)
    b = validate_alignment("好", [item("好")], 1000, 1000)
    data = merge_chunks([a, b], 2000, True)
    assert [(s.text, s.start_time, s.end_time) for s in data] == [("你", 100, 300), ("好", 1100, 1300)]
    for offset in (900, 1100):
        with pytest.raises(AlignmentError):
            merge_chunks([a, replace(b, offset_ms=offset)], 2000, True)
    with pytest.raises(AlignmentError):
        merge_chunks([a], 2000, True)


def test_lossless_chunks_cover_tail_once_and_split_only_silence():
    audio = (Sine(400).to_audio_segment(duration=600) + AudioSegment.silent(600) +
             Sine(400).to_audio_segment(duration=603)).set_frame_rate(16000).set_channels(1)
    chunks = split_audio(audio, lambda: None, chunk_ms=1300)
    assert len(chunks) == 2
    assert chunks[1][1] == len(chunks[0][0])
    assert b"".join(c.raw_data for c, _ in chunks) == audio.raw_data
    with pytest.raises(AlignmentError, match="boundary"):
        split_audio(Sine(400).to_audio_segment(duration=2400), lambda: None, 1300)


def test_cache_invalidates_all_alignment_inputs_without_plaintext():
    key = alignment_key(b"audio", "private-text", "zh")
    assert alignment_key(b"audio", "private-text", "Chinese") == key
    for args, kwargs in [((b"other", "private-text", "zh"), {}),
                         ((b"audio", "other", "zh"), {}),
                         ((b"audio", "private-text", "zh"), {"revision": "other"}),
                         ((b"audio", "private-text", "zh"), {"policy": "other"}),
                         ((b"audio", "private-text", "zh"), {"config": "other"})]:
        assert alignment_key(*args, **kwargs) != key
    assert "private-text" not in key


@pytest.fixture
def config():
    return TranscribeConfig(transcribe_model=TranscribeModelEnum.WHISPER_API, transcribe_language="zh",
                            whisper_api_model="gpt-4o-transcribe", whisper_api_provider="videocaptioner",
                            whisper_api_key="synthetic-key", whisper_api_base="https://gateway.example/v1")


def test_missing_runtime_stops_before_audio_io_or_client(tmp_path, config, monkeypatch):
    monkeypatch.setenv("VIDEOCAPTIONER_ALIGNMENT_RUNTIME", str(tmp_path))
    monkeypatch.setattr(aligned_api, "submit_cancellable", lambda *a: pytest.fail("upload forbidden"))
    with pytest.raises(AlignmentError, match="runtime missing"):
        aligned_api.AlignedAPI("nonexistent.wav", config)
    (tmp_path / ".installing").touch()
    with pytest.raises(AlignmentError, match="downloading"):
        locate_runtime(tmp_path)


def test_real_s1_parser_through_mock_alignment_to_srt_and_cache(tmp_path, config, monkeypatch):
    from videocaptioner.core.asr.transcribe import transcribe

    calls = []
    class Runtime:
        def __init__(self, *_): pass
        def start(self, *args): calls.append("health")
        def align(self, binary, text, check):
            calls.append("align")
            assert binary[:4] == b"RIFF" and text == "你好。"
            return [item(), item("好", 350, 700)]
        def close(self): calls.append("close")

    class Cache(dict):
        def set(self, key, value, **kwargs): self[key] = value

    cache = Cache()
    audio = Sine(400).to_audio_segment(duration=1000).set_frame_rate(16000).set_channels(1)
    def handler(request):
        calls.append("upload")
        assert calls[0] == "health"
        body = request.read()
        assert b"timestamp_granularities" not in body and b"verbose_json" not in body
        assert b'filename="audio.wav"' in body
        assert b"private-input" not in body
        return httpx.Response(200, json={"text": "你好。"})

    monkeypatch.setattr(aligned_api, "AlignmentRuntime", Runtime)
    monkeypatch.setattr(aligned_api, "locate_runtime", lambda: None)
    monkeypatch.setattr(aligned_api, "decode_audio", lambda *a: audio)
    monkeypatch.setattr(aligned_api, "get_asr_cache", lambda: cache)
    monkeypatch.setattr(aligned_api, "is_cache_enabled", lambda: True)
    monkeypatch.setattr("videocaptioner.core.asr.api_transcription.create_async_client", lambda *a: openai.AsyncOpenAI(
        api_key="synthetic-key", base_url="https://gateway.example/v1", max_retries=0,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler))))
    for _ in range(2):
        result = transcribe("private-input.wav", config)
        result.save(str(tmp_path / "output.srt"))
        assert result.segments[0].start_time == 100
        assert result.segments[-1].end_time == 700  # optimize_timing must not extend measured spans.
    assert calls == ["health", "upload", "align", "close", "health", "close"]
    assert "00:00:00,100" in (tmp_path / "output.srt").read_text(encoding="utf-8-sig")
    assert all("synthetic-key" not in k and "你好" not in k for k in cache)


@pytest.fixture
def runtime_layout(tmp_path):
    bridge = tmp_path / "bridge.py"
    return RuntimeLayout(tmp_path, Path(sys.executable), bridge, tmp_path / "model")


def test_runtime_handshake_scrubbed_env_and_shutdown(runtime_layout, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "secret")
    monkeypatch.setenv("VIDEOCAPTIONER_WHISPER_API_KEY", "secret")
    runtime_layout.bridge.write_text(
        "import json, os, sys\n"
        "assert not any(k.startswith(('OPENAI_', 'VIDEOCAPTIONER_')) for k in os.environ)\n"
        "assert os.environ['HF_HUB_OFFLINE'] == '1'\n"
        f"print({json.dumps({'status': 'ready', 'revision': MODEL_REVISION, 'policy': POLICY, 'language': 'Chinese'})!r}, flush=True)\n"
        "for line in sys.stdin:\n"
        " from pathlib import Path\n"
        " root = Path(json.loads(line)['directory'])\n"
        " (root / 'result.json').write_text('[]')\n"
        " print(json.dumps({'status': 'ready'}), flush=True)\n", encoding="utf-8")
    runtime = AlignmentRuntime(runtime_layout, timeout=5)
    try:
        runtime.start("zh")
        process = runtime.process
        assert runtime.align(wav_bytes(AudioSegment.silent(1000).set_frame_rate(16000)), "") == []
    finally:
        runtime.close()
    assert process.poll() is not None and not runtime.reader.is_alive()


@pytest.mark.parametrize("mode", ["timeout", "cancel", "crash", "malformed"])
def test_runtime_failure_leaves_no_process_or_reader(runtime_layout, mode):
    runtime_layout.bridge.write_text(
        "import time\n" + ("print('bad', flush=True)\n" if mode == "malformed" else "") +
        ("raise SystemExit(1)" if mode == "crash" else "time.sleep(20)"), encoding="utf-8")
    runtime = AlignmentRuntime(runtime_layout, timeout=0.3)
    def check():
        if mode == "cancel" and runtime.process is not None:
            raise AlignmentError("cancelled")
    with pytest.raises(AlignmentError):
        runtime.start("zh", check)
    assert runtime.process is None
    assert runtime.reader is None or not runtime.reader.is_alive()


def test_probe_worker_context_and_release(monkeypatch):
    from videocaptioner.ui.thread.alignment_thread import AlignmentThread

    context = ContextVar("alignment-test", default="missing")
    context.set("job")
    observed = []
    class Runtime:
        def start(self, language, check):
            check()
            observed.append((context.get(), language))
        def close(self): observed.append("closed")
    monkeypatch.setattr("videocaptioner.ui.thread.alignment_thread.AlignmentRuntime", Runtime)
    thread = AlignmentThread()
    context.set("other")
    thread.start()
    assert thread.wait(3000)
    assert observed == [("job", "zh"), "closed"]


def test_health_failure_prevents_upload_and_always_closes(config, monkeypatch):
    calls = []
    class Runtime:
        def __init__(self, *_): pass
        def start(self, *args): raise AlignmentError("runtime failed")
        def close(self): calls.append("closed")
    monkeypatch.setattr(aligned_api, "locate_runtime", lambda: None)
    monkeypatch.setattr(aligned_api, "AlignmentRuntime", Runtime)
    monkeypatch.setattr(aligned_api, "decode_audio", lambda *a: pytest.fail("must preflight first"))
    monkeypatch.setattr(aligned_api, "submit_cancellable", lambda *a: pytest.fail("must not upload"))
    with pytest.raises(AlignmentError):
        aligned_api.AlignedAPI("unused.wav", config).run()
    assert calls == ["closed"]


def test_cancel_before_retry_does_not_upload_again(monkeypatch):
    from videocaptioner.core.asr.api_profiles import JSON_TEXT
    from videocaptioner.core.asr.api_transcription import build_request, submit_transcription

    calls = []
    def handler(request):
        calls.append("upload")
        return httpx.Response(503)
    def check():
        if calls:
            raise AlignmentError("cancelled")
    with openai.OpenAI(api_key="synthetic", base_url="https://gateway.example/v1", max_retries=0,
                      http_client=httpx.Client(transport=httpx.MockTransport(handler))) as client:
        with pytest.raises(AlignmentError, match="cancelled"):
            submit_transcription(client, build_request(
                wav_bytes(AudioSegment.silent(1000, frame_rate=16000)), "gpt-4o-transcribe", JSON_TEXT),
                check_cancel=check)
    assert calls == ["upload"]


def test_manifest_revision_mismatch_is_not_ready(runtime_layout):
    root = runtime_layout.root
    python = root / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    python.parent.mkdir(parents=True)
    python.touch()
    runtime_layout.bridge.touch()
    runtime_layout.model.mkdir()
    (runtime_layout.model / "config.json").write_text("{}")
    manifest = {"model_revision": "different", "policy": POLICY, "protocol": "alignment-v1"}
    (root / "runtime-manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(AlignmentError, match="invalid"):
        locate_runtime(root)
    manifest["model_revision"] = MODEL_REVISION
    (root / "runtime-manifest.json").write_text(json.dumps(manifest))
    assert locate_runtime(root).model == runtime_layout.model
    (root / ".failed").touch()
    with pytest.raises(AlignmentError, match="installation failed"):
        locate_runtime(root)


def test_alignment_wait_cancel_removes_child_tree(runtime_layout):
    runtime_layout.bridge.write_text(
        "import sys, time, json\n"
        f"print({json.dumps({'status': 'ready', 'revision': MODEL_REVISION, 'policy': POLICY, 'language': 'Chinese'})!r}, flush=True)\n"
        "for line in sys.stdin: time.sleep(20)\n", encoding="utf-8")
    runtime = AlignmentRuntime(runtime_layout, timeout=5)
    try:
        runtime.start("zh")
        process = runtime.process
        count = 0
        def check():
            nonlocal count
            count += 1
            if count > 2:
                raise AlignmentError("cancelled")
        with pytest.raises(AlignmentError, match="cancelled"):
            runtime.align(wav_bytes(AudioSegment.silent(1000, frame_rate=16000)), "你好", check)
        assert process.poll() is not None
        assert not runtime.reader.is_alive()
    finally:
        runtime.close()


def test_cancelling_inflight_api_closes_task_and_never_retries(monkeypatch):
    import asyncio

    from videocaptioner.core.asr.api_profiles import JSON_TEXT
    from videocaptioner.core.asr.api_transcription import build_request, submit_cancellable

    events = []
    async def handler(request):
        events.append("upload")
        try:
            await asyncio.sleep(60)
            return httpx.Response(200, json={"text": "你好"})
        finally:
            events.append("closed")
    def check():
        if "upload" in events:
            raise AlignmentError("cancelled")
    monkeypatch.setattr("videocaptioner.core.asr.api_transcription.create_async_client", lambda *a: openai.AsyncOpenAI(
        api_key="synthetic", base_url="https://gateway.example/v1", max_retries=0,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler))))
    with pytest.raises(AlignmentError, match="cancelled"):
        submit_cancellable("https://gateway.example/v1", "synthetic", build_request(
            wav_bytes(AudioSegment.silent(1000, frame_rate=16000)), "gpt-4o-transcribe", JSON_TEXT), check)
    assert events == ["upload", "closed"]


@pytest.mark.parametrize("code,attempts", [(401, 1), (404, 1), (413, 1), (429, 3), (503, 3), (302, 1)])
def test_async_transport_retains_s1_retry_and_privacy_policy(monkeypatch, code, attempts):
    import traceback

    from videocaptioner.core.asr.api_profiles import JSON_TEXT, ASRAPIError
    from videocaptioner.core.asr.api_transcription import build_request, submit_cancellable

    calls = []
    def handler(request):
        calls.append(True)
        return httpx.Response(code, json={"error": {"message": "private-response"}},
                              headers={"Location": "https://other.example", "Retry-After": "999999"})
    async def sleep(_): pass
    monkeypatch.setattr("videocaptioner.core.asr.api_transcription.asyncio.sleep", sleep)
    monkeypatch.setattr("videocaptioner.core.asr.api_transcription.create_async_client", lambda *a: openai.AsyncOpenAI(
        api_key="synthetic", base_url="https://gateway.example/v1", max_retries=0,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler))))
    with pytest.raises(ASRAPIError) as error:
        submit_cancellable("https://gateway.example/v1", "synthetic", build_request(
            wav_bytes(AudioSegment.silent(1000, frame_rate=16000)), "gpt-4o-transcribe", JSON_TEXT), lambda: None)
    assert len(calls) == attempts
    assert "private-response" not in "".join(traceback.format_exception(error.value))

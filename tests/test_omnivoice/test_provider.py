"""OmniVoice integration contracts without importing or downloading GPU libraries."""

import hashlib
import io
import json
import sys
import time

import pytest

from videocaptioner.cli.commands.dub import build_dubbing_config
from videocaptioner.core.dubbing import presets
from videocaptioner.core.dubbing.config import DubbingConfig, TTSProviderEnum
from videocaptioner.core.dubbing.engine import DubbingEngine
from videocaptioner.core.tts import TTSConfig
from videocaptioner.core.tts.omnivoice import prepare, runtime
from videocaptioner.core.tts.omnivoice.config import CODE_REVISION, MODEL_REVISION, OmniVoiceOptions


def test_provider_selection_does_not_require_api_credentials_or_change_vieneu():
    config = build_dubbing_config({"dubbing": {"tts_provider": "omnivoice-local"}})
    assert config.tts_provider == TTSProviderEnum.OMNIVOICE_LOCAL
    assert config.tts_config.voice == "auto" and not config.tts_config.api_key
    assert presets.is_managed_provider("omnivoice-local")
    assert presets.provider_from_key("vieneu-local") == TTSProviderEnum.VIENEU_LOCAL
    unrelated = build_dubbing_config({"omnivoice": {"reference_audio": "unused.wav"}})
    assert unrelated.tts_provider == TTSProviderEnum.OPENAI


def test_reference_requires_both_parts_and_cli_reads_text_file(tmp_path):
    with pytest.raises(ValueError):
        OmniVoiceOptions(reference_audio="reference.wav")
    with pytest.raises(ValueError):
        OmniVoiceOptions(reference_text="reference")
    text = tmp_path / "reference.txt"
    text.write_text("Xin chào", encoding="utf-8")
    config = build_dubbing_config({"dubbing": {"tts_provider": "omnivoice-local"},
        "omnivoice": {"reference_audio": "reference.wav", "reference_text_file": str(text)}})
    assert config.omnivoice.reference_text == "Xin chào"
    assert "Xin chào" not in repr(config.omnivoice)


@pytest.mark.parametrize("partial,status", [(b"old", 200), (b"pay", 206)])
def test_download_resume_honors_server_range_or_restarts(tmp_path, monkeypatch, partial, status):
    path = tmp_path / "model.bin"
    path.with_name("model.bin.part").write_bytes(partial)
    class Response(io.BytesIO):
        headers = {"Content-Range": "bytes 3-6/7"}
    response = Response(b"load" if status == 206 else b"payload")
    response.status = status
    monkeypatch.setattr(prepare.urllib.request, "urlopen", lambda *a, **kw: response)
    prepare.download("https://example.invalid/model", path, hashlib.sha256(b"payload").hexdigest())
    assert path.read_bytes() == b"payload" and not path.with_name("model.bin.part").exists()


def test_invalid_download_and_unowned_directory_never_activate(tmp_path, monkeypatch):
    class Response(io.BytesIO):
        status = 200
        headers = {}
    monkeypatch.setattr(prepare.urllib.request, "urlopen", lambda *a, **kw: Response(b"bad"))
    with pytest.raises(RuntimeError, match="checksum"):
        prepare.download("https://example.invalid/model", tmp_path / "model.bin", "0" * 64)
    assert not (tmp_path / "model.bin").exists()
    reason = "not owned" if prepare.os.name == "nt" else "targets Windows"
    with pytest.raises(RuntimeError, match=reason):
        prepare.prepare_runtime(str(tmp_path))
    assert not (tmp_path / "ready.json").exists()


FAKE = '''import json, sys, wave, time
print('VC_OMNI ' + json.dumps({'status':'ready','sample_rate':24000}), flush=True)
for line in sys.stdin:
    value=json.loads(line)
    if value['operation']=='configure':
        print('VC_OMNI '+json.dumps({'status':'configured'}), flush=True)
    else:
        if value['text']=='wait': time.sleep(30)
        with wave.open(value['output'],'wb') as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000); w.writeframes(b'\\0\\1'*2400)
        print('VC_OMNI '+json.dumps({'status':'complete'}), flush=True)
'''


@pytest.fixture
def fake_runtime(tmp_path, monkeypatch):
    (tmp_path / "worker.py").write_text(FAKE, encoding="utf-8")
    monkeypatch.setattr(runtime, "resources", lambda: tmp_path)
    monkeypatch.setattr(runtime, "verify", lambda *a: {})
    popen = runtime.subprocess.Popen
    processes = []
    def start(args, **kwargs):
        command = [sys.executable, *args[1:]] if len(args) > 2 and str(args[2]).endswith("worker.py") else args
        process = popen(command, **kwargs)
        processes.append(process)
        return process
    monkeypatch.setattr(runtime.subprocess, "Popen", start)
    service = runtime.OmniVoiceRuntime()
    monkeypatch.setattr(runtime, "_service", service)
    return service, processes


def test_runtime_identity_provider_wav_and_cleanup(tmp_path, fake_runtime):
    service, processes = fake_runtime
    config = DubbingConfig(tts_provider=TTSProviderEnum.OMNIVOICE_LOCAL,
        tts_config=TTSConfig("old", "", "", voice="auto"), omnivoice=OmniVoiceOptions(language="zh"))
    with service.acquire(config):
        assert config.target_language == "zh" and config.strip_cjk is False
        assert config.managed_tts_identity["code_revision"] == CODE_REVISION
        assert config.managed_tts_identity["model_revision"] == MODEL_REVISION
        assert config.tts_config.sample_rate == 24000
        assert not DubbingEngine()._create_tts_provider(config).config.use_cache
        output = tmp_path / "out.wav"
        assert service.synthesize("hello", str(output)) == 0.1
        assert output.exists()
    assert service.process is None and service.lease.handle is None
    assert all(p.poll() is not None for p in processes)
    assert config.tts_config.model == "old" and not config.managed_tts_identity
    assert config.strip_cjk is True


def test_cancellation_during_silent_inference_reaps_process(fake_runtime):
    service, processes = fake_runtime
    cancel_at = float("inf")
    def check(*args):
        if time.monotonic() >= cancel_at:
            raise ValueError("cancelled")
    config = DubbingConfig(tts_config=TTSConfig("", "", ""))
    with pytest.raises(ValueError, match="cancelled"):
        with service.acquire(config, check):
            cancel_at = time.monotonic() + 0.15
            service.synthesize("wait", "unused.wav")
    assert all(p.poll() is not None for p in processes)
    assert service.lease.handle is None and service.scratch is None


def test_worker_imports_do_not_load_gpu_into_app():
    assert "torch" not in sys.modules
    assert "omnivoice" not in sys.modules


def test_female_uses_one_fixed_reference_for_every_group(fake_runtime):
    service, _ = fake_runtime
    config = DubbingConfig(tts_provider=TTSProviderEnum.OMNIVOICE_LOCAL,
        tts_config=TTSConfig("", "", "", voice="female"))
    requests = []
    original = service.request

    def record(payload):
        requests.append(dict(payload))
        return original(payload)

    service.request = record
    with service.acquire(config):
        configured = next(item for item in requests if item["operation"] == "configure")
        assert configured["reference_audio"], "female must pin a speaker, not redesign each sentence"
        assert configured["reference_text"]
        assert len(config.managed_tts_identity["reference_sha256"]) == 64


def test_voice_changes_cache_identity_and_cannot_switch_mid_job(fake_runtime):
    from videocaptioner.core.dubbing.review import synthesis_cache_key

    service, _ = fake_runtime
    keys = []
    for voice in ("vi-female-1", "vi-female-2", "vi-female-1"):
        config = DubbingConfig(tts_provider=TTSProviderEnum.OMNIVOICE_LOCAL,
            tts_config=TTSConfig("", "", "", voice=voice))
        with service.acquire(config):
            keys.append(synthesis_cache_key("Same text", config))
            with pytest.raises(ValueError, match="one selected voice"):
                service.synthesize("words", "unused.wav", voice="vi-male-1")
    assert keys[0] == keys[2] and keys[0] != keys[1]


def test_reference_transcript_and_audio_both_invalidate_cache(tmp_path, fake_runtime):
    from videocaptioner.core.dubbing.review import synthesis_cache_key

    service, _ = fake_runtime
    audio = tmp_path / "reference.wav"
    keys = []
    for content, transcript in ((b"audio1", "words1"), (b"audio1", "words2"), (b"audio2", "words2")):
        audio.write_bytes(content)
        config = DubbingConfig(tts_provider=TTSProviderEnum.OMNIVOICE_LOCAL,
            tts_config=TTSConfig("", "", "", voice="auto"),
            omnivoice=OmniVoiceOptions(reference_audio=str(audio), reference_text=transcript))
        with service.acquire(config):
            keys.append(synthesis_cache_key("Same text", config))
    assert len(set(keys)) == 3


def test_installed_model_integrity_is_checked(tmp_path, monkeypatch):
    python = tmp_path / "env" / ("Scripts/python.exe" if prepare.os.name == "nt" else "bin/python")
    python.parent.mkdir(parents=True)
    python.touch()
    (tmp_path / "ready.json").write_text(json.dumps({"code_revision": CODE_REVISION, "model_revision": MODEL_REVISION}))
    monkeypatch.setattr(prepare, "recipe", lambda: {"files": [{"path": "weights", "sha256": "0" * 64, "blob_id": ""}]})
    with pytest.raises(RuntimeError, match="not ready"):
        prepare.verify(tmp_path)

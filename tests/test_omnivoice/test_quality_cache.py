"""Reference cache isolation, corruption recovery and quality option contracts."""

import json
import sys
from types import SimpleNamespace

import pytest

from videocaptioner.core.tts.omnivoice.config import OmniVoiceOptions
from videocaptioner.core.tts.omnivoice.prompt_cache import PromptCache


@pytest.fixture(scope="session")
def retained_application():
    from PyQt5.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


def test_cached_prompt_validates_shape_range_and_safe_fields(tmp_path, monkeypatch):
    from videocaptioner.resources.omnivoice.worker import load_prompt

    monkeypatch.setitem(sys.modules, "omnivoice.models.omnivoice", SimpleNamespace(VoiceClonePrompt=SimpleNamespace))
    torch = SimpleNamespace(long="long", tensor=lambda value, **kw: value)
    path = tmp_path / "prompt.json"
    value = dict(schema="omnivoice-tokens-v1", tokens=[[1, 2]] * 8, text="Lời mẫu.", rms=0.1)
    path.write_text(json.dumps(value), encoding="utf-8")
    restored = load_prompt(path, torch)
    assert restored.ref_audio_tokens == value["tokens"]
    assert restored.ref_text == value["text"] and restored.ref_rms == value["rms"]
    for key, invalid in (("tokens", [[1, 2]] * 7), ("tokens", [[-1, 2]] * 8),
        ("tokens", [[1, 2]] * 7 + [[1]]), ("rms", float("nan")), ("text", ""), ("schema", "old")):
        path.write_text(json.dumps({**value, key: invalid}), encoding="utf-8")
        with pytest.raises(ValueError):
            load_prompt(path, torch)


def test_presets_keep_baseline_and_explicit_steps():
    assert OmniVoiceOptions().effective_steps == 32
    assert OmniVoiceOptions(quality_preset="more-steps").effective_steps == 64
    assert OmniVoiceOptions(steps=16).effective_steps == 16
    with pytest.raises(ValueError):
        OmniVoiceOptions(quality_preset="unmeasured")
    with pytest.raises(ValueError):
        OmniVoiceOptions(seed=-1)


def test_prompt_cache_roundtrip_corruption_and_identity(tmp_path):
    identity = dict(audio="a", text="b", model="c", tokenizer="d", worker="e", preprocess=True)
    source, restored = tmp_path / "fresh.json", tmp_path / "restored.json"
    source.write_text(json.dumps({"tokens": [[1, 2]], "text": "Lời mẫu", "rms": 0.1}), encoding="utf-8")
    cache = PromptCache(identity)
    assert cache.store(source) and cache.restore(restored)
    assert json.loads(source.read_text(encoding="utf-8")) == json.loads(restored.read_text(encoding="utf-8"))
    for key in identity:
        assert not PromptCache({**identity, key: "changed"}).restore(restored)
    cache.path.write_text("broken", encoding="utf-8")
    assert not cache.restore(restored)
    assert cache.store(source)
    entry = json.loads(cache.path.read_text(encoding="utf-8"))
    entry["prompt"]["tokens"][0][0] += 1
    cache.path.write_text(json.dumps(entry), encoding="utf-8")
    assert not cache.restore(restored)


def test_quality_selection_roundtrip_to_gui_and_cli(retained_application):
    from videocaptioner.cli.commands.dub import build_dubbing_config
    from videocaptioner.ui.common.config import cfg
    from videocaptioner.ui.components.omnivoice_panel import OmniVoicePanel
    from videocaptioner.ui.task_factory import TaskFactory

    app = retained_application
    old = cfg.omnivoice_quality_preset.value
    old_provider = cfg.dubbing_tts_provider.value
    old_enabled = cfg.dubbing_enabled.value
    old_batch = cfg.omnivoice_batch_size.value
    old_pitch, old_pause = cfg.omnivoice_pitch.value, cfg.omnivoice_pause_ms.value
    panel = OmniVoicePanel()
    try:
        panel.quality_preset.setCurrentIndex(1)
        panel.batch_size.setCurrentIndex(2)
        panel.pitch.setValue(1.5)
        panel.pause_ms.setValue(90)
        panel.save()
        cfg.set(cfg.dubbing_tts_provider, "omnivoice-local")
        cfg.set(cfg.dubbing_enabled, True)
        assert TaskFactory.create_dubbing_config().omnivoice.effective_steps == 64
        assert TaskFactory.create_dubbing_config().omnivoice.batch_size == 4
        assert TaskFactory.create_dubbing_config().omnivoice.pitch_semitones == 1.5
        assert TaskFactory.create_dubbing_config().omnivoice.punctuation_pause_ms == 90
        config = build_dubbing_config({"dubbing": {"tts_provider": "omnivoice-local"},
            "omnivoice": {"quality_preset": "more-steps"}})
        assert config.omnivoice.effective_steps == 64
    finally:
        panel.close()
        cfg.set(cfg.omnivoice_quality_preset, old)
        cfg.set(cfg.dubbing_tts_provider, old_provider)
        cfg.set(cfg.dubbing_enabled, old_enabled)
        cfg.set(cfg.omnivoice_batch_size, old_batch)
        cfg.set(cfg.omnivoice_pitch, old_pitch)
        cfg.set(cfg.omnivoice_pause_ms, old_pause)
        app.processEvents()

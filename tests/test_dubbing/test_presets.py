"""Tests for core/dubbing/presets: provider tables shared by GUI and CLI."""

from pathlib import Path

from videocaptioner.core.dubbing import presets
from videocaptioner.core.dubbing.config import AudioMixMode, TTSProviderEnum


def test_every_combo_key_has_a_preset():
    assert set(presets.TTS_PROVIDER_KEYS) == set(presets.TTS_PROVIDER_PRESETS)
    assert presets.MANAGED_PROVIDER_KEY in presets.TTS_PROVIDER_KEYS


def test_provider_keys_accept_dash_and_underscore():
    assert presets.provider_from_key("local_ai") is TTSProviderEnum.LOCAL_AI
    assert presets.provider_from_key("local-ai") is TTSProviderEnum.LOCAL_AI
    assert presets.provider_from_key("VieNeu_Local") is TTSProviderEnum.VIENEU_LOCAL
    assert presets.provider_from_key("minimax") is TTSProviderEnum.MINIMAX
    assert presets.provider_from_key("unknown") is TTSProviderEnum.OPENAI


def test_managed_provider_detection():
    assert presets.is_managed_provider("vieneu-local")
    assert presets.is_managed_provider("vieneu_local")
    assert not presets.is_managed_provider("openai")


def test_mix_mode_keys():
    assert [presets.mix_mode_from_key(k) for k in presets.MIX_MODE_KEYS] == [
        AudioMixMode.KEEP_ORIGINAL,
        AudioMixMode.REDUCE_ORIGINAL,
        AudioMixMode.MUTE_ORIGINAL,
    ]
    assert presets.mix_mode_from_key("bogus") is AudioMixMode.REDUCE_ORIGINAL


def test_fill_provider_defaults_only_fills_blank_fields():
    preset = presets.TTS_PROVIDER_PRESETS["openai"]
    assert presets.fill_provider_defaults(preset, "", "", "") == (
        "alloy",
        "https://api.openai.com/v1",
        "tts-1",
    )
    assert presets.fill_provider_defaults(preset, " nova ", "https://mine/v1", "tts-1-hd") == (
        "nova",
        "https://mine/v1",
        "tts-1-hd",
    )
    managed = presets.TTS_PROVIDER_PRESETS["vieneu-local"]
    assert presets.fill_provider_defaults(managed, "", "", "") == ("", "", "")


def test_merged_output_path_sits_beside_video(tmp_path):
    video = tmp_path / "clips" / "talk.mkv"
    assert presets.merged_output_path(str(video)) == str(Path(video.parent) / "talk_merged.mp4")

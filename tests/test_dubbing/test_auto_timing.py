"""Auto timing guards and measured media reuse; synthetic audio is not listening acceptance."""

import json
import math
import shutil
import subprocess
import wave
from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace

import pytest

from videocaptioner.core.dubbing.auto_timing import (
    AutoTimingPlan,
    _selection,
    auto_config,
    choose_with_llm,
    evaluate,
    solve,
)
from videocaptioner.core.dubbing.cache import PersistentTTSCache
from videocaptioner.core.dubbing.config import DubbingConfig
from videocaptioner.core.dubbing.engine import DubbingEngine
from videocaptioner.core.dubbing.models import DubbingGroup
from videocaptioner.core.dubbing.orchestrator import DubbingOrchestrator
from videocaptioner.core.dubbing.review import synthesis_cache_key
from videocaptioner.core.tts import TTSConfig
from videocaptioner.core.utils.subprocess_helper import child_environment


def group(name="g1", start=0, duration=4, hard_end=None):
    return DubbingGroup(name, [name], start, start + 1, start + 1, 1,
                        "Source", "Display", "Keep all 42 names, no omissions.",
                        measured_duration=duration, hard_end_time=hard_end)


def test_solver_objective_caps_silence_and_shared_measured_policy(tmp_path):
    groups = [group("g1", 0, 5), group("g2", 3, 6), group("g3", 25, 2, 28)]
    before = deepcopy(groups)
    candidates = solve(groups, 30)
    assert candidates and groups == before
    assert candidates == tuple(sorted(candidates, key=lambda c: (-c.video_speed, c.voice_tempo)))
    assert all(1 <= c.voice_tempo <= 1.2 and .5 <= c.video_speed <= 1 and not c.measured for c in candidates)
    assert candidates[0].video_speed != .77
    chosen = candidates[0]
    rendered = [replace(g, measured_duration=g.measured_duration / chosen.voice_tempo) for g in groups]
    config = auto_config(DubbingConfig(tts_config=TTSConfig("fixture", "", "")))
    config.voice_tempo, config.video_speed = chosen.voice_tempo, chosen.video_speed
    actual = evaluate(rendered, 30 / chosen.video_speed, chosen.voice_tempo, chosen.video_speed, 2000, measured=True)
    DubbingOrchestrator(DubbingEngine())._apply_sequential_policy(rendered, config, tmp_path, actual.video_duration)
    assert [(g.playback_start_time, g.playback_end_time, g.needs_review) for g in rendered] == [
        (s.start, s.end, s.needs_review) for s in actual.slots]
    assert actual.slots[2].start >= 25 / chosen.video_speed


def test_no_feasible_hard_scene_boundary_and_no_slowdown():
    assert not solve([group(duration=50)], 5)
    assert not solve([group(duration=8, hard_end=2)], 100)
    assert not solve([group(duration=10)], 6, allow_video_slowdown=False)
    assert solve([group(duration=10)], 6)


@pytest.mark.parametrize("tempo,speed,delay", [(math.nan, 1, 2000), (1.21, 1, 2000),
    (1, .49, 2000), (1, 1.01, 2000), (True, 1, 2000), (1, 1, math.nan), (1, 1, -1)])
def test_invalid_limits(tempo, speed, delay):
    with pytest.raises(ValueError):
        evaluate([group()], 20, tempo, speed, delay)


def test_invalid_audio_and_ids():
    with pytest.raises(ValueError):
        solve([group(duration=math.nan)], 20)
    with pytest.raises(ValueError):
        solve([group(), group()], 20)


def test_strict_llm_allowlist_schema_repairs_timeout_and_cancel():
    groups = [group()]
    candidates = solve(groups, 20)
    valid = {"candidate_id": candidates[0].candidate_id, "reason": "Có số 42; chọn nhịp rõ.", "sensitive_group_ids": ["g1"]}
    for payload in ({**valid, "candidate_id": "fake"}, {**valid, "tempo": 3},
                    {**valid, "sensitive_group_ids": ["unknown"]}, {"reason": "missing"}):
        with pytest.raises(ValueError):
            _selection(json.dumps(payload), candidates, {"g1"})
    with pytest.raises(ValueError):
        _selection('{"candidate_id":"a","candidate_id":"b"}', candidates, {"g1"})
    config = DubbingConfig(rewrite_model="fixture", rewrite_api_key="secret", rewrite_api_base="https://example.test/v1")
    calls = []

    def caller(**kwargs):
        calls.append(kwargs)
        assert "secret" not in json.dumps(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="{}" if len(calls) < 3 else json.dumps(valid)))])

    result = choose_with_llm(candidates, groups, config, lambda *a: None, lambda: False, caller)
    assert result[1] == "llm" and result[3] == 3
    assert len(calls) == 3

    def timeout(**kwargs):
        raise TimeoutError("secret must never enter reason")

    fallback = choose_with_llm(candidates, groups, config, lambda *a: None, lambda: False, timeout)
    assert fallback[1] == "solver-fallback" and fallback[3] == 1 and "secret" not in fallback[2]
    with pytest.raises(RuntimeError, match="cancelled"):
        choose_with_llm(candidates, groups, config, lambda *a: None, lambda: True, timeout)


def test_missing_llm_and_invalid_schema_exhaust_budget():
    candidates = solve([group()], 20)
    result = choose_with_llm(candidates, [group()], DubbingConfig(), lambda *a: None, lambda: False)
    assert result[1] == "solver-fallback" and result[3] == 0
    result = choose_with_llm(candidates, [group()], DubbingConfig(rewrite_model="fixture"),
        lambda *a: None, lambda: False, lambda **k: SimpleNamespace(choices=[]))
    assert result[1] == "solver-fallback" and result[3] == 3


@pytest.mark.parametrize("has_audio", [False, True])
def test_real_proposal_apply_export_cache_reuse_and_stale_rejection(tmp_path, has_audio):
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        pytest.skip("FFmpeg required")
    video, subtitle = tmp_path / "source.mp4", tmp_path / "source.srt"
    command = ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=black:s=160x90:r=10:d=3"]
    if has_audio:
        command += ["-f", "lavfi", "-i", "sine=frequency=440:duration=3", "-c:a", "aac"]
    subprocess.run(command + ["-c:v", "libx264", "-pix_fmt", "yuv420p", str(video)],
                   env=child_environment(), capture_output=True, check=True)
    subtitle.write_text("1\n00:00:00,000 --> 00:00:01,000\nKeep all words.\n", encoding="utf-8")
    config = auto_config(DubbingConfig(tts_config=TTSConfig("fixture", "", "", voice="fixed"), strip_cjk=False))

    class CacheOnly:
        def synthesize(self, *a, **k):
            raise AssertionError("Auto must never generate speech")

    engine = DubbingEngine(cache_root=tmp_path / "cache", tts_provider_factory=lambda _: CacheOnly())
    review = engine.prepare_review(str(video), str(subtitle), config)
    with pytest.raises(ValueError, match="Thiếu WAV"):
        engine.propose_timing(str(video), str(subtitle), config, review, use_llm=False)
    source = tmp_path / "native.wav"
    with wave.open(str(source), "wb") as wav:
        wav.setparams((1, 2, 8000, 0, "NONE", "not compressed"))
        wav.writeframes(b"\x01\x02" * 40000)
    key = synthesis_cache_key(review.groups[0].tts_text, config)
    cache = PersistentTTSCache(engine.cache_root)
    cache.put(key, source, provider="fixture", model="fixture", voice="fixed", sample_rate=8000)
    original = (cache.root / f"{key}.wav").read_bytes()
    proposal = engine.propose_timing(str(video), str(subtitle), config, review, use_llm=False)
    assert proposal.can_apply and proposal.selected.measured and proposal.selected.video_speed < 1
    assert proposal.selected.max_delay_ms <= 2000
    config.voice_tempo, config.video_speed = proposal.selected.voice_tempo, proposal.selected.video_speed
    config.subtitle_mode = "soft"
    for name in ("preview", "export"):
        engine.dub(str(video), str(subtitle), str(tmp_path / f"{name}.mp4"), config,
                   review=review, timing_plan=proposal)
        assert engine.last_report["summary"]["total_tts_attempts"] == 0
        assert engine.last_report["summary"]["cache_hits"] == 1
        assert engine.last_report["groups"][0]["applied_speed"] == proposal.selected.voice_tempo
        assert engine.last_report["groups"][0]["measured_duration"] > 4
        assert engine.last_report["groups"][0]["playback_end_time"] == proposal.selected.slots[0].end
    assert (cache.root / f"{key}.wav").read_bytes() == original
    config.voice_tempo = 1.01
    with pytest.raises(ValueError, match="settings changed"):
        engine.dub(str(video), str(subtitle), str(tmp_path / "bad-rate.mp4"), config, review=review, timing_plan=proposal)
    config.voice_tempo = proposal.selected.voice_tempo
    changed_review = review.with_group_text(review.groups[0].group_id, "Changed speech")
    with pytest.raises(ValueError, match="Thiếu WAV"):
        engine.dub(str(video), str(subtitle), str(tmp_path / "bad-words.mp4"), config, review=changed_review, timing_plan=proposal)
    native = cache.root / f"{key}.wav"
    data = bytearray(native.read_bytes())
    data[-1] ^= 1
    native.write_bytes(data)
    with pytest.raises(ValueError, match="source/audio changed"):
        engine.dub(str(video), str(subtitle), str(tmp_path / "bad-audio.mp4"), config, review=review, timing_plan=proposal)
    assert not (tmp_path / "bad-audio.mp4").exists()
    subtitle.write_text(subtitle.read_text() + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="source mismatch"):
        engine.propose_timing(str(video), str(subtitle), config, review, use_llm=False)


def test_prediction_cannot_be_applied():
    candidate = solve([group()], 20)[0]
    proposal = AutoTimingPlan("a" * 64, (candidate,), candidate, "solver", "predicted", 2000, True)
    assert not proposal.can_apply

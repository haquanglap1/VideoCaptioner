"""Automatic Batch recovery keeps native speech and only applies measured playback."""

import json
import shutil
import subprocess
import wave
from contextlib import nullcontext
from copy import deepcopy
from types import SimpleNamespace

import pytest

from videocaptioner.core.dubbing import auto_timing
from videocaptioner.core.dubbing.cache import PersistentTTSCache
from videocaptioner.core.dubbing.config import DubbingConfig
from videocaptioner.core.dubbing.engine import DubbingEngine
from videocaptioner.core.dubbing.models import DubbingReviewRequired
from videocaptioner.core.dubbing.orchestrator import DubbingOrchestrator
from videocaptioner.core.dubbing.review import DubbingReview, synthesis_cache_key
from videocaptioner.core.llm.rate_limit import LLMRateLimitError
from videocaptioner.core.tts import TTSConfig
from videocaptioner.core.utils.subprocess_helper import child_environment


@pytest.mark.parametrize('mode', ['llm', 'timeout', 'quota', 'cancel', 'no-feasible', 'fits'])
def test_automatic_overflow_uses_existing_audio_and_measured_llm_choice(tmp_path, monkeypatch, mode):
    if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):
        pytest.skip('FFmpeg required')
    video, subtitle = tmp_path / 'source.mp4', tmp_path / 'spoken.srt'
    subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=s=160x90:r=10:d=3',
                    '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(video)],
                   env=child_environment(), capture_output=True, check=True)
    subtitle.write_text('1\n00:00:00,000 --> 00:00:01,000\nKeep all words, 42 names.\n', encoding='utf-8')
    config = auto_timing.auto_config(DubbingConfig(tts_config=TTSConfig('fixture', '', '', voice='fixed',
        response_format='wav', sample_rate=8000), strip_cjk=False, rewrite_model='fixture',
        rewrite_api_key='private-fixture', rewrite_api_base='https://example.test/v1'))
    config.subtitle_mode = 'soft'
    before = deepcopy(config)

    class CacheOnly:
        def synthesize(self, *args, **kwargs):
            raise AssertionError('Automatic timing must not synthesize again')

    engine = DubbingEngine(cache_root=tmp_path / 'cache', tts_provider_factory=lambda _: CacheOnly())
    review = engine.prepare_review(str(video), str(subtitle), config)
    text = review.groups[0].tts_text
    native = tmp_path / 'native.wav'
    duration = 12 if mode == 'no-feasible' else (1 if mode == 'fits' else 3.138)
    with wave.open(str(native), 'wb') as wav:
        wav.setparams((1, 2, 8000, 0, 'NONE', 'not compressed'))
        wav.writeframes(b'\x01\x02' * round(duration * 8000))
    cache = PersistentTTSCache(engine.cache_root)
    key = synthesis_cache_key(text, config)
    cache.put(key, native, provider='fixture', model='fixture', voice='fixed', sample_rate=8000)
    original = (cache.root / f'{key}.wav').read_bytes()
    calls = []
    stopped = [False]

    def caller(**kwargs):
        calls.append(kwargs)
        assert str(tmp_path) not in json.dumps(kwargs)
        assert 'private-fixture' not in json.dumps(kwargs)
        if mode == 'timeout':
            raise TimeoutError('Fixture')
        if mode == 'quota':
            raise LLMRateLimitError('quota')
        if mode == 'cancel':
            stopped[0] = True
            raise TimeoutError('Cancelled')
        payload = json.loads(kwargs['messages'][1]['content'])
        assert payload['groups'][0]['text'] == text
        result = {'candidate_id': payload['candidates'][0]['candidate_id'],
                  'reason': 'Keep every word.', 'sensitive_group_ids': []}
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(result)))])

    monkeypatch.setattr(auto_timing, 'OwnedLLMRequest', lambda *a, **k: caller)
    output = tmp_path / 'result.mp4'
    if mode != 'fits':
        with pytest.raises(DubbingReviewRequired):
            engine.dub(str(video), str(subtitle), str(output), config)
        assert not calls and not output.exists()
    errors = {'quota': LLMRateLimitError, 'cancel': RuntimeError, 'no-feasible': DubbingReviewRequired}
    if mode in errors:
        with pytest.raises(errors[mode]):
            engine.dub(str(video), str(subtitle), str(output), config,
                       auto_timing_on_overflow=True, cancelled=lambda: stopped[0])
        assert not output.exists()
        assert engine.last_review.groups[0].tts_text == text
        assert len(calls) == (0 if mode == 'no-feasible' else 1)
    else:
        engine.dub(str(video), str(subtitle), str(output), config, auto_timing_on_overflow=True)
        assert output.is_file()
        report = engine.last_report
        assert report['summary']['total_tts_attempts'] == 0
        assert report['summary']['cache_hits'] == 1
        assert report['groups'][0]['tts_text'] == text
        assert not report['groups'][0]['needs_review']
        assert 1 <= report['voice_tempo'] <= 1.2 and .5 <= report['video_speed'] <= 1
        assert len(calls) == (0 if mode == 'fits' else 1)
        decoded = subprocess.run(['ffmpeg', '-v', 'error', '-i', str(output), '-f', 'null', '-'],
                                 env=child_environment(), capture_output=True)
        assert decoded.returncode == 0 and not decoded.stderr
    assert config == before
    assert (cache.root / f'{key}.wav').read_bytes() == original


def test_automatic_recovery_has_one_budget_when_measured_export_still_fails(monkeypatch):
    config = auto_timing.auto_config(DubbingConfig(tts_config=TTSConfig('fixture', '', '')))
    engine = DubbingEngine()
    failed = SimpleNamespace(needs_review=True, measured_duration=3.138, fit_status='needs-review',
                             playback_start_time=0, playback_end_time=3.138)
    review = SimpleNamespace(groups=[failed], can_resume=True, to_dict=lambda: {})
    calls, proposals = [], []

    def run(*args, **kwargs):
        calls.append(kwargs)
        engine.last_review = review
        raise DubbingReviewRequired(reason='Measured export still overflows')

    def propose(*args, **kwargs):
        proposals.append(kwargs)
        return SimpleNamespace(can_apply=True, decision_source='solver',
                               selected=SimpleNamespace(voice_tempo=1.0, video_speed=.9))

    monkeypatch.setattr(engine, '_managed_runtime_context', lambda *a: nullcontext())
    monkeypatch.setattr(DubbingReview, 'from_report', lambda _: review)
    monkeypatch.setattr(engine, 'propose_timing', propose)
    monkeypatch.setattr(DubbingOrchestrator, 'run', run)
    with pytest.raises(DubbingReviewRequired, match='Measured export still overflows'):
        engine.dub('fixture.mp4', 'fixture.srt', 'output.mp4', config, auto_timing_on_overflow=True)
    assert len(calls) == 2 and len(proposals) == 1
    assert calls[1]['timing_plan'] is not None


@pytest.mark.parametrize('mode', ['hard', 'soft-resize', 'resize'])
def test_fractional_playback_export_preserves_frame_timestamps(tmp_path, monkeypatch, mode):
    if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):
        pytest.skip('FFmpeg required')
    from videocaptioner.core.dubbing.playback import render_captions, resize_video, retime_video
    monkeypatch.setattr('videocaptioner.core.utils.video_utils.check_cuda_available', lambda: False)
    source, output = tmp_path / 'source.mp4', tmp_path / 'output.mp4'
    subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=s=256x144:r=30:d=5',
                    '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(source)],
                   env=child_environment(), capture_output=True, check=True)
    retimed = retime_video(str(source), tmp_path / 'retimed.mp4', .73, lambda *a: None)
    caption = tmp_path / 'caption.srt'
    caption.write_text('1\n00:00:00,000 --> 00:00:04,000\nKeep all frames.\n', encoding='utf-8')
    config = DubbingConfig(subtitle_mode='hard' if mode == 'hard' else 'soft', output_resolution=720)
    if mode == 'resize':
        resize_video(retimed, output, config.output_resolution, lambda *a: None)
    else:
        render_captions(retimed, output, caption, config, lambda *a: None)

    def timestamps(path):
        result = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_packets',
                                 '-show_entries', 'packet=pts_time', '-of', 'json', str(path)],
                                env=child_environment(), capture_output=True, check=True)
        return sorted(float(p['pts_time']) for p in json.loads(result.stdout)['packets'])

    before, after = timestamps(retimed), timestamps(output)
    assert len(before) == len(after) == 150
    assert len(set(after)) == len(after)
    assert max(abs(a - b) for a, b in zip(before, after)) < .001

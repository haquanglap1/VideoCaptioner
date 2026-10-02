"""Standalone spoken text export using measured dubbing and the Editor's SRT adapter."""

import math
import shutil
import wave
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from videocaptioner.core.dubbing.cache import PersistentTTSCache
from videocaptioner.core.dubbing.config import TTSProviderEnum
from videocaptioner.core.dubbing.engine import DubbingEngine
from videocaptioner.core.dubbing.models import DubbingFitStatus, DubbingGroup
from videocaptioner.core.dubbing.orchestrator import DubbingOrchestrator
from videocaptioner.core.dubbing.scheduling import sequential_slots
from videocaptioner.core.editor.adapters import project_to_tts_asr
from videocaptioner.core.editor.models import EditorCue, EditorProject, stable_cue_id


@dataclass(frozen=True)
class TextAudioResult:
    audio_path: str
    subtitle_path: str
    parts_directory: str
    segments: int
    duration_ms: int


def export_text_audio(text, output_path, config, callback=None, *, engine=None) -> TextAudioResult:
    """Each nonempty line is a whole cue; never shorten speech to an invented video window."""
    callback = callback or (lambda *_: None)
    if config.tts_provider != TTSProviderEnum.OMNIVOICE_LOCAL or not config.tts_config:
        raise ValueError("Text/audio export requires OmniVoice configuration")
    if config.tts_config.speed != 1:
        raise ValueError("Text/audio export keeps full speech at speed1")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines or len(lines) > 1000 or len(text) > 50000:
        raise ValueError("Nhập 1–1000 dòng, tối đa 50.000 ký tự.")
    target = Path(output_path)
    subtitle = target.with_suffix(".srt")
    if target.suffix.lower() != ".wav" or target.exists() or subtitle.exists():
        raise ValueError("Chọn tên WAV và SRT mới; không ghi đè file đã có.")
    target.parent.mkdir(parents=True, exist_ok=True)
    parts = target.parent / (target.stem + "-parts-" + uuid4().hex[:8])
    parts.mkdir()
    (parts / "approved.txt").write_text(text, encoding="utf-8")
    engine = engine or DubbingEngine()
    orchestration = DubbingOrchestrator(engine)
    groups = [DubbingGroup(f"line-{i+1}", [i+1], 0, 1, 1, 1, line, line, line) for i, line in enumerate(lines)]
    with engine._managed_runtime_context(config, callback):
        cache = PersistentTTSCache(engine.cache_root, enabled=config.cache_enabled)
        provider = engine._create_tts_provider(config)
        orchestration._resolve_cache_hits(groups, config, cache)
        for group in groups:
            if group.audio_path:
                copied = parts / (group.group_id + ".wav")
                shutil.copyfile(group.audio_path, copied)
                group.audio_path = str(copied)
        orchestration._synthesize_missing_groups(groups, config, provider, cache, parts, callback)
        orchestration._measure_groups(groups)
    if any(g.fit_status == DubbingFitStatus.FAILED or not g.audio_path for g in groups):
        raise RuntimeError(f"Chưa đủ audio; các đoạn đã tạo được giữ trong {parts}")
    duration = sum(g.measured_duration for g in groups) + 0.08 * (len(groups) - 1)
    # There is no pre-existing video/subtitle deadline. Use native sequential slot positions unchanged.
    slots = sequential_slots(groups, video_duration=duration + 0.001, max_speed=1, max_delay=10, gap=0.08)
    cues = []
    staged_audio = parts / "complete.wav"
    frames = 0
    with wave.open(str(staged_audio), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(24000)
        for index, (group, slot) in enumerate(zip(groups, slots)):
            callback(85, "Đang ghép đủ audio và căn SRT theo WAV đã đo...")
            start_frame = round(slot.start * 24000)
            if start_frame < frames:
                raise RuntimeError("Unexpected overlap in measured speech")
            output.writeframes(b"\0\0" * (start_frame - frames))
            frames = start_frame
            with wave.open(group.audio_path, "rb") as source:
                if (source.getframerate(), source.getnchannels(), source.getsampwidth()) != (24000, 1, 2):
                    raise RuntimeError("Unexpected speech WAV format")
                expected = source.getnframes()
                copied = 0
                while data := source.readframes(24000):
                    callback(88, "Đang ghép audio...")
                    copied += len(data) // 2
                    output.writeframes(data)
                if copied != expected:
                    raise RuntimeError("Truncated speech WAV; no partial export")
            frames += copied
            start_ms, end_ms = round(start_frame / 24), round(frames / 24)
            cue_id = stable_cue_id(index, start_ms, end_ms, group.tts_text)
            cues.append(EditorCue(cue_id, start_ms, end_ms, group.source_text, group.subtitle_text, group.tts_text))
    project = EditorProject("speech-" + uuid4().hex, target.stem, "", "", math.ceil(frames / 24), cues=cues)
    staged_subtitle = parts / "complete.srt"
    staged_subtitle.write_text(project_to_tts_asr(project).to_srt(), encoding="utf-8")
    callback(95, "Đang lưu WAV và SRT...")
    # Exclusive creation also rejects a target that appeared while synthesis was running.
    for source, destination in ((staged_audio, target), (staged_subtitle, subtitle)):
        with source.open("rb") as stream, destination.open("xb") as saved:
            shutil.copyfileobj(stream, saved)
    return TextAudioResult(str(target), str(subtitle), str(parts), len(cues), project.duration_ms)

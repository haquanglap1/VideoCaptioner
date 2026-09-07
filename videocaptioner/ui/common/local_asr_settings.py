"""Snapshot local options without touching runtime, disk or network."""

from videocaptioner.core.asr.local.profiles import LocalASRConfig
from videocaptioner.core.entities import TranscribeModelEnum
from videocaptioner.ui.common.config import cfg


def local_config() -> LocalASRConfig:
    # Hidden provider controls retain preferences, but must not affect another engine's job.
    supports_diarization = cfg.transcribe_model.value in (TranscribeModelEnum.QWEN_LOCAL, TranscribeModelEnum.WHISPER_API)
    return LocalASRConfig(model=cfg.local_asr_model.value, diarize=cfg.local_asr_diarize.value and supports_diarization,
                          chunk_ms=cfg.local_asr_chunk.value, timeout=cfg.local_asr_timeout.value,
                          runtime_root=cfg.local_asr_root.value, diarization_root=cfg.local_diarization_root.value)

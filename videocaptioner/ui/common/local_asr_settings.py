"""Snapshot local options without touching runtime, disk or network."""

from videocaptioner.core.asr.local.profiles import LocalASRConfig
from videocaptioner.ui.common.config import cfg


def local_config() -> LocalASRConfig:
    return LocalASRConfig(model=cfg.local_asr_model.value, diarize=cfg.local_asr_diarize.value,
                          chunk_ms=cfg.local_asr_chunk.value, timeout=cfg.local_asr_timeout.value,
                          runtime_root=cfg.local_asr_root.value, diarization_root=cfg.local_diarization_root.value)

"""Resource admission for concurrent video stages, independent of Qt."""

from dataclasses import dataclass
from enum import Enum

from videocaptioner.core.asr.api_profiles import resolve_profile
from videocaptioner.core.entities import TranscribeConfig, TranscribeModelEnum


class BatchStage(str, Enum):
    ASR = "asr"
    SUBTITLE = "subtitle"
    DUBBING = "dubbing"
    SYNTHESIS = "synthesis"


@dataclass(frozen=True)
class BatchLimits:
    videos: int = 3
    asr: int = 2
    subtitle: int = 3
    dubbing: int = 2
    synthesis: int = 1
    gpu: int = 1

    def __post_init__(self):
        if any(not 1 <= value <= 8 for value in vars(self).values()):
            raise ValueError("Batch concurrency must be between 1 and 8")
        if self.gpu not in (1, 2):
            raise ValueError("GPU concurrency must be 1 or 2")


class BatchAdmission:
    def __init__(self, limits: BatchLimits):
        self.limits = limits
        self.active: dict[str, tuple[BatchStage, bool]] = {}
        self.exclusive: set[str] = set()

    def waiting_for(self, job: str, stage: BatchStage, gpu: bool, exclusive=False) -> str:
        if job in self.active:
            return "stage"
        gpu_jobs = sum(uses_gpu for _, uses_gpu in self.active.values())
        if gpu and (gpu_jobs >= self.limits.gpu or (gpu_jobs and (exclusive or self.exclusive))):
            return "gpu"
        if sum(kind == stage for kind, _ in self.active.values()) >= getattr(self.limits, stage.value):
            return "stage"
        return ""

    def acquire(self, job: str, stage: BatchStage, gpu: bool, exclusive=False) -> bool:
        if self.waiting_for(job, stage, gpu, exclusive):
            return False
        self.active[job] = stage, gpu
        if gpu and exclusive:
            self.exclusive.add(job)
        return True

    def release(self, job: str):
        self.active.pop(job, None)
        self.exclusive.discard(job)


def asr_uses_gpu(config: TranscribeConfig) -> bool:
    # Local diarization and source separation may use GPU even with cloud ASR.
    if config.local_asr and config.local_asr.diarize:
        return True
    if config.transcribe_model in (TranscribeModelEnum.QWEN_LOCAL, TranscribeModelEnum.WHISPER_CPP):
        return True
    if config.transcribe_model == TranscribeModelEnum.WHISPER_API:
        # Text-only API profiles use a local forced aligner for subtitle timing.
        return not resolve_profile(config.whisper_api_model or "whisper-1", config.whisper_api_request_profile,
                                   config.whisper_api_provider).timestamp_levels
    return config.transcribe_model == TranscribeModelEnum.FASTER_WHISPER and (
        config.faster_whisper_device != "cpu" or config.faster_whisper_ff_mdx_kim2)

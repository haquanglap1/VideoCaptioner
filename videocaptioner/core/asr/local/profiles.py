"""Pinned S5 models and explicit local configuration; no heavyweight imports."""

from dataclasses import dataclass


@dataclass(frozen=True)
class LocalModel:
    id: str
    repository: str
    revision: str
    runtime: str
    license: str
    gated: bool = False


MODELS = {
    "qwen-1.7b": LocalModel("qwen-1.7b", "Qwen/Qwen3-ASR-1.7B",
                           "7278e1e70fe206f11671096ffdd38061171dd6e5", "qwen", "Apache-2.0"),
    "qwen-0.6b": LocalModel("qwen-0.6b", "Qwen/Qwen3-ASR-0.6B",
                           "5eb144179a02acc5e5ba31e748d22b0cf3e303b0", "qwen", "Apache-2.0"),
    "aligner": LocalModel("aligner", "Qwen/Qwen3-ForcedAligner-0.6B",
                         "c7cbfc2048c462b0d63a45797104fc9db3ad62b7", "qwen", "Apache-2.0"),
    "community-1": LocalModel("community-1", "pyannote/speaker-diarization-community-1",
                             "3533c8cf8e369892e6b79ff1bf80f7b0286a54ee", "diarization", "CC-BY-4.0", True),
}
PROTOCOL = "local-asr-v1"
RECOGNITION_POLICY = "qwen-text-v1"
DIARIZATION_POLICY = "overlap-conservative-model-window-v2"
# The pinned Community-1 segmentation uses 10-second windows with a 10% step.
DIARIZATION_WINDOW_MS = 10000
DIARIZATION_WINDOW_STEP_MS = 1000


@dataclass(frozen=True)
class LocalASRConfig:
    model: str = "qwen-1.7b"
    diarize: bool = False
    chunk_ms: int = 120_000
    timeout: int = 180
    runtime_root: str = ""
    diarization_root: str = ""

    def __post_init__(self):
        if self.model not in ("qwen-1.7b", "qwen-0.6b"):
            raise ValueError("Select qwen-1.7b or qwen-0.6b explicitly.")
        if type(self.diarize) is not bool:
            raise ValueError("Local diarization must be boolean.")
        if type(self.chunk_ms) is not int or not 1000 <= self.chunk_ms <= 240_000:
            raise ValueError("Local ASR chunk duration must be 1000–240000 milliseconds.")
        if type(self.timeout) is not int or not 1 <= self.timeout <= 3600:
            raise ValueError("Local stage deadline must be 1–3600 seconds.")
        if not isinstance(self.runtime_root, str) or not isinstance(self.diarization_root, str):
            raise ValueError("Invalid local runtime location.")

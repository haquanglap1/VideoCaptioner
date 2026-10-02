"""Pinned OmniVoice runtime and explicit synthesis options."""

import json
import math
import os
from dataclasses import dataclass, field
from pathlib import Path

from videocaptioner.config import ROOT_PATH, portable_models_path

POLICY = "omnivoice-local-v1"
CODE_REVISION = "08be0b4ccbac3e13e374e86fbfead4b4cac343e2"
MODEL_REVISION = "c5fdb5ccb189668d56333f77ba2629f4cd7535f4"


def resources() -> Path:
    return Path(__file__).resolve().parents[3] / "resources" / "omnivoice"


def recipe() -> dict:
    return json.loads((resources() / "recipe.json").read_text(encoding="utf-8"))


def runtime_root(explicit: str = "") -> Path:
    selected = explicit or os.environ.get("VIDEOCAPTIONER_OMNIVOICE_RUNTIME", "")
    if selected:
        return Path(selected).expanduser().resolve()
    packaged = portable_models_path(Path(ROOT_PATH))
    if packaged:
        return packaged / "omnivoice"
    from platformdirs import user_data_dir
    return Path(user_data_dir("VideoCaptioner", appauthor=False)) / "runtimes" / f"omnivoice-{CODE_REVISION[:8]}"


@dataclass(frozen=True)
class OmniVoiceOptions:
    runtime: str = ""
    reference_audio: str = ""
    reference_text: str = field(default="", repr=False)
    language: str = "vi"
    steps: int = 32
    seed: int = 0
    timeout: int = 300
    quality_preset: str = "balanced"
    batch_size: int = 1
    batch_max_chars: int = 600
    pitch_semitones: float = 0.0
    punctuation_pause_ms: int = 0

    @property
    def effective_steps(self) -> int:
        return 64 if self.quality_preset == "more-steps" else self.steps

    def __post_init__(self):
        if (type(self.pitch_semitones) not in (int, float) or not math.isfinite(self.pitch_semitones)
            or not -6 <= self.pitch_semitones <= 6):
            raise ValueError("OmniVoice pitch must be between -6 and 6 semitones")
        if type(self.punctuation_pause_ms) is not int or not 0 <= self.punctuation_pause_ms <= 500:
            raise ValueError("OmniVoice punctuation pause must be between 0 and 500 ms")
        if type(self.batch_size) is not int or self.batch_size not in (1, 2, 4):
            raise ValueError("OmniVoice batch size must be 1, 2 or 4.")
        if type(self.batch_max_chars) is not int or not 64 <= self.batch_max_chars <= 4000:
            raise ValueError("OmniVoice batch character budget must be between 64 and 4000.")
        if self.quality_preset not in ("balanced", "more-steps"):
            raise ValueError("Unknown OmniVoice quality preset")
        if type(self.seed) is not int or not 0 <= self.seed < 2**63:
            raise ValueError("OmniVoice seed must be an integer between 0 and 2**63-1.")
        if bool(self.reference_audio) != bool(self.reference_text.strip()):
            raise ValueError("OmniVoice needs both reference audio and its transcript, or neither.")
        if not isinstance(self.language, str) or not self.language.strip():
            raise ValueError("OmniVoice language is required.")
        if type(self.steps) is not int or not 1 <= self.steps <= 64:
            raise ValueError("OmniVoice steps must be between 1 and 64.")
        if type(self.timeout) is not int or not 1 <= self.timeout <= 3600:
            raise ValueError("OmniVoice timeout must be between 1 and 3600 seconds.")


def status(explicit: str = "") -> str:
    root = runtime_root(explicit)
    # Opening the panel stays cheap; only the prepare worker verifies hashes.
    return "Installed; use Prepare / resume to verify" if (root / "ready.json").is_file() else "Not prepared"

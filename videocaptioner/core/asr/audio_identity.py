"""Content identity for a whole recording, independent of file names and containers."""

import hashlib
import re
from dataclasses import asdict, dataclass
from typing import Callable

from pydub import AudioSegment

POLICY = "pcm-s16le-mono-16000-v1"
Check = Callable[[], None]


@dataclass(frozen=True)
class AudioIdentity:
    policy: str
    sha256: str
    samples: int

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict | None) -> "AudioIdentity | None":
        if value is None:
            return None
        if (not isinstance(value, dict) or set(value) != {"policy", "sha256", "samples"}
                or value["policy"] != POLICY or not isinstance(value["sha256"], str)
                or re.fullmatch(r"[0-9a-f]{64}", value["sha256"]) is None
                or type(value["samples"]) is not int or value["samples"] <= 0):
            raise ValueError("Invalid audio identity; choose the original source for review.")
        return cls(**value)


def identify_audio(audio: AudioSegment, check: Check = lambda: None) -> AudioIdentity:
    """Hash every PCM sample, including a sub-millisecond tail; never hash transcript/path."""
    if (audio.frame_rate, audio.channels, audio.sample_width) != (16000, 1, 2) or not audio.raw_data:
        raise ValueError("Audio identity requires nonempty PCM16 mono 16 kHz audio.")
    digest = hashlib.sha256()
    raw = memoryview(audio.raw_data)
    for offset in range(0, len(raw), 1024 * 1024):
        check()
        digest.update(raw[offset:offset + 1024 * 1024])
    check()
    return AudioIdentity(POLICY, digest.hexdigest(), len(raw) // 2)


def require_audio_match(expected: AudioIdentity | None, actual: AudioIdentity) -> bool:
    if expected is None:
        return False
    if expected != actual:
        raise ValueError("Audio does not match the saved recording. Select the original source; no inference or API request was made.")
    return True


def verify_audio_file(expected: AudioIdentity | None, path: str, check: Check = lambda: None) -> bool:
    from .alignment.audio import decode_audio

    return require_audio_match(expected, identify_audio(decode_audio(path, check), check))

"""Optional provenance shared by subtitles and the editor; no speaker inference."""

from dataclasses import asdict, dataclass
from typing import Literal


@dataclass(frozen=True)
class ASRMetadata:
    provider: str
    # An opaque local request scope, never a remote job ID or credential.
    scope: str
    speaker: str | None = None
    timing: Literal["native", "edited"] = "native"

    @property
    def speaker_id(self) -> str | None:
        return f"{self.provider}:{self.scope}:{self.speaker}" if self.speaker is not None else None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict | None) -> "ASRMetadata | None":
        if value is None:
            return None
        if (not isinstance(value, dict) or not isinstance(value.get("provider"), str)
                or not isinstance(value.get("scope"), str)
                or value.get("timing", "native") not in ("native", "edited")
                or (value.get("speaker") is not None and not isinstance(value["speaker"], str))):
            raise ValueError("Invalid ASR metadata; review required.")
        return cls(value["provider"], value["scope"], value.get("speaker"), value.get("timing", "native"))


@dataclass(frozen=True)
class ASRAudioEvent:
    text: str
    start_ms: int
    end_ms: int
    metadata: ASRMetadata

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict) -> "ASRAudioEvent":
        metadata = ASRMetadata.from_dict(value.get("metadata"))
        start, end = value.get("start_ms"), value.get("end_ms")
        if (metadata is None or not isinstance(value.get("text"), str)
                or type(start) is not int or type(end) is not int or start < 0 or end < start):
            raise ValueError("Invalid ASR audio event; review required.")
        return cls(value["text"], start, end, metadata)

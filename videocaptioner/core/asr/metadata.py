"""Optional provenance shared by subtitles and the editor; no speaker inference."""

from dataclasses import asdict, dataclass, field, replace
from typing import Literal


@dataclass(frozen=True)
class ASRMetadata:
    provider: str
    # An opaque local request scope, never a remote job ID or credential.
    scope: str
    speaker: str | None = None
    timing: Literal["native", "edited"] = "native"
    speaker_override: str | None = None
    token_ids: tuple[str, ...] = field(default=(), compare=False)

    def same_source(self, other: "ASRMetadata | None") -> bool:
        return other is not None and (self.provider, self.scope, self.speaker, self.speaker_override) == (
            other.provider, other.scope, other.speaker, other.speaker_override)

    def with_tokens_from(self, other: "ASRMetadata") -> "ASRMetadata":
        if not self.same_source(other):
            raise ValueError("Cannot merge different ASR provenance.")
        return replace(self, timing="edited" if "edited" in (self.timing, other.timing) else "native",
                       token_ids=tuple(dict.fromkeys((*self.token_ids, *other.token_ids))))

    @property
    def speaker_id(self) -> str | None:
        if self.speaker_override is not None:
            return self.speaker_override or None
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
        override = value.get("speaker_override")
        if override is not None and not isinstance(override, str):
            raise ValueError("Invalid speaker override.")
        tokens = value.get("token_ids", ())
        if not isinstance(tokens, (list, tuple)) or any(not isinstance(t, str) or not t for t in tokens):
            raise ValueError("Invalid ASR token association.")
        return cls(value["provider"], value["scope"], value.get("speaker"), value.get("timing", "native"), override, tuple(tokens))


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

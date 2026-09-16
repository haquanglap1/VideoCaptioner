"""Optional provenance shared by subtitles and the editor; no speaker inference."""

from dataclasses import asdict, dataclass, field, replace
from typing import Literal


@dataclass(frozen=True)
class StageProvenance:
    provider: str
    model: str
    revision: str
    policy: str

    @classmethod
    def from_dict(cls, value: dict | None) -> "StageProvenance | None":
        if value is None:
            return None
        if not isinstance(value, dict) or set(value) != {"provider", "model", "revision", "policy"}:
            raise ValueError("Invalid ASR stage provenance.")
        if any(not isinstance(v, str) for v in value.values()) or not value["provider"] or not value["model"] or not value["policy"]:
            raise ValueError("Invalid ASR stage provenance.")
        return cls(**value)


@dataclass(frozen=True)
class SpeakerAssociation:
    stage: StageProvenance
    scope: str
    status: str
    candidates: tuple[str, ...] = ()
    coverage_ppm: int = 0

    @classmethod
    def from_dict(cls, value: dict | None) -> "SpeakerAssociation | None":
        if value is None:
            return None
        try:
            raw = dict(value)
            stage = StageProvenance.from_dict(raw.pop("stage"))
            candidates = raw.pop("candidates", ())
            if not isinstance(candidates, (list, tuple)) or any(not isinstance(c, str) or not c for c in candidates):
                raise ValueError
            if stage is None:
                raise ValueError
            result = cls(stage, candidates=tuple(candidates), **raw)
            if (not isinstance(result.scope, str) or not result.scope or
                    result.status not in ("assigned", "unknown", "ambiguous", "overlap") or
                    type(result.coverage_ppm) is not int or not 0 <= result.coverage_ppm <= 1_000_000):
                raise ValueError
            return result
        except (TypeError, KeyError, ValueError):
            raise ValueError("Invalid local speaker association.") from None


@dataclass(frozen=True)
class ASRMetadata:
    provider: str
    # An opaque local request scope, never a remote job ID or credential.
    scope: str
    speaker: str | None = None
    timing: Literal["native", "edited", "aligned", "imported"] = "native"
    speaker_override: str | None = None
    token_ids: tuple[str, ...] = field(default=(), compare=False)
    recognition: StageProvenance | None = None
    alignment: StageProvenance | None = None
    diarization: SpeakerAssociation | None = None

    def same_source(self, other: "ASRMetadata | None") -> bool:
        return other is not None and (self.provider, self.scope, self.speaker, self.speaker_override,
                                       self.recognition, self.alignment, self.diarization) == (
            other.provider, other.scope, other.speaker, other.speaker_override,
            other.recognition, other.alignment, other.diarization)

    def with_tokens_from(self, other: "ASRMetadata") -> "ASRMetadata":
        if not self.same_source(other):
            raise ValueError("Cannot merge different ASR provenance.")
        if self.timing != other.timing and "edited" not in (self.timing, other.timing):
            raise ValueError("Cannot merge native and aligned timing.")
        return replace(self, timing="edited" if "edited" in (self.timing, other.timing) else self.timing,
                       token_ids=tuple(dict.fromkeys((*self.token_ids, *other.token_ids))))

    @property
    def speaker_id(self) -> str | None:
        if self.speaker_override is not None:
            return self.speaker_override or None
        if self.diarization is not None:
            return (f"{self.diarization.stage.provider}:{self.diarization.scope}:{self.speaker}"
                    if self.speaker is not None else None)
        return f"{self.provider}:{self.scope}:{self.speaker}" if self.speaker is not None else None

    def to_dict(self) -> dict:
        result = asdict(self)
        # Preserve the S3/S4.1 wire shape when the optional S5 stages are absent.
        for key in ("recognition", "alignment", "diarization"):
            if result[key] is None:
                del result[key]
        return result

    @classmethod
    def from_dict(cls, value: dict | None) -> "ASRMetadata | None":
        if value is None:
            return None
        if (not isinstance(value, dict) or not isinstance(value.get("provider"), str)
                or not isinstance(value.get("scope"), str)
                or value.get("timing", "native") not in ("native", "edited", "aligned", "imported")
                or (value.get("speaker") is not None and not isinstance(value["speaker"], str))):
            raise ValueError("Invalid ASR metadata; review required.")
        override = value.get("speaker_override")
        if override is not None and not isinstance(override, str):
            raise ValueError("Invalid speaker override.")
        tokens = value.get("token_ids", ())
        if not isinstance(tokens, (list, tuple)) or any(not isinstance(t, str) or not t for t in tokens):
            raise ValueError("Invalid ASR token association.")
        result = cls(value["provider"], value["scope"], value.get("speaker"), value.get("timing", "native"), override, tuple(tokens),
                     StageProvenance.from_dict(value.get("recognition")),
                     StageProvenance.from_dict(value.get("alignment")),
                     SpeakerAssociation.from_dict(value.get("diarization")))
        if result.timing == "aligned" and result.alignment is None:
            raise ValueError("Aligned timing requires alignment provenance.")
        if result.diarization is not None:
            assigned = result.diarization.status == "assigned"
            if (assigned != (result.speaker is not None) or
                    assigned and result.diarization.candidates != (result.speaker,)):
                raise ValueError("Invalid local speaker decision.")
        return result


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

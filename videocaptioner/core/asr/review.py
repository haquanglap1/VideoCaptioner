"""Local recognition review, separate from the cache of accepted ASR results."""

from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from uuid import uuid4

from .api_profiles import ASRAPIError
from .asr_data import ASRData
from .audio_identity import AudioIdentity
from .native_result import _timing, native_cues, parse_native

SCHEMA = "asr-review-v1"
RawTime = int | float | str | bool | None


def review_directory() -> Path:
    from videocaptioner.config import APPDATA_PATH

    return APPDATA_PATH / "asr-review"


def _raw_time(value: object) -> RawTime:
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    return value if isinstance(value, (int, float, str, bool)) or value is None else None


@dataclass(frozen=True)
class ReviewToken:
    id: str
    text: str
    start: RawTime
    end: RawTime
    speaker: str | None = None
    kind: str = "word"
    translation_status: str | None = None


@dataclass(frozen=True)
class TimingOverride:
    token_id: str
    start_ms: int
    end_ms: int
    source: str = "user"


@dataclass(frozen=True)
class TimingIssue:
    token_id: str
    index: int
    reason: str


@dataclass(frozen=True)
class NativeReview:
    provider: str
    model: str
    scope: str
    duration_ms: int
    text: str = field(repr=False)
    tokens: tuple[ReviewToken, ...] = field(repr=False)
    diarize: bool = True
    word_timing: bool = True
    language: str = ""
    overrides: tuple[TimingOverride, ...] = ()
    audio_identity: AudioIdentity | None = None

    @classmethod
    def capture(cls, response: dict, provider: str, model: str, scope: str, duration_ms: int,
                diarize: bool, word_timing: bool, language: str = "",
                audio_identity: AudioIdentity | None = None) -> NativeReview:
        """Whitelist parser data only; no endpoint, headers, IDs, media path or credentials."""
        items = response.get("tokens" if provider == "soniox" else "words")
        if not isinstance(response.get("text"), str) or not isinstance(items, list):
            raise ASRAPIError("Missing native transcript or token list; review required.")
        tokens = []
        for index, item in enumerate(items):
            if not isinstance(item, dict) or not isinstance(item.get("text"), str):
                raise ASRAPIError("Malformed native token; review required.")
            speaker = item.get("speaker" if provider == "soniox" else "speaker_id")
            kind = item.get("type", "") if provider == "scribe" else "word"
            status = item.get("translation_status") if provider == "soniox" else None
            if (speaker is not None and not isinstance(speaker, str)) or not isinstance(kind, str):
                raise ASRAPIError("Malformed native token identity; review required.")
            if status is not None and not isinstance(status, str):
                raise ASRAPIError("Malformed native translation status; review required.")
            tokens.append(ReviewToken(f"token-{index + 1:06d}", item["text"],
                                      _raw_time(item.get("start_ms" if provider == "soniox" else "start")),
                                      _raw_time(item.get("end_ms" if provider == "soniox" else "end")),
                                      speaker, kind, status))
        return cls(provider, model, scope, duration_ms, response["text"], tuple(tokens),
                   diarize, word_timing, language, audio_identity=audio_identity)

    def _item(self, token: ReviewToken) -> dict:
        override = next((o for o in self.overrides if o.token_id == token.id), None)
        scale = 1 if self.provider == "soniox" else 1000
        start = override.start_ms / scale if override else token.start
        end = override.end_ms / scale if override else token.end
        if self.provider == "soniox":
            return {"text": token.text, "start_ms": start, "end_ms": end,
                    "speaker": token.speaker, "translation_status": token.translation_status}
        return {"text": token.text, "start": start, "end": end,
                "speaker_id": token.speaker, "type": token.kind}

    def response(self) -> dict:
        return {"text": self.text, "tokens" if self.provider == "soniox" else "words":
                [self._item(token) for token in self.tokens]}

    def timing_ms(self, token: ReviewToken) -> tuple[int, int] | None:
        keys = ("start_ms", "end_ms", 1) if self.provider == "soniox" else ("start", "end", 1000)
        try:
            return _timing(self._item(token), *keys, self.duration_ms)
        except ASRAPIError:
            return None

    def issues(self) -> tuple[TimingIssue, ...]:
        issues = []
        for index, token in enumerate(self.tokens):
            if token.kind == "spacing" or token.text.isspace():
                continue
            times = self.timing_ms(token)
            if times is None:
                issues.append(TimingIssue(token.id, index, "Missing, nonfinite, negative, reversed or out-of-bounds timestamp"))
            elif times[0] == times[1] and token.kind != "audio_event" and any(c.isalnum() for c in token.text):
                issues.append(TimingIssue(token.id, index, "Zero-duration speech token"))
        return tuple(issues)

    def edit_timing(self, token_id: str, start_ms: int, end_ms: int) -> NativeReview:
        if token_id not in {t.id for t in self.tokens}:
            raise ValueError("Unknown review token ID.")
        if type(start_ms) is not int or type(end_ms) is not int or not 0 <= start_ms < end_ms <= self.duration_ms:
            raise ValueError("Use integer milliseconds with 0 <= start < end <= audio duration.")
        edits = tuple(o for o in self.overrides if o.token_id != token_id)
        return replace(self, overrides=(*edits, TimingOverride(token_id, start_ms, end_ms)))

    def resume(self) -> ASRData:
        """Validate the entire local result. Never upload, cache as native, or return a prefix."""
        if self.issues():
            raise ASRAPIError("Native timing still requires review; no subtitles were exported.")
        data = parse_native(self.response(), self.provider, self.duration_ms, self.scope, self.diarize,
                            token_ids=tuple(t.id for t in self.tokens),
                            edited_token_ids=frozenset(o.token_id for o in self.overrides))
        data.audio_identity = self.audio_identity
        return data if self.word_timing else native_cues(data)

    def to_dict(self) -> dict:
        return {"schema": SCHEMA, "recognition_sha256": self.recognition_fingerprint(), **self._payload()}

    def _payload(self) -> dict:
        raw = asdict(self)
        # An absent optional identity must retain legacy recognition checksums.
        if self.audio_identity is None:
            raw.pop("audio_identity")
        return raw

    def recognition_fingerprint(self) -> str:
        raw = self._payload()
        raw.pop("overrides")
        return hashlib.sha256(json.dumps(raw, ensure_ascii=False, sort_keys=True, allow_nan=False).encode()).hexdigest()

    @classmethod
    def from_dict(cls, data: dict) -> NativeReview:
        if isinstance(data, dict) and data.get("schema") == "local-asr-review-v1":
            from .local.review import LocalReview
            return LocalReview.from_dict(data)
        try:
            raw = dict(data)
            if raw.pop("schema") != SCHEMA:
                raise ValueError
            fingerprint = raw.pop("recognition_sha256")
            raw["audio_identity"] = AudioIdentity.from_dict(raw.get("audio_identity"))
            raw["tokens"] = tuple(ReviewToken(**t) for t in raw["tokens"])
            raw["overrides"] = tuple(TimingOverride(**o) for o in raw.get("overrides", []))
            result = cls(**raw)
            if (result.provider not in ("soniox", "scribe") or not isinstance(result.model, str)
                    or not isinstance(result.scope, str) or not result.scope
                    or type(result.duration_ms) is not int or result.duration_ms <= 0
                    or not isinstance(result.text, str) or not isinstance(result.language, str)
                    or type(result.diarize) is not bool or type(result.word_timing) is not bool):
                raise ValueError
            ids = [t.id for t in result.tokens]
            if len(set(ids)) != len(ids):
                raise ValueError
            for token in result.tokens:
                if (not isinstance(token.id, str) or not token.id or not isinstance(token.text, str)
                        or not isinstance(token.kind, str)
                        or token.speaker is not None and not isinstance(token.speaker, str)
                        or token.translation_status is not None and not isinstance(token.translation_status, str)):
                    raise ValueError
                if any(v is not None and type(v) not in (int, float, str, bool) for v in (token.start, token.end)):
                    raise ValueError
            if len({o.token_id for o in result.overrides}) != len(result.overrides):
                raise ValueError
            for edit in result.overrides:
                if edit.source != "user":
                    raise ValueError
                result.edit_timing(edit.token_id, edit.start_ms, edit.end_ms)
            if result.recognition_fingerprint() != fingerprint:
                raise ValueError
            return result
        except (ValueError, TypeError, KeyError, AttributeError):
            raise ValueError("Invalid ASR review file; no provider request was made.") from None

    def save(self, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(self.to_dict(), ensure_ascii=False, allow_nan=False, indent=2)
        name = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                             suffix=".tmp", delete=False) as handle:
                name = handle.name
                handle.write(payload)
            os.replace(name, path)
        finally:
            if name:
                Path(name).unlink(missing_ok=True)
        return path

    def save_new(self) -> Path:
        return self.save(review_directory() / f"review-{uuid4().hex}.asr-review.json")

    @classmethod
    def load(cls, path: str | Path) -> NativeReview:
        try:
            return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
        except (OSError, ValueError, TypeError):
            raise ValueError("Cannot open ASR review JSON; no provider request was made.") from None


class NativeReviewRequired(ASRAPIError):
    def __init__(self, review: NativeReview, reason: str, path: Path | None):
        self.review = review
        self.path = path
        super().__init__(reason + " Recognition retained for local ASR review; do not upload again."
                         + (" Local save failed; save the in-memory review before closing." if path is None else ""))


@dataclass
class ReviewSession:
    review: NativeReview


@dataclass
class EditReviewTimingCommand:
    session: ReviewSession
    token_id: str
    start_ms: int
    end_ms: int
    description: str = "Override ASR token timing"
    _old: NativeReview | None = field(default=None, init=False, repr=False)

    def execute(self) -> None:
        updated = self.session.review.edit_timing(self.token_id, self.start_ms, self.end_ms)
        self._old = self.session.review
        self.session.review = updated

    def undo(self) -> None:
        if self._old is not None:
            self.session.review = self._old

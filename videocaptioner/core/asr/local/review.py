"""Strict alignment review using the existing timing editor and CommandStack."""

import json
from dataclasses import dataclass

from ..alignment.contract import MODEL_REPOSITORY, MODEL_REVISION, POLICY, validate_alignment
from ..asr_data import ASRData, ASRDataSeg
from ..audio_identity import AudioIdentity
from ..metadata import ASRMetadata, StageProvenance
from ..native_result import native_cues
from ..review import NativeReview, ReviewToken, TimingIssue, TimingOverride, _raw_time
from .sentence_timing import SENTENCE_POLICIES, sentence_cues

SCHEMA = "local-asr-review-v1"


@dataclass(frozen=True)
class ReviewChunk:
    offset_ms: int
    duration_ms: int
    text: str
    token_ids: tuple[str, ...]


@dataclass(frozen=True)
class LocalReview(NativeReview):
    chunks: tuple[ReviewChunk, ...] = ()
    recognition: StageProvenance | None = None
    acoustic_rejected: tuple[str, ...] = ()
    pending_diarization: bool = False
    recognition_complete: bool = True
    alignment_policy: str = POLICY

    def _payload(self) -> dict:
        raw = super()._payload()
        if self.recognition_complete:
            raw.pop("recognition_complete")
        if self.alignment_policy == POLICY:
            raw.pop("alignment_policy")
        return raw

    @classmethod
    def capture_chunks(cls, *, stage: StageProvenance, scope: str, durations: list[tuple[int, int]],
                       texts: list[str], raw: list[list[dict]], word_timing: bool,
                       acoustic_rejected: tuple[str, ...] = (),
                       audio_identity: AudioIdentity | None = None) -> "LocalReview":
        chunks, tokens = [], []
        for index, ((offset, duration), text) in enumerate(zip(durations, texts)):
            items = raw[index] if index < len(raw) else []
            if not items and text:
                items = [{"text": text, "start_ms": None, "end_ms": None}]
            ids = []
            for item in items:
                token_id = f"token-{len(tokens) + 1:06d}"
                ids.append(token_id)
                # Raw local predictions use chunk-relative ms. Keep invalid values for review.
                def absolute(value):
                    return _raw_time(value + offset if type(value) in (int, float) else value)
                tokens.append(ReviewToken(token_id, item.get("text", ""), absolute(item.get("start_ms")),
                                          absolute(item.get("end_ms"))))
            chunks.append(ReviewChunk(offset, duration, text, tuple(ids)))
        return cls(stage.provider, stage.model, scope, sum(d for _, d in durations), "".join(texts), tuple(tokens),
                   False, word_timing, "zh", chunks=tuple(chunks), recognition=stage,
                   acoustic_rejected=acoustic_rejected, audio_identity=audio_identity)

    def timing_ms(self, token: ReviewToken) -> tuple[int, int] | None:
        edit = next((o for o in self.overrides if o.token_id == token.id), None)
        start, end = (edit.start_ms, edit.end_ms) if edit else (token.start, token.end)
        if type(start) is not int or type(end) is not int or not 0 <= start < end <= self.duration_ms:
            return None
        return start, end

    def issues(self) -> tuple[TimingIssue, ...]:
        issues = []
        if not self.recognition_complete:
            issues.append(TimingIssue("", 0, "Recognition is incomplete; timing edits cannot recover missing speech text"))
        previous = 0
        edited = {o.token_id for o in self.overrides}
        if self.alignment_policy in SENTENCE_POLICIES:
            for chunk in self.chunks:
                try:
                    sentence_cues(chunk.text, self._sentence_items(chunk), chunk.duration_ms, policy=self.alignment_policy)
                except ValueError as exc:
                    issues.append(TimingIssue(chunk.token_ids[0] if chunk.token_ids else "", 0, str(exc)))
        for index, token in enumerate(self.tokens):
            timing = self.timing_ms(token)
            if self.alignment_policy not in SENTENCE_POLICIES:
                if timing is None:
                    issues.append(TimingIssue(token.id, index, "Invalid or missing alignment timing"))
                elif timing[0] < previous:
                    issues.append(TimingIssue(token.id, index, "Overlapping alignment timing"))
            if timing:
                previous = timing[1]
            if token.id in self.acoustic_rejected and token.id not in edited:
                issues.append(TimingIssue(token.id, index, "Acoustic support requires user review and measured timing override"))
        return tuple(issues)

    def _sentence_items(self, chunk: ReviewChunk) -> list[dict]:
        by_id = {t.id: t for t in self.tokens}
        edits = {o.token_id: o for o in self.overrides}
        items = []
        for token_id in chunk.token_ids:
            token = by_id[token_id]
            edit = edits.get(token_id)
            start, end = (edit.start_ms, edit.end_ms) if edit else (token.start, token.end)
            items.append({"text": token.text,
                          "start_ms": start - chunk.offset_ms if type(start) is int else start,
                          "end_ms": end - chunk.offset_ms if type(end) is int else end})
        return items

    def resume(self) -> ASRData:
        if self.issues():
            raise ValueError("Local alignment still requires review; no subtitles were exported.")
        by_id = {t.id: t for t in self.tokens}
        edited = {o.token_id for o in self.overrides}
        alignment = StageProvenance("qwen-aligner", MODEL_REPOSITORY, MODEL_REVISION, self.alignment_policy)
        cues, boundary = [], 0
        for chunk in self.chunks:
            if chunk.offset_ms != boundary:
                raise ValueError("Incomplete local review audio coverage.")
            if self.alignment_policy in SENTENCE_POLICIES:
                for cue in sentence_cues(chunk.text, self._sentence_items(chunk), chunk.duration_ms, policy=self.alignment_policy):
                    ids = chunk.token_ids[cue.first_token:cue.stop_token]
                    metadata = ASRMetadata(self.provider, self.scope, timing="edited" if edited.intersection(ids) else "aligned",
                                           token_ids=ids, recognition=self.recognition, alignment=alignment)
                    cues.append(ASRDataSeg(cue.span.text, cue.span.start_ms + chunk.offset_ms,
                                          cue.span.end_ms + chunk.offset_ms, metadata=metadata,
                                          cue_id=f"{self.provider}:{self.scope}:{ids[0]}"))
                boundary += chunk.duration_ms
                continue
            items = []
            for token_id in chunk.token_ids:
                token = by_id[token_id]
                times = self.timing_ms(token)
                if times is None:
                    raise ValueError("Missing timing.")
                items.append({"text": token.text, "start_ms": times[0] - chunk.offset_ms,
                              "end_ms": times[1] - chunk.offset_ms})
            result = validate_alignment(chunk.text, items, chunk.duration_ms, chunk.offset_ms)
            for token_id, span in zip(chunk.token_ids, result.spans):
                metadata = ASRMetadata(self.provider, self.scope, timing="edited" if token_id in edited else "aligned",
                                       token_ids=(token_id,), recognition=self.recognition, alignment=alignment)
                cues.append(ASRDataSeg(span.text, span.start_ms + chunk.offset_ms, span.end_ms + chunk.offset_ms,
                                       metadata=metadata, cue_id=f"{self.provider}:{self.scope}:{token_id}"))
            boundary += chunk.duration_ms
        if boundary != self.duration_ms:
            raise ValueError("Incomplete local review audio coverage.")
        data = ASRData(cues, audio_identity=self.audio_identity, pending_diarization=self.pending_diarization)
        return data if self.word_timing or self.alignment_policy in SENTENCE_POLICIES else native_cues(data)

    def to_dict(self) -> dict:
        return {"schema": SCHEMA, "recognition_sha256": self.recognition_fingerprint(), **self._payload()}

    @classmethod
    def from_dict(cls, data: dict) -> "LocalReview":
        try:
            raw = dict(data)
            if raw.pop("schema") != SCHEMA:
                raise ValueError
            fingerprint = raw.pop("recognition_sha256")
            raw["audio_identity"] = AudioIdentity.from_dict(raw.get("audio_identity"))
            raw["recognition"] = StageProvenance.from_dict(raw["recognition"])
            raw["tokens"] = tuple(ReviewToken(**t) for t in raw["tokens"])
            raw["chunks"] = tuple(ReviewChunk(c["offset_ms"], c["duration_ms"], c["text"], tuple(c["token_ids"])) for c in raw["chunks"])
            raw["overrides"] = tuple(TimingOverride(**o) for o in raw.get("overrides", []))
            raw["acoustic_rejected"] = tuple(raw.get("acoustic_rejected", ()))
            result = cls(**raw)
            if (result.recognition is None or result.provider != result.recognition.provider or
                    result.model != result.recognition.model or not isinstance(result.scope, str) or not result.scope or
                    type(result.word_timing) is not bool or result.diarize is not False or result.language != "zh" or
                    type(result.pending_diarization) is not bool or
                    type(result.recognition_complete) is not bool or
                    result.alignment_policy not in (POLICY, *SENTENCE_POLICIES) or
                    (result.alignment_policy in SENTENCE_POLICIES and result.word_timing) or
                    type(result.duration_ms) is not int or result.duration_ms <= 0):
                raise ValueError
            ids = [t.id for t in result.tokens]
            if len(set(ids)) != len(ids) or any(not isinstance(t.id, str) or not t.id or not isinstance(t.text, str) for t in result.tokens):
                raise ValueError
            if any(t.kind != "word" or t.speaker is not None or t.translation_status is not None for t in result.tokens):
                raise ValueError
            for token in result.tokens:
                if any(v is not None and type(v) not in (int, float, str, bool) for v in (token.start, token.end)):
                    raise ValueError
            boundary, associated = 0, []
            for chunk in result.chunks:
                if (type(chunk.offset_ms) is not int or chunk.offset_ms != boundary or
                        type(chunk.duration_ms) is not int or not 0 < chunk.duration_ms <= 240_000 or not isinstance(chunk.text, str)):
                    raise ValueError
                associated.extend(chunk.token_ids)
                boundary += chunk.duration_ms
            if associated != ids or boundary != result.duration_ms or "".join(c.text for c in result.chunks) != result.text:
                raise ValueError
            if not set(result.acoustic_rejected).issubset(ids) or len({o.token_id for o in result.overrides}) != len(result.overrides):
                raise ValueError
            for edit in result.overrides:
                if edit.source != "user":
                    raise ValueError
                result.edit_timing(edit.token_id, edit.start_ms, edit.end_ms)
            if result.recognition_fingerprint() != fingerprint:
                raise ValueError
            json.dumps(result.to_dict(), allow_nan=False)
            return result
        except (ValueError, TypeError, KeyError, AttributeError):
            raise ValueError("Invalid local ASR review file; no model was called.") from None

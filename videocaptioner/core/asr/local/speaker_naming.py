"""Name diarized speaker clusters with one LLM request; cues keep their anonymous labels.

Only transcript text, anonymous labels, line counts and the user's background block leave the
machine: never audio, file paths or credentials. The reply is a strict JSON contract that is
validated before anything is written. One explicit retry; after that the subtitles stay unnamed.
Qt-independent: the GUI and the CLI both call :func:`name_speakers` and :func:`apply_decisions`.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass, field, replace
from typing import Any, Callable, Mapping, Sequence

from videocaptioner.core.llm.client import LLMCredentials
from videocaptioner.core.llm.request_policy import validate_request_timeout
from videocaptioner.core.prompts import get_prompt
from videocaptioner.core.translate.conversation import (
    Character,
    Evidence,
    SpeakerMapping,
)

from ..asr_data import ASRData
from ..metadata import MAX_NAMING_EVIDENCE, SpeakerNaming, SpeakerProfile

PROMPT_PATH = "asr/speaker_naming"
AUTO_CONFIRM_CONFIDENCE = 0.8
MAX_TRANSCRIPT_CHARS = 20_000
MAX_CLUSTERS = 40
MISSING_CLUSTER_LINES = 3
MAX_LINE_CHARS = 400
MAX_LABEL_CHARS = 40
MAX_REPLY_CHARS = 256 * 1024
# Reasoning models spend completion tokens before the JSON; leave headroom per cluster.
COMPLETION_BASE, COMPLETION_PER_CLUSTER, COMPLETION_MAX = 2000, 200, 12000
UNKNOWN_LABEL = "?"
REPLY_KEYS = frozenset({"label", "name", "role", "gender", "age_group", "confidence", "evidence_cue_ids"})
Check = Callable[[], None]


class SpeakerNamingError(ValueError):
    """Unusable input or an invalid reply; the diarized subtitles are kept unchanged."""


def prompt_text() -> str:
    return get_prompt(PROMPT_PATH)


def prompt_sha256() -> str:
    return hashlib.sha256(prompt_text().encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class SpeakerNamingSettings:
    """Job snapshot of the LLM to ask; credentials never reach documents or child processes."""

    credentials: LLMCredentials = field(repr=False)
    model: str = ""
    timeout: int = 120
    context_notes: str = ""

    def __post_init__(self) -> None:
        validate_request_timeout(self.timeout)
        if not self.credentials.is_complete or not isinstance(self.model, str) or not self.model.strip():
            raise SpeakerNamingError("Configure the LLM service, model and API key before naming speakers.")
        if not isinstance(self.context_notes, str):
            raise SpeakerNamingError("Context notes must be text.")
        object.__setattr__(self, "model", self.model.strip())


@dataclass(frozen=True)
class SpeakerCluster:
    speaker_id: str
    label: str
    cue_ids: tuple[str, ...]


@dataclass(frozen=True)
class TranscriptLine:
    number: int
    cue_id: str
    label: str
    text: str


def _one_line(value: str, limit: int) -> str:
    text = " ".join(value.replace("\r", "\n").split())
    text = "".join(c for c in text if ord(c) >= 32 and c != "|")
    return text[:limit]


def speaker_clusters(data: ASRData) -> tuple[SpeakerCluster, ...]:
    """Assigned anonymous speakers in order of first appearance. User overrides are already named."""
    cues: dict[str, list[str]] = {}
    raw_labels: dict[str, str] = {}
    for seg in data.segments:
        meta = seg.metadata
        if meta is None or meta.speaker is None or meta.speaker_override is not None:
            continue
        speaker_id = meta.speaker_id
        if speaker_id is None:
            continue
        cues.setdefault(speaker_id, []).append(seg.cue_id)
        raw_labels.setdefault(speaker_id, meta.speaker)
    clusters = []
    used: Counter[str] = Counter()
    for index, (speaker_id, cue_ids) in enumerate(cues.items()):
        label = _one_line(raw_labels[speaker_id], MAX_LABEL_CHARS)
        if label.isdecimal():
            label = f"SPEAKER_{label}"
        if not label or label == UNKNOWN_LABEL:
            label = f"SPEAKER_{index}"
        used[label] += 1
        if used[label] > 1:
            # Two scopes can reuse a raw label; the prompt needs one tag per cluster.
            label = f"{label}#{used[label]}"
        clusters.append(SpeakerCluster(speaker_id, label, tuple(cue_ids)))
    return tuple(clusters)


def transcript_lines(data: ASRData, clusters: Sequence[SpeakerCluster]) -> tuple[TranscriptLine, ...]:
    labels = {c.speaker_id: c.label for c in clusters}
    lines = []
    for number, seg in enumerate(data.segments, 1):
        meta = seg.metadata
        if meta is None or meta.speaker_id is None:
            label = UNKNOWN_LABEL
        elif meta.speaker_override is not None:
            label = _one_line(meta.speaker_override, MAX_LABEL_CHARS) or UNKNOWN_LABEL
        else:
            label = labels.get(meta.speaker_id, UNKNOWN_LABEL)
        lines.append(TranscriptLine(number, seg.cue_id, label, _one_line(seg.text, MAX_LINE_CHARS)))
    return tuple(lines)


def _line_cost(line: TranscriptLine) -> int:
    return len(line.text) + len(line.label) + 10


def sample_lines(lines: Sequence[TranscriptLine], clusters: Sequence[SpeakerCluster],
                 limit: int = MAX_TRANSCRIPT_CHARS) -> tuple[tuple[TranscriptLine, ...], bool]:
    """Head, middle and tail within the budget, plus a few lines of any cluster left out."""
    if sum(_line_cost(line) for line in lines) <= limit:
        return tuple(lines), False
    budget = limit // 3
    chosen: set[int] = set()

    def take(start: int, step: int) -> None:
        spent, index = 0, start
        while 0 <= index < len(lines) and spent + _line_cost(lines[index]) <= budget:
            chosen.add(index)
            spent += _line_cost(lines[index])
            index += step

    take(0, 1)
    take(len(lines) - 1, -1)
    middle = len(lines) // 2
    spent, left, right = 0, middle, middle + 1
    while (left >= 0 or right < len(lines)) and spent < budget:
        for index in (left, right):
            if 0 <= index < len(lines) and spent + _line_cost(lines[index]) <= budget:
                chosen.add(index)
                spent += _line_cost(lines[index])
        left, right = left - 1, right + 1
    by_cue = {line.cue_id: index for index, line in enumerate(lines)}
    for cluster in clusters:
        if not any(lines[i].label == cluster.label for i in chosen):
            chosen.update(by_cue[c] for c in cluster.cue_ids[:MISSING_CLUSTER_LINES] if c in by_cue)
    return tuple(lines[i] for i in sorted(chosen)), True


def render_transcript(lines: Sequence[TranscriptLine], total: int) -> str:
    rendered, previous = [], 0
    for line in lines:
        if line.number != previous + 1:
            rendered.append("...")
        rendered.append(f"{line.number} | {line.label} | {line.text}")
        previous = line.number
    if previous < total:
        rendered.append("...")
    return "\n".join(rendered)


def naming_messages(data: ASRData, clusters: Sequence[SpeakerCluster],
                    context_notes: str = "") -> tuple[list[dict], tuple[TranscriptLine, ...], bool]:
    """Chat messages for one request; returns the numbered lines the reply may cite."""
    lines = transcript_lines(data, clusters)
    sample, sampled = sample_lines(lines, clusters)
    parts = []
    notes = context_notes.strip()
    if notes:
        parts.append(notes)
    parts.append("CLUSTERS:\n" + "\n".join(f"{c.label}: {len(c.cue_ids)} lines" for c in clusters))
    heading = ("TRANSCRIPT (sampled head, middle and tail; '...' marks omitted lines):"
               if sampled else "TRANSCRIPT:")
    parts.append(heading + "\n" + render_transcript(sample, len(lines)))
    messages = [{"role": "system", "content": prompt_text()},
                {"role": "user", "content": "\n\n".join(parts)}]
    return messages, lines, sampled


def _unique(pairs: list[tuple[str, Any]]) -> dict:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise SpeakerNamingError("Speaker naming reply repeats a JSON field")
        result[key] = value
    return result


def parse_naming_reply(content: Any, clusters: Sequence[SpeakerCluster],
                       lines: Sequence[TranscriptLine]) -> tuple[SpeakerProfile, ...]:
    """Strict contract: one entry per cluster in order, exact keys, cited lines must exist."""
    if not isinstance(content, str) or len(content) > MAX_REPLY_CHARS:
        raise SpeakerNamingError("Speaker naming reply is missing or oversized")
    text = content.strip()
    if text.startswith("```"):
        fenced = text.split("\n")
        if len(fenced) < 2 or not fenced[-1].strip().startswith("```"):
            raise SpeakerNamingError("Speaker naming reply is truncated")
        text = "\n".join(fenced[1:-1]).strip()
    try:
        payload = json.loads(text, object_pairs_hook=_unique)
    except ValueError as exc:
        if isinstance(exc, SpeakerNamingError):
            raise
        raise SpeakerNamingError("Speaker naming reply is not JSON") from None
    if not isinstance(payload, dict) or set(payload) != {"speakers"} or not isinstance(payload["speakers"], list):
        raise SpeakerNamingError("Speaker naming reply must contain only speakers")
    entries = payload["speakers"]
    if len(entries) != len(clusters):
        raise SpeakerNamingError("Speaker naming reply does not cover every cluster exactly once")
    by_number = {line.number: line.cue_id for line in lines}
    profiles = []
    for cluster, entry in zip(clusters, entries):
        if not isinstance(entry, dict) or set(entry) != REPLY_KEYS:
            raise SpeakerNamingError("Speaker naming reply has an entry with unexpected fields")
        if entry["label"] != cluster.label:
            raise SpeakerNamingError("Speaker naming reply changed or reordered the cluster labels")
        cited = entry["evidence_cue_ids"]
        if (not isinstance(cited, list) or len(cited) > MAX_NAMING_EVIDENCE
                or any(type(number) is not int or number not in by_number for number in cited)):
            raise SpeakerNamingError("Speaker naming reply cites lines that are not in the transcript")
        evidence = tuple(dict.fromkeys(by_number[number] for number in cited))
        try:
            profiles.append(SpeakerProfile(cluster.speaker_id, cluster.label, entry["name"], entry["role"],
                                           entry["gender"], entry["age_group"], entry["confidence"], evidence))
        except ValueError as exc:
            raise SpeakerNamingError(f"Speaker naming reply has an invalid entry: {exc}") from None
    return tuple(profiles)


def _reply_content(response: Any) -> str:
    try:
        choice = response.choices[0]
        content = choice.message.content
    except (AttributeError, IndexError, TypeError):
        raise SpeakerNamingError("Speaker naming reply is missing") from None
    if getattr(choice, "finish_reason", "stop") not in (None, "stop"):
        usage = getattr(response, "usage", None)
        reasoning = getattr(getattr(usage, "completion_tokens_details", None), "reasoning_tokens", None)
        if not (isinstance(content, str) and content.strip()) or reasoning:
            raise SpeakerNamingError("The model spent its completion budget on hidden reasoning without "
                                     "returning names; choose a non-reasoning model for speaker naming")
        raise SpeakerNamingError("Speaker naming reply was cut off")
    return content


def name_speakers(data: ASRData, settings: SpeakerNamingSettings, *, request: Callable[..., Any] | None = None,
                  check: Check = lambda: None, notify: Callable[[str], None] = lambda _: None) -> ASRData:
    """Ask once (plus one retry on an invalid reply) and attach the names to a copy of ``data``.

    Returns ``data`` untouched when no cue has an assigned anonymous speaker. Cancellation and
    provider failures surface as ``RuntimeError`` from the request; invalid replies raise
    :class:`SpeakerNamingError` after the retry.
    """
    clusters = speaker_clusters(data)
    if not clusters:
        return data
    if len(clusters) > MAX_CLUSTERS:
        raise SpeakerNamingError(f"Too many speaker clusters to name in one request ({len(clusters)} > {MAX_CLUSTERS})")
    messages, lines, sampled = naming_messages(data, clusters, settings.context_notes)

    def cancelled() -> bool:
        try:
            check()
            return False
        except Exception:
            return True

    if request is None:
        from videocaptioner.core.llm.owned_request import OwnedLLMRequest

        request = OwnedLLMRequest(settings.credentials, settings.timeout, cancelled, log_content=False)
    failure = ""
    profiles: tuple[SpeakerProfile, ...] = ()
    for attempt in range(2):
        check()
        notify(f"Naming {len(clusters)} speaker clusters with {settings.model}" + (" (retry)" if attempt else ""))
        response = request(messages=messages, model=settings.model,
                           max_completion_tokens=min(COMPLETION_MAX, COMPLETION_BASE + COMPLETION_PER_CLUSTER * len(clusters)))
        check()
        try:
            profiles = parse_naming_reply(_reply_content(response), clusters, lines)
            break
        except SpeakerNamingError as exc:
            failure = str(exc)
    else:
        raise SpeakerNamingError(failure)
    naming = SpeakerNaming(settings.model, prompt_sha256(), profiles, len(data.segments), sampled)
    return apply_naming(data, naming)


def _entry_ids(speaker_id: str) -> tuple[str, str]:
    digest = hashlib.sha256(speaker_id.encode("utf-8")).hexdigest()[:12]
    return f"ai-char-{digest}", f"ai-map-{digest}"


def _copy(data: ASRData) -> ASRData:
    return data.with_segments(list(data.segments))


def _character_for(characters: dict[str, Character], name: str) -> Character | None:
    return next((c for c in characters.values() if c.label.strip() == name), None)


def apply_naming(data: ASRData, naming: SpeakerNaming) -> ASRData:
    """Write the LLM result into ``speaker_naming`` and propose/confirm S4 characters and mappings.

    Confidence at or above :data:`AUTO_CONFIRM_CONFIDENCE` with cited evidence and a unique name
    is confirmed automatically; everything else stays a proposal for the review table. Entries the
    user made or confirmed earlier are never replaced.
    """
    clusters = {c.speaker_id: c for c in speaker_clusters(data)}
    cue_ids = {s.cue_id for s in data.segments}
    counts = Counter(p.name for p in naming.profiles if p.name)
    context = data.conversation_context
    characters = {c.id: c for c in context.characters}
    mappings = {m.id: m for m in context.mappings}
    # Drop this run's earlier machine proposals first; user-made entries and anything they still
    # reference stay untouched, so a rerun is idempotent without orphaning confirmed links.
    for profile in naming.profiles:
        if profile.speaker_id not in clusters:
            raise SpeakerNamingError("Speaker naming refers to a cluster that is not in this document")
        _, map_id = _entry_ids(profile.speaker_id)
        previous = mappings.get(map_id)
        if previous is not None and previous.evidence.source == "text":
            del mappings[map_id]
    for profile in naming.profiles:
        char_id, _ = _entry_ids(profile.speaker_id)
        previous = characters.get(char_id)
        if (previous is not None and previous.evidence.source == "text"
                and not any(m.character_id == char_id for m in mappings.values())):
            del characters[char_id]
    profiles = []
    for profile in naming.profiles:
        cluster = clusters[profile.speaker_id]
        char_id, map_id = _entry_ids(profile.speaker_id)
        decided = [m for m in mappings.values() if m.speaker_id == profile.speaker_id
                   and m.evidence.status in ("confirmed", "locked")]
        if decided:
            profiles.append(replace(profile, status="confirmed"))
            continue
        evidence = tuple(i for i in profile.evidence_cue_ids if i in cue_ids) or cluster.cue_ids[:MISSING_CLUSTER_LINES]
        if not profile.name:
            profiles.append(replace(profile, evidence_cue_ids=evidence, status="proposed"))
            continue
        auto = (profile.confidence >= AUTO_CONFIRM_CONFIDENCE and bool(profile.evidence_cue_ids)
                and counts[profile.name] == 1)
        status = "confirmed" if auto else "proposed"
        target = _character_for(characters, profile.name)
        if target is None:
            target = Character(char_id, profile.name, Evidence("text", status, evidence))
            characters[char_id] = target
        mappings[map_id] = SpeakerMapping(map_id, profile.speaker_id, target.id, evidence=Evidence("text", status, evidence))
        profiles.append(replace(profile, evidence_cue_ids=evidence, status=status))
    updated = replace(context, characters=tuple(characters.values()), mappings=tuple(mappings.values()))
    updated.validate()
    result = _copy(data)
    result.conversation_context = updated
    result.speaker_naming = replace(naming, profiles=tuple(profiles))
    return result


def apply_decisions(data: ASRData, decisions: Mapping[str, str]) -> ASRData:
    """The user's names from the review table: confirmed user evidence, or rejection when blank."""
    naming = data.speaker_naming
    if naming is None:
        raise SpeakerNamingError("Nothing to review: this document has no speaker naming result")
    context = data.conversation_context
    characters = {c.id: c for c in context.characters}
    mappings = {m.id: m for m in context.mappings}
    profiles = []
    for profile in naming.profiles:
        if profile.speaker_id not in decisions:
            profiles.append(profile)
            continue
        name = " ".join(str(decisions[profile.speaker_id]).split())
        char_id, map_id = _entry_ids(profile.speaker_id)
        mappings.pop(map_id, None)
        orphan = characters.get(char_id)
        if orphan is not None and not any(m.character_id == char_id for m in mappings.values()):
            del characters[char_id]
        if not name:
            profiles.append(replace(profile, status="rejected"))
            continue
        target = _character_for(characters, name)
        if target is None:
            target = Character(char_id, name, Evidence("user", "confirmed", profile.evidence_cue_ids))
            characters[char_id] = target
        mappings[map_id] = SpeakerMapping(map_id, profile.speaker_id, target.id,
                                          evidence=Evidence("user", "confirmed", profile.evidence_cue_ids))
        profiles.append(replace(profile, name=name, status="confirmed"))
    updated = replace(context, characters=tuple(characters.values()), mappings=tuple(mappings.values()))
    updated.validate()
    result = _copy(data)
    result.conversation_context = updated
    result.speaker_naming = replace(naming, profiles=tuple(profiles))
    return result

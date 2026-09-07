"""Evidence-backed dialogue context. No identity or addressee inference from audio labels."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any, Literal

POLICY = "conversation-context-v1"
REQUEST_POLICY = "conversation-request-v2"
Status = Literal["unknown", "proposed", "confirmed", "locked"]


@dataclass(frozen=True)
class Evidence:
    source: Literal["user", "text"] = "user"
    status: Status = "confirmed"
    cue_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class Scope:
    scene_id: str = ""
    cue_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class Character:
    id: str
    label: str
    evidence: Evidence = Evidence()


@dataclass(frozen=True)
class Scene:
    id: str
    label: str
    cue_ids: tuple[str, ...]
    evidence: Evidence = Evidence()


@dataclass(frozen=True)
class SpeakerMapping:
    id: str
    speaker_id: str
    character_id: str
    scope: Scope = Scope()
    evidence: Evidence = Evidence()


@dataclass(frozen=True)
class CueAssignment:
    id: str
    scope: Scope
    speaker_id: str = ""
    # Empty means explicitly unknown; several IDs mean a group, never the previous speaker.
    addressee_ids: tuple[str, ...] = ()
    mentioned_ids: tuple[str, ...] = ()
    mode: Literal["dialogue", "narration", "quotation", "unknown"] = "unknown"
    evidence: Evidence = Evidence()


@dataclass(frozen=True)
class AddressRule:
    id: str
    speaker_id: str
    addressee_ids: tuple[str, ...]
    self_term: str
    address_term: str
    scope: Scope = Scope()
    evidence: Evidence = Evidence()


@dataclass(frozen=True)
class ConversationContext:
    characters: tuple[Character, ...] = ()
    scenes: tuple[Scene, ...] = ()
    mappings: tuple[SpeakerMapping, ...] = ()
    assignments: tuple[CueAssignment, ...] = ()
    rules: tuple[AddressRule, ...] = ()

    @property
    def enabled(self) -> bool:
        return any(getattr(self, f.name) for f in fields(self))

    def to_dict(self) -> dict:
        # Collections are sets of stable IDs. Order in a form is not semantic.
        data = {f.name: [asdict(item) for item in sorted(getattr(self, f.name), key=lambda x: x.id)]
                for f in fields(self)}
        def canonical(value: Any) -> Any:
            if isinstance(value, dict):
                return {key: canonical(val) for key, val in value.items()}
            if isinstance(value, (list, tuple)):
                if all(isinstance(i, str) for i in value):
                    return sorted(set(value))
                return [canonical(i) for i in value]
            return value
        return canonical({"policy": POLICY, **data})

    @classmethod
    def from_dict(cls, data: dict | None) -> ConversationContext:
        if data is None:
            return cls()
        try:
            if not isinstance(data, dict) or data.get("policy", POLICY) != POLICY:
                raise ValueError
            allowed = {f.name for f in fields(cls)} | {"policy"}
            if set(data) - allowed:
                raise ValueError
            types = (Character, Scene, SpeakerMapping, CueAssignment, AddressRule)
            values: dict[str, Any] = {}
            for field, item_type in zip(fields(cls), types):
                items = []
                for raw in data.get(field.name, []):
                    item = dict(raw)
                    if "evidence" in item:
                        evidence = dict(item["evidence"])
                        evidence["cue_ids"] = _ids(evidence.get("cue_ids", []))
                        item["evidence"] = Evidence(**evidence)
                    if "scope" in item:
                        scope = dict(item["scope"])
                        scope["cue_ids"] = _ids(scope.get("cue_ids", []))
                        item["scope"] = Scope(**scope)
                    for name in ("cue_ids", "addressee_ids", "mentioned_ids"):
                        if name in item:
                            item[name] = _ids(item[name])
                    items.append(item_type(**item))
                values[field.name] = tuple(items)
            result = cls(**values)
            result.validate()
            return result
        except (TypeError, KeyError, ValueError, AttributeError) as exc:
            raise ValueError("Invalid conversation context; review required.") from exc

    def validate(self) -> None:
        characters = {c.id for c in self.characters}
        scenes = {s.id for s in self.scenes}
        all_ids = [item.id for f in fields(self) for item in getattr(self, f.name)]
        if len(set(all_ids)) != len(all_ids):
            raise ValueError("Context IDs must be unique across collections.")
        for f in fields(self):
            items = getattr(self, f.name)
            if not isinstance(items, tuple) or len({i.id for i in items}) != len(items):
                raise ValueError("Duplicate context IDs; review required.")
            for item in items:
                if not isinstance(item.id, str) or not item.id.strip():
                    raise ValueError("Context requires stable IDs.")
                ev = item.evidence
                if ev.source not in ("user", "text") or ev.status not in ("unknown", "proposed", "confirmed", "locked"):
                    raise ValueError("Invalid evidence state.")
                _ids(ev.cue_ids)
                if ev.source == "text" and not ev.cue_ids:
                    raise ValueError("Text proposals require cue evidence.")
                for name in ("label", "self_term", "address_term", "speaker_id", "character_id"):
                    if hasattr(item, name) and not isinstance(getattr(item, name), str):
                        raise ValueError("Invalid context text field.")
                scope = getattr(item, "scope", Scope())
                _ids(scope.cue_ids)
                if scope.scene_id and scope.scene_id not in scenes:
                    raise ValueError("Missing scene reference.")
        for scene in self.scenes:
            if not scene.cue_ids:
                raise ValueError("A scene needs explicit cue boundaries.")
        for mapping in self.mappings:
            if not mapping.speaker_id or mapping.character_id not in characters:
                raise ValueError("Missing character or scoped speaker mapping.")
        for item in (*self.assignments, *self.rules):
            if item.speaker_id and item.speaker_id not in characters:
                raise ValueError("Missing speaker character.")
            if any(i not in characters for i in item.addressee_ids):
                raise ValueError("Missing addressee character.")
        for assignment in self.assignments:
            if assignment.mode not in ("dialogue", "narration", "quotation", "unknown"):
                raise ValueError("Invalid utterance mode.")
            if any(i not in characters for i in assignment.mentioned_ids):
                raise ValueError("Missing mentioned character.")
        for rule in self.rules:
            if not rule.speaker_id or not rule.addressee_ids or not rule.self_term.strip() or not rule.address_term.strip():
                raise ValueError("A directed rule needs both parties and terms.")


def _ids(value) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)) or any(not isinstance(i, str) or not i for i in value):
        raise ValueError("Expected an ID list.")
    return tuple(sorted(set(value)))


def load_context(path: str | Path) -> ConversationContext:
    """Read the same optional field from editor/ASR JSON or a standalone context file."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return ConversationContext.from_dict(data.get("conversation_context", data))
    except (OSError, ValueError, AttributeError) as exc:
        raise ValueError("Cannot load conversation context; check the JSON file.") from exc


@dataclass(frozen=True)
class SourceCue:
    id: str
    text: str
    speaker: str = ""


@dataclass(frozen=True)
class ResolvedCue:
    id: str
    speaker_id: str = ""
    addressee_ids: tuple[str, ...] = ()
    mentioned_ids: tuple[str, ...] = ()
    mode: str = "unknown"
    self_term: str = ""
    address_term: str = ""
    review: tuple[str, ...] = ()


def _applies(scope: Scope, cue_id: str, context: ConversationContext) -> bool:
    return (not scope.cue_ids or cue_id in scope.cue_ids) and (
        not scope.scene_id or any(s.id == scope.scene_id and cue_id in s.cue_ids
                                 and s.evidence.status in ("confirmed", "locked") for s in context.scenes))


def _choose(items, issues: list[str], category: str):
    accepted = [i for i in items if i.evidence.status in ("confirmed", "locked")]
    if any(i.evidence.status in ("unknown", "proposed") for i in items):
        issues.append(f"{category}: proposal needs confirmation")
    if not accepted:
        return None
    def rank(item):
        ev, scope = item.evidence, getattr(item, "scope", Scope())
        return (ev.source == "user", ev.status == "locked", bool(scope.cue_ids), bool(scope.scene_id))
    best = max(rank(i) for i in accepted)
    winners = [i for i in accepted if rank(i) == best]
    if len(winners) != 1:
        issues.append(f"{category}: conflicting confirmed entries")
        return None
    return winners[0]


@dataclass(frozen=True)
class ConversationSnapshot:
    context: ConversationContext
    cues: tuple[SourceCue, ...]
    resolved: tuple[ResolvedCue, ...]
    fingerprint: str
    review: tuple[str, ...] = ()

    def request_data(self, cue_ids: tuple[str, ...], radius: int = 4) -> dict:
        selected = set(cue_ids)
        if selected - {cue.id for cue in self.cues}:
            raise ValueError("Missing selected cue association.")
        indexes = {i for pos, cue in enumerate(self.cues) if cue.id in selected
                   for i in range(max(0, pos - radius), min(len(self.cues), pos + radius + 1))}
        resolved = [c for c in self.resolved if c.id in selected]
        characters = {i for c in resolved for i in (c.speaker_id, *c.addressee_ids, *c.mentioned_ids) if i}
        # Retain the confirmed character glossary even for a short ambiguous selection.
        characters.update(c.id for c in self.context.characters if c.evidence.status in ("confirmed", "locked"))
        speakers = {c.speaker for c in self.cues if c.id in selected and c.speaker}
        relevant: list[Character | Scene | SpeakerMapping | CueAssignment | AddressRule] = [
            c for c in self.context.characters if c.id in characters]
        relevant += [s for s in self.context.scenes if selected.intersection(s.cue_ids)]
        relevant += [m for m in self.context.mappings if m.speaker_id in speakers
                     and any(_applies(m.scope, cid, self.context) for cid in selected)]
        relevant += [a for a in self.context.assignments
                     if any(_applies(a.scope, cid, self.context) for cid in selected)]
        relevant += [r for r in self.context.rules if any(
            c.mode == "dialogue" and c.speaker_id == r.speaker_id
            and set(c.addressee_ids) == set(r.addressee_ids) and _applies(r.scope, c.id, self.context)
            for c in resolved)]
        accepted = [item for item in relevant if item.evidence.status in ("confirmed", "locked")]
        evidence_ids = {cid for item in accepted for cid in item.evidence.cue_ids}
        indexes.update(i for i, cue in enumerate(self.cues) if cue.id in evidence_ids)
        # Empty/default fields carry no evidence. The prompt defines their unknown semantics once.
        selected_data = [{key: value for key, value in asdict(c).items()
                          if key != "review" and value and value != "unknown"} for c in resolved]
        reviews: dict[str, list[str]] = {}
        for cue in resolved:
            for issue in cue.review:
                if "conflict" in issue or "proposal" in issue:
                    reviews.setdefault(issue, []).append(cue.id)
        return {
            "policy": REQUEST_POLICY,
            "characters": [asdict(c) for c in self.context.characters
                           if c.id in characters and c.evidence.status in ("confirmed", "locked")],
            "selected": selected_data,
            "source_window": [{key: value for key, value in asdict(self.cues[i]).items() if value}
                              for i in sorted(indexes)],
            "evidence": [{"entry_id": item.id, **asdict(item.evidence)} for item in accepted
                         if item.evidence.cue_ids],
            "review": {"document": self.review, "cues_by_issue": reviews} if self.review or reviews else {},
        }


def prepare_snapshot(cues: tuple[SourceCue, ...], context: ConversationContext) -> ConversationSnapshot:
    # Freeze nested collections even when a caller constructed them using lists.
    context = ConversationContext.from_dict(context.to_dict())
    ids = {c.id for c in cues}
    if len(ids) != len(cues) or any(not c.id for c in cues):
        raise ValueError("Missing or duplicate cue association; review required.")
    review = []
    speakers = {c.speaker for c in cues if c.speaker}
    if any(m.speaker_id not in speakers for m in context.mappings):
        review.append("Unmatched scoped speaker mapping; a new request is not the same identity.")
    invalid = set()
    for f in fields(context):
        for item in getattr(context, f.name):
            refs = set(item.evidence.cue_ids) | set(getattr(item, "cue_ids", ()))
            refs.update(getattr(item, "scope", Scope()).cue_ids)
            if refs - ids:
                invalid.add(item.id)
                review.append("Context refers to missing cues; reattach or review after split/import.")
    active_characters = {c.id for c in context.characters
                         if c.evidence.status in ("confirmed", "locked") and c.id not in invalid}
    def applicable(item, cue_id):
        return (item.id not in invalid and item.scope.scene_id not in invalid
                and _applies(item.scope, cue_id, context))
    resolved = []
    for cue in cues:
        issues: list[str] = []
        mapping = _choose([m for m in context.mappings if m.speaker_id == cue.speaker
                           and applicable(m, cue.id)], issues, "mapping")
        assignment = _choose([a for a in context.assignments if applicable(a, cue.id)], issues, "assignment")
        speaker_choice = _choose([i for i in (mapping, assignment) if i is not None], issues, "speaker")
        speaker = (speaker_choice.character_id if isinstance(speaker_choice, SpeakerMapping)
                   else speaker_choice.speaker_id if speaker_choice else "")
        if speaker not in active_characters:
            speaker = ""
        listeners = assignment.addressee_ids if assignment else ()
        if any(i not in active_characters for i in listeners):
            listeners = ()
        mode = assignment.mode if assignment else "unknown"
        if not speaker:
            issues.append("Unknown speaker character")
        if not listeners:
            issues.append("Unknown addressee; do not infer from previous speaker")
        rule = None
        if speaker and listeners and mode == "dialogue":
            rule = _choose([r for r in context.rules if applicable(r, cue.id) and r.speaker_id == speaker
                            and set(r.addressee_ids) == set(listeners)],
                           issues, "rule")
        if mode != "dialogue":
            issues.append("Narration, quotation or unknown mode: no directed pronoun substitution")
        resolved.append(ResolvedCue(cue.id, speaker, listeners, assignment.mentioned_ids if assignment else (),
                                    mode, rule.self_term if rule else "", rule.address_term if rule else "",
                                    tuple(issues)))
    payload = {"request_policy": REQUEST_POLICY, "context": context.to_dict(), "source": [asdict(c) for c in cues]}
    fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return ConversationSnapshot(context, cues, tuple(resolved), fingerprint, tuple(sorted(set(review))))


def check_context_update(old: ConversationContext, new: ConversationContext, *, user_edit: bool) -> None:
    """Machines may add proposals, but cannot replace confirmed choices or unlock user data."""
    new.validate()
    if user_edit:
        return
    for f in fields(old):
        incoming = {i.id: i for i in getattr(new, f.name)}
        for item in getattr(old, f.name):
            if (item.evidence.source == "user" or item.evidence.status in ("confirmed", "locked")):
                if incoming.get(item.id) != item:
                    raise ValueError("Confirmed context requires an explicit user edit.")
        prior = {i.id: i for i in getattr(old, f.name)}
        for item in incoming.values():
            if prior.get(item.id) != item and (item.evidence.source != "text" or item.evidence.status != "proposed"):
                raise ValueError("Machine changes must remain evidence-backed proposals.")

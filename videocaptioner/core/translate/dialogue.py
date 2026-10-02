"""Source-bound spoken translations, separate from display subtitle timing."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from videocaptioner.core.asr.asr_data import ASRData

SCHEMA = "dialogue-translation-v1"
POLICY = "spoken-dialogue-v1"
MAX_BLOCK_MS = 8000
MAX_CONTINUATION_MS = 12000


def fingerprint(value: object) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":")).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class DialogueCue:
    cue_id: str
    source_text: str
    subtitle_text: str
    start_ms: int
    end_ms: int
    speaker: str = ""
    scene: str = ""


def hard_boundary(previous: DialogueCue, current: DialogueCue) -> bool:
    return (previous.speaker != current.speaker or previous.scene != current.scene
            or current.start_ms < previous.end_ms or current.start_ms - previous.end_ms >= 1000)


@dataclass(frozen=True)
class SpeechBlock:
    cue_ids: tuple[str, ...]
    text: str

    @property
    def block_id(self) -> str:
        return "dialogue-" + fingerprint(self.cue_ids)[:16]


def validate_blocks(cues: tuple[DialogueCue, ...], blocks: tuple[SpeechBlock, ...]) -> None:
    if tuple(cid for block in blocks for cid in block.cue_ids) != tuple(c.cue_id for c in cues):
        raise ValueError("Speech blocks must cover each owned cue exactly once, in source order.")
    by_id = {cue.cue_id: cue for cue in cues}
    for block in blocks:
        if not block.cue_ids or not isinstance(block.text, str) or not block.text.strip() or len(block.text) > 8000:
            raise ValueError("Each speech block requires nonempty text and cue IDs.")
        members = [by_id[cid] for cid in block.cue_ids]
        if any(hard_boundary(a, b) for a, b in zip(members, members[1:])):
            raise ValueError("A speech block crosses a speaker, scene, overlap or long-silence boundary.")
        if len(members) > 1 and members[-1].end_ms - members[0].start_ms > MAX_BLOCK_MS:
            continuation = (members[-1].end_ms - members[0].start_ms <= MAX_CONTINUATION_MS
                            and all(not re.search(r"[.!?。！？][\"'”’)]*\s*$", cue.source_text)
                                    for cue in members[:-1]))
            if not continuation:
                raise ValueError("Keep blocks within 8 seconds, or 12 seconds only to finish an unpunctuated source continuation.")


@dataclass(frozen=True)
class DialogueDocument:
    cues: tuple[DialogueCue, ...]
    blocks: tuple[SpeechBlock, ...]
    target_language: str
    producer: str = POLICY

    def validate(self) -> None:
        ids = [cue.cue_id for cue in self.cues]
        if not ids or len(set(ids)) != len(ids) or not all(isinstance(cid, str) and cid for cid in ids):
            raise ValueError("Dialogue requires unique, nonempty source cue IDs.")
        if not isinstance(self.target_language, str) or not self.target_language.strip() or self.producer != POLICY:
            raise ValueError("Unsupported dialogue language or producer policy.")
        previous_start = -1
        for cue in self.cues:
            if (type(cue.start_ms) is not int or type(cue.end_ms) is not int
                    or cue.start_ms < previous_start or cue.start_ms < 0 or cue.end_ms <= cue.start_ms
                    or not all(isinstance(t, str) for t in (cue.source_text, cue.subtitle_text, cue.speaker, cue.scene))
                    or not cue.source_text.strip() or not cue.subtitle_text.strip()):
                raise ValueError("Invalid dialogue cue text or timing.")
            previous_start = cue.start_ms
        validate_blocks(self.cues, self.blocks)

    @property
    def source_sha256(self) -> str:
        return fingerprint([{key: value for key, value in asdict(cue).items() if key != "subtitle_text"}
                            for cue in self.cues])

    def to_dict(self) -> dict:
        self.validate()
        return {"schema": SCHEMA, "policy": self.producer, "target_language": self.target_language,
                "source_sha256": self.source_sha256,
                "cues": [asdict(cue) for cue in self.cues],
                "speech_blocks": [{"cue_ids": list(block.cue_ids), "text": block.text} for block in self.blocks]}

    @classmethod
    def from_dict(cls, data: dict) -> DialogueDocument:
        try:
            if data["schema"] != SCHEMA or data["policy"] != POLICY:
                raise ValueError("Unsupported dialogue schema.")
            blocks = []
            for item in data["speech_blocks"]:
                if not isinstance(item["cue_ids"], list) or not all(isinstance(cid, str) for cid in item["cue_ids"]):
                    raise ValueError("Invalid dialogue membership.")
                blocks.append(SpeechBlock(tuple(item["cue_ids"]), item["text"]))
            result = cls(tuple(DialogueCue(**item) for item in data["cues"]), tuple(blocks),
                         data["target_language"], data["policy"])
            result.validate()
            if result.source_sha256 != data["source_sha256"]:
                raise ValueError("Dialogue source fingerprint mismatch; prepare the dialogue again.")
            return result
        except (KeyError, TypeError, AttributeError) as exc:
            raise ValueError("Invalid dialogue document.") from exc

    @classmethod
    def load(cls, path: str | Path) -> DialogueDocument:
        source = Path(path)
        if source.stat().st_size > 16 * 1024 * 1024:
            raise ValueError("Dialogue document exceeds 16 MiB.")
        return cls.from_dict(json.loads(source.read_text(encoding="utf-8-sig")))

    def save(self, path: str | Path) -> None:
        """Explicit export never replaces an existing plan."""
        payload = json.dumps(self.to_dict(), ensure_ascii=False, indent=2)
        with Path(path).open("x", encoding="utf-8") as output:
            output.write(payload)

    def subtitle_data(self) -> ASRData:
        from videocaptioner.core.asr.asr_data import ASRData, ASRDataSeg
        return ASRData([ASRDataSeg(text=c.source_text, start_time=c.start_ms, end_time=c.end_ms,
                                  translated_text=c.subtitle_text, cue_id=c.cue_id) for c in self.cues])


def available_dialogue_path(subtitle_path: str | Path) -> Path:
    source = Path(subtitle_path)
    candidate = source.with_suffix(".dialogue.json")
    count = 1
    while candidate.exists():
        candidate = source.with_name(f"{source.stem}.dialogue-{count}.json")
        count += 1
    return candidate

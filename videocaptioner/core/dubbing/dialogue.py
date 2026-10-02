"""Adapt validated dialogue to the existing sequential review and playback pipeline."""

import json
from copy import deepcopy
from pathlib import Path

from videocaptioner.core.translate.dialogue import SCHEMA, DialogueDocument, hard_boundary

from .config import DubbingConfig
from .models import DubbingGroup, DubbingTextSource, DubbingTimingMode, UnresolvedFitPolicy
from .planner import predict_spoken_duration

PLAN_SCHEMA = "dubbing-plan-dialogue-v1"


def load_dialogue(path: str) -> DialogueDocument | None:
    source = Path(path)
    if source.suffix.lower() != ".json":
        return None
    if source.stat().st_size > 16 * 1024 * 1024:
        raise ValueError("Subtitle JSON exceeds 16 MiB.")
    value = json.loads(source.read_text(encoding="utf-8-sig"))
    if isinstance(value, dict) and value.get("schema") == SCHEMA:
        return DialogueDocument.from_dict(value)
    return None


def source_config(path: str, config: DubbingConfig) -> DubbingConfig:
    from .playback import playback_config
    config = playback_config(config)
    document = load_dialogue(path)
    if document is None:
        return config
    return dialogue_preset(config, document.target_language)


def dialogue_preset(config: DubbingConfig, target_language: str) -> DubbingConfig:
    result = deepcopy(config)
    result.timing_mode = DubbingTimingMode.NATURAL
    result.unresolved_policy = UnresolvedFitPolicy.SEQUENTIAL
    result.text_source = DubbingTextSource.AUTO
    result.target_language = target_language
    result.natural_max_speed = 1.0
    result.silence_guard_ms = 80
    result.rewrite_enabled = False
    result.strip_cjk = False
    if result.tts_config:
        result.tts_config.speed = 1.0
    return result


def dialogue_groups(document: DialogueDocument, video_duration: float) -> list[DubbingGroup]:
    document.validate()
    cues = {cue.cue_id: cue for cue in document.cues}
    groups = []
    for index, block in enumerate(document.blocks):
        members = [cues[cid] for cid in block.cue_ids]
        start, end = members[0].start_ms / 1000, members[-1].end_ms / 1000
        next_cue = cues[document.blocks[index + 1].cue_ids[0]] if index + 1 < len(document.blocks) else None
        available_end = max(end, next_cue.start_ms / 1000 - 0.08) if next_cue else video_duration
        hard_end = next_cue.start_ms / 1000 if next_cue and hard_boundary(members[-1], next_cue) else video_duration
        warnings = []
        if len(members) > 1 and not members[0].speaker:
            warnings.append("Unknown speaker: review this merged dialogue block before synthesis.")
        if end - start > 8:
            warnings.append("Source span exceeds 8 seconds; review this long sentence/continuation.")
        groups.append(DubbingGroup(
            group_id=block.block_id, cue_ids=list(block.cue_ids), start_time=start,
            subtitle_end_time=end, available_end_time=available_end,
            available_duration=max(0, available_end - start),
            source_text=" ".join(c.source_text for c in members),
            subtitle_text=" ".join(c.subtitle_text for c in members),
            tts_text=block.text, original_tts_text=block.text,
            predicted_duration=predict_spoken_duration(block.text, document.target_language),
            hard_end_time=hard_end, warnings=warnings,
        ))
    return groups

"""Lossless adapters between editor state and existing subtitle/dubbing models."""

from __future__ import annotations

from typing import Iterable

from videocaptioner.core.asr.asr_data import ASRData, ASRDataSeg
from videocaptioner.core.asr.metadata import ASRMetadata
from videocaptioner.core.dubbing.models import DubbingCue, DubbingReport

from .models import EditorCue, EditorProject, stable_cue_id


def cues_from_asr(asr_data: ASRData) -> list[EditorCue]:
    cues: list[EditorCue] = []
    for index, segment in enumerate(asr_data.segments, start=1):
        source = str(segment.text or "")
        translated = str(segment.translated_text or "")
        display = translated or source
        cues.append(
            EditorCue(
                id=stable_cue_id(index, segment.start_time, segment.end_time, source),
                start_ms=int(segment.start_time),
                end_ms=int(segment.end_time),
                source_text=source,
                display_text=display,
                tts_text=display,
                speaker=segment.speaker or "",
                asr_metadata=segment.metadata,
            )
        )
    return cues


def cue_metadata(cue: EditorCue) -> ASRMetadata | None:
    metadata = cue.asr_metadata
    if cue.speaker == ((metadata.speaker_id or "") if metadata else ""):
        return metadata
    if not cue.speaker and metadata is None:
        return None
    return ASRMetadata("user", metadata.scope if metadata else "editor", cue.speaker or None, "edited")


def project_to_asr(project: EditorProject, *, display_only: bool = False) -> ASRData:
    segments: list[ASRDataSeg] = []
    for cue in sorted(project.cues, key=lambda item: (item.start_ms, item.end_ms, item.id)):
        if display_only:
            segments.append(ASRDataSeg(cue.display_text, cue.start_ms, cue.end_ms, metadata=cue_metadata(cue)))
        else:
            translated = cue.display_text if cue.display_text != cue.source_text else ""
            segments.append(
                ASRDataSeg(cue.source_text or cue.display_text, cue.start_ms, cue.end_ms, translated, cue_metadata(cue))
            )
    return ASRData(segments, project.audio_events)


def project_to_tts_asr(project: EditorProject) -> ASRData:
    return ASRData(
        [
            ASRDataSeg(cue.tts_text, cue.start_ms, cue.end_ms, metadata=cue_metadata(cue))
            for cue in sorted(project.cues, key=lambda item: (item.start_ms, item.end_ms, item.id))
        ]
    )


def project_to_dubbing_cues(project: EditorProject) -> list[DubbingCue]:
    return [
        DubbingCue(
            cue_id=cue.id,
            start_time=cue.start_ms / 1000.0,
            end_time=cue.end_ms / 1000.0,
            source_text=cue.source_text,
            subtitle_text=cue.display_text,
            tts_text=cue.tts_text,
            speaker=cue.speaker,
            voice=cue.voice,
            group_id=cue.group_id,
            original_index=index,
            metadata={
                "voice_speed": cue.voice_speed,
                "voice_settings": dict(cue.voice_settings),
            },
        )
        for index, cue in enumerate(
            sorted(project.cues, key=lambda item: (item.start_ms, item.end_ms, item.id))
        )
    ]


def apply_dubbing_report(project: EditorProject, report: DubbingReport | dict) -> None:
    payload = report.to_dict() if isinstance(report, DubbingReport) else dict(report)
    cue_map = {cue.id: cue for cue in project.cues}
    for group in payload.get("groups", []):
        group_id = str(group.get("group_id", ""))
        warnings = [str(item) for item in group.get("warnings", [])]
        for cue_id in group.get("cue_ids", []):
            cue = cue_map.get(str(cue_id))
            if not cue:
                continue
            cue.group_id = group_id
            cue.audio_path = str(group.get("audio_path", ""))
            cue.fit_status = str(group.get("fit_status", "pending"))
            cue.fit_ratio = float(group.get("fit_ratio", 0.0) or 0.0)
            cue.warnings = list(warnings)
    project.touch()


def update_cues_from_groups(project: EditorProject, groups: Iterable[object]) -> None:
    cue_map = {cue.id: cue for cue in project.cues}
    for group in groups:
        for cue_id in getattr(group, "cue_ids", []):
            cue = cue_map.get(str(cue_id))
            if not cue:
                continue
            cue.group_id = str(getattr(group, "group_id", ""))
            cue.audio_path = str(getattr(group, "audio_path", ""))
            status = getattr(group, "fit_status", "pending")
            cue.fit_status = getattr(status, "value", str(status))
            cue.fit_ratio = float(getattr(group, "fit_ratio", 0.0) or 0.0)
            cue.warnings = [str(item) for item in getattr(group, "warnings", [])]
    project.touch()

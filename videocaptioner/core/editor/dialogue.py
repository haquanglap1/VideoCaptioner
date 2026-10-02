"""Keep parent dialogue ownership while editing display cues independently."""

from dataclasses import replace
from pathlib import Path

from videocaptioner.core.translate.dialogue import DialogueCue, DialogueDocument, SpeechBlock

from .models import EditorProject


def attach_dialogue(project: EditorProject, document: DialogueDocument) -> None:
    """Initialize a new project before it is attached to a CommandStack."""
    document.validate()
    by_id = {cue.id: cue for cue in project.cues}
    project.dialogue_document = document
    for source in document.cues:
        by_id[source.cue_id].speaker = source.speaker
    for block in document.blocks:
        for index, cid in enumerate(block.cue_ids):
            cue = by_id[cid]
            cue.group_id = block.block_id
            cue.tts_text = block.text if index == 0 else ""
            if index:
                cue.warnings.append(f"Lời đọc của nhóm nằm ở cue {block.cue_ids[0]}; cue này chỉ hiển thị phụ đề.")


def dialogue_from_project(project: EditorProject) -> DialogueDocument | None:
    original = project.dialogue_document
    if original is None:
        return None
    expected = [cue.cue_id for cue in original.cues]
    current = sorted(project.cues, key=lambda cue: (cue.start_ms, cue.end_ms, cue.id))
    if [cue.id for cue in current] != expected:
        raise ValueError("Cue của kịch bản thoại đã bị thêm/xóa/tách/đảo; chuẩn bị và duyệt lại kịch bản trước TTS.")
    by_id = {cue.id: cue for cue in current}
    blocks = []
    for block in original.blocks:
        members = [by_id[cid] for cid in block.cue_ids]
        if any(cue.tts_text.strip() for cue in members[1:]):
            raise ValueError("Sửa lời đọc ở cue đầu của nhóm thoại; các cue tiếp theo chỉ giữ phụ đề hiển thị.")
        if len({cue.voice for cue in members}) > 1:
            raise ValueError("Một nhóm thoại cần cùng giọng; chọn cả nhóm khi đổi giọng.")
        blocks.append(SpeechBlock(block.cue_ids, members[0].tts_text))
    cues = tuple(DialogueCue(cue.id, cue.source_text, cue.display_text, cue.start_ms, cue.end_ms,
                             cue.speaker, source.scene) for cue, source in zip(current, original.cues))
    result = replace(original, cues=cues, blocks=tuple(blocks))
    result.validate()
    return result


def existing_dialogue_audio(project: EditorProject, start_ms: int, end_ms: int) -> list[dict[str, object]]:
    from videocaptioner.core.dubbing.cache import measure_audio_duration
    from videocaptioner.core.dubbing.config import DubbingConfig
    from videocaptioner.core.dubbing.dialogue import dialogue_groups, dialogue_preset
    from videocaptioner.core.dubbing.engine import DubbingEngine
    from videocaptioner.core.dubbing.orchestrator import DubbingOrchestrator

    document = dialogue_from_project(project)
    if document is None:
        return []
    groups = dialogue_groups(document, project.duration_ms / 1000)
    available = []
    for group in groups:
        path = project.cue_by_id(str(group.cue_ids[0])).audio_path
        if path and Path(path).is_file():
            group.audio_path = path
            group.measured_duration = measure_audio_duration(path)
            available.append(group)
    if not available:
        return []
    config = dialogue_preset(DubbingConfig(), document.target_language)
    DubbingOrchestrator(DubbingEngine())._apply_sequential_policy(
        available, config, Path("."), project.duration_ms / 1000)
    if any(group.needs_review for group in available):
        raise ValueError("Audio lời thoại vượt giới hạn trễ/cảnh; duyệt lại lời đọc trước khi phát/xuất.")
    result = []
    for group in available:
        start, end = group.playback_start_time, group.playback_end_time
        assert start is not None and end is not None
        if start < end_ms / 1000 and end > start_ms / 1000:
            result.append({"audio_path": group.audio_path, "start_time": max(0, start - start_ms / 1000),
                           "end_time": min(end, end_ms / 1000) - start_ms / 1000,
                           "audio_offset": max(0, start_ms / 1000 - start)})
    return result

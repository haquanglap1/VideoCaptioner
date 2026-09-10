from copy import deepcopy

import pytest

from videocaptioner.core.asr.asr_data import ASRData, ASRDataSeg
from videocaptioner.core.editor.adapters import cues_from_asr, project_to_asr, project_to_tts_asr
from videocaptioner.core.editor.commands import (
    CommandStack,
    EditCueTextCommand,
    EditCueTimingCommand,
    SplitCueCommand,
)
from videocaptioner.core.editor.models import EditorProject
from videocaptioner.core.editor.project_store import EditorProjectStore
from videocaptioner.core.entities import SubtitleLayoutEnum
from videocaptioner.core.ocr.models import OcrError
from videocaptioner.core.subtitle.editing import export_subtitle, merge_rows, write_editor_handoff
from videocaptioner.core.translate.base import BaseTranslator
from videocaptioner.core.translate.types import TargetLanguage

from .test_document import make_document


def subtitles():
    document = make_document(approved=True)
    return document.resume(document.visual_source)


def project():
    data = subtitles()
    return EditorProject("fixture", "Synthetic", "", "", 1500,
                         cues=cues_from_asr(data), visual_source=data.visual_source)


def test_two_source_lines_survive_clone_json_selection_and_translation(tmp_path):
    class Translator(BaseTranslator):
        def _translate_chunk(self, chunk):
            for item in chunk:
                item.translated_text = "Ba học sinh, năm 2026."
            return chunk

    data = subtitles()
    selection = data.with_segments([data.segments[0].clone()])
    translator = Translator(1, 10, TargetLanguage.VIETNAMESE, None)
    try:
        translated = translator.translate_subtitle(selection, context_data=data)
    finally:
        translator.close()
    cue = translated.segments[0]
    assert cue.text == "学生三人\n2026年。" and cue.translated_text == "Ba học sinh, năm 2026."
    assert cue.ocr_metadata == data.segments[0].ocr_metadata
    assert translated.visual_source == data.visual_source and translated.has_metadata
    assert not translated.is_word_timestamp() and cue.speaker is None and cue.metadata is None
    destination = tmp_path / "translated.json"
    translated.save(str(destination))
    reopened = ASRData.from_subtitle_file(str(destination))
    assert reopened.to_document() == translated.to_document()


def test_editor_edit_undo_redo_and_save_keep_raw_lineage(tmp_path):
    state = project()
    original = deepcopy(state.cues[0])
    stack = CommandStack()
    stack.execute(EditCueTextCommand(state, original.id, "source_text", "Explicit source edit"))
    stack.execute(EditCueTimingCommand(state, original.id, 210, 490))
    assert state.cues[0].ocr_metadata.text_edited and state.cues[0].ocr_metadata.timing_edited
    assert state.cues[0].ocr_metadata.observations == original.ocr_metadata.observations
    stack.undo()
    stack.undo()
    assert state.cues[0] == original
    stack.redo()
    stack.redo()
    store = EditorProjectStore()
    path, srt = store.save(state, tmp_path / "fixture.vceditor.json")
    reopened = store.load(path)
    assert reopened.cues == state.cues and reopened.visual_source == state.visual_source
    assert project_to_asr(reopened).visual_source == state.visual_source
    assert project_to_tts_asr(reopened).segments[0].ocr_metadata == state.cues[0].ocr_metadata
    assert srt.endswith(".srt") and not list(tmp_path.glob("*.ass"))


def test_explicit_split_merge_lineage_and_undo():
    state = project()
    original = deepcopy(state.cues[0])
    stack = CommandStack()
    with pytest.raises(ValueError, match="explicit"):
        stack.execute(SplitCueCommand(state, original.id, 350))
    stack.execute(SplitCueCommand(state, original.id, 350, source_split_index=4))
    assert "".join(c.source_text for c in state.cues) == original.source_text
    assert len({c.id for c in state.cues}) == 2
    assert all(c.ocr_metadata.timing_edited and c.ocr_metadata.text_edited for c in state.cues)
    assert all(c.ocr_metadata.observations == original.ocr_metadata.observations for c in state.cues)
    split_state = deepcopy(state.cues)
    stack.undo()
    assert state.cues == [original]
    stack.redo()
    assert state.cues == split_state
    data = project_to_asr(state)
    table = merge_rows(data.to_json(), [0, 1])
    merged = ASRData.from_json(table)
    merged.visual_source = state.visual_source
    assert len(merged.segments[0].ocr_metadata.observations) == 1
    data.merge_with_next_segment(0)
    assert data.segments[0].ocr_metadata.timing_edited
    assert data.segments[0].ocr_metadata.observations == original.ocr_metadata.observations


def test_reject_mixed_source_merge_missing_identity_and_empty_cues():
    data = subtitles()
    bad = data.to_document()
    bad.pop("visual_source")
    with pytest.raises(OcrError):
        ASRData.from_json(bad)
    with pytest.raises(ValueError, match="cannot be dropped"):
        data.with_segments([data.segments[0].clone(text="")])
    data.segments.append(ASRDataSeg("Legacy", 700, 900))
    with pytest.raises(OcrError):
        data.merge_segments(0, 1)


def test_table_export_and_editor_handoff_keep_visual_metadata(tmp_path):
    data = subtitles()
    table = data.to_json()
    export = tmp_path / "table.json"
    export_subtitle(table, str(export), SubtitleLayoutEnum.ONLY_ORIGINAL, visual_source=data.visual_source)
    assert ASRData.from_subtitle_file(str(export)).to_document() == data.to_document()
    handoff = write_editor_handoff(table, tmp_path, "handoff", "fixture.mov", visual_source=data.visual_source)
    assert handoff.suffix == ".json"
    assert ASRData.from_subtitle_file(str(handoff)).to_document() == data.to_document()


def test_short_ocr_cue_is_kept_but_overlap_is_rejected():
    state = project()
    stack = CommandStack()
    stack.execute(EditCueTimingCommand(state, state.cues[0].id, 200, 220))
    state.validate_all_cues()
    assert state.cues[0].duration_ms == 20 and state.cues[0].asr_metadata is None
    second = deepcopy(state.cues[0])
    second.id += "-second"
    state.cues.append(second)
    with pytest.raises(ValueError, match="overlap"):
        state.validate_all_cues()


def test_translated_split_needs_explicit_boundaries_and_failed_command_does_not_mutate():
    state = project()
    cue = state.cues[0]
    cue.display_text = cue.tts_text = "Ba học sinh năm 2026."
    original = deepcopy(cue)
    stack = CommandStack()
    with pytest.raises(ValueError, match="explicit"):
        stack.execute(SplitCueCommand(state, cue.id, 350, source_split_index=4))
    assert state.cues == [original] and not stack.can_undo
    stack.execute(SplitCueCommand(state, cue.id, 350, source_split_index=4,
                                  display_split_index=11, tts_split_index=11))
    assert "".join(c.display_text for c in state.cues) == original.display_text
    stack.undo()
    assert state.cues == [original]

"""Project styling must preserve the OCR lineage introduced by the ASR branch."""

from copy import deepcopy
from dataclasses import replace

import pytest

from videocaptioner.core.editor.adapters import project_to_asr
from videocaptioner.core.editor.commands import (
    CommandStack,
    EditCueTextCommand,
    EditSubtitleStyleCommand,
)
from videocaptioner.core.editor.project_store import EditorProjectStore
from videocaptioner.core.editor.subtitle_style import EditorSubtitleStyle

from .test_metadata import project


@pytest.mark.parametrize("style", [
    EditorSubtitleStyle(spacing=2.5),
    EditorSubtitleStyle(background=True, bg_opacity=0.375, padding_h=23),
    EditorSubtitleStyle.from_dict({"align_h": "right", "font_size": 88, "margin_v": 47}),
])
def test_style_edit_save_reopen_keeps_ocr_source_and_raw_observations(tmp_path, style):
    state = project()
    state.width, state.height = 1280, 720
    source = state.visual_source
    original = deepcopy(state.cues)
    original_style = state.subtitle_style
    stack = CommandStack()
    stack.execute(EditSubtitleStyleCommand(state, style))
    assert state.cues == original and state.visual_source == source
    stack.execute(EditCueTextCommand(state, state.cues[0].id, "display_text", "Explicit display edit"))
    stack.undo()
    assert state.cues == original and state.subtitle_style == style
    stack.undo()
    assert state.subtitle_style == original_style
    stack.redo()
    store = EditorProjectStore()
    for index in range(2):
        path, srt = store.save(state, tmp_path / f"round-{index}.vceditor.json")
        state = store.load(path)
        assert state.subtitle_style == style
        assert state.cues == original and state.visual_source == source
        assert project_to_asr(state).segments[0].ocr_metadata == original[0].ocr_metadata
        assert srt.endswith(".srt")
    assert not list(tmp_path.glob("*.ass"))
    before = state.to_dict()
    store.save_as_ass(state, tmp_path / "explicit.ass")
    assert state.to_dict() == before
    assert (tmp_path / "explicit.ass").is_file()
    CommandStack().execute(EditSubtitleStyleCommand(state, replace(style, primary_color="#123456")))
    assert state.cues == original and state.visual_source == source

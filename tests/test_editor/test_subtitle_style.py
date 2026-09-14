import json
from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import pytest

from videocaptioner.core.editor.commands import CommandStack, EditSubtitleStyleCommand
from videocaptioner.core.editor.models import EditorCue, EditorProject
from videocaptioner.core.editor.project_store import EditorProjectStore
from videocaptioner.core.editor.subtitle_style import EditorSubtitleStyle


def test_old_project_defaults_and_partial_style_remain_schema_v1():
    payload = EditorProject.empty().to_dict()
    payload.pop("subtitle_style")
    old = EditorProject.from_dict(payload)
    assert old.subtitle_style == EditorSubtitleStyle()
    payload["subtitle_style"] = {"font_size": 55, "future_field": "ignored"}
    loaded = EditorProject.from_dict(payload)
    assert loaded.subtitle_style == replace(EditorSubtitleStyle(), font_size=55)
    assert loaded.schema_version == "editor-project-v1"


@pytest.mark.parametrize(
    "values",
    [
        {"font_name": ""},
        {"font_name": "Arial,Fontsize=200"},
        {"font_name": "a\nb"},
        {"font_name": "a'b"},
        {"primary_color": "red"},
        {"outline_color": "#abcdef00"},
        {"font_size": 0},
        {"font_size": True},
        {"font_size": 42.5},
        {"alignment": 0},
        {"alignment": 10},
        {"margin_bottom": -1},
        {"outline_width": float("nan")},
        {"spacing": float("inf")},
        {"bold": "false"},
        [],
        "invalid",
    ],
)
def test_invalid_style_is_rejected(values):
    with pytest.raises(ValueError):
        EditorSubtitleStyle.from_dict(values)


def test_style_command_has_immutable_snapshot_and_undo_redo():
    project = EditorProject.empty()
    original = project.subtitle_style
    values = {"font_size": 64, "primary_color": "#FF0000"}
    style = EditorSubtitleStyle.from_dict(values)
    stack = CommandStack()
    stack.execute(EditSubtitleStyleCommand(project, style))
    values["font_size"] = 100
    assert project.is_dirty
    assert project.subtitle_style.font_size == 64
    assert project.subtitle_style.primary_color == "#ff0000"
    with pytest.raises(FrozenInstanceError):
        style.font_size = 99
    assert stack.undo()
    assert project.subtitle_style == original
    assert stack.redo()
    assert project.subtitle_style == style
    assert EditorProject.empty().subtitle_style == original


def test_style_survives_save_reopen_and_explicit_ass_only(tmp_path):
    project = EditorProject.empty(str(tmp_path / "input.mp4"), 2000)
    project.width, project.height = 1080, 1920
    project.cues = [EditorCue("stable", 200, 1500, "source", "Display\nTiếng Việt", "voice")]
    project.subtitle_style = EditorSubtitleStyle(
        font_name="Missing Font Family",
        font_size=61,
        bold=False,
        primary_color="#1234ab",
        outline_color="#ab3412",
        outline_width=3.5,
        spacing=1.5,
        alignment=8,
        margin_left=12,
        margin_right=14,
        margin_bottom=44,
    )
    store = EditorProjectStore()
    project_file, srt_file = store.save(project, tmp_path / "edit.vceditor.json")
    assert not list(tmp_path.glob("*.ass"))
    assert not project.is_dirty
    payload = json.loads(Path(project_file).read_text(encoding="utf-8"))
    assert payload["subtitle_style"] == project.subtitle_style.to_dict()
    assert not Path(payload["video_path"]).is_absolute()
    loaded = store.load(project_file)
    assert loaded.subtitle_style == project.subtitle_style
    assert loaded.cues[0].id == "stable"
    assert loaded.cues[0].tts_text == "voice"
    assert "Display\nTiếng Việt" in Path(srt_file).read_text(encoding="utf-8")
    output = store.save_as_ass(loaded, tmp_path / "styled.ass")
    ass = Path(output).read_text(encoding="utf-8")
    assert "PlayResX: 405\nPlayResY: 720" in ass
    assert "Style: Default,Missing Font Family,61,&H00AB3412" in ass
    assert r"Display\NTiếng Việt" in ass
    assert not loaded.is_dirty
    assert not list(tmp_path.glob("*.tmp"))

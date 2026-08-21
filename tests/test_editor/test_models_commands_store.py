import json
from pathlib import Path

import pytest

from videocaptioner.core.editor.adapters import project_to_dubbing_cues
from videocaptioner.core.editor.commands import (
    AddCueCommand,
    AddLayerCommand,
    CommandStack,
    DeleteCueCommand,
    EditCueTextCommand,
    EditCueTimingCommand,
    EditTrackStateCommand,
    EditVoiceSettingsCommand,
    MoveCueCommand,
    ResizeCueCommand,
    SplitCueCommand,
)
from videocaptioner.core.editor.models import (
    EditorCue,
    EditorLayer,
    EditorLayerKind,
    EditorProject,
    TimelineIndex,
)
from videocaptioner.core.editor.project_store import EditorProjectStore


def make_project() -> EditorProject:
    project = EditorProject.empty("C:/media/input.mp4", 5000)
    project.cues = [
        EditorCue("cue-a", 0, 500, "source A", "display A", "tts A"),
        EditorCue("cue-b", 1000, 1600, "source B", "display B", "tts B"),
    ]
    project.validate_all_cues()
    return project


def test_command_stack_covers_text_timing_move_resize_and_track_state():
    project = make_project()
    stack = CommandStack()

    stack.execute(EditCueTextCommand(project, "cue-a", "display_text", "edited"))
    stack.execute(EditCueTimingCommand(project, "cue-a", 50, 550))
    stack.execute(MoveCueCommand(project, "cue-a", 100))
    stack.execute(ResizeCueCommand(project, "cue-a", new_end_ms=700))
    stack.execute(EditTrackStateCommand(project, "track-a1", muted=True, locked=True))

    assert project.cue_by_id("cue-a").display_text == "edited"
    assert (project.cue_by_id("cue-a").start_ms, project.cue_by_id("cue-a").end_ms) == (100, 700)
    assert project.track_by_id("track-a1").muted is True
    assert project.track_by_id("track-a1").locked is True

    for _ in range(5):
        assert stack.undo()
    assert project.cue_by_id("cue-a").display_text == "display A"
    assert (project.cue_by_id("cue-a").start_ms, project.cue_by_id("cue-a").end_ms) == (0, 500)
    assert project.track_by_id("track-a1").muted is False
    assert project.track_by_id("track-a1").locked is False

    for _ in range(5):
        assert stack.redo()
    assert project.cue_by_id("cue-a").end_ms == 700


def test_split_delete_add_voice_settings_and_undo_redo():
    project = make_project()
    stack = CommandStack()
    stack.execute(SplitCueCommand(project, "cue-a", 250))
    assert len(project.cues) == 3
    right_id = next(cue.id for cue in project.cues if cue.id not in {"cue-a", "cue-b"})
    assert project.cue_by_id("cue-a").end_ms == 250
    assert project.cue_by_id(right_id).start_ms == 250

    stack.execute(DeleteCueCommand(project, right_id))
    stack.execute(
        AddCueCommand(project, EditorCue("cue-new", 700, 900, "s", "d", "t"))
    )
    stack.execute(
        EditVoiceSettingsCommand(
            project,
            "cue-new",
            "alloy",
            1.15,
            {"model": "tts-1", "api_key": "must-not-persist"},
        )
    )
    assert project.cue_by_id("cue-new").voice == "alloy"
    assert project.cue_by_id("cue-new").voice_speed == pytest.approx(1.15)
    assert stack.undo()
    assert project.cue_by_id("cue-new").voice == ""
    assert stack.redo()
    assert project.cue_by_id("cue-new").voice == "alloy"


def test_timing_validation_rejects_negative_overlap_and_too_short():
    project = make_project()
    stack = CommandStack()
    with pytest.raises(ValueError, match="non-negative"):
        stack.execute(EditCueTimingCommand(project, "cue-a", -1, 200))
    with pytest.raises(ValueError, match="overlaps"):
        stack.execute(EditCueTimingCommand(project, "cue-a", 800, 1200))
    with pytest.raises(ValueError, match="at least"):
        stack.execute(EditCueTimingCommand(project, "cue-a", 100, 120))
    assert stack.can_undo is False


def test_project_store_round_trip_is_relative_srt_only_and_keeps_three_text_fields(tmp_path):
    video = tmp_path / "media" / "input.mp4"
    video.parent.mkdir()
    video.write_bytes(b"video-fixture")
    subtitle = tmp_path / "media" / "input.srt"
    subtitle.write_text(
        "1\n00:00:00,000 --> 00:00:00,800\nOriginal\nTranslated\n",
        encoding="utf-8",
    )
    store = EditorProjectStore()
    project = store.create_from_media(str(video), str(subtitle), duration_ms=2000)
    cue = project.cues[0]
    cue.display_text = "Display only"
    cue.tts_text = "Spoken only"
    cue.voice_settings = {"model": "fake", "api_key": "secret"}
    project.layers.append(
        EditorLayer(
            "layer-text",
            EditorLayerKind.TEXT,
            0,
            1000,
            properties={"text": "Title"},
        )
    )

    project_path, srt_path = store.save(project, tmp_path / "project" / "demo.vceditor.json")
    payload = json.loads(Path(project_path).read_text(encoding="utf-8"))
    assert payload["schema_version"] == "editor-project-v1"
    assert not Path(payload["video_path"]).is_absolute()
    assert not Path(payload["subtitle_path"]).is_absolute()
    assert not Path(payload["tracks"][0]["clips"][0]["source_path"]).is_absolute()
    assert "api_key" not in payload["cues"][0]["voice_settings"]
    assert list(Path(project_path).parent.glob("*.ass")) == []
    assert "Display only" in Path(srt_path).read_text(encoding="utf-8")
    assert "Spoken only" not in Path(srt_path).read_text(encoding="utf-8")

    reopened = store.load(project_path)
    restored = reopened.cues[0]
    assert restored.source_text == "Original"
    assert restored.display_text == "Display only"
    assert restored.tts_text == "Spoken only"
    assert reopened.video_path == str(video.resolve())
    assert reopened.track_by_id("track-v1").clips[0].source_path == str(video.resolve())
    assert reopened.layers[0].properties["text"] == "Title"


def test_explicit_ass_is_the_only_persistent_ass_route(tmp_path):
    project = make_project()
    project.video_path = str(tmp_path / "input.mp4")
    Path(project.video_path).write_bytes(b"x")
    store = EditorProjectStore()
    store.save(project, tmp_path / "demo.vceditor.json", subtitle_path=tmp_path / "demo.srt")
    assert list(tmp_path.glob("*.ass")) == []
    ass_path = store.save_as_ass(project, tmp_path / "manual.ass")
    assert Path(ass_path).is_file()
    assert "[Events]" in Path(ass_path).read_text(encoding="utf-8")


def test_timeline_index_queries_only_visible_subset_for_1000_cues():
    cues = [
        EditorCue(
            f"cue-{index:04d}",
            index * 3600,
            index * 3600 + 1800,
            f"source {index}",
            f"display {index}",
            f"tts {index}",
        )
        for index in range(1000)
    ]
    index = TimelineIndex(cues)
    visible = index.visible(30 * 60 * 1000, 30 * 60 * 1000 + 10_000)
    assert 1 <= len(visible) <= 4
    assert len(index.cues) == 1000


def test_dubbing_adapter_preserves_source_display_tts_and_stable_ids():
    project = make_project()
    cues = project_to_dubbing_cues(project)
    assert [cue.cue_id for cue in cues] == ["cue-a", "cue-b"]
    assert cues[0].source_text == "source A"
    assert cues[0].subtitle_text == "display A"
    assert cues[0].tts_text == "tts A"


def test_visual_layers_are_undoable_and_round_trip_in_model():
    project = make_project()
    stack = CommandStack()
    layer = EditorLayer(
        "mask-1",
        EditorLayerKind.MASK,
        0,
        1000,
        properties={"mode": "solid", "color": "black"},
    )
    stack.execute(AddLayerCommand(project, layer))
    assert project.layer_by_id("mask-1").kind == EditorLayerKind.MASK
    assert stack.undo()
    assert project.layers == []
    assert stack.redo()
    restored = EditorProject.from_dict(project.to_dict())
    assert restored.layer_by_id("mask-1").properties["mode"] == "solid"

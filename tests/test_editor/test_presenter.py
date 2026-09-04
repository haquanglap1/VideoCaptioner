"""Unit tests for the Qt-independent editor presenter."""

from pathlib import Path

import pytest

from videocaptioner.core.editor import presenter
from videocaptioner.core.editor.commands import (
    CommandStack,
    EditCueSpeakerCommand,
    EditCueTextCommand,
    EditCueTimingCommand,
    EditTrackStateCommand,
    EditVoiceSettingsCommand,
)
from videocaptioner.core.editor.models import (
    EditorCue,
    EditorLayer,
    EditorLayerKind,
    EditorProject,
)


def _project(duration_ms: int = 10_000) -> EditorProject:
    project = EditorProject.empty("C:/clips/talk.mp4", duration_ms)
    project.cues = [
        EditorCue("cue-a", 1000, 2000, "source", "display", "tts"),
        EditorCue("cue-b", 2300, 3300, "source 2", "display 2", "tts 2", speaker="A"),
    ]
    project.validate_all_cues()
    return project


# --------------------------------------------------------------------- cues


def test_new_cue_span_uses_up_to_one_second_before_next_cue():
    project = _project()
    assert presenter.new_cue_span(project, 0) == (0, 1000)
    assert presenter.new_cue_span(project, 2050) == (2050, 2300)
    assert presenter.new_cue_span(project, 9500) == (9500, 10_000)


def test_new_cue_span_rejects_playhead_inside_cue_or_without_room():
    project = _project()
    with pytest.raises(presenter.CuePlacementError) as inside:
        presenter.new_cue_span(project, 1500)
    assert inside.value.reason == "inside_cue"
    with pytest.raises(presenter.CuePlacementError) as cramped:
        presenter.new_cue_span(project, 2270)
    assert cramped.value.reason == "no_space"


def test_new_cue_is_a_placeholder_with_fresh_id():
    project = _project()
    cue = presenter.new_cue(project, 4000)
    assert cue.id.startswith("cue-") and cue.id not in {"cue-a", "cue-b"}
    assert (cue.start_ms, cue.end_ms) == (4000, 5000)
    assert (cue.source_text, cue.display_text, cue.tts_text) == ("", "New subtitle", "New subtitle")


def test_split_position_prefers_playhead_inside_margins():
    cue = EditorCue("cue-a", 1000, 2000, "s", "d", "t")
    assert presenter.split_position(cue, 1500) == 1500
    assert presenter.split_position(cue, 1050) == 1050
    assert presenter.split_position(cue, 1049) == 1500
    assert presenter.split_position(cue, 1951) == 1500
    assert presenter.split_position(cue, 5000) == 1500


def _values(cue: EditorCue, **overrides):
    values = {
        "start_ms": cue.start_ms,
        "end_ms": cue.end_ms,
        "source_text": cue.source_text,
        "display_text": cue.display_text,
        "tts_text": cue.tts_text,
        "speaker": cue.speaker,
        "voice": cue.voice,
        "voice_speed": cue.voice_speed,
    }
    values.update(overrides)
    return values


def test_inspector_commands_only_for_changed_fields():
    project = _project()
    cue = project.cue_by_id("cue-b")
    assert presenter.inspector_commands(project, "cue-b", _values(cue)) == []

    commands = presenter.inspector_commands(
        project,
        "cue-b",
        _values(cue, end_ms=3500, display_text="edited", speaker="B", voice_speed=1.2),
    )
    kinds = [type(command) for command in commands]
    assert kinds == [
        EditCueTimingCommand,
        EditCueTextCommand,
        EditCueSpeakerCommand,
        EditVoiceSettingsCommand,
    ]
    stack = CommandStack()
    for command in commands:
        stack.execute(command)
    assert cue.end_ms == 3500
    assert cue.display_text == "edited"
    assert cue.speaker == "B"
    assert cue.voice_speed == 1.2


def test_inspector_commands_unknown_cue_raises():
    with pytest.raises(KeyError):
        presenter.inspector_commands(_project(), "cue-zzz", {})


# ------------------------------------------------------------------- tracks


def test_track_state_command_covers_every_flag_and_rejects_others():
    project = _project()
    track_id = project.tracks[0].id
    for field_name in ("muted", "locked", "visible"):
        command = presenter.track_state_command(project, track_id, field_name, True)
        assert isinstance(command, EditTrackStateCommand)
    with pytest.raises(ValueError):
        presenter.track_state_command(project, track_id, "solo", True)


def test_track_locked_tolerates_missing_project_or_track():
    project = _project()
    assert presenter.track_locked(None, presenter.FX_TRACK_ID) is False
    assert presenter.track_locked(project, "track-nope") is False
    fx = project.track_by_id(presenter.FX_TRACK_ID)
    fx.locked = True
    assert presenter.track_locked(project, presenter.FX_TRACK_ID) is True


# ------------------------------------------------------------------- layers


def test_layer_range_prefers_non_empty_selection():
    project = _project()
    project.playhead_ms = 8000
    assert presenter.layer_range(project) == (8000, 10_000)
    project.selection_start_ms, project.selection_end_ms = 500, 400
    assert presenter.layer_range(project) == (8000, 10_000)
    project.selection_start_ms, project.selection_end_ms = 500, 900
    assert presenter.layer_range(project) == (500, 900)


def test_unique_layer_name_counts_up():
    assert presenter.unique_layer_name([], "Blur") == "Blur"
    assert presenter.unique_layer_name(["Blur"], "Blur") == "Blur 2"
    assert presenter.unique_layer_name(["Blur", "Blur 2", "Blur 3"], "Blur") == "Blur 4"


def test_layer_properties_per_kind():
    assert presenter.layer_properties(EditorLayerKind.TEXT, "hi") == {
        "text": "hi",
        "font_size": 42,
        "font_color": "white",
        "outline_width": 2,
    }
    assert presenter.layer_properties(EditorLayerKind.LOGO, "C:/logo.png") == {"path": "C:/logo.png"}
    assert presenter.layer_properties(EditorLayerKind.MASK, "pixelate") == {
        "mode": "pixelate",
        "color": "black",
        "strength": 12,
    }
    assert presenter.layer_properties(EditorLayerKind.MASK, "bogus")["mode"] == "solid"
    assert presenter.layer_properties(EditorLayerKind.BLUR, 30) == {"strength": 30}
    assert presenter.layer_properties(EditorLayerKind.BLUR) == {"strength": 12}


def test_new_layer_gets_unique_name_and_id():
    project = _project()
    project.layers = [EditorLayer("layer-1", EditorLayerKind.BLUR, 0, 1000, name="Blur")]
    layer = presenter.new_layer(project, EditorLayerKind.BLUR, {"strength": 5}, 100, 900)
    assert layer.id.startswith("layer-") and layer.id != "layer-1"
    assert layer.name == "Blur 2"
    assert (layer.start_ms, layer.end_ms, layer.properties) == (100, 900, {"strength": 5})


def test_layer_index_and_pending_changes_and_label():
    project = _project()
    hidden = EditorLayer("layer-2", EditorLayerKind.TEXT, 1500, 2250, name="Text", visible=False)
    project.layers = [
        EditorLayer("layer-1", EditorLayerKind.BLUR, 0, 1000, name="Blur"),
        hidden,
    ]
    assert presenter.layer_index(project, "layer-2") == 1
    assert presenter.layer_index(project, "layer-x") == -1
    assert presenter.layer_pending_changes(hidden, {"name": "Text", "opacity": 0.5, "x": 0.25}) == {
        "opacity": 0.5
    }
    assert presenter.layer_list_label(project.layers[0]) == "BLUR  0.00s\u20131.00s  Blur"
    assert presenter.layer_list_label(hidden) == "TEXT  1.50s\u20132.25s  Text  \u00b7"


# -------------------------------------------------------------------- paths


def test_suggested_paths_sit_next_to_the_video():
    video = "C:/clips/talk.mp4"
    assert presenter.suggested_project_path(video).endswith("talk.vceditor.json")
    assert presenter.suggested_ass_path(video).endswith("talk.ass")
    assert presenter.suggested_export_path(video).endswith("talk-edited.mp4")
    assert Path(presenter.suggested_export_path(video)).parent == Path("C:/clips")


def test_preview_output_path_is_per_project_and_signature(tmp_path):
    path = presenter.preview_output_path(tmp_path, "proj-1", "abc")
    assert path == tmp_path / "editor_preview" / "proj-1" / "preview-abc.mp4"

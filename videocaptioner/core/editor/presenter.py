"""Qt-independent decisions behind the Video Editor view.

The view owns widgets, dialogs and worker threads. The placement, naming and
change-detection rules below only need the project model, so they live here
and are unit-tested without a QApplication.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
from uuid import uuid4

from videocaptioner.core.editor.commands import (
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
from videocaptioner.core.editor.project_store import EditorProjectStore

FX_TRACK_ID = "track-fx1"
NEW_CUE_TEXT = "New subtitle"
NEW_CUE_MAX_MS = 1000
NEW_CUE_MIN_MS = 50
SPLIT_MARGIN_MS = 50
LAYER_DEFAULT_SPAN_MS = 5000
CUE_TEXT_FIELDS: Tuple[str, ...] = ("source_text", "display_text", "tts_text")
MASK_MODES: Tuple[str, ...] = ("solid", "pixelate", "blur")
DEFAULT_BLUR_STRENGTH = 12
TRACK_STATE_FIELDS: Tuple[str, ...] = ("muted", "locked", "visible")


class CuePlacementError(ValueError):
    """No room for a new cue; ``reason`` is ``inside_cue`` or ``no_space``."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


# --------------------------------------------------------------------- cues


def new_cue_span(project: EditorProject, position_ms: int) -> Tuple[int, int]:
    """Free slot starting at the playhead: up to 1 s, never overlapping a cue."""
    if project.active_cue_at(position_ms):
        raise CuePlacementError("inside_cue")
    previous_end = max((cue.end_ms for cue in project.cues if cue.end_ms <= position_ms), default=0)
    next_start = min(
        (cue.start_ms for cue in project.cues if cue.start_ms >= position_ms),
        default=project.duration_ms,
    )
    start = max(position_ms, previous_end)
    end = min(next_start, start + NEW_CUE_MAX_MS)
    if end - start < NEW_CUE_MIN_MS:
        raise CuePlacementError("no_space")
    return start, end


def new_cue(project: EditorProject, position_ms: int, text: str = NEW_CUE_TEXT) -> EditorCue:
    """A placeholder cue in the free slot at ``position_ms`` (see ``new_cue_span``)."""
    start, end = new_cue_span(project, position_ms)
    return EditorCue(f"cue-{uuid4().hex[:16]}", start, end, "", text, text)


def split_position(cue: EditorCue, playhead_ms: int) -> int:
    """Split at the playhead when it leaves both halves >= 50 ms, else at the middle."""
    if cue.start_ms + SPLIT_MARGIN_MS <= playhead_ms <= cue.end_ms - SPLIT_MARGIN_MS:
        return playhead_ms
    return cue.start_ms + cue.duration_ms // 2


def inspector_commands(project: EditorProject, cue_id: str, values: Dict[str, Any]) -> List[Any]:
    """Commands for the inspector fields that actually differ from the cue."""
    cue = project.cue_by_id(cue_id)
    commands: List[Any] = []
    if (cue.start_ms, cue.end_ms) != (values["start_ms"], values["end_ms"]):
        commands.append(EditCueTimingCommand(project, cue_id, values["start_ms"], values["end_ms"]))
    for field_name in CUE_TEXT_FIELDS:
        if getattr(cue, field_name) != values[field_name]:
            commands.append(EditCueTextCommand(project, cue_id, field_name, values[field_name]))
    if cue.speaker != values["speaker"]:
        commands.append(EditCueSpeakerCommand(project, cue_id, values["speaker"]))
    if cue.voice != values["voice"] or cue.voice_speed != values["voice_speed"]:
        commands.append(
            EditVoiceSettingsCommand(
                project,
                cue_id,
                values["voice"],
                values["voice_speed"],
                dict(cue.voice_settings),
            )
        )
    return commands


# ------------------------------------------------------------------- tracks


def track_state_command(
    project: EditorProject, track_id: str, field_name: str, value: bool
) -> EditTrackStateCommand:
    if field_name == "muted":
        return EditTrackStateCommand(project, track_id, muted=value)
    if field_name == "locked":
        return EditTrackStateCommand(project, track_id, locked=value)
    if field_name == "visible":
        return EditTrackStateCommand(project, track_id, visible=value)
    raise ValueError(f"Unsupported track state: {field_name}")


def track_locked(project: Optional[EditorProject], track_id: str) -> bool:
    if project is None:
        return False
    try:
        return project.track_by_id(track_id).locked
    except KeyError:
        return False


# ------------------------------------------------------------------- layers


def layer_range(project: EditorProject) -> Tuple[int, int]:
    """The selected range when it is non-empty, else 5 s from the playhead."""
    if (
        project.selection_start_ms is not None
        and project.selection_end_ms is not None
        and project.selection_end_ms > project.selection_start_ms
    ):
        return project.selection_start_ms, project.selection_end_ms
    start = project.playhead_ms
    return start, min(project.duration_ms, start + LAYER_DEFAULT_SPAN_MS)


def unique_layer_name(existing: Iterable[str], base: str) -> str:
    names = set(existing)
    if base not in names:
        return base
    index = 2
    while f"{base} {index}" in names:
        index += 1
    return f"{base} {index}"


def layer_properties(kind: EditorLayerKind, value: Any = None) -> Dict[str, Any]:
    """Initial properties for a layer from the single value the dialog asks for."""
    if kind == EditorLayerKind.TEXT:
        return {"text": str(value or ""), "font_size": 42, "font_color": "white", "outline_width": 2}
    if kind == EditorLayerKind.LOGO:
        return {"path": str(value or "")}
    if kind == EditorLayerKind.MASK:
        mode = value if value in MASK_MODES else MASK_MODES[0]
        return {"mode": mode, "color": "black", "strength": DEFAULT_BLUR_STRENGTH}
    strength = DEFAULT_BLUR_STRENGTH if value is None else int(value)
    return {"strength": strength}


def new_layer(
    project: EditorProject,
    kind: EditorLayerKind,
    properties: Dict[str, Any],
    start_ms: int,
    end_ms: int,
) -> EditorLayer:
    """A layer with a fresh id and a name unique among the project's layers."""
    return EditorLayer(
        f"layer-{uuid4().hex[:12]}",
        kind,
        start_ms,
        end_ms,
        name=unique_layer_name((layer.name for layer in project.layers), kind.value.title()),
        properties=properties,
    )


def layer_index(project: EditorProject, layer_id: str) -> int:
    for position, layer in enumerate(project.layers):
        if layer.id == layer_id:
            return position
    return -1


def layer_pending_changes(layer: EditorLayer, changes: Dict[str, Any]) -> Dict[str, Any]:
    """Only the inspector fields whose value differs from the layer."""
    return {key: value for key, value in changes.items() if getattr(layer, key, None) != value}


def layer_list_label(layer: EditorLayer) -> str:
    """Row text for the layer panel; a trailing dot marks hidden layers."""
    return (
        f"{layer.kind.value.upper()}  {layer.start_ms / 1000:.2f}s–"
        f"{layer.end_ms / 1000:.2f}s  {layer.name}"
        + ("" if layer.visible else "  ·")
    )


# -------------------------------------------------------------------- paths


def suggested_project_path(video_path: str) -> str:
    return str(Path(video_path).with_suffix(EditorProjectStore.project_suffix))


def suggested_ass_path(video_path: str) -> str:
    return str(Path(video_path).with_suffix(".ass"))


def suggested_export_path(video_path: str) -> str:
    video = Path(video_path)
    return str(video.with_name(video.stem + "-edited.mp4"))


def preview_output_path(cache_root: Path, project_id: str, signature: str) -> Path:
    """Per-project preview file; the signature keeps stale renders apart."""
    return Path(cache_root) / "editor_preview" / project_id / f"preview-{signature}.mp4"

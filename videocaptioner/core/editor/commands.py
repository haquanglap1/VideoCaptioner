"""Undoable commands; every editor mutation flows through :class:`CommandStack`."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol
from uuid import uuid4

from .models import EditorCue, EditorLayer, EditorProject


class EditorCommand(Protocol):
    description: str

    def execute(self) -> None: ...

    def undo(self) -> None: ...


class CommandStack:
    def __init__(self, *, limit: int = 200):
        self.limit = max(1, int(limit))
        self._undo: list[EditorCommand] = []
        self._redo: list[EditorCommand] = []
        self._callbacks: list[Callable[[], None]] = []

    def add_changed_callback(self, callback: Callable[[], None]) -> None:
        self._callbacks.append(callback)

    def _changed(self) -> None:
        for callback in tuple(self._callbacks):
            callback()

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)

    @property
    def undo_description(self) -> str:
        return self._undo[-1].description if self._undo else ""

    @property
    def redo_description(self) -> str:
        return self._redo[-1].description if self._redo else ""

    def execute(self, command: EditorCommand) -> None:
        command.execute()
        self._undo.append(command)
        if len(self._undo) > self.limit:
            self._undo.pop(0)
        self._redo.clear()
        self._changed()

    def undo(self) -> bool:
        if not self._undo:
            return False
        command = self._undo.pop()
        command.undo()
        self._redo.append(command)
        self._changed()
        return True

    def redo(self) -> bool:
        if not self._redo:
            return False
        command = self._redo.pop()
        command.execute()
        self._undo.append(command)
        self._changed()
        return True

    def clear(self) -> None:
        self._undo.clear()
        self._redo.clear()
        self._changed()


@dataclass
class CompositeCommand:
    commands: list[EditorCommand]
    description: str = "Edit cue"

    def execute(self) -> None:
        completed: list[EditorCommand] = []
        try:
            for command in self.commands:
                command.execute()
                completed.append(command)
        except Exception:
            for command in reversed(completed):
                command.undo()
            raise

    def undo(self) -> None:
        for command in reversed(self.commands):
            command.undo()


@dataclass
class EditCueTextCommand:
    project: EditorProject
    cue_id: str
    field_name: str
    new_text: str
    description: str = "Edit cue text"
    _old_text: str | None = field(default=None, init=False)

    def execute(self) -> None:
        if self.field_name not in {"source_text", "display_text", "tts_text"}:
            raise ValueError(f"Unsupported cue text field: {self.field_name}")
        cue = self.project.cue_by_id(self.cue_id)
        if self._old_text is None:
            self._old_text = str(getattr(cue, self.field_name))
        setattr(cue, self.field_name, str(self.new_text))
        self.project.touch()

    def undo(self) -> None:
        cue = self.project.cue_by_id(self.cue_id)
        setattr(cue, self.field_name, self._old_text or "")
        self.project.touch()


@dataclass
class EditCueSpeakerCommand:
    project: EditorProject
    cue_id: str
    speaker: str
    description: str = "Edit cue speaker"
    _old: str | None = field(default=None, init=False)

    def execute(self) -> None:
        cue = self.project.cue_by_id(self.cue_id)
        if self._old is None:
            self._old = cue.speaker
        cue.speaker = str(self.speaker)
        self.project.touch()

    def undo(self) -> None:
        self.project.cue_by_id(self.cue_id).speaker = self._old or ""
        self.project.touch()


@dataclass
class EditCueTimingCommand:
    project: EditorProject
    cue_id: str
    start_ms: int
    end_ms: int
    description: str = "Edit cue timing"
    _old_timing: tuple[int, int] | None = field(default=None, init=False)

    def execute(self) -> None:
        cue = self.project.cue_by_id(self.cue_id)
        if self._old_timing is None:
            self._old_timing = (cue.start_ms, cue.end_ms)
        self.project.validate_cue_timing(self.start_ms, self.end_ms, excluding_id=cue.id)
        cue.start_ms = int(self.start_ms)
        cue.end_ms = int(self.end_ms)
        self.project.cues.sort(key=lambda item: (item.start_ms, item.end_ms, item.id))
        self.project.touch()

    def undo(self) -> None:
        if self._old_timing is None:
            return
        cue = self.project.cue_by_id(self.cue_id)
        cue.start_ms, cue.end_ms = self._old_timing
        self.project.cues.sort(key=lambda item: (item.start_ms, item.end_ms, item.id))
        self.project.touch()


class MoveCueCommand(EditCueTimingCommand):
    description = "Move cue"

    def __init__(self, project: EditorProject, cue_id: str, new_start_ms: int):
        cue = project.cue_by_id(cue_id)
        super().__init__(project, cue_id, int(new_start_ms), int(new_start_ms) + cue.duration_ms)
        self.description = "Move cue"


class ResizeCueCommand(EditCueTimingCommand):
    description = "Resize cue"

    def __init__(
        self,
        project: EditorProject,
        cue_id: str,
        *,
        new_start_ms: int | None = None,
        new_end_ms: int | None = None,
    ):
        cue = project.cue_by_id(cue_id)
        super().__init__(
            project,
            cue_id,
            cue.start_ms if new_start_ms is None else int(new_start_ms),
            cue.end_ms if new_end_ms is None else int(new_end_ms),
        )
        self.description = "Resize cue"


@dataclass
class AddCueCommand:
    project: EditorProject
    cue: EditorCue
    description: str = "Add cue"

    def execute(self) -> None:
        if any(item.id == self.cue.id for item in self.project.cues):
            raise ValueError(f"Duplicate cue ID: {self.cue.id}")
        self.project.validate_cue_timing(self.cue.start_ms, self.cue.end_ms)
        self.project.cues.append(self.cue)
        self.project.cues.sort(key=lambda item: (item.start_ms, item.end_ms, item.id))
        self.project.touch()

    def undo(self) -> None:
        self.project.cues.remove(self.project.cue_by_id(self.cue.id))
        self.project.touch()


@dataclass
class DeleteCueCommand:
    project: EditorProject
    cue_id: str
    description: str = "Delete cue"
    _cue: EditorCue | None = field(default=None, init=False)

    def execute(self) -> None:
        cue = self.project.cue_by_id(self.cue_id)
        if self._cue is None:
            self._cue = cue
        self.project.cues.remove(cue)
        self.project.touch()

    def undo(self) -> None:
        if self._cue is None:
            return
        if any(item.id == self._cue.id for item in self.project.cues):
            return
        self.project.cues.append(self._cue)
        self.project.cues.sort(key=lambda item: (item.start_ms, item.end_ms, item.id))
        self.project.touch()


def _split_text(text: str) -> tuple[str, str]:
    words = text.split()
    if len(words) < 2:
        return text, text
    split_at = max(1, len(words) // 2)
    return " ".join(words[:split_at]), " ".join(words[split_at:])


@dataclass
class SplitCueCommand:
    project: EditorProject
    cue_id: str
    split_ms: int
    description: str = "Split cue"
    _original: EditorCue | None = field(default=None, init=False)
    _right: EditorCue | None = field(default=None, init=False)

    def execute(self) -> None:
        cue = self.project.cue_by_id(self.cue_id)
        split_ms = int(self.split_ms)
        if split_ms - cue.start_ms < 50 or cue.end_ms - split_ms < 50:
            raise ValueError("Split point must leave at least 50 ms on both sides")
        if self._original is None:
            self._original = deepcopy(cue)
            source_left, source_right = _split_text(cue.source_text)
            display_left, display_right = _split_text(cue.display_text)
            tts_left, tts_right = _split_text(cue.tts_text)
            self._right = deepcopy(cue)
            self._right.id = f"cue-{uuid4().hex[:16]}"
            self._right.start_ms = split_ms
            self._right.source_text = source_right
            self._right.display_text = display_right
            self._right.tts_text = tts_right
            self._right.audio_path = ""
            self._right.group_id = ""
            self._right.fit_status = "pending"
            cue.source_text = source_left
            cue.display_text = display_left
            cue.tts_text = tts_left
        else:
            assert self._right is not None
            cue.source_text, _ = _split_text(self._original.source_text)
            cue.display_text, _ = _split_text(self._original.display_text)
            cue.tts_text, _ = _split_text(self._original.tts_text)
        cue.end_ms = split_ms
        cue.audio_path = ""
        cue.group_id = ""
        cue.fit_status = "pending"
        assert self._right is not None
        if not any(item.id == self._right.id for item in self.project.cues):
            self.project.cues.append(self._right)
        self.project.cues.sort(key=lambda item: (item.start_ms, item.end_ms, item.id))
        self.project.touch()

    def undo(self) -> None:
        if self._original is None or self._right is None:
            return
        index = self.project.cue_index(self.cue_id)
        self.project.cues[index] = deepcopy(self._original)
        self.project.cues = [item for item in self.project.cues if item.id != self._right.id]
        self.project.cues.sort(key=lambda item: (item.start_ms, item.end_ms, item.id))
        self.project.touch()


@dataclass
class EditVoiceSettingsCommand:
    project: EditorProject
    cue_id: str
    voice: str
    voice_speed: float
    settings: dict[str, Any]
    description: str = "Edit voice settings"
    _old: tuple[str, float, dict[str, Any]] | None = field(default=None, init=False)

    def execute(self) -> None:
        if not 0.25 <= float(self.voice_speed) <= 4.0:
            raise ValueError("Voice speed must be between 0.25 and 4.0")
        cue = self.project.cue_by_id(self.cue_id)
        if self._old is None:
            self._old = (cue.voice, cue.voice_speed, deepcopy(cue.voice_settings))
        cue.voice = str(self.voice)
        cue.voice_speed = float(self.voice_speed)
        cue.voice_settings = deepcopy(self.settings)
        cue.audio_path = ""
        cue.fit_status = "pending"
        self.project.touch()

    def undo(self) -> None:
        if self._old is None:
            return
        cue = self.project.cue_by_id(self.cue_id)
        cue.voice, cue.voice_speed, cue.voice_settings = deepcopy(self._old)
        cue.audio_path = ""
        cue.fit_status = "pending"
        self.project.touch()


@dataclass
class EditTrackStateCommand:
    project: EditorProject
    track_id: str
    muted: bool | None = None
    locked: bool | None = None
    visible: bool | None = None
    description: str = "Edit track state"
    _old: tuple[bool, bool, bool] | None = field(default=None, init=False)

    def execute(self) -> None:
        track = self.project.track_by_id(self.track_id)
        if self._old is None:
            self._old = (track.muted, track.locked, track.visible)
        if self.muted is not None:
            track.muted = bool(self.muted)
        if self.locked is not None:
            track.locked = bool(self.locked)
        if self.visible is not None:
            track.visible = bool(self.visible)
        self.project.touch()

    def undo(self) -> None:
        if self._old is None:
            return
        track = self.project.track_by_id(self.track_id)
        track.muted, track.locked, track.visible = self._old
        self.project.touch()


@dataclass
class AddLayerCommand:
    project: EditorProject
    layer: EditorLayer
    description: str = "Add visual layer"

    def execute(self) -> None:
        if any(item.id == self.layer.id for item in self.project.layers):
            raise ValueError(f"Duplicate layer ID: {self.layer.id}")
        if self.layer.start_ms < 0 or self.layer.end_ms <= self.layer.start_ms:
            raise ValueError("Invalid visual layer timing")
        self.project.layers.append(self.layer)
        self.project.touch()

    def undo(self) -> None:
        self.project.layers.remove(self.project.layer_by_id(self.layer.id))
        self.project.touch()


@dataclass
class EditLayerCommand:
    project: EditorProject
    layer_id: str
    changes: dict[str, Any]
    description: str = "Edit visual layer"
    _old: dict[str, Any] | None = field(default=None, init=False)

    def execute(self) -> None:
        layer = self.project.layer_by_id(self.layer_id)
        allowed = {
            "start_ms", "end_ms", "name", "visible", "locked", "opacity",
            "x", "y", "width", "height", "properties",
        }
        unknown = set(self.changes) - allowed
        if unknown:
            raise ValueError(f"Unsupported visual layer fields: {sorted(unknown)}")
        if self._old is None:
            self._old = {key: deepcopy(getattr(layer, key)) for key in self.changes}
        for key, value in self.changes.items():
            setattr(layer, key, deepcopy(value))
        if layer.start_ms < 0 or layer.end_ms <= layer.start_ms:
            if self._old:
                for key, value in self._old.items():
                    setattr(layer, key, deepcopy(value))
            raise ValueError("Invalid visual layer timing")
        self.project.touch()

    def undo(self) -> None:
        if self._old is None:
            return
        layer = self.project.layer_by_id(self.layer_id)
        for key, value in self._old.items():
            setattr(layer, key, deepcopy(value))
        self.project.touch()


@dataclass
class DeleteLayerCommand:
    project: EditorProject
    layer_id: str
    description: str = "Delete visual layer"
    _layer: EditorLayer | None = field(default=None, init=False)

    def execute(self) -> None:
        layer = self.project.layer_by_id(self.layer_id)
        if self._layer is None:
            self._layer = layer
        self.project.layers.remove(layer)
        self.project.touch()

    def undo(self) -> None:
        if self._layer and not any(item.id == self._layer.id for item in self.project.layers):
            self.project.layers.append(self._layer)
            self.project.touch()

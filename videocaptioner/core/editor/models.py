"""Qt-independent, versioned domain models for the Video Editor."""

from __future__ import annotations

import hashlib
from bisect import bisect_right
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Iterable
from uuid import uuid4

EDITOR_PROJECT_SCHEMA = "editor-project-v1"
MIN_CUE_DURATION_MS = 50


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def stable_cue_id(index: int, start_ms: int, end_ms: int, text: str) -> str:
    """Return a content-derived opaque ID for first import; persisted IDs never change."""
    payload = f"{index}\0{start_ms}\0{end_ms}\0{text}".encode("utf-8", errors="replace")
    return f"cue-{hashlib.sha256(payload).hexdigest()[:16]}"


class _StringEnum(str, Enum):
    def __str__(self) -> str:
        return self.value


class EditorTrackKind(_StringEnum):
    VIDEO = "video"
    AUDIO = "audio"
    SUBTITLE_TTS = "subtitle_tts"
    VISUAL = "visual"


class EditorLayerKind(_StringEnum):
    BLUR = "blur"
    LOGO = "logo"
    MASK = "mask"
    TEXT = "text"


@dataclass
class EditorClip:
    id: str
    start_ms: int
    end_ms: int
    source_path: str = ""
    label: str = ""

    @property
    def duration_ms(self) -> int:
        return max(0, self.end_ms - self.start_ms)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EditorClip":
        return cls(
            id=str(data.get("id", f"clip-{uuid4().hex[:12]}")),
            start_ms=int(data.get("start_ms", 0)),
            end_ms=int(data.get("end_ms", 0)),
            source_path=str(data.get("source_path", "")),
            label=str(data.get("label", "")),
        )


@dataclass
class EditorTrack:
    id: str
    name: str
    kind: EditorTrackKind
    muted: bool = False
    locked: bool = False
    visible: bool = True
    clips: list[EditorClip] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["kind"] = self.kind.value
        data["clips"] = [clip.to_dict() for clip in self.clips]
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EditorTrack":
        return cls(
            id=str(data.get("id", "")),
            name=str(data.get("name", "")),
            kind=EditorTrackKind(data.get("kind", EditorTrackKind.VIDEO.value)),
            muted=bool(data.get("muted", False)),
            locked=bool(data.get("locked", False)),
            visible=bool(data.get("visible", True)),
            clips=[EditorClip.from_dict(item) for item in data.get("clips", [])],
        )


@dataclass
class EditorCue:
    id: str
    start_ms: int
    end_ms: int
    source_text: str
    display_text: str
    tts_text: str
    speaker: str = ""
    voice: str = ""
    voice_speed: float = 1.0
    voice_settings: dict[str, Any] = field(default_factory=dict)
    audio_path: str = ""
    group_id: str = ""
    fit_status: str = "pending"
    fit_ratio: float = 0.0
    warnings: list[str] = field(default_factory=list)

    @property
    def duration_ms(self) -> int:
        return max(0, self.end_ms - self.start_ms)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["voice_settings"] = sanitize_voice_settings(self.voice_settings)
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EditorCue":
        display = str(data.get("display_text", data.get("subtitle_text", "")))
        return cls(
            id=str(data.get("id", f"cue-{uuid4().hex[:16]}")),
            start_ms=int(data.get("start_ms", 0)),
            end_ms=int(data.get("end_ms", 0)),
            source_text=str(data.get("source_text", "")),
            display_text=display,
            tts_text=str(data.get("tts_text", display)),
            speaker=str(data.get("speaker", "")),
            voice=str(data.get("voice", "")),
            voice_speed=float(data.get("voice_speed", 1.0)),
            voice_settings=sanitize_voice_settings(dict(data.get("voice_settings", {}) or {})),
            audio_path=str(data.get("audio_path", "")),
            group_id=str(data.get("group_id", "")),
            fit_status=str(data.get("fit_status", "pending")),
            fit_ratio=float(data.get("fit_ratio", 0.0) or 0.0),
            warnings=[str(item) for item in data.get("warnings", [])],
        )


@dataclass
class EditorLayer:
    id: str
    kind: EditorLayerKind
    start_ms: int
    end_ms: int
    name: str = ""
    visible: bool = True
    locked: bool = False
    opacity: float = 1.0
    x: float = 0.25
    y: float = 0.25
    width: float = 0.5
    height: float = 0.25
    properties: dict[str, Any] = field(default_factory=dict)

    @property
    def duration_ms(self) -> int:
        return max(0, self.end_ms - self.start_ms)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["kind"] = self.kind.value
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EditorLayer":
        return cls(
            id=str(data.get("id", f"layer-{uuid4().hex[:12]}")),
            kind=EditorLayerKind(data.get("kind", EditorLayerKind.TEXT.value)),
            start_ms=int(data.get("start_ms", 0)),
            end_ms=int(data.get("end_ms", 0)),
            name=str(data.get("name", "")),
            visible=bool(data.get("visible", True)),
            locked=bool(data.get("locked", False)),
            opacity=max(0.0, min(1.0, float(data.get("opacity", 1.0)))),
            x=max(0.0, min(1.0, float(data.get("x", 0.25)))),
            y=max(0.0, min(1.0, float(data.get("y", 0.25)))),
            width=max(0.001, min(1.0, float(data.get("width", 0.5)))),
            height=max(0.001, min(1.0, float(data.get("height", 0.25)))),
            properties=dict(data.get("properties", {}) or {}),
        )


_SECRET_SETTING_PARTS = ("api_key", "apikey", "token", "secret", "password", "cookie")


def sanitize_voice_settings(settings: dict[str, Any]) -> dict[str, Any]:
    """Keep reproducible voice choices but never persist credentials."""
    return {
        str(key): value
        for key, value in settings.items()
        if not any(part in str(key).casefold() for part in _SECRET_SETTING_PARTS)
    }


def default_editor_tracks(video_path: str, duration_ms: int) -> list[EditorTrack]:
    duration_ms = max(0, int(duration_ms))
    video_clip = EditorClip("clip-v1", 0, duration_ms, video_path, "Video")
    audio_clip = EditorClip("clip-a1", 0, duration_ms, video_path, "Original Audio")
    return [
        EditorTrack("track-v1", "V1 Video", EditorTrackKind.VIDEO, clips=[video_clip]),
        EditorTrack("track-a1", "A1 Original Audio", EditorTrackKind.AUDIO, clips=[audio_clip]),
        EditorTrack("track-ts1", "TS1 Subtitle + TTS", EditorTrackKind.SUBTITLE_TTS),
        EditorTrack("track-fx1", "FX1 Visual Layers", EditorTrackKind.VISUAL),
    ]


@dataclass
class EditorProject:
    project_id: str
    title: str
    video_path: str
    subtitle_path: str
    duration_ms: int
    width: int = 0
    height: int = 0
    fps: float = 0.0
    cues: list[EditorCue] = field(default_factory=list)
    tracks: list[EditorTrack] = field(default_factory=list)
    layers: list[EditorLayer] = field(default_factory=list)
    voice_settings: dict[str, Any] = field(default_factory=dict)
    playhead_ms: int = 0
    selection_start_ms: int | None = None
    selection_end_ms: int | None = None
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)
    schema_version: str = EDITOR_PROJECT_SCHEMA
    is_dirty: bool = field(default=False, repr=False, compare=False)
    _cue_index_cache: Any = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        self.duration_ms = max(0, int(self.duration_ms))
        if not self.tracks:
            self.tracks = default_editor_tracks(self.video_path, self.duration_ms)
        self.cues.sort(key=lambda cue: (cue.start_ms, cue.end_ms, cue.id))
        self.validate_all_cues()

    @classmethod
    def empty(cls, video_path: str = "", duration_ms: int = 0) -> "EditorProject":
        title = Path(video_path).stem if video_path else "Untitled"
        return cls(
            project_id=f"project-{uuid4().hex}",
            title=title,
            video_path=video_path,
            subtitle_path="",
            duration_ms=duration_ms,
        )

    def cue_by_id(self, cue_id: str) -> EditorCue:
        for cue in self.cues:
            if cue.id == cue_id:
                return cue
        raise KeyError(f"Unknown editor cue: {cue_id}")

    def cue_index(self, cue_id: str) -> int:
        for index, cue in enumerate(self.cues):
            if cue.id == cue_id:
                return index
        raise KeyError(f"Unknown editor cue: {cue_id}")

    def track_by_id(self, track_id: str) -> EditorTrack:
        for track in self.tracks:
            if track.id == track_id:
                return track
        raise KeyError(f"Unknown editor track: {track_id}")

    def layer_by_id(self, layer_id: str) -> EditorLayer:
        for layer in self.layers:
            if layer.id == layer_id:
                return layer
        raise KeyError(f"Unknown editor layer: {layer_id}")

    def active_cue_at(self, position_ms: int) -> EditorCue | None:
        position_ms = int(position_ms)
        if self._cue_index_cache is None:
            self._cue_index_cache = TimelineIndex(self.cues)
        matches = self._cue_index_cache.visible(position_ms, position_ms + 1)
        return matches[0] if matches else None

    def validate_cue_timing(
        self,
        start_ms: int,
        end_ms: int,
        *,
        excluding_id: str = "",
    ) -> None:
        start_ms, end_ms = int(start_ms), int(end_ms)
        if start_ms < 0:
            raise ValueError("Cue start must be non-negative")
        if end_ms - start_ms < MIN_CUE_DURATION_MS:
            raise ValueError(f"Cue duration must be at least {MIN_CUE_DURATION_MS} ms")
        if self.duration_ms and end_ms > self.duration_ms:
            raise ValueError("Cue end exceeds video duration")
        for cue in self.cues:
            if cue.id == excluding_id:
                continue
            if start_ms < cue.end_ms and end_ms > cue.start_ms:
                raise ValueError(f"Cue timing overlaps {cue.id}")

    def validate_all_cues(self) -> None:
        previous: EditorCue | None = None
        for cue in sorted(self.cues, key=lambda item: (item.start_ms, item.end_ms, item.id)):
            if cue.start_ms < 0 or cue.end_ms - cue.start_ms < MIN_CUE_DURATION_MS:
                raise ValueError(f"Invalid timing for {cue.id}")
            if self.duration_ms and cue.end_ms > self.duration_ms:
                raise ValueError(f"Cue {cue.id} exceeds video duration")
            if previous and cue.start_ms < previous.end_ms:
                raise ValueError(f"Cue {cue.id} overlaps {previous.id}")
            previous = cue

    def touch(self) -> None:
        self.updated_at = utc_now_iso()
        self.is_dirty = True
        self._cue_index_cache = None

    def to_dict(self, *, video_path: str | None = None, subtitle_path: str | None = None) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "project_id": self.project_id,
            "title": self.title,
            "video_path": self.video_path if video_path is None else video_path,
            "subtitle_path": self.subtitle_path if subtitle_path is None else subtitle_path,
            "duration_ms": self.duration_ms,
            "width": self.width,
            "height": self.height,
            "fps": self.fps,
            "cues": [cue.to_dict() for cue in self.cues],
            "tracks": [track.to_dict() for track in self.tracks],
            "layers": [layer.to_dict() for layer in self.layers],
            "voice_settings": sanitize_voice_settings(self.voice_settings),
            "playhead_ms": self.playhead_ms,
            "selection_start_ms": self.selection_start_ms,
            "selection_end_ms": self.selection_end_ms,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EditorProject":
        schema = str(data.get("schema_version", ""))
        if schema != EDITOR_PROJECT_SCHEMA:
            raise ValueError(f"Unsupported editor project schema: {schema or '<missing>'}")
        return cls(
            project_id=str(data.get("project_id", f"project-{uuid4().hex}")),
            title=str(data.get("title", "Untitled")),
            video_path=str(data.get("video_path", "")),
            subtitle_path=str(data.get("subtitle_path", "")),
            duration_ms=int(data.get("duration_ms", 0)),
            width=int(data.get("width", 0)),
            height=int(data.get("height", 0)),
            fps=float(data.get("fps", 0.0)),
            cues=[EditorCue.from_dict(item) for item in data.get("cues", [])],
            tracks=[EditorTrack.from_dict(item) for item in data.get("tracks", [])],
            layers=[EditorLayer.from_dict(item) for item in data.get("layers", [])],
            voice_settings=sanitize_voice_settings(dict(data.get("voice_settings", {}) or {})),
            playhead_ms=int(data.get("playhead_ms", 0)),
            selection_start_ms=data.get("selection_start_ms"),
            selection_end_ms=data.get("selection_end_ms"),
            created_at=str(data.get("created_at", utc_now_iso())),
            updated_at=str(data.get("updated_at", utc_now_iso())),
            schema_version=schema,
        )


class TimelineIndex:
    """Immutable viewport index with O(log n + visible cues) queries."""

    def __init__(self, cues: Iterable[EditorCue]):
        self.cues = sorted(cues, key=lambda cue: (cue.start_ms, cue.end_ms, cue.id))
        self.starts = [cue.start_ms for cue in self.cues]
        self.prefix_max_ends: list[int] = []
        max_end = -1
        for cue in self.cues:
            max_end = max(max_end, cue.end_ms)
            self.prefix_max_ends.append(max_end)

    def visible(self, start_ms: int, end_ms: int) -> list[EditorCue]:
        if not self.cues or end_ms <= start_ms:
            return []
        first = bisect_right(self.prefix_max_ends, int(start_ms))
        last = bisect_right(self.starts, int(end_ms) - 1)
        if first >= last:
            return []
        return self.cues[first:last]

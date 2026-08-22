"""Native PyQt5 Video Editor widgets."""

from .layer_inspector import LayerInspector
from .subtitle_inspector import SubtitleInspector
from .timeline_view import EditorTimelineView
from .track_header import EditorTrackHeader
from .video_preview import EditorVideoPreview

__all__ = [
    "EditorTimelineView",
    "EditorTrackHeader",
    "EditorVideoPreview",
    "LayerInspector",
    "SubtitleInspector",
]

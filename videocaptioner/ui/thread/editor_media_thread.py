"""Background FFmpeg/editor workers. They emit data and never touch widgets."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from PyQt5.QtCore import QThread, pyqtSignal

from videocaptioner.core.editor.media import (
    EditorMediaCache,
    build_thumbnails,
    build_waveform,
    export_editor_video,
    probe_media,
    render_fast_preview,
)
from videocaptioner.core.editor.project_store import EditorProjectStore


class EditorMediaThread(QThread):
    completed = pyqtSignal(str, object)
    failed = pyqtSignal(str, str)

    def __init__(self, request_signature: str, action: str, payload: dict, parent=None):
        super().__init__(parent)
        self.request_signature = request_signature
        self.action = action
        self.payload = dict(payload)

    def run(self) -> None:
        try:
            if self.action == "open":
                video_path = str(self.payload["video_path"])
                subtitle_path = str(self.payload["subtitle_path"])
                info = probe_media(video_path)
                project = EditorProjectStore().create_from_media(
                    video_path,
                    subtitle_path,
                    duration_ms=info.duration_ms,
                    width=info.width,
                    height=info.height,
                    fps=info.fps,
                )
                for track in project.tracks:
                    for clip in track.clips:
                        clip.end_ms = info.duration_ms
                self.completed.emit(self.request_signature, project)
            elif self.action == "load-project":
                project = EditorProjectStore().load(str(self.payload["project_path"]))
                info = probe_media(project.video_path)
                project.duration_ms = info.duration_ms
                project.width = info.width
                project.height = info.height
                project.fps = info.fps
                self.completed.emit(self.request_signature, project)
            elif self.action == "waveform":
                cache = EditorMediaCache(self.payload.get("cache_root"))
                result = build_waveform(str(self.payload["video_path"]), cache=cache)
                self.completed.emit(self.request_signature, result)
            elif self.action == "thumbnails":
                cache = EditorMediaCache(self.payload.get("cache_root"))
                result = build_thumbnails(
                    str(self.payload["video_path"]),
                    duration_ms=int(self.payload.get("duration_ms", 0)),
                    cache=cache,
                )
                self.completed.emit(self.request_signature, result)
            else:
                raise ValueError(f"Unsupported editor media action: {self.action}")
        except Exception as exc:
            self.failed.emit(self.request_signature, str(exc))


class EditorRenderThread(QThread):
    progress = pyqtSignal(int, str)
    completed = pyqtSignal(str, str)
    failed = pyqtSignal(str, str)

    def __init__(
        self,
        request_signature: str,
        action: str,
        project,
        output_path: str,
        *,
        dubbing_config=None,
        parent=None,
    ):
        super().__init__(parent)
        self.request_signature = request_signature
        self.action = action
        self.project = deepcopy(project)
        self.output_path = str(output_path)
        self.dubbing_config = deepcopy(dubbing_config)

    def run(self) -> None:
        try:
            def callback(value, message):
                self.progress.emit(int(value), str(message))

            if self.action == "preview":
                output = render_fast_preview(self.project, self.output_path, callback=callback)
            elif self.action == "export":
                output = export_editor_video(
                    self.project,
                    self.output_path,
                    dubbing_config=self.dubbing_config,
                    callback=callback,
                )
            else:
                raise ValueError(f"Unsupported editor render action: {self.action}")
            if not Path(output).is_file():
                raise RuntimeError("Editor render did not create an output file")
            self.completed.emit(self.request_signature, output)
        except Exception as exc:
            self.failed.emit(self.request_signature, str(exc))

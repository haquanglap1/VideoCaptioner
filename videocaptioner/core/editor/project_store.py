"""Atomic project/SRT persistence for ``editor-project-v1``."""

from __future__ import annotations

import json
import os
from pathlib import Path
from uuid import uuid4

from videocaptioner.core.asr.asr_data import ASRData

from .adapters import cues_from_asr, project_to_asr
from .models import EDITOR_PROJECT_SCHEMA, EditorProject


class EditorProjectStore:
    project_suffix = ".vceditor.json"

    @staticmethod
    def _atomic_write(path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.parent / f".{path.name}.{os.getpid()}.{uuid4().hex}.tmp"
        try:
            with temp_path.open("w", encoding="utf-8", newline="\n") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, path)
        finally:
            temp_path.unlink(missing_ok=True)

    @staticmethod
    def _relative_path(path: str, base_dir: Path, *, required: bool = True) -> str:
        """Serialize relative when possible.

        ``required=False`` keeps an absolute path for satellite assets (logo images,
        cached TTS WAVs) that legitimately live on another drive — losing the whole
        save because a decoration is on ``C:`` is worse than one absolute entry.
        """
        if not path:
            return ""
        resolved = Path(path).resolve()
        try:
            relative = os.path.relpath(resolved, base_dir.resolve())
        except ValueError as exc:
            if required:
                raise ValueError(
                    "Editor project and referenced media must be on the same drive for relative paths"
                ) from exc
            return resolved.as_posix()
        if Path(relative).is_absolute():
            if required:
                raise ValueError("Editor project paths must be relative")
            return resolved.as_posix()
        return Path(relative).as_posix()

    @staticmethod
    def _resolved_path(path: str, base_dir: Path) -> str:
        return str((base_dir / Path(path)).resolve()) if path else ""

    def create_from_media(
        self,
        video_path: str,
        subtitle_path: str,
        *,
        duration_ms: int = 0,
        width: int = 0,
        height: int = 0,
        fps: float = 0.0,
    ) -> EditorProject:
        asr_data = ASRData.from_subtitle_file(subtitle_path)
        cues = cues_from_asr(asr_data)
        inferred_duration = max((cue.end_ms for cue in cues), default=0)
        project = EditorProject.empty(video_path, max(int(duration_ms), inferred_duration))
        project.subtitle_path = str(Path(subtitle_path).resolve())
        project.width = int(width)
        project.height = int(height)
        project.fps = float(fps)
        project.cues = cues
        project.validate_all_cues()
        project.is_dirty = False
        return project

    def save(
        self,
        project: EditorProject,
        project_path: str | Path,
        *,
        subtitle_path: str | Path | None = None,
    ) -> tuple[str, str]:
        project_file = Path(project_path).resolve()
        if not project_file.name.lower().endswith(self.project_suffix):
            project_file = project_file.with_name(project_file.stem + self.project_suffix)
        if subtitle_path is None:
            base_name = project_file.name[: -len(self.project_suffix)]
            subtitle_file = project_file.with_name(f"{base_name}.srt")
        else:
            subtitle_file = Path(subtitle_path).resolve()
        if subtitle_file.suffix.lower() != ".srt":
            raise ValueError("Normal editor save only persists an SRT subtitle artifact")

        project.validate_all_cues()
        display_srt = project_to_asr(project, display_only=True).to_srt()
        relative_video = self._relative_path(project.video_path, project_file.parent)
        relative_subtitle = self._relative_path(str(subtitle_file), project_file.parent)
        payload = project.to_dict(
            video_path=relative_video,
            subtitle_path=relative_subtitle,
        )
        for track in payload.get("tracks", []):
            for clip in track.get("clips", []):
                source_path = str(clip.get("source_path", ""))
                clip["source_path"] = self._relative_path(source_path, project_file.parent)
        for cue in payload.get("cues", []):
            audio_path = str(cue.get("audio_path", ""))
            cue["audio_path"] = self._relative_path(
                audio_path, project_file.parent, required=False
            )
        for layer in payload.get("layers", []):
            properties = layer.get("properties", {})
            asset_path = str(properties.get("path", ""))
            if asset_path:
                properties["path"] = self._relative_path(
                    asset_path, project_file.parent, required=False
                )
        payload["schema_version"] = EDITOR_PROJECT_SCHEMA
        serialized = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"

        self._atomic_write(subtitle_file, display_srt)
        self._atomic_write(project_file, serialized)
        project.subtitle_path = str(subtitle_file)
        project.is_dirty = False
        return str(project_file), str(subtitle_file)

    def load(self, project_path: str | Path) -> EditorProject:
        project_file = Path(project_path).resolve()
        data = json.loads(project_file.read_text(encoding="utf-8"))
        if data.get("schema_version") != EDITOR_PROJECT_SCHEMA:
            raise ValueError(
                f"Unsupported editor project schema: {data.get('schema_version', '<missing>')}"
            )
        data["video_path"] = self._resolved_path(str(data.get("video_path", "")), project_file.parent)
        data["subtitle_path"] = self._resolved_path(
            str(data.get("subtitle_path", "")), project_file.parent
        )
        for track in data.get("tracks", []):
            for clip in track.get("clips", []):
                clip["source_path"] = self._resolved_path(
                    str(clip.get("source_path", "")), project_file.parent
                )
        for cue in data.get("cues", []):
            cue["audio_path"] = self._resolved_path(
                str(cue.get("audio_path", "")), project_file.parent
            )
        for layer in data.get("layers", []):
            properties = layer.get("properties", {})
            if properties.get("path"):
                properties["path"] = self._resolved_path(
                    str(properties["path"]), project_file.parent
                )
        project = EditorProject.from_dict(data)
        project.is_dirty = False
        return project

    def save_as_ass(
        self,
        project: EditorProject,
        ass_path: str | Path,
        *,
        style_str: str | None = None,
    ) -> str:
        destination = Path(ass_path).resolve()
        if destination.suffix.lower() != ".ass":
            raise ValueError("Explicit ASS export requires an .ass destination")
        content = project_to_asr(project, display_only=True).to_ass(style_str=style_str)
        self._atomic_write(destination, content)
        return str(destination)

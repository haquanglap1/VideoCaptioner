"""Editor adapter for selected-group regeneration through ``DubbingEngine``."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from videocaptioner.core.dubbing.config import DubbingConfig
from videocaptioner.core.dubbing.engine import DubbingEngine

from .adapters import project_to_dubbing_cues, update_cues_from_groups
from .models import EditorProject


def regenerate_selected_voice(
    project: EditorProject,
    cue_ids: set[str],
    config: DubbingConfig,
    output_dir: str | Path,
    *,
    engine: DubbingEngine | None = None,
    callback: Callable[[int, str], None] | None = None,
):
    dubbing_engine = engine or DubbingEngine()
    groups = dubbing_engine.regenerate_groups(
        project_to_dubbing_cues(project),
        set(cue_ids),
        video_duration=project.duration_ms / 1000.0,
        config=config,
        output_dir=output_dir,
        callback=callback,
    )
    update_cues_from_groups(project, groups)
    return groups

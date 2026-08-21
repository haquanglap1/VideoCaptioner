"""Selected-group voice regeneration worker."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from PyQt5.QtCore import QThread, pyqtSignal

from videocaptioner.core.dubbing.engine import DubbingEngine
from videocaptioner.core.editor.adapters import project_to_dubbing_cues


class EditorVoiceThread(QThread):
    progress = pyqtSignal(int, str)
    completed = pyqtSignal(str, object)
    failed = pyqtSignal(str, str)

    def __init__(
        self,
        request_signature: str,
        project,
        cue_ids: set[str],
        config,
        output_dir: str | Path,
        parent=None,
    ):
        super().__init__(parent)
        self.request_signature = request_signature
        self.cues = project_to_dubbing_cues(deepcopy(project))
        self.duration = project.duration_ms / 1000.0
        self.cue_ids = set(cue_ids)
        self.config = deepcopy(config)
        self.output_dir = Path(output_dir)

    def run(self) -> None:
        try:
            engine = DubbingEngine()
            groups = engine.regenerate_groups(
                self.cues,
                set(self.cue_ids),
                video_duration=self.duration,
                config=self.config,
                output_dir=self.output_dir,
                callback=lambda value, message: self.progress.emit(int(value), str(message)),
            )
            self.completed.emit(self.request_signature, groups)
        except Exception as exc:
            self.failed.emit(self.request_signature, str(exc))

"""Capture a video's task settings on the GUI thread before queueing work."""

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path

from videocaptioner.core.entities import (
    BatchTaskType,
    DubbingTask,
    SubtitleTask,
    SynthesisTask,
    TranscribeTask,
)


@dataclass
class BatchPlan:
    transcribe: TranscribeTask | None = None
    subtitle: SubtitleTask | None = None
    dubbing: DubbingTask | None = None
    synthesis: SynthesisTask | None = None

    @classmethod
    def capture(cls, path: str, kind: BatchTaskType, factory, *, dub: bool, task_id: str):
        plan = cls()
        full = kind == BatchTaskType.FULL_PROCESS
        linked = kind in (BatchTaskType.FULL_PROCESS, BatchTaskType.TRANS_SUB)
        source = path
        legacy_source = None
        if kind not in (BatchTaskType.SUBTITLE, BatchTaskType.DUBBING):
            plan.transcribe = factory.create_transcribe_task(path, need_next_task=linked, task_id=task_id)
            if linked and plan.transcribe.output_path:
                legacy_source = plan.transcribe.output_path
                output = Path(plan.transcribe.output_path)
                identity = hashlib.sha256(os.path.normcase(str(Path(path).resolve())).encode()).hexdigest()[:12]
                # Equal basenames in different source folders must not share intermediate subtitles.
                plan.transcribe.output_path = str(output.parent.parent.with_name(
                    output.parent.parent.name + "-" + identity) / output.parent.name / output.name)
            source = plan.transcribe.output_path or path
        if linked or kind == BatchTaskType.SUBTITLE:
            plan.subtitle = factory.create_subtitle_task(source, path if linked else None,
                                                         need_next_task=linked, task_id=task_id)
            if legacy_source and plan.subtitle.output_path:
                plan.subtitle.reuse_output_path = str(Path(legacy_source).parent / Path(plan.subtitle.output_path).name)
        if kind == BatchTaskType.DUBBING or (full and dub):
            plan.dubbing = factory.create_dubbing_task(path, source, task_id=task_id)
        if full:
            video = plan.dubbing.output_path if plan.dubbing else path
            plan.synthesis = factory.create_synthesis_task(video, source, task_id=task_id, title_source=path)
            if plan.dubbing:
                plan.synthesis.output_directory = plan.dubbing.output_directory
            if plan.dubbing and plan.synthesis.synthesis_config.need_video and plan.dubbing.dubbing_config:
                plan.dubbing.dubbing_config.subtitle_mode = "none"
                plan.dubbing.dubbing_config.output_resolution = 0
                plan.dubbing.title_translation = None
        return plan

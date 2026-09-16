"""Stage subtitle files so cancellation during rendering publishes no partial output."""

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Callable, Iterable

from videocaptioner.core.asr.asr_data import ASRData
from videocaptioner.core.entities import SubtitleLayoutEnum


@dataclass(frozen=True)
class SubtitleOutput:
    path: str
    layout: SubtitleLayoutEnum = SubtitleLayoutEnum.ONLY_ORIGINAL
    style: str = ""


def publish_subtitles(data: ASRData, outputs: Iterable[SubtitleOutput], cancelled: Callable[[], bool],
                      commit_lock: Lock) -> bool:
    staged: dict[Path, Path] = {}
    temporary: list[Path] = []
    try:
        for output in outputs:
            if cancelled():
                return False
            target = Path(output.path)
            target.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=target.parent, suffix=target.suffix, delete=False) as handle:
                path = Path(handle.name)
            temporary.append(path)
            data.save(str(path), ass_style=output.style, layout=output.layout)
            staged[target] = path
        with commit_lock:
            if cancelled():
                return False
            # Cancellation and publication have one ordering point; no socket or render
            # runs under this lock. A cancel after commit does not roll back completed work.
            for target, path in staged.items():
                os.replace(path, target)
        return True
    finally:
        for path in temporary:
            path.unlink(missing_ok=True)

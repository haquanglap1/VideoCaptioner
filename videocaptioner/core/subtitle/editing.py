"""Qt-independent editing operations on the subtitle table dictionary.

The subtitle tab keeps its rows in the ``ASRData.to_json()`` shape: keys are
1-based row numbers as strings, values carry ``start_time``/``end_time`` in
milliseconds plus ``original_subtitle``/``translated_subtitle``. Everything
here works on that structure so the view only wires signals and dialogs.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from videocaptioner.core.asr.asr_data import ASRData
from videocaptioner.core.entities import SubtitleLayoutEnum, SupportedSubtitleFormats

SubtitleTable = Dict[str, Dict[str, Any]]

# Playback stops slightly before the cue end so the player does not run into
# the next cue when the user clicks a row.
_PLAYBACK_END_GUARD_MS = 50


def renumber(items: Iterable[Dict[str, Any]]) -> SubtitleTable:
    """Rebuild a table with consecutive 1-based string keys."""
    return {str(index): item for index, item in enumerate(items, 1)}


def merge_rows(data: SubtitleTable, rows: Sequence[int]) -> SubtitleTable:
    """Merge the span covered by ``rows`` into one cue.

    Every row from the first to the last selected index is merged, including
    unselected rows in between: dropping them would silently lose subtitles
    and keeping them would overlap the merged cue's time range. Text is joined
    with single spaces; the result keeps the first start and the last end.
    """
    rows = sorted(set(rows))
    if len(rows) < 2:
        return dict(data)
    items = list(data.values())
    first, last = rows[0], rows[-1]
    if first < 0 or last >= len(items):
        raise IndexError(f"rows {rows} outside table of {len(items)} items")
    span = items[first : last + 1]
    merged = {
        "start_time": span[0]["start_time"],
        "end_time": span[-1]["end_time"],
        "original_subtitle": " ".join(item["original_subtitle"] for item in span),
        "translated_subtitle": " ".join(item["translated_subtitle"] for item in span),
    }
    return renumber(items[:first] + [merged] + items[last + 1 :])


def delete_rows(data: SubtitleTable, rows: Iterable[int]) -> SubtitleTable:
    """Drop the given row indexes and renumber the remainder."""
    drop = set(rows)
    return renumber(item for index, item in enumerate(data.values()) if index not in drop)


def select_rows(data: SubtitleTable, rows: Iterable[int]) -> SubtitleTable:
    """Subset of ``data`` at the given row indexes, keeping the original keys.

    Used for re-translating a selection: the worker returns results under the
    same keys, so the model can patch rows in place.
    """
    keys = list(data.keys())
    return {keys[row]: data[keys[row]] for row in sorted(set(rows))}


def replace_text(data: SubtitleTable, search: str, replacement: str) -> int:
    """Replace ``search`` in both text columns, in place. Returns rows changed."""
    if not search:
        return 0
    changed = 0
    for item in data.values():
        hit = False
        for field in ("original_subtitle", "translated_subtitle"):
            text = item.get(field)
            if isinstance(text, str) and search in text:
                item[field] = text.replace(search, replacement)
                hit = True
        if hit:
            changed += 1
    return changed


def playback_range(item: Dict[str, Any]) -> Tuple[int, int]:
    """(start, end) in ms to play for a cue, stopping just before its end."""
    start = int(item["start_time"])
    end = int(item["end_time"])
    guarded = end - _PLAYBACK_END_GUARD_MS
    return start, guarded if guarded > start else end


def find_supported_subtitle(paths: Iterable[str]) -> Tuple[Optional[str], List[str]]:
    """Pick the first existing file with a supported subtitle extension.

    Returns ``(path or None, unsupported extensions seen before it)`` so the
    caller can report each rejected drop.
    """
    supported = {fmt.value for fmt in SupportedSubtitleFormats}
    rejected: List[str] = []
    for path in paths:
        if not os.path.isfile(path):
            continue
        ext = os.path.splitext(path)[1][1:].lower()
        if ext in supported:
            return path, rejected
        rejected.append(ext)
    return None, rejected


def supported_subtitle_extensions() -> List[str]:
    return [fmt.value for fmt in SupportedSubtitleFormats]


def export_subtitle(
    data: SubtitleTable,
    path: str,
    layout: SubtitleLayoutEnum,
    style: Optional[str] = None,
) -> None:
    """Write the table to ``path``; ``.ass`` uses ``style`` (ASS style block)."""
    asr_data = ASRData.from_json(data)
    if path.lower().endswith(".ass"):
        asr_data.to_ass(style, layout, path)
    else:
        asr_data.save(path, layout=layout)


def pipeline_reexport_targets(
    output_path: Optional[str], video_path: Optional[str]
) -> List[str]:
    """Files the optimize/translate pipeline wrote for a task, if they exist.

    Changing the layout after a run must update those files; user-opened
    subtitle paths are deliberately not included.
    """
    candidates: List[str] = []
    if output_path:
        candidates.append(output_path)
    if video_path:
        video = Path(video_path)
        candidates.append(str(video.parent / f"{video.stem}.srt"))
    return [target for target in dict.fromkeys(candidates) if Path(target).exists()]


def reexport_pipeline_outputs(
    data: SubtitleTable,
    output_path: Optional[str],
    video_path: Optional[str],
    layout: SubtitleLayoutEnum,
    style: Optional[str] = None,
) -> List[str]:
    """Re-save pipeline outputs with a new layout. Returns paths written."""
    written: List[str] = []
    for target in pipeline_reexport_targets(output_path, video_path):
        try:
            export_subtitle(data, target, layout, style)
        except Exception:
            continue
        written.append(target)
    return written


def task_folder(output_path: Optional[str], subtitle_path: str) -> str:
    """Directory to reveal for a task: the output's folder when it exists."""
    if output_path and Path(output_path).exists():
        return str(Path(output_path).parent)
    return str(Path(subtitle_path).parent)


def write_editor_handoff(
    data: SubtitleTable, handoff_dir: Path, task_id: str, video_path: str
) -> Path:
    """Persist the current table as SRT for the Video Editor without touching
    the task's source subtitle file."""
    handoff_dir.mkdir(parents=True, exist_ok=True)
    name = task_id or Path(video_path).stem
    target = handoff_dir / f"{name}.srt"
    ASRData.from_json(data).to_srt(save_path=str(target))
    return target

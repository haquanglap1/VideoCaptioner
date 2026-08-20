"""Daily log-file naming, discovery, and bounded size rotation."""

from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path

from videocaptioner.config import LOG_PATH

LEGACY_LLM_LOG_KEY = "legacy"
_LLM_DAY_RE = re.compile(r"^llm_requests-(\d{4}-\d{2}-\d{2})\.jsonl(?:\.\d+)?$")


def local_day(value: date | datetime | None = None) -> str:
    current = value or datetime.now()
    return current.strftime("%Y-%m-%d")


def daily_app_log_path(
    log_dir: str | Path | None = None,
    day: str | None = None,
) -> Path:
    root = Path(log_dir) if log_dir is not None else LOG_PATH
    return root / f"app-{day or local_day()}.log"


def daily_llm_log_path(
    log_dir: str | Path | None = None,
    day: str | None = None,
) -> Path:
    root = Path(log_dir) if log_dir is not None else LOG_PATH
    return root / f"llm_requests-{day or local_day()}.jsonl"


def legacy_llm_log_path(log_dir: str | Path | None = None) -> Path:
    root = Path(log_dir) if log_dir is not None else LOG_PATH
    return root / "llm_requests.jsonl"


def llm_log_files_for_day(
    day: str,
    log_dir: str | Path | None = None,
) -> list[Path]:
    root = Path(log_dir) if log_dir is not None else LOG_PATH
    if day == LEGACY_LLM_LOG_KEY:
        legacy = legacy_llm_log_path(root)
        old = root / "llm_requests.jsonl.old"
        return [path for path in (old, legacy) if path.is_file()]
    files = [path for path in root.glob(f"llm_requests-{day}.jsonl*") if path.is_file()]
    return sorted(files, key=lambda path: (path.stat().st_mtime_ns, path.name))


def available_llm_log_days(
    log_dir: str | Path | None = None,
    *,
    include_today: bool = True,
) -> list[str]:
    root = Path(log_dir) if log_dir is not None else LOG_PATH
    days: set[str] = {local_day()} if include_today else set()
    if root.is_dir():
        for path in root.iterdir():
            match = _LLM_DAY_RE.match(path.name)
            if match:
                days.add(match.group(1))
    result = sorted(days, reverse=True)
    if legacy_llm_log_path(root).is_file() or (root / "llm_requests.jsonl.old").is_file():
        result.append(LEGACY_LLM_LOG_KEY)
    return result


def rotate_size_limited_file(path: Path, max_bytes: int, backup_count: int) -> None:
    if backup_count <= 0 or not path.is_file() or path.stat().st_size < max_bytes:
        return
    oldest = path.with_name(f"{path.name}.{backup_count}")
    oldest.unlink(missing_ok=True)
    for index in range(backup_count - 1, 0, -1):
        source = path.with_name(f"{path.name}.{index}")
        if source.exists():
            source.replace(path.with_name(f"{path.name}.{index + 1}"))
    path.replace(path.with_name(f"{path.name}.1"))

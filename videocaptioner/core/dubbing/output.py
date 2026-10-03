"""Centralized video destinations with source-bound receipts and exclusive naming."""

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path

from videocaptioner.core.dubbing.completed import receipt_path


@dataclass(frozen=True)
class VideoDestination:
    output: Path
    receipt: Path
    root: Path | None = None


def video_destination(output: str, directory: str, source: str, stage="dubbing") -> VideoDestination:
    if not directory.strip():
        return VideoDestination(Path(output), receipt_path(output, stage))
    root = Path(directory.strip()).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    if not root.is_dir():
        raise ValueError("Thư mục lưu video lồng tiếng không hợp lệ")
    metadata = root / ".videocaptioner"
    if not metadata.resolve().is_relative_to(root):
        raise ValueError("Thư mục metadata nằm ngoài thư mục lưu video")
    metadata.mkdir(exist_ok=True)
    identity = hashlib.sha256(os.path.normcase(str(Path(source).resolve())).encode()).hexdigest()[:24]
    return VideoDestination(root / Path(output).name, metadata / f"{identity}.{stage}.json", root)


class OutputClaim:
    """Reserve a filename across workers/apps; remove only our unused placeholder."""

    def __init__(self, output: str, check=lambda: None):
        original = Path(output)
        candidate, count = original, 2
        while True:
            check()
            try:
                if candidate.with_name(candidate.stem + "-subtitles").exists():
                    raise FileExistsError("Existing subtitle output")
                with candidate.open("xb") as stream:
                    self.identity = os.fstat(stream.fileno()).st_ino
                break
            except FileExistsError:
                candidate = original.with_name(f"{original.stem} ({count}){original.suffix}")
                count += 1
        self.path = candidate

    def close(self):
        try:
            current = self.path.stat()
            if current.st_ino == self.identity and current.st_size == 0:
                self.path.unlink()
        except OSError:
            pass

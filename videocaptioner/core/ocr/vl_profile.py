"""Optional, path-free recognizer identity; omitted entirely from legacy documents."""

from dataclasses import dataclass

from .codec import sha256
from .models import OcrError


@dataclass(frozen=True)
class VlProfile:
    id: str
    recipe_sha256: str
    worker_sha256: str

    def __post_init__(self):
        if self.id != "paddleocr-vl-1.5-anchor-v1":
            raise OcrError("Unsupported OCR recognizer recipe")
        sha256(self.recipe_sha256)
        sha256(self.worker_sha256)

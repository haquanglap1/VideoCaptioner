"""Path-free identity of the vision LLM reading policy; omitted from legacy documents."""

from dataclasses import dataclass

from .codec import sha256
from .models import OcrError

PROFILE_ID = "vision-sheet-v1"
MAX_ROWS = 40
MIN_WIDTH, MAX_WIDTH = 320, 2048


@dataclass(frozen=True)
class VisionProfile:
    id: str
    model: str
    rows: int
    width: int
    crops: int
    prompt_sha256: str

    def __post_init__(self):
        if self.id != PROFILE_ID:
            raise OcrError("Unsupported OCR vision policy")
        if (not isinstance(self.model, str) or not self.model.strip() or self.model != self.model.strip()
                or len(self.model) > 200 or any(ord(c) < 32 for c in self.model)):
            raise OcrError("Vision OCR needs the exact model name from the LLM settings")
        if type(self.rows) is not int or not 1 <= self.rows <= MAX_ROWS:
            raise OcrError(f"Vision OCR rows per request must be 1..{MAX_ROWS}")
        if type(self.width) is not int or not MIN_WIDTH <= self.width <= MAX_WIDTH:
            raise OcrError(f"Vision OCR sheet width must be {MIN_WIDTH}..{MAX_WIDTH} pixels")
        if self.crops not in (1, 2):
            raise OcrError("Vision OCR reads one or two crops per cue")
        sha256(self.prompt_sha256)

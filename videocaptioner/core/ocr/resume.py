"""Verify one completed track before extending an immutable OCR checkpoint."""

from __future__ import annotations

import hashlib

from .document import TIMING_ISSUES, OcrConfig, OcrDocument
from .models import OcrError
from .tracking import TrackedRegion


def validate_resume(document: OcrDocument, config: OcrConfig) -> None:
    if document.complete:
        raise OcrError("Bản OCR đã quét xong; có thể xuất phụ đề hoặc mở bảng phụ đề.")
    if document.config != config or config.profile_snapshot is None:
        raise OcrError("Tiếp tục OCR cần giữ nguyên vùng, đoạn chọn và profile đã lưu.")


class ResumeBoundary:
    """Replay pixels/timing only; accepted observations never go back through OCR."""

    def __init__(self, document: OcrDocument):
        validate_resume(document, document.config)
        self.anchor = document.cues[-1] if document.cues else None
        self.pending = self.anchor is not None
        self.start_ms = self.anchor.exact_start_ms if self.anchor else None
        self.seek_pts = self.anchor.first_pts if self.anchor else None
        self.initial_issues = (("track_holding_limit",) if self.anchor
                               and "track_holding_limit" in self.anchor.issues else ())

    def accept(self, region: TrackedRegion) -> bool:
        if not self.pending:
            return True
        anchor = self.anchor
        assert anchor is not None
        actual = (region.start_ms, region.end_ms, region.first_pts, region.last_pts,
                  region.start_window_ms, region.end_window_ms, set(region.issues),
                  tuple((frame.pts, hashlib.sha256(frame.rgb).hexdigest()) for frame in region.candidates))
        expected = (anchor.exact_start_ms, anchor.exact_end_ms, anchor.first_pts, anchor.last_pts,
                    anchor.start_window_ms, anchor.end_window_ms, set(anchor.issues) & TIMING_ISSUES,
                    tuple((candidate.frame_pts, candidate.crop_sha256) for candidate in anchor.candidates))
        if actual != expected:
            raise OcrError("Không xác minh được điểm nối OCR; giữ checkpoint và quét mới để kiểm tra nguồn.")
        self.pending = False
        return False

    def finish(self) -> None:
        if self.pending:
            raise OcrError("Không tìm thấy cue tại điểm tiếp tục OCR; checkpoint được giữ nguyên.")

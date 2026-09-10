"""Undoable review state, independent of Qt; raw observations remain immutable."""

from dataclasses import dataclass

from .document import OcrCue, OcrDocument


@dataclass
class OcrReviewSession:
    document: OcrDocument


@dataclass
class ReviewOcrCueCommand:
    session: OcrReviewSession
    cue: OcrCue
    description: str = "Review OCR cue"
    _before: OcrDocument | None = None

    def execute(self) -> None:
        updated = self.session.document.replace_cue(self.cue)
        if self._before is None:
            self._before = self.session.document
        self.session.document = updated

    def undo(self) -> None:
        if self._before is not None:
            self.session.document = self._before


ISSUE_LABELS = {
    "uncalibrated_profile": "Model chưa được hiệu chuẩn; nhiều ảnh cùng đọc một câu vẫn có thể cùng sai.",
    "engine_disagreement": "Các ảnh cho kết quả chữ khác nhau.",
    "insufficient_independent_crops": "Chưa đủ ảnh độc lập để đối chiếu.",
    "low_engine_score": "Engine báo điểm nhận dạng thấp.",
    "empty_engine_read": "Có ảnh không đọc được chữ; chưa thể xuất kết quả đầy đủ.",
    "no_engine_read": "Thiếu kết quả nhận dạng.",
    "model_revision_mismatch": "Phiên bản model không đồng nhất.",
    "selection_clipped_start": "Đầu câu bị cắt bởi đoạn video đã chọn.",
    "selection_clipped_end": "Cuối câu bị cắt bởi đoạn video đã chọn.",
    "unknown_last_frame_duration": "Chưa biết thời lượng frame cuối.",
    "fade_or_contrast_change": "Chữ mờ dần hoặc đổi tương phản; biên thời gian chưa chắc chắn.",
    "track_holding_limit": "Nhóm chữ chạm giới hạn theo dõi; chưa xác nhận biên đổi câu.",
    "uncertain_boundary": "Cần xem lại khoảng bất định ở biên câu.",
    "submillisecond_span": "Khoảng đo nhỏ hơn độ phân giải phụ đề millisecond.",
}


def issue_labels(cue: OcrCue) -> str:
    return "\n".join(ISSUE_LABELS.get(issue, "Cần xem lại: " + issue) for issue in cue.pending_issues)

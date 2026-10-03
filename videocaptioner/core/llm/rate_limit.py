"""Job-scoped admission and recovery for rejected HTTP 429 requests."""

import math
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from threading import Lock

BACKOFF_SECONDS = 5.0

class LLMRateLimitError(RuntimeError):
    def __init__(self, kind: str = "rate_limit", retry_after: float = 0):
        self.kind, self.retry_after = kind, retry_after
        reason = ("Dịch vụ LLM đã hết hạn mức hoặc số dư. Kiểm tra hạn mức/tài khoản API."
                  if kind == "quota" else
                  "Dịch vụ LLM đang giới hạn yêu cầu. Chưa thể tiếp tục trong thời gian chờ cho phép.")
        super().__init__(f"HTTP 429: {reason} Đã dừng xử lý; bản dịch hoàn tất vẫn được giữ. "
                         "Bấm Bắt đầu xử lý để thử lại sau khi dịch vụ sẵn sàng.")


def rate_limit_error(exc: BaseException) -> LLMRateLimitError:
    body = getattr(exc, "body", None)
    error = body.get("error", body) if isinstance(body, dict) else {}
    error = error if isinstance(error, dict) else {}
    codes = {str(error.get(key, "")).lower() for key in ("code", "type")}
    quota = bool(codes & {"insufficient_quota", "quota_exceeded", "billing_hard_limit_reached",
                          "insufficient_balance", "credits_exhausted"})
    headers = getattr(getattr(exc, "response", None), "headers", {})
    value = headers.get("retry-after", "")
    delay = 0.0
    try:
        delay = float(value)
    except (TypeError, ValueError):
        try:
            date = parsedate_to_datetime(value)
            delay = (date - datetime.now(timezone.utc)).total_seconds()
        except (TypeError, ValueError, OverflowError):
            pass
    if not math.isfinite(delay) or delay < 0:
        delay = 0.0
    return LLMRateLimitError("quota" if quota else "rate_limit", delay)


def find_rate_limit(exc: BaseException | None) -> LLMRateLimitError | None:
    seen = set()
    while exc is not None and id(exc) not in seen:
        if isinstance(exc, LLMRateLimitError):
            return exc
        seen.add(id(exc))
        exc = exc.__cause__ or exc.__context__
    return None


class RateLimitGate:
    """Share a cooldown across chunks; one probe may resume a rejected job.

    The caller's configured worker pool controls normal concurrency. After a
    rejection, only one runs at a time, with two recovery probes for the job.
    """

    def __init__(self):
        self.lock = Lock()
        self.active = 0
        self.limit: int | None = None
        self.rejections = 0
        self.ready_at = 0.0
        self.failure: LLMRateLimitError | None = None

    def enter(self) -> bool:
        with self.lock:
            if self.failure:
                raise self.failure from None
            if ((self.limit is not None and self.active >= self.limit)
                    or time.monotonic() < self.ready_at):
                return False
            self.active += 1
            return True

    def leave(self):
        with self.lock:
            self.active -= 1

    def reject(self, error: LLMRateLimitError, remaining: float):
        with self.lock:
            # Initial requests already in flight share the same first rejection.
            if self.limit is None or time.monotonic() >= self.ready_at:
                self.rejections += 1
            self.limit = 1
            delay = max(error.retry_after, BACKOFF_SECONDS * 2 ** min(self.rejections - 1, 2))
            if error.kind == "quota" or self.rejections >= 3 or delay >= remaining:
                self.failure = error
            else:
                self.ready_at = max(self.ready_at, time.monotonic() + delay)
            if self.failure:
                raise self.failure from None

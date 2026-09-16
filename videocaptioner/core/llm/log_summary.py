"""Read both legacy and owned-request journals without treating missing usage as zero."""

from dataclasses import dataclass


def count(value) -> int | None:
    return value if type(value) is int and value >= 0 else None


@dataclass(frozen=True)
class LogUsage:
    prompt: int | None
    completion: int | None
    total: int | None
    cached: int | None
    reasoning: int | None
    total_reported: bool


def log_usage(entry: dict) -> LogUsage:
    response = entry.get("response") or {}
    usage = response.get("usage") or {}
    prompt, completion = count(usage.get("prompt_tokens")), count(usage.get("completion_tokens"))
    total = count(usage.get("total_tokens"))
    reported = total is not None
    if total is None and prompt is not None and completion is not None:
        total = prompt + completion
    return LogUsage(prompt, completion, total,
                    count((usage.get("prompt_tokens_details") or {}).get("cached_tokens")),
                    count((usage.get("completion_tokens_details") or {}).get("reasoning_tokens")), reported)


def log_outcome(entry: dict) -> str:
    if entry.get("outcome"):
        return entry["outcome"]
    status = count(entry.get("status"))
    return "success" if status is not None and 200 <= status < 300 else "http_error" if status and status >= 400 else "unknown"

"""LLM request/response logging through httpx event hooks.

The request captured in ``_on_request`` is paired with the parsed SDK response
handed to ``log_llm_response`` via a ``ContextVar``. The OpenAI client is
synchronous, so both hooks and the caller run in the same thread and context.
A process-wide dict keyed by ``id(request)`` was used before and mixed entries
up when several translator threads ran at once.
"""

import contextvars
import json
import threading
import time
from datetime import datetime
from typing import Any, Dict, Optional

import httpx

from videocaptioner.config import LOG_PATH
from videocaptioner.core.llm.context import get_task_context
from videocaptioner.core.utils.log_files import (
    daily_llm_log_path,
    rotate_size_limited_file,
)

MAX_LOG_SIZE = 10 * 1024 * 1024  # 10MB


_log_lock = threading.Lock()
# Request captured for the chat completion currently in flight on this
# thread/context. One slot is enough: a retry simply overwrites it.
_current_request: contextvars.ContextVar[Optional[Dict[str, Any]]] = contextvars.ContextVar(
    "videocaptioner_llm_current_request", default=None
)


# ==================== Log file ====================


def _rotate_if_needed(log_file) -> None:
    """Keep at most two 10 MB backups for each day."""
    rotate_size_limited_file(log_file, MAX_LOG_SIZE, backup_count=2)


def _write_log(entry: Dict[str, Any]) -> None:
    try:
        LOG_PATH.mkdir(parents=True, exist_ok=True)
        with _log_lock:
            log_file = daily_llm_log_path(LOG_PATH)
            _rotate_if_needed(log_file)
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass


# ==================== HTTPX hooks ====================


def _on_request(request: httpx.Request) -> None:
    """Capture the outgoing chat completion request for the current context."""
    if "/chat/completions" not in str(request.url):
        return

    try:
        request_body = json.loads(request.content.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        request_body = {"raw": request.content.decode("utf-8", errors="replace")}

    _current_request.set(
        {
            "start_time": time.time(),
            "url": str(request.url),
            "request": request_body,
        }
    )


def _on_response(response: httpx.Response) -> None:
    """Attach status and latency to the request captured in this context."""
    pending = _current_request.get()
    if pending is None or pending.get("url") != str(response.request.url):
        return

    pending["status"] = response.status_code
    pending["duration_ms"] = int((time.time() - pending["start_time"]) * 1000)
    pending["completed"] = True


# ==================== Public API ====================


def create_logging_http_client() -> httpx.Client:
    return httpx.Client(
        event_hooks={
            "request": [_on_request],
            "response": [_on_response],
        }
    )


def log_llm_response(response: Any) -> None:
    """Write the request captured in this context together with the parsed response."""
    pending = _current_request.get()
    if pending is None:
        return
    _current_request.set(None)

    response_data = {}
    if response and hasattr(response, "model_dump"):
        response_data = response.model_dump()

    ctx = get_task_context()

    log_entry = {
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "task_id": ctx.task_id if ctx else "",
        "file_name": ctx.file_name if ctx else "",
        "stage": ctx.stage if ctx else "",
        "url": pending.get("url", ""),
        "status": pending.get("status", 0),
        "duration_ms": pending.get("duration_ms", 0),
        "request": pending.get("request", {}),
        "response": response_data,
    }

    _write_log(log_entry)

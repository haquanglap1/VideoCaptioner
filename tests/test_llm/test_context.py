"""Tests for task context propagation.

The task context labels every LLM request in llm_requests.jsonl. It has two
requirements that pull in opposite directions:

1. Worker threads in a ThreadPoolExecutor must see the submitting thread's
   context (ThreadPoolExecutor does not propagate contextvars by itself).
2. Two tasks running concurrently must not see each other's context — that was
   the bug with the previous module-level global.
"""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from videocaptioner.core.llm.context import (
    clear_task_context,
    generate_task_id,
    get_task_context,
    set_task_context,
    submit_with_context,
    update_stage,
)


def test_generate_task_id_is_8_hex_chars():
    task_id = generate_task_id()
    assert len(task_id) == 8
    int(task_id, 16)  # raises if not hex


def test_set_get_update_clear():
    set_task_context(task_id="abcd1234", file_name="video.mp4", stage="subtitle")
    ctx = get_task_context()
    assert ctx is not None
    assert (ctx.task_id, ctx.file_name, ctx.stage) == ("abcd1234", "video.mp4", "subtitle")

    update_stage("translate")
    ctx = get_task_context()
    assert ctx is not None
    assert ctx.stage == "translate"
    assert ctx.task_id == "abcd1234"  # rest is preserved

    clear_task_context()
    assert get_task_context() is None


def test_update_stage_without_context_is_noop():
    clear_task_context()
    update_stage("translate")
    assert get_task_context() is None


def test_submit_with_context_propagates_into_worker_thread():
    set_task_context(task_id="feed0001", file_name="a.mp4", stage="translate")
    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            future = submit_with_context(executor, get_task_context)
            worker_ctx = future.result()
        assert worker_ctx is not None
        assert worker_ctx.task_id == "feed0001"
        assert worker_ctx.stage == "translate"
    finally:
        clear_task_context()


def test_plain_submit_does_not_propagate():
    """Documents why submit_with_context exists at all."""
    set_task_context(task_id="feed0002", file_name="b.mp4", stage="optimize")
    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            assert executor.submit(get_task_context).result() is None
    finally:
        clear_task_context()


def test_concurrent_tasks_do_not_leak_context():
    """Two tasks in flight at once must keep separate labels.

    The barrier forces both workers to be inside their callable simultaneously,
    which is exactly when a shared module-level global returned the wrong task.
    """
    barrier = Barrier(2, timeout=10)

    def run_task(task_id: str, file_name: str):
        set_task_context(task_id=task_id, file_name=file_name, stage="translate")
        with ThreadPoolExecutor(max_workers=1) as executor:
            def read_after_both_started():
                barrier.wait()
                ctx = get_task_context()
                return None if ctx is None else (ctx.task_id, ctx.file_name)

            return submit_with_context(executor, read_after_both_started).result()

    with ThreadPoolExecutor(max_workers=2) as outer:
        first = outer.submit(run_task, "aaaa1111", "first.mp4")
        second = outer.submit(run_task, "bbbb2222", "second.mp4")
        results = {first.result(), second.result()}

    assert results == {("aaaa1111", "first.mp4"), ("bbbb2222", "second.mp4")}


def test_submit_with_context_allows_many_concurrent_submits():
    """Each submit needs its own context copy.

    Reusing one contextvars.Context across concurrent runs raises
    "cannot enter context: is already entered".
    """
    set_task_context(task_id="cccc3333", file_name="c.mp4", stage="split")
    try:
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [
                submit_with_context(executor, lambda: get_task_context().task_id)
                for _ in range(20)
            ]
            assert {f.result() for f in futures} == {"cccc3333"}
    finally:
        clear_task_context()

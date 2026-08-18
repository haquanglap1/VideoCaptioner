"""任务上下文管理

使用 contextvars 存储任务上下文，使并行运行的多个任务（批量处理）互不干扰。

ThreadPoolExecutor 不会自动复制 contextvars，所以每个 submit 点都必须通过
``submit_with_context`` 提交，否则工作线程读不到当前任务标签。
"""

import contextvars
import uuid
from concurrent.futures import Executor, Future
from dataclasses import dataclass
from typing import Any, Callable, Optional


@dataclass
class TaskContext:
    """任务上下文"""

    task_id: str  # 任务唯一标识，如 "a1b2c3d4"
    file_name: str  # 处理的文件名，如 "video.mp4"
    stage: str  # 当前阶段: transcribe / split / optimize / translate / synthesis


_current_context: contextvars.ContextVar[Optional[TaskContext]] = contextvars.ContextVar(
    "videocaptioner_task_context", default=None
)


def generate_task_id() -> str:
    """生成 8 位任务 ID"""
    return uuid.uuid4().hex[:8]


def set_task_context(task_id: str, file_name: str, stage: str) -> None:
    """设置当前任务上下文（仅影响当前线程/上下文）"""
    _current_context.set(
        TaskContext(task_id=task_id, file_name=file_name, stage=stage)
    )


def get_task_context() -> Optional[TaskContext]:
    """获取当前任务上下文"""
    return _current_context.get()


def update_stage(stage: str) -> None:
    """更新当前阶段"""
    ctx = _current_context.get()
    if ctx:
        _current_context.set(
            TaskContext(task_id=ctx.task_id, file_name=ctx.file_name, stage=stage)
        )


def clear_task_context() -> None:
    """清除任务上下文"""
    _current_context.set(None)


def submit_with_context(
    executor: Executor, fn: Callable[..., Any], *args: Any, **kwargs: Any
) -> Future:
    """向线程池提交任务，同时把调用方的任务上下文带进工作线程。

    每次调用都新建一份 context 副本：同一个 Context 对象不能被并发 ``run``，
    复用会抛 "cannot enter context: is already entered"。
    """
    ctx = contextvars.copy_context()
    return executor.submit(ctx.run, fn, *args, **kwargs)

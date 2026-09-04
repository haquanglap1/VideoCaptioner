"""Subprocess helpers: scrubbed child environment and async stream reading."""

import os
import queue
import subprocess
import threading
from typing import Callable, Dict, Mapping, Optional, Tuple

from ..utils.logger import setup_logger

logger = setup_logger("subprocess_helper")

# Suppress the conhost.exe console window that subprocess.Popen would
# otherwise spawn for every child on Windows.
_NO_WINDOW = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0

# Variables that must never reach a child process: the app's own credential
# names and anything the OpenAI SDK would pick up implicitly. Matched
# case-insensitively because Windows environment names are.
SECRET_ENV_PREFIXES: Tuple[str, ...] = ("OPENAI_", "VIDEOCAPTIONER_")


def child_environment(overrides: Optional[Mapping[str, str]] = None) -> Dict[str, str]:
    """Copy of ``os.environ`` for subprocesses with credential variables removed.

    PATH additions made at import time (bundled FFmpeg, Faster-Whisper, Deno)
    are kept because they live in ``os.environ``; only ``OPENAI_*`` and
    ``VIDEOCAPTIONER_*`` are dropped so FFmpeg, whisper, yt-dlp and the VieNeu
    sidecar never inherit an API key. ``overrides`` are applied last.
    """
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.upper().startswith(SECRET_ENV_PREFIXES)
    }
    if overrides:
        env.update(overrides)
    return env


class StreamReader:
    """通用的子进程输出流Reading器"""

    def __init__(self, process: subprocess.Popen):
        """
        初始化流Reading器

        Args:
            process: 子进程对象
        """
        self.process = process
        self.output_queue = queue.Queue()
        self.threads = []

    def start_reading(self) -> None:
        """启动异步Readingstdout和stderr"""
        # 启动stdoutReading线程
        if self.process.stdout:
            stdout_thread = threading.Thread(
                target=self._read_stream,
                args=(self.process.stdout, "stdout"),
                daemon=True,
            )
            stdout_thread.start()
            self.threads.append(stdout_thread)

        # 启动stderrReading线程
        if self.process.stderr:
            stderr_thread = threading.Thread(
                target=self._read_stream,
                args=(self.process.stderr, "stderr"),
                daemon=True,
            )
            stderr_thread.start()
            self.threads.append(stderr_thread)

    def _read_stream(self, stream, stream_name: str) -> None:
        """Reading流并放入队列"""
        try:
            for line in iter(stream.readline, ""):
                if line:
                    self.output_queue.put((stream_name, line))
        except Exception as e:
            logger.debug(f"Reading {stream_name} ended: {e}")
        finally:
            stream.close()

    def get_output(self, timeout: float = 0.1) -> Optional[Tuple[str, str]]:
        """
        获取输出

        Args:
            timeout: 等待超时时间

        Returns:
            (stream_name, line) 或 None
        """
        try:
            return self.output_queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def get_remaining_output(self) -> list:
        """获取队列中剩余的All输出"""
        output = []
        while not self.output_queue.empty():
            try:
                output.append(self.output_queue.get_nowait())
            except queue.Empty:
                break
        return output

    def is_empty(self) -> bool:
        """检查队列是否为空"""
        return self.output_queue.empty()


def run_process_with_stream_reader(
    cmd: list,
    stdout_handler: Optional[Callable[[str], None]] = None,
    stderr_handler: Optional[Callable[[str], None]] = None,
    **popen_kwargs,
) -> subprocess.Popen:
    """
    运行子进程并使用StreamReader处理输出

    Args:
        cmd: Command列表
        stdout_handler: stdout行处理函数
        stderr_handler: stderr行处理函数
        **popen_kwargs: 传递给subprocess.Popen的额外参数

    Returns:
        子进程对象

    Example:
        ```python
        def handle_stdout(line):
            print(f"[stdout] {line.strip()}")

        def handle_stderr(line):
            print(f"[stderr] {line.strip()}")

        process = run_process_with_stream_reader(
            ["ls", "-la"],
            stdout_handler=handle_stdout,
            stderr_handler=handle_stderr
        )
        process.wait()
        ```
    """
    default_kwargs = {
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "text": True,
        "encoding": "utf-8",
        "bufsize": 1,  # line buffered
        "creationflags": _NO_WINDOW,
        "env": child_environment(),
    }
    default_kwargs.update(popen_kwargs)

    # 启动进程
    process = subprocess.Popen(cmd, **default_kwargs)

    # 创建流Reading器
    reader = StreamReader(process)
    reader.start_reading()

    # 处理输出的线程
    def process_output():
        while True:
            # 检查进程状态
            if process.poll() is not None:
                # 进程已ended，Reading剩余输出
                for stream_name, line in reader.get_remaining_output():
                    if stream_name == "stdout" and stdout_handler:
                        stdout_handler(line)
                    elif stream_name == "stderr" and stderr_handler:
                        stderr_handler(line)
                break

            # Reading输出
            output = reader.get_output()
            if output:
                stream_name, line = output
                if stream_name == "stdout" and stdout_handler:
                    stdout_handler(line)
                elif stream_name == "stderr" and stderr_handler:
                    stderr_handler(line)

    # 如果提供了处理函数，启动处理线程
    if stdout_handler or stderr_handler:
        handler_thread = threading.Thread(target=process_output, daemon=True)
        handler_thread.start()

    return process

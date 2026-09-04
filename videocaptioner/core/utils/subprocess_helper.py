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
    """Asynchronous reader for a child process's stdout/stderr."""

    def __init__(self, process: subprocess.Popen):
        """
        Start with the process whose pipes will be read.

        Args:
            process: child process
        """
        self.process = process
        self.output_queue = queue.Queue()
        self.threads = []

    def start_reading(self) -> None:
        """Start background threads that read stdout and stderr."""
        # stdout reader thread
        if self.process.stdout:
            stdout_thread = threading.Thread(
                target=self._read_stream,
                args=(self.process.stdout, "stdout"),
                daemon=True,
            )
            stdout_thread.start()
            self.threads.append(stdout_thread)

        # stderr reader thread
        if self.process.stderr:
            stderr_thread = threading.Thread(
                target=self._read_stream,
                args=(self.process.stderr, "stderr"),
                daemon=True,
            )
            stderr_thread.start()
            self.threads.append(stderr_thread)

    def _read_stream(self, stream, stream_name: str) -> None:
        """Read a stream line by line into the queue."""
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
        Pop one line.

        Args:
            timeout: seconds to wait for output

        Returns:
            (stream_name, line) or None when nothing arrived in time
        """
        try:
            return self.output_queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def get_remaining_output(self) -> list:
        """Drain everything still queued."""
        output = []
        while not self.output_queue.empty():
            try:
                output.append(self.output_queue.get_nowait())
            except queue.Empty:
                break
        return output

    def is_empty(self) -> bool:
        """True when no output is queued."""
        return self.output_queue.empty()


def run_process_with_stream_reader(
    cmd: list,
    stdout_handler: Optional[Callable[[str], None]] = None,
    stderr_handler: Optional[Callable[[str], None]] = None,
    **popen_kwargs,
) -> subprocess.Popen:
    """
    Run a subprocess and feed its output lines to handlers via StreamReader.

    Args:
        cmd: command as an argument list
        stdout_handler: called with each stdout line
        stderr_handler: called with each stderr line
        **popen_kwargs: extra arguments for subprocess.Popen (``env`` defaults
            to the scrubbed child environment)

    Returns:
        The running Popen object.

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

    # Start the process
    process = subprocess.Popen(cmd, **default_kwargs)

    # Reader threads for both pipes
    reader = StreamReader(process)
    reader.start_reading()

    # Dispatch queued lines to the handlers
    def process_output():
        while True:
            # Check whether the process has exited
            if process.poll() is not None:
                # Process exited: drain the remaining output
                for stream_name, line in reader.get_remaining_output():
                    if stream_name == "stdout" and stdout_handler:
                        stdout_handler(line)
                    elif stream_name == "stderr" and stderr_handler:
                        stderr_handler(line)
                break

            # Read output
            output = reader.get_output()
            if output:
                stream_name, line = output
                if stream_name == "stdout" and stdout_handler:
                    stdout_handler(line)
                elif stream_name == "stderr" and stderr_handler:
                    stderr_handler(line)

    # Only spin up the dispatcher when someone wants the lines
    if stdout_handler or stderr_handler:
        handler_thread = threading.Thread(target=process_output, daemon=True)
        handler_thread.start()

    return process

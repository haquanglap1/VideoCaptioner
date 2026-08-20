import logging
import logging.handlers
import threading
from pathlib import Path

from ...config import LOG_LEVEL, LOG_PATH
from .log_files import daily_app_log_path


class DailySizeRotatingFileHandler(logging.Handler):
    """Write to one dated file, with bounded size backups inside that day."""

    def __init__(
        self,
        log_dir: str | Path,
        *,
        max_bytes: int = 10 * 1024 * 1024,
        backup_count: int = 5,
        encoding: str = "utf-8",
    ):
        super().__init__()
        self.log_dir = Path(log_dir)
        self.max_bytes = max_bytes
        self.backup_count = backup_count
        self.encoding = encoding
        self._day = ""
        self._delegate: logging.handlers.RotatingFileHandler | None = None

    def _ensure_delegate(self) -> logging.handlers.RotatingFileHandler:
        path = daily_app_log_path(self.log_dir)
        day = path.stem.removeprefix("app-")
        if self._delegate is not None and day == self._day:
            return self._delegate
        if self._delegate is not None:
            self._delegate.close()
        path.parent.mkdir(parents=True, exist_ok=True)
        self._delegate = logging.handlers.RotatingFileHandler(
            path,
            maxBytes=self.max_bytes,
            backupCount=self.backup_count,
            encoding=self.encoding,
        )
        self._delegate.setFormatter(self.formatter)
        self._day = day
        return self._delegate

    def setFormatter(self, fmt: logging.Formatter | None) -> None:
        super().setFormatter(fmt)
        if self._delegate is not None:
            self._delegate.setFormatter(fmt)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._ensure_delegate().emit(record)
        except Exception:
            self.handleError(record)

    def close(self) -> None:
        if self._delegate is not None:
            self._delegate.close()
            self._delegate = None
        super().close()


_shared_file_handler: DailySizeRotatingFileHandler | None = None
_shared_handler_lock = threading.Lock()


def _get_shared_file_handler() -> DailySizeRotatingFileHandler:
    global _shared_file_handler
    with _shared_handler_lock:
        if _shared_file_handler is None:
            _shared_file_handler = DailySizeRotatingFileHandler(LOG_PATH)
        return _shared_file_handler


def setup_logger(
    name: str,
    level: int = LOG_LEVEL,
    info_fmt: str = "%(message)s",  # INFO级别使用简化格式
    default_fmt: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s",  # 其他级别使用详细格式
    datefmt: str = "%Y-%m-%d %H:%M:%S",
    log_file: str | None = None,
    console_output: bool = True,
) -> logging.Logger:
    """
    创建并配置一个日志记录器，INFO级别使用简化格式。

    参数:
    - name: 日志记录器的名称
    - level: 日志级别
    - info_fmt: INFO级别的日志格式字符串
    - default_fmt: 其他级别的日志格式字符串
    - datefmt: 时间格式字符串
    - log_file: 日志文件路径
    """

    logger = logging.getLogger(name)
    logger.setLevel(level)

    if not logger.handlers:
        class LevelSpecificFormatter(logging.Formatter):
            """Thread-safe formatter that uses different formats per log level."""
            def format(self, record):
                # Use local variable instead of mutating shared _style._fmt
                fmt = info_fmt if record.levelno == logging.INFO else default_fmt
                formatter = logging.Formatter(fmt, datefmt=datefmt)
                return formatter.format(record)

        level_formatter = LevelSpecificFormatter(default_fmt, datefmt=datefmt)

        # 只在console_output为True时添加控制台处理器
        if console_output:
            console_handler = logging.StreamHandler()
            console_handler.setLevel(level)
            console_handler.setFormatter(level_formatter)
            logger.addHandler(console_handler)

        # The default handler is shared across all named loggers so midnight
        # and size rotation cannot race through multiple open file handles.
        if log_file is None:
            file_handler = _get_shared_file_handler()
            file_handler.setLevel(level)
            file_handler.setFormatter(level_formatter)
            logger.addHandler(file_handler)
        elif log_file:
            Path(log_file).parent.mkdir(parents=True, exist_ok=True)
            file_handler = logging.handlers.RotatingFileHandler(
                log_file, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
            )
            file_handler.setLevel(level)
            file_handler.setFormatter(level_formatter)
            logger.addHandler(file_handler)
        logger.propagate = False

    # 设置特定库的日志级别为ERROR以减少日志噪音
    error_loggers = [
        "urllib3",
        "requests",
        "openai",
        "httpx",
        "httpcore",
        "ssl",
        "certifi",
    ]
    for lib in error_loggers:
        logging.getLogger(lib).setLevel(logging.ERROR)

    return logger

"""Dubbing thread — chạy DubbingEngine trên QThread."""

import datetime

from PyQt5.QtCore import QThread, pyqtSignal

from videocaptioner.core.dubbing.engine import DubbingEngine
from videocaptioner.core.entities import DubbingTask
from videocaptioner.core.utils.logger import setup_logger

logger = setup_logger("dubbing_thread")


class DubbingThread(QThread):
    """Thread lồng tiếng video."""

    finished = pyqtSignal(DubbingTask)
    progress = pyqtSignal(int, str)
    error = pyqtSignal(str)
    report_ready = pyqtSignal(object)

    def __init__(self, task: DubbingTask):
        super().__init__()
        self.task = task

    def run(self):
        engine = None
        try:
            self.task.started_at = datetime.datetime.now()

            config = self.task.dubbing_config
            if not config:
                raise ValueError("DubbingConfig chưa được cấu hình")

            logger.info("\n%s", config.print_config())

            video_path = self.task.video_path
            subtitle_path = self.task.subtitle_path
            output_path = self.task.output_path

            if not video_path:
                raise ValueError(self.tr("Đường dẫn video đang trống"))
            if not subtitle_path:
                raise ValueError(self.tr("Đường dẫn phụ đề đang trống"))
            if not output_path:
                raise ValueError(self.tr("Đường dẫn đầu ra đang trống"))

            engine = DubbingEngine()
            engine.dub(
                video_path=video_path,
                subtitle_path=subtitle_path,
                output_path=output_path,
                config=config,
                callback=self._progress_callback,
            )
            self.task.report_path = engine.last_report_path
            self.task.dubbing_report = engine.last_report
            if self.task.dubbing_report:
                self.report_ready.emit(self.task.dubbing_report)

            self.task.completed_at = datetime.datetime.now()
            self.progress.emit(100, self.tr("Lồng tiếng hoàn tất"))
            self.finished.emit(self.task)

        except Exception as e:
            if engine is not None:
                self.task.report_path = engine.last_report_path
                self.task.dubbing_report = engine.last_report
                if self.task.dubbing_report:
                    self.report_ready.emit(self.task.dubbing_report)
            logger.exception("Dubbing thất bại: %s", e)
            self.error.emit(str(e))
            self.progress.emit(100, self.tr("Lồng tiếng thất bại"))

    def _progress_callback(self, value: int, message: str):
        self.progress.emit(value, message)

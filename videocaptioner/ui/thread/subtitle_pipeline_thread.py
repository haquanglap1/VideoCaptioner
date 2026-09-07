import datetime
from pathlib import Path

from PyQt5.QtCore import QThread, pyqtSignal

from videocaptioner.core.entities import (
    DubbingTask,
    FullProcessTask,
    SubtitleTask,
    SynthesisTask,
    TranscribeTask,
)
from videocaptioner.core.utils.logger import setup_logger

from .dubbing_thread import DubbingThread
from .subtitle_thread import SubtitleThread
from .transcript_thread import TranscriptThread
from .video_synthesis_thread import VideoSynthesisThread

logger = setup_logger("subtitle_pipeline_thread")


class SubtitlePipelineThread(QThread):
    """字幕处理全流程线程，包含:
    1. 转录生成字幕
    2. 字幕优化/翻译
    3. Dubbing / lồng tiếng (optional)
    4. 视频合成
    """

    progress = pyqtSignal(int, str)  # 进度值, 进度描述
    finished = pyqtSignal(FullProcessTask)
    error = pyqtSignal(str)

    def __init__(self, task: FullProcessTask):
        super().__init__()
        self.task = task
        self.has_error = False

    def stop(self):
        self.requestInterruption()

    def run(self):
        try:

            def handle_error(error_msg):
                logger.error("pipeline 发生错误: %s", error_msg)
                self.has_error = True
                self.error.emit(error_msg)

            # Determine progress weights based on whether dubbing is enabled
            dubbing_enabled = (
                self.task.dubbing_config is not None
                and self.task.dubbing_config.enabled
            )
            if dubbing_enabled:
                # Transcribe 0-30%, Subtitle 30-50%, Dubbing 50-70%, Synthesis 70-100%
                t_end, s_start, s_end = 30, 30, 50
                d_start, d_end = 50, 70
                v_start, v_end = 70, 100
            else:
                # Original weights: Transcribe 0-40%, Subtitle 40-60%, Synthesis 60-100%
                t_end, s_start, s_end = 40, 40, 60
                d_start, d_end = 0, 0  # unused
                v_start, v_end = 60, 100

            # 1. 转录生成字幕
            self.task.started_at = datetime.datetime.now()
            logger.info(f"\n{self.task.transcribe_config.print_config()}")
            logger.info(f"\n{self.task.subtitle_config.print_config()}")
            if self.task.synthesis_config:
                logger.info(f"\n{self.task.synthesis_config.print_config()}")
            if dubbing_enabled:
                logger.info(f"\n{self.task.dubbing_config.print_config()}")
            self.progress.emit(0, self.tr("开始转录"))

            # 创建转录任务
            transcribe_task = TranscribeTask(
                file_path=self.task.file_path,
                transcribe_config=self.task.transcribe_config,
                need_next_task=True,
                queued_at=self.task.queued_at,
                started_at=self.task.started_at,
                completed_at=self.task.completed_at,
            )
            transcript_thread = TranscriptThread(transcribe_task)
            transcript_thread.progress.connect(
                lambda value, msg: self.progress.emit(int(value * t_end / 100), msg)
            )
            transcript_thread.error.connect(handle_error)
            transcript_thread.run()

            if self.has_error:
                logger.info("转录过程中发生错误，终止流程")
                return

            # 2. 字幕优化/翻译
            self.progress.emit(s_start, self.tr("开始优化字幕"))

            # 创建字幕任务
            subtitle_task = SubtitleTask(
                subtitle_path=transcribe_task.output_path or "",
                video_path=self.task.file_path,
                output_path=self.task.output_path,
                subtitle_config=self.task.subtitle_config,
                need_next_task=True,
                queued_at=self.task.queued_at,
                started_at=self.task.started_at,
                completed_at=self.task.completed_at,
            )
            optimization_thread = SubtitleThread(subtitle_task)
            s_range = s_end - s_start
            optimization_thread.progress.connect(
                lambda value, msg: self.progress.emit(int(s_start + value * s_range / 100), msg)
            )
            optimization_thread.error.connect(handle_error)
            optimization_thread.run()

            if self.has_error:
                logger.info("字幕优化过程中发生错误，终止流程")
                return

            # 3. Dubbing / lồng tiếng (optional)
            video_for_synthesis = self.task.file_path  # default: video gốc
            if dubbing_enabled:
                self.progress.emit(d_start, self.tr("Bắt đầu lồng tiếng"))

                # Output dubbed video next to the final output; the task factory
                # always sets output_path, so a blank one is a wiring bug.
                source_path, output_path = self.task.file_path, self.task.output_path
                if not source_path or not output_path:
                    handle_error(self.tr("Thiếu đường dẫn đầu ra cho video lồng tiếng"))
                    return
                dubbed_video_path = str(
                    Path(output_path).parent / f"{Path(source_path).stem}_dubbed.mp4"
                )

                dubbing_task = DubbingTask(
                    video_path=self.task.file_path,
                    subtitle_path=subtitle_task.dubbing_subtitle_path,
                    output_path=dubbed_video_path,
                    dubbing_config=self.task.dubbing_config,
                    queued_at=self.task.queued_at,
                    started_at=self.task.started_at,
                    completed_at=self.task.completed_at,
                )
                dubbing_thread = DubbingThread(dubbing_task)
                d_range = d_end - d_start
                dubbing_thread.progress.connect(
                    lambda value, msg: self.progress.emit(int(d_start + value * d_range / 100), msg)
                )
                dubbing_thread.error.connect(handle_error)
                dubbing_thread.run()

                if self.has_error:
                    logger.info("Dubbing thất bại, dừng pipeline để tránh báo thành công sai")
                    return
                elif Path(dubbed_video_path).is_file():
                    video_for_synthesis = dubbed_video_path
                    logger.info("Dubbing thành công, dùng video dubbed cho synthesis")
                else:
                    handle_error("Dubbing không tạo artifact đầu ra")
                    return

            # 4. 视频合成
            self.progress.emit(v_start, self.tr("开始合成视频"))

            # 创建合成任务
            synthesis_task = SynthesisTask(
                video_path=video_for_synthesis,
                subtitle_path=subtitle_task.output_path,
                output_path=self.task.output_path,
                synthesis_config=self.task.synthesis_config,
                queued_at=self.task.queued_at,
                started_at=self.task.started_at,
                completed_at=self.task.completed_at,
            )
            synthesis_thread = VideoSynthesisThread(synthesis_task)
            v_range = v_end - v_start
            synthesis_thread.progress.connect(
                lambda value, msg: self.progress.emit(int(v_start + value * v_range / 100), msg)
            )
            synthesis_thread.error.connect(handle_error)
            synthesis_thread.run()

            if self.has_error:
                logger.info("视频合成过程中发生错误，终止流程")
                return

            logger.info("处理完成")
            self.progress.emit(100, self.tr("处理完成"))
            self.finished.emit(self.task)

        except Exception as e:
            logger.exception("处理失败: %s", str(e))
            self.error.emit(str(e))

import datetime
import tempfile
from pathlib import Path

from PyQt5.QtCore import QThread, pyqtSignal

from videocaptioner.core.asr.asr_data import ASRData
from videocaptioner.core.entities import SynthesisTask
from videocaptioner.core.utils.logger import setup_logger
from videocaptioner.core.utils.video_utils import add_subtitles, add_subtitles_with_style

logger = setup_logger("video_synthesis_thread")


class VideoSynthesisThread(QThread):
    finished = pyqtSignal(SynthesisTask)
    progress = pyqtSignal(int, str)
    error = pyqtSignal(str)

    def __init__(self, task: SynthesisTask):
        super().__init__()
        self.task = task
        logger.debug(f"Khoi tao VideoSynthesisThread, task: {self.task}")

    def run(self):
        try:
            self.task.started_at = datetime.datetime.now()
            config = self.task.synthesis_config
            logger.info(f"\n{config.print_config()}")

            video_file = self.task.video_path
            subtitle_file = self.task.subtitle_path
            output_path = self.task.output_path

            if not config.need_video:
                logger.info("Khong can ghep video, bo qua")
                self.progress.emit(100, self.tr("Hoàn tất ghép video"))
                self.finished.emit(self.task)
                return

            logger.info(f"Bat dau ghep video: {video_file}")
            self.progress.emit(5, self.tr("Đang ghép video"))

            if not video_file:
                raise ValueError(self.tr("Đường dẫn video đang trống"))
            if not subtitle_file:
                raise ValueError(self.tr("Đường dẫn phụ đề đang trống"))
            if not output_path:
                raise ValueError(self.tr("Đường dẫn đầu ra đang trống"))

            video_quality = config.video_quality
            crf = video_quality.get_crf()
            preset = video_quality.get_preset()

            # Doc du lieu phu de
            asr_data = ASRData.from_subtitle_file(subtitle_file)

            if config.soft_subtitle:
                # Phu de mem: chuyen ve SRT roi nhung vao video
                with tempfile.NamedTemporaryFile(
                    mode="w",
                    suffix=".srt",
                    delete=False,
                    encoding="utf-8",
                    prefix="VideoCaptioner_soft_",
                ) as f:
                    srt_content = asr_data.to_srt(layout=config.subtitle_layout)
                    f.write(srt_content)
                    temp_srt_path = f.name

                try:
                    add_subtitles(
                        video_file,
                        temp_srt_path,
                        output_path,
                        crf=crf,
                        preset=preset,
                        soft_subtitle=True,
                        progress_callback=self.progress_callback,
                    )
                finally:
                    Path(temp_srt_path).unlink(missing_ok=True)

            else:
                # Phu de cung: render bang cau hinh kieu phu de
                add_subtitles_with_style(
                    video_path=video_file,
                    asr_data=asr_data,
                    output_path=output_path,
                    render_mode=config.render_mode,
                    subtitle_layout=config.subtitle_layout,
                    ass_style=config.ass_style,
                    rounded_style=config.rounded_style,
                    crf=crf,
                    preset=preset,
                    progress_callback=self.progress_callback,
                )

            self.progress.emit(100, self.tr("Hoàn tất ghép video"))
            logger.info(f"Ghep video hoan tat, luu tai: {output_path}")
            self.finished.emit(self.task)

        except Exception as e:
            logger.exception(f"Ghep video that bai: {e}")
            self.error.emit(str(e))
            self.progress.emit(100, self.tr("Ghép video thất bại"))

    def progress_callback(self, value, message):
        progress = int(5 + int(value) / 100 * 95)
        logger.debug(f"Tien do ghep video: {progress}% - {message}")
        self.progress.emit(progress, str(progress) + "% " + message)

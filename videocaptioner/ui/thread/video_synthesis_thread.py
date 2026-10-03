import datetime
import tempfile
from pathlib import Path

from PyQt5.QtCore import QThread, pyqtSignal

from videocaptioner.core.dubbing.completed import (
    CompletedVideo,
    load_video,
    save_video,
    video_identity,
)
from videocaptioner.core.dubbing.output import OutputClaim, video_destination
from videocaptioner.core.entities import SynthesisTask
from videocaptioner.core.llm.context import task_context
from videocaptioner.core.llm.rate_limit import llm_admission_scope
from videocaptioner.core.subtitle.synthesis import load_synthesis_subtitles
from videocaptioner.core.translate.dialogue import fingerprint
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
        self.llm_gate = None
        self.output_reservations = None
        self.output_claim = None
        logger.debug(f"Khoi tao VideoSynthesisThread, task: {self.task}")

    def run(self):
        from videocaptioner.core.utils.subprocess_helper import cancellation_scope
        try:
            with (cancellation_scope(self._check_cancelled), llm_admission_scope(self.llm_gate),
                  task_context(self.task.task_id, Path(self.task.video_path or "").name, "synthesis")):
                self._run()
        finally:
            if self.output_claim:
                self.output_claim.close()

    def _run(self):
        try:
            self._check_cancelled()
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

            if not video_file:
                raise ValueError(self.tr("Đường dẫn video đang trống"))
            if not subtitle_file:
                raise ValueError(self.tr("Đường dẫn phụ đề đang trống"))
            if not output_path:
                raise ValueError(self.tr("Đường dẫn đầu ra đang trống"))

            destination = video_destination(output_path, self.task.output_directory,
                                            self.task.source_video_path or video_file, "synthesis")
            self.task.output_path = output_path = str(destination.output)
            receipt = destination.receipt
            identity = ""
            if self.task.reuse_completed_output:
                identity = fingerprint([video_identity(video_file, subtitle_file, config, check=self._check_cancelled),
                                        self.task.input_subtitle_layout.value if self.task.input_subtitle_layout else None])
                cached = load_video(receipt, identity, self._check_cancelled, root=destination.root)
                if cached:
                    self.task.output_path = cached.output
                    self.progress.emit(100, self.tr("Đã có video hoàn tất; dùng lại, không xuất lại"))
                    self.finished.emit(self.task)
                    return

            from .video_title import prepare_video_title
            prepare_video_title(self.task, self._check_cancelled, self.progress.emit, self.output_reservations)
            if destination.root is not None:
                self.output_claim = OutputClaim(self.task.output_path, self._check_cancelled)
                self.task.output_path = str(self.output_claim.path)
            output_path = self.task.output_path
            assert output_path is not None

            logger.info(f"Bat dau ghep video: {video_file}")
            self.progress.emit(5, self.tr("Đang ghép video"))

            video_quality = config.video_quality
            crf = video_quality.get_crf()
            preset = video_quality.get_preset()

            asr_data = load_synthesis_subtitles(
                subtitle_file, input_layout=self.task.input_subtitle_layout
            )

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
                        output_resolution=config.output_resolution,
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
                    output_resolution=config.output_resolution,
                )

            self._check_cancelled()
            if identity:
                try:
                    save_video(receipt, identity, CompletedVideo(output_path), self._check_cancelled, root=destination.root)
                except (OSError, ValueError):
                    logger.warning("Could not save completed synthesis receipt")
            self.progress.emit(100, self.tr("Hoàn tất ghép video"))
            logger.info(f"Ghep video hoan tat, luu tai: {output_path}")
            self.finished.emit(self.task)

        except Exception as e:
            self.failure = e
            if self.isInterruptionRequested():
                return
            logger.exception(f"Ghep video that bai: {e}")
            self.error.emit(str(e))
            self.progress.emit(100, self.tr("Ghép video thất bại"))

    def progress_callback(self, value, message):
        self._check_cancelled()
        progress = int(5 + int(value) / 100 * 95)
        logger.debug(f"Tien do ghep video: {progress}% - {message}")
        self.progress.emit(progress, str(progress) + "% " + message)

    def _check_cancelled(self):
        if self.isInterruptionRequested() or QThread.currentThread().isInterruptionRequested():
            raise RuntimeError("Video synthesis cancelled.")

    def stop(self):
        self.requestInterruption()

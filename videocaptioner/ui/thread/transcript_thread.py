import datetime
import tempfile
from pathlib import Path

from PyQt5.QtCore import QThread, pyqtSignal

from videocaptioner.core.asr.api_transcription import TranscriptionResult
from videocaptioner.core.asr.local.review import LocalReview
from videocaptioner.core.asr.review import NativeReviewRequired
from videocaptioner.core.asr.transcribe import recognize_text, transcribe
from videocaptioner.core.entities import (
    TranscribeModelEnum,
    TranscribeOutputFormatEnum,
    TranscribeTask,
)
from videocaptioner.core.utils.logger import setup_logger
from videocaptioner.core.utils.video_utils import video2audio

logger = setup_logger("transcript_thread")


class TranscriptThread(QThread):
    finished = pyqtSignal(TranscribeTask)
    progress = pyqtSignal(int, str)
    error = pyqtSignal(str)
    review_required = pyqtSignal(object)

    def __init__(self, task: TranscribeTask):
        super().__init__()
        self.task = task

    def run(self):
        try:
            self.task.started_at = datetime.datetime.now()
            self.task.asr_data = None
            self.task.transcript_path = None
            logger.info(f"\n{self.task.transcribe_config.print_config()}")

            self._validate_task()

            # 检查是否已下载字幕文件
            if self._check_downloaded_subtitle():
                return

            self._perform_transcription()

        except Exception as e:
            message = str(e)
            if isinstance(e, NativeReviewRequired):
                recovered = self._recover_transcript(e)
                if recovered:
                    if not self.task.need_next_task:
                        self.task.output_path = self.task.transcript_path
                        self.progress.emit(100, self.tr("Nhận dạng hoàn tất; đã lưu TXT. Phụ đề cần kiểm tra thời gian."))
                        self.finished.emit(self.task)
                        return
                    message = self.tr("Đã lưu transcript TXT. Pipeline phụ đề dừng vì thời gian chưa hợp lệ: ") + str(self.task.transcript_path)
                self.review_required.emit(e)
            logger.exception("Transcription output could not be completed: %s", message)
            self.error.emit(message)
            self.progress.emit(100, self.tr("转录失败"))

    def _recover_transcript(self, error: NativeReviewRequired) -> bool:
        review = error.review
        if (not isinstance(review, LocalReview) or not review.recognition_complete
                or not self.task.output_path or self.isInterruptionRequested()
                or QThread.currentThread().isInterruptionRequested()):
            return False
        try:
            saved = TranscriptionResult(review.text).save_text(
                Path(self.task.output_path).with_suffix(".txt"), unique=True)
        except OSError:
            return False
        self.task.transcript_path = str(saved)
        return True

    def _validate_task(self):
        """验证任务配置"""
        if not self.task.file_path:
            raise ValueError(self.tr("文件路径为空"))

        video_path = Path(self.task.file_path)
        if not video_path.exists():
            logger.error(f"视频文件不存在：{video_path}")
            raise ValueError(self.tr("视频文件不存在"))

        if not self.task.transcribe_config:
            raise ValueError(self.tr("转录配置为空"))

        if not self.task.output_path:
            raise ValueError(self.tr("输出路径为空"))

    def _check_downloaded_subtitle(self) -> bool:
        """检查是否存在下载的字幕文件"""
        if not (self.task.need_next_task and self.task.file_path):
            return False

        subtitle_dir = Path(self.task.file_path).parent / "subtitle"
        if not subtitle_dir.exists():
            return False

        downloaded_subtitles = list(subtitle_dir.glob("【下载字幕】*"))
        if not downloaded_subtitles:
            return False

        subtitle_file = downloaded_subtitles[0]
        self.task.output_path = str(subtitle_file)
        logger.info(f"字幕文件已下载，跳过转录。找到下载的字幕文件：{subtitle_file}")
        self.progress.emit(100, self.tr("字幕已下载"))
        self.finished.emit(self.task)
        return True

    def _perform_transcription(self):
        """执行转录流程"""
        assert self.task.file_path is not None
        assert self.task.transcribe_config is not None
        assert self.task.output_path is not None

        video_path = Path(self.task.file_path)

        self.progress.emit(5, self.tr("转换音频中"))
        logger.info("开始转换音频")

        # 创建临时音频文件（delete=False 避免 Windows 权限问题）
        temp_audio_file = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        temp_audio_path = temp_audio_file.name
        temp_audio_file.close()  # 立即关闭文件句柄，让 ffmpeg 可以写入

        try:
            # 转换音频文件
            # 获取选中的音轨索引（如果有）
            audio_track_index = self.task.selected_audio_track_index
            is_success = video2audio(
                str(video_path),
                output=temp_audio_path,
                audio_track_index=audio_track_index,
            )
            if not is_success:
                logger.error("音频转换失败")
                raise RuntimeError(self.tr("音频转换失败"))

            self.progress.emit(20, self.tr("语音转录中"))
            logger.info("开始语音转录")

            config = self.task.transcribe_config
            if (config.transcribe_model is TranscribeModelEnum.QWEN_LOCAL
                    and config.output_format is TranscribeOutputFormatEnum.TXT
                    and not self.task.need_next_task):
                result = recognize_text(temp_audio_path, config, callback=self.progress_callback)
                if self.isInterruptionRequested() or QThread.currentThread().isInterruptionRequested():
                    return
                saved = result.save_text(Path(self.task.output_path).with_suffix(".txt"))
                self.task.output_path = self.task.transcript_path = str(saved)
                self.progress.emit(100, self.tr("Đã lưu transcript TXT; không chạy căn thời gian hoặc gán người nói."))
                self.finished.emit(self.task)
                return

            # Timed exports keep their subtitle validation contract.
            asr_data = transcribe(
                temp_audio_path,
                self.task.transcribe_config,
                callback=self.progress_callback,
            )

            self.task.asr_data = asr_data
            if self.isInterruptionRequested() or QThread.currentThread().isInterruptionRequested():
                return

            # Save the configured subtitle formats.
            output_path = Path(self.task.output_path)
            output_format_enum = self.task.transcribe_config.output_format
            base_path = output_path.with_suffix("")

            # 根据选择的格式导出
            if output_format_enum == TranscribeOutputFormatEnum.ALL:
                formats_to_export = [
                    fmt.value.lower()
                    for fmt in TranscribeOutputFormatEnum
                    if fmt != TranscribeOutputFormatEnum.ALL
                ]
            else:
                formats_to_export = [output_format_enum.value.lower()]

            if self.task.need_next_task:
                formats_to_export.append(TranscribeOutputFormatEnum.SRT.value.lower())
            formats_to_export = list(set(formats_to_export))

            # 保存字幕文件
            for fmt in formats_to_export:
                save_path = f"{base_path}.{fmt}"
                asr_data.save(save_path)
                logger.info("%s 字幕文件已保存到: %s", fmt.upper(), save_path)

            self.progress.emit(100, self.tr("转录完成"))
            self.finished.emit(self.task)
        finally:
            Path(temp_audio_path).unlink(missing_ok=True)

    def progress_callback(self, value, message):
        if self.isInterruptionRequested() or QThread.currentThread().isInterruptionRequested():
            from videocaptioner.core.asr.alignment.contract import AlignmentError

            raise AlignmentError("cancelled")
        progress = min(20 + (value * 0.8), 100)
        self.progress.emit(int(progress), message)

    def stop(self):
        self.requestInterruption()

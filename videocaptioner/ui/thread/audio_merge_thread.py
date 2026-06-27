"""Audio merge thread — ghép 1 file audio ngoài vào video (không qua TTS).

Tái dùng mix_audio_tracks với cùng các tuỳ chọn âm thanh như lồng tiếng.
"""

import shutil

from PyQt5.QtCore import QThread, pyqtSignal

from videocaptioner.core.dubbing.audio_mixer import mix_audio_tracks
from videocaptioner.core.dubbing.config import AudioMixMode
from videocaptioner.core.utils.logger import setup_logger

logger = setup_logger("audio_merge_thread")


class AudioMergeThread(QThread):
    """Thread ghép audio ngoài vào video."""

    finished = pyqtSignal(str)  # output_path
    progress = pyqtSignal(int, str)
    error = pyqtSignal(str)

    def __init__(
        self,
        video_path: str,
        audio_path: str,
        output_path: str,
        mix_mode: AudioMixMode,
        original_volume: float,
        voice_volume: float,
    ):
        super().__init__()
        self.video_path = video_path
        self.audio_path = audio_path
        self.output_path = output_path
        self.mix_mode = mix_mode
        self.original_volume = original_volume
        self.voice_volume = voice_volume

    def run(self):
        try:
            if shutil.which("ffmpeg") is None:
                raise RuntimeError(
                    "Không tìm thấy ffmpeg. Vui lòng cài FFmpeg và thêm vào PATH."
                )

            self.progress.emit(10, self.tr("Đang ghép audio vào video..."))
            ok = mix_audio_tracks(
                self.video_path,
                self.audio_path,
                self.output_path,
                mix_mode=self.mix_mode,
                original_volume=self.original_volume,
                voice_volume=self.voice_volume,
            )
            if not ok:
                raise RuntimeError("Ghép audio thất bại (xem log để biết chi tiết)")

            self.progress.emit(100, self.tr("Ghép audio hoàn tất"))
            self.finished.emit(self.output_path)

        except Exception as e:
            logger.exception("Ghép audio thất bại: %s", e)
            self.error.emit(str(e))
            self.progress.emit(100, self.tr("Ghép audio thất bại"))

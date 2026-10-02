"""A bounded reference recorder, activated only by an explicit user action."""

import wave
from uuid import uuid4

from PyQt5.QtCore import QObject, QTimer, pyqtSignal
from PyQt5.QtMultimedia import QAudio, QAudioDeviceInfo, QAudioFormat, QAudioInput

from videocaptioner.core.tts.omnivoice import voices


class ReferenceRecorder(QObject):
    recorded = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.active = False
        self.input = None
        self.stream = None
        self.buffer = bytearray()
        self.rate, self.channels = 24000, 1
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.stop)

    def start(self):
        if self.active:
            return
        device = QAudioDeviceInfo.defaultInputDevice()
        if device.isNull():
            self.failed.emit("Không tìm thấy microphone mặc định.")
            return
        chosen = None
        for rate in (24000, 48000, 44100, 16000):
            for channels in (1, 2):
                fmt = QAudioFormat()
                fmt.setCodec("audio/pcm")
                fmt.setSampleRate(rate)
                fmt.setChannelCount(channels)
                fmt.setSampleSize(16)
                fmt.setSampleType(QAudioFormat.SignedInt)
                fmt.setByteOrder(QAudioFormat.LittleEndian)
                if device.isFormatSupported(fmt):
                    chosen = fmt
                    break
            if chosen is not None:
                break
        if chosen is None:
            self.failed.emit("Microphone không hỗ trợ PCM16 tương thích.")
            return
        self.buffer.clear()
        self.rate, self.channels = chosen.sampleRate(), chosen.channelCount()
        self.input = QAudioInput(device, chosen, self)
        self.input.stateChanged.connect(self._state_changed)
        self.active = True
        self.stream = self.input.start()
        if not self.active:
            return
        if self.stream is None:
            self.cancel()
            self.failed.emit("Không mở được microphone; kiểm tra quyền microphone của ứng dụng.")
            return
        self.stream.readyRead.connect(self._read)
        self.timer.start(10000)

    def _state_changed(self, state):
        if self.active and state == QAudio.State.StoppedState and self.input and self.input.error() != QAudio.Error.NoError:
            self.cancel()
            self.failed.emit("Microphone đã dừng do lỗi thiết bị.")

    def _read(self):
        if not self.active or self.stream is None:
            return
        limit = self.rate * self.channels * 2 * 10
        self.buffer.extend(bytes(self.stream.readAll())[:max(0, limit - len(self.buffer))])
        if len(self.buffer) >= limit:
            self.stop()

    def cancel(self):
        self.stop(save=False)

    def stop(self, *, save=True):
        if not self.active:
            return
        if self.stream is not None:
            limit = self.rate * self.channels * 2 * 10
            self.buffer.extend(bytes(self.stream.readAll())[:max(0, limit - len(self.buffer))])
        self.active = False
        self.timer.stop()
        if self.input is not None:
            self.input.stop()
            self.input.deleteLater()
        self.input = self.stream = None
        if not save:
            self.buffer.clear()
            return
        try:
            frame_bytes = 2 * self.channels
            frames = len(self.buffer) // frame_bytes
            if not 3 <= frames / self.rate <= 10 or not any(self.buffer):
                raise ValueError("Thu mẫu có tiếng dài 3–10 giây, rồi thử lại.")
            root = voices.library_root() / "recordings"
            root.mkdir(parents=True, exist_ok=True)
            path = root / (uuid4().hex + ".wav")
            with wave.open(str(path), "wb") as audio:
                audio.setnchannels(self.channels)
                audio.setsampwidth(2)
                audio.setframerate(self.rate)
                audio.writeframes(bytes(self.buffer[:frames * frame_bytes]))
            self.recorded.emit(str(path))
        except Exception as exc:
            self.failed.emit(str(exc))
        finally:
            self.buffer.clear()

import hashlib
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Callable, List, Optional, Union

try:
    import GPUtil
except ImportError:
    GPUtil = None  # type: ignore[assignment]

from videocaptioner.core.utils.subprocess_helper import child_environment

from ..utils.logger import setup_logger
from ..utils.subprocess_helper import StreamReader
from .asr_data import ASRData, ASRDataSeg
from .base import BaseASR
from .status import ASRStatus

logger = setup_logger("faster_whisper")
MIN_PROGRAM_SIZE = 1024 * 1024


def _is_valid_program(path: Optional[str]) -> bool:
    if not path:
        return False
    program_path = Path(path)
    try:
        return program_path.is_file() and program_path.stat().st_size >= MIN_PROGRAM_SIZE
    except OSError:
        return False


def _which_valid(program: str) -> Optional[str]:
    path = shutil.which(program)
    return path if _is_valid_program(path) else None


class FasterWhisperASR(BaseASR):
    """Faster-Whisper local ASR implementation.

    Runs whisper model locally using faster-whisper/faster-whisper-xxl binary.
    Supports CPU/CUDA acceleration and various VAD methods.
    """

    def __init__(
        self,
        audio_input: Union[str, bytes],
        faster_whisper_program: str,
        whisper_model: str,
        model_dir: str,
        language: str = "zh",
        device: str = "cpu",
        output_dir: Optional[str] = None,
        output_format: str = "srt",
        use_cache: bool = False,
        need_word_time_stamp: bool = False,
        # VAD parameters
        vad_filter: bool = True,
        vad_threshold: float = 0.4,
        vad_method: str = "",  # https://github.com/Purfview/whisper-standalone-win/discussions/231
        # Audio processing
        ff_mdx_kim2: bool = False,
        # Text processing parameters
        one_word: int = 0,
        sentence: bool = False,
        max_line_width: int = 100,
        max_line_count: int = 1,
        max_comma: int = 20,
        max_comma_cent: int = 50,
        prompt: Optional[str] = None,
    ):
        super().__init__(audio_input, use_cache)

        # Basic parameters
        self.model_path = whisper_model
        self.model_dir = model_dir
        self.faster_whisper_program = faster_whisper_program
        self.need_word_time_stamp = need_word_time_stamp
        self.language = language
        self.device = device
        self.output_dir = output_dir
        self.output_format = output_format

        # VAD parameters
        self.vad_filter = vad_filter
        self.vad_threshold = vad_threshold
        self.vad_method = vad_method

        # Audio processing parameters
        self.ff_mdx_kim2 = ff_mdx_kim2

        # Text processing parameters
        self.one_word = one_word
        self.sentence = sentence
        self.max_line_width = max_line_width
        self.max_line_count = max_line_count
        self.max_comma = max_comma
        self.max_comma_cent = max_comma_cent
        self.prompt = prompt

        self.process = None

        # Line width for sentence splitting
        if self.language in ["zh", "ja", "ko"]:
            self.max_line_width = 30
        else:
            self.max_line_width = 90

        # Sentence splitting options
        if self.need_word_time_stamp:
            self.one_word = 1
        else:
            self.one_word = 0
            self.sentence = True

        # Pick the binary by device
        if self.device == "cpu":
            xxl_program = _which_valid("faster-whisper-xxl")
            cpu_program = _which_valid("faster-whisper")
            if xxl_program:
                self.faster_whisper_program = xxl_program
            elif cpu_program:
                self.faster_whisper_program = cpu_program
                self.vad_method = ""
            else:
                raise EnvironmentError(
                    "Không tìm thấy chương trình Faster Whisper hợp lệ. "
                    "Vui lòng tải lại chương trình trong phần Quản lý mô hình."
                )
        elif self.device == "cuda":
            xxl_program = _which_valid("faster-whisper-xxl")
            if not xxl_program:
                raise EnvironmentError(
                    "Không tìm thấy Faster Whisper GPU hợp lệ. "
                    "Tệp chương trình có thể bị hỏng hoặc chưa tải xong. "
                    "Vui lòng tải lại bản GPU trong Quản lý mô hình, "
                    "hoặc đổi Thiết bị chạy sang cpu nếu chỉ dùng bản CPU."
                )
            self.faster_whisper_program = xxl_program

    def _build_command(self, audio_input: str) -> List[str]:
        """Build command line arguments for faster-whisper."""

        cmd = [
            str(self.faster_whisper_program),
            "-m",
            str(self.model_path),
            # "--verbose", "true",
            "--print_progress",
        ]

        # Model directory argument
        if self.model_dir:
            cmd.extend(["--model_dir", str(self.model_dir)])

        cmd.extend([str(audio_input), "-d", self.device, "--output_format", self.output_format])

        # Pass -l only for an explicit language; empty lets faster-whisper auto-detect
        if self.language:
            cmd.extend(["-l", self.language])

        # Output directory
        if self.output_dir:
            cmd.extend(["-o", str(self.output_dir)])
        else:
            cmd.extend(["-o", "source"])

        # VAD parameters
        if self.vad_filter:
            cmd.extend(
                [
                    "--vad_filter",
                    "true",
                    "--vad_threshold",
                    f"{self.vad_threshold:.2f}",
                ]
            )
            if self.vad_method:
                cmd.extend(["--vad_method", self.vad_method])
        else:
            cmd.extend(["--vad_filter", "false"])

        # Vocal separation
        if self.ff_mdx_kim2 and self.faster_whisper_program.startswith(
            "faster-whisper-xxl"
        ):
            cmd.append("--ff_mdx_kim2")

        # Text processing parameters
        if self.one_word:
            self.one_word = 1
        else:
            self.one_word = 0
        if self.one_word in [0, 1, 2]:
            cmd.extend(["--one_word", str(self.one_word)])

        if self.sentence:
            cmd.extend(
                [
                    "--sentence",
                    "--max_line_width",
                    str(self.max_line_width),
                    "--max_line_count",
                    str(self.max_line_count),
                    "--max_comma",
                    str(self.max_comma),
                    "--max_comma_cent",
                    str(self.max_comma_cent),
                ]
            )

        # Prompt
        if self.prompt:
            cmd.extend(["--initial_prompt", self.prompt])

        # Silence the completion beep
        cmd.extend(["--beep_off"])

        # RTX 50-series GPUs need an explicit compute_type
        if is_rtx_50_series():
            cmd.extend(["--compute_type", "float16"])

        return cmd

    def _make_segments(self, resp_data: str) -> List[ASRDataSeg]:
        asr_data = ASRData.from_srt(resp_data)

        # Keywords that mark hallucinated text
        hallucination_keywords = [
            "请不吝点赞 订阅 转发",
            "打赏支持明镜",
        ]
        # Drop music markers and hallucinated text
        filtered_segments = []
        for seg in asr_data.segments:
            text = seg.text.strip()

            # Skip music markers
            if text.startswith(("【", "[", "(", "（")):
                continue

            # Skip text containing hallucination keywords
            if any(keyword in text for keyword in hallucination_keywords):
                continue

            filtered_segments.append(seg)

        return filtered_segments

    def _run(
        self, callback: Optional[Callable[[int, str], None]] = None, **kwargs: Any
    ) -> str:
        def _default_callback(x, y):
            pass

        if callback is None:
            callback = _default_callback

        with tempfile.TemporaryDirectory() as temp_path:
            temp_dir = Path(temp_path)
            wav_path = temp_dir / "audio.wav"
            output_path = wav_path.with_suffix(".srt")

            if isinstance(self.audio_input, str):
                shutil.copy2(self.audio_input, wav_path)
            else:
                if self.file_binary:
                    wav_path.write_bytes(self.file_binary)
                else:
                    raise ValueError("No audio data available")

            cmd = self._build_command(str(wav_path))

            logger.debug("Faster Whisper command: %s", " ".join(cmd))
            callback(*ASRStatus.TRANSCRIBING.with_progress(5))

            self.process = subprocess.Popen(
                cmd, env=child_environment(),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="ignore",
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )

            # Consume output through StreamReader
            reader = StreamReader(self.process)
            reader.start_reading()

            is_finish = False
            error_msg = ""
            last_progress = 0

            # Process output as it arrives
            while True:
                # Check process state
                if self.process.poll() is not None:
                    # Process ended; read the remaining output
                    for _stream_name, line in reader.get_remaining_output():
                        line = line.strip()
                        if line:
                            if "error" in line:
                                error_msg += line
                            else:
                                logger.debug(line)
                    break

                # Read output
                output = reader.get_output(timeout=0.1)
                if output:
                    _stream_name, line = output
                    line = line.strip()
                    if line:
                        # Parse the progress percentage
                        if match := re.search(r"(\d+)%", line):
                            progress = int(match.group(1))
                            if progress == 100:
                                is_finish = True
                            mapped_progress = int(5 + (progress * 0.9))
                            # Progress may only increase
                            if mapped_progress > last_progress:
                                last_progress = mapped_progress
                                callback(mapped_progress, f"{mapped_progress}%")
                        if "Subtitles are written to" in line:
                            is_finish = True
                            callback(*ASRStatus.COMPLETED.callback_tuple())
                        if "error" in line or "Error" in line:
                            error_msg += line
                            logger.error(line)
                        else:
                            logger.debug(line)

            if not is_finish:
                logger.error("Faster Whisper Error: %s", error_msg)
                raise RuntimeError(error_msg)

            # Decide whether recognition succeeded
            if not output_path.exists():
                logger.debug("Faster Whisper 返回值: %s", self.process.returncode)
                raise RuntimeError(f"Faster Whisper 输出文件不存在: {output_path}")

            logger.debug("Faster Whisper ASR completed")

            callback(*ASRStatus.COMPLETED.callback_tuple())

            return output_path.read_text(encoding="utf-8")

    def _get_key(self):
        """Cache key for this configuration."""
        cmd = self._build_command("")
        cmd_hash = hashlib.md5(str(cmd).encode()).hexdigest()
        return f"{self.crc32_hex}-{cmd_hash}"


def is_rtx_50_series() -> bool:
    """Whether the GPU is an RTX 50-series card."""
    if GPUtil is None:
        logger.debug("GPUtil 未安装，无法检测 GPU 型号")
        return False
    try:
        gpus = GPUtil.getGPUs()
        for gpu in gpus:
            gpu_name = gpu.name.lower()
            # Look for a 50-series marker such as RTX 5090 or RTX 5080
            if re.search(r"rtx\s*50\d{2}", gpu_name):
                logger.debug(f"Detected RTX 50 系显卡: {gpu.name}")
                return True
    except Exception as e:
        logger.debug(f"无法检测 GPU 型号: {e}")
    return False

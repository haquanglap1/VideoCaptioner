"""Draft reference transcripts using an already installed local Whisper model."""

import re
from dataclasses import dataclass, field, replace
from pathlib import Path


@dataclass(frozen=True)
class ReferenceASROptions:
    program: str = ""
    model_dir: str = ""
    model: str = "tiny"
    language: str = "vi"
    device: str = "cuda"
    timeout: int = 300

    def __post_init__(self):
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", self.model) or self.device not in ("cpu", "cuda"):
            raise ValueError("Invalid installed Whisper model or device")
        if type(self.timeout) is not int or not 1 <= self.timeout <= 3600:
            raise ValueError("Reference ASR timeout must be 1-3600 seconds")


@dataclass(frozen=True)
class ReferenceTranscript:
    audio_path: str = field(repr=False)
    text: str = field(repr=False)
    source_stamp: tuple[int, int]


def transcribe_reference(audio_path: str, options: ReferenceASROptions, check=lambda: None) -> ReferenceTranscript:
    from videocaptioner.config import MODEL_PATH
    from videocaptioner.core.asr.alignment.audio import decode_audio, wav_bytes
    from videocaptioner.core.asr.alignment.contract import AlignmentError
    from videocaptioner.core.asr.faster_whisper import FasterWhisperASR
    from videocaptioner.core.asr.local.sentence_fallback import WhisperSentenceFallback
    from videocaptioner.core.entities import TranscribeConfig

    source = Path(audio_path)
    before = source.stat()
    if before.st_size > 50 * 1024 * 1024:
        raise ValueError("Reference audio must be smaller than 50 MiB")
    root = Path(options.model_dir) if options.model_dir else MODEL_PATH
    model = root / f"faster-whisper-{options.model}"
    if not all((model / name).is_file() for name in ("model.bin", "config.json", "tokenizer.json")):
        raise ValueError("Chọn model Faster-Whisper đã cài; chép lời mẫu không tự tải model.")
    check()
    audio = decode_audio(str(source), check)
    if not 3000 <= len(audio) <= 10000 or not audio.rms:
        raise ValueError("Giọng mẫu cần có tiếng, dài 3–10 giây.")
    binary = wav_bytes(audio)
    engine = FasterWhisperASR(binary, options.program, options.model, str(root.resolve()),
        language=options.language, device=options.device, vad_filter=False, need_word_time_stamp=False)
    config = TranscribeConfig()
    config.local_asr = replace(config.local_asr, timeout=options.timeout)
    # Reuse the existing cancellable, leased subprocess runner, without Qwen inference or fallback logic.
    try:
        raw = WhisperSentenceFallback(config)._request(engine, binary, check)
    except AlignmentError:
        raise RuntimeError("Không chép được lời mẫu bằng Faster-Whisper đã cài; kiểm tra chương trình/model hoặc nhập lời thủ công.") from None
    segments = engine._make_segments(raw)
    text = " ".join(segment.text.strip() for segment in segments if segment.text.strip())
    after = source.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ValueError("Audio mẫu đã thay đổi trong khi chép lời; hãy chạy lại trên mẫu mới.")
    check()
    if not text:
        raise ValueError("ASR không tìm thấy lời; nhập transcript thủ công.")
    return ReferenceTranscript(str(source.resolve()), text, (after.st_size, after.st_mtime_ns))

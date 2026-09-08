from contextlib import nullcontext
from copy import deepcopy

from videocaptioner.core.asr.aligned_api import AlignedAPI
from videocaptioner.core.asr.alignment.audio import decode_audio
from videocaptioner.core.asr.api_profiles import resolve_profile
from videocaptioner.core.asr.asr_data import ASRData
from videocaptioner.core.asr.audio_identity import identify_audio
from videocaptioner.core.asr.bcut import BcutASR
from videocaptioner.core.asr.chunked_asr import ChunkedASR
from videocaptioner.core.asr.faster_whisper import FasterWhisperASR
from videocaptioner.core.asr.jianying import JianYingASR
from videocaptioner.core.asr.local.audio import source_snapshot
from videocaptioner.core.asr.local.pipeline import (
    QwenLocalASR,
    add_local_speakers,
    diarization_preflight,
)
from videocaptioner.core.asr.native_api import NativeASR
from videocaptioner.core.asr.whisper_api import WhisperAPI
from videocaptioner.core.asr.whisper_cpp import WhisperCppASR
from videocaptioner.core.entities import TranscribeConfig, TranscribeModelEnum


def transcribe(audio_path: str, config: TranscribeConfig, callback=None) -> ASRData:
    """Transcribe audio file using specified configuration.

    Args:
        audio_path: Path to audio file
        config: Transcription configuration
        callback: Progress callback function(progress: int, message: str)

    Returns:
        ASRData: Transcription result data
    """

    def _default_callback(x, y):
        pass

    if callback is None:
        callback = _default_callback

    if config.transcribe_model is None:
        raise ValueError("Transcription model not set")

    config = deepcopy(config)
    # Text-only language/runtime validation must precede source IO as in S2.
    prepared = None
    if (config.transcribe_model is TranscribeModelEnum.WHISPER_API and not resolve_profile(
            config.whisper_api_model or "whisper-1", config.whisper_api_request_profile,
            config.whisper_api_provider).timestamp_levels):
        prepared = AlignedAPI(audio_path, config)

    # Create ASR instance based on model type
    if config.local_asr.diarize:
        if config.transcribe_model not in (TranscribeModelEnum.QWEN_LOCAL, TranscribeModelEnum.WHISPER_API):
            raise ValueError("Local diarization supports Qwen Local or Whisper API; do not merge native speaker labels implicitly.")
        diarization_preflight(config.local_asr)
        # Fail local health before spending on gateway recognition.
        if config.transcribe_model is TranscribeModelEnum.WHISPER_API:
            from videocaptioner.core.asr.local.runtime import LocalRuntime
            def check():
                callback(0, "Checking local diarization before recognition")
            runtime = LocalRuntime(diarization_preflight(config.local_asr, verify=True, check=check), config.local_asr.timeout)
            try:
                runtime.start(check)
            finally:
                runtime.close()
    def snapshot_check():
        callback(0, "Preparing hybrid audio snapshot")

    snapshot_required = config.local_asr.diarize or config.transcribe_model in (
        TranscribeModelEnum.WHISPER_API, TranscribeModelEnum.SONIOX, TranscribeModelEnum.SCRIBE)
    source = source_snapshot(audio_path, snapshot_check) if snapshot_required else nullcontext(audio_path)
    with source as job_audio:
        if prepared is not None:
            prepared.audio_path = job_audio
        asr = prepared if prepared is not None else _create_asr_instance(job_audio, config)
        identity = None
        if isinstance(asr, (ChunkedASR, NativeASR)) and snapshot_required:
            identity = identify_audio(decode_audio(job_audio, snapshot_check), snapshot_check)
            if isinstance(asr, NativeASR):
                asr.audio_identity = identity
        asr_data = asr.run(callback=callback)
        if identity is not None:
            asr_data.audio_identity = identity
        asr_data.pending_diarization = config.local_asr.diarize
        if config.local_asr.diarize:
            return add_local_speakers(job_audio, asr_data, config, aligned=isinstance(asr, AlignedAPI), callback=callback)
        if (not config.need_word_time_stamp and config.transcribe_model is not TranscribeModelEnum.FASTER_WHISPER
                and not isinstance(asr, (AlignedAPI, NativeASR, QwenLocalASR))):
            asr_data.optimize_timing()
        return asr_data


def _create_asr_instance(audio_path: str, config: TranscribeConfig) -> ChunkedASR | AlignedAPI | NativeASR | QwenLocalASR:
    """Create appropriate ASR instance based on configuration.

    Args:
        audio_path: Path to audio file
        config: Transcription configuration

    Returns:
        ChunkedASR: Chunked ASR instance ready to run
    """
    model_type = config.transcribe_model
    if model_type == TranscribeModelEnum.QWEN_LOCAL:
        return QwenLocalASR(audio_path, config)

    if model_type in (TranscribeModelEnum.SONIOX, TranscribeModelEnum.SCRIBE):
        expected = "soniox" if model_type == TranscribeModelEnum.SONIOX else "scribe"
        if config.native_asr is None or config.native_asr.provider != expected:
            raise ValueError("Configure credentials for the selected native ASR provider.")
        return NativeASR(audio_path, config.native_asr, config.transcribe_language, config.need_word_time_stamp)

    if model_type == TranscribeModelEnum.JIANYING:
        return _create_jianying_asr(audio_path, config)

    elif model_type == TranscribeModelEnum.BIJIAN:
        return _create_bijian_asr(audio_path, config)

    elif model_type == TranscribeModelEnum.WHISPER_CPP:
        return _create_whisper_cpp_asr(audio_path, config)

    elif model_type == TranscribeModelEnum.WHISPER_API:
        return _create_whisper_api_asr(audio_path, config)

    elif model_type == TranscribeModelEnum.FASTER_WHISPER:
        return _create_faster_whisper_asr(audio_path, config)

    else:
        raise ValueError(f"Invalid transcription model: {model_type}")


def _create_jianying_asr(audio_path: str, config: TranscribeConfig) -> ChunkedASR:
    """Create JianYing ASR instance with chunking support."""
    asr_kwargs = {
        "use_cache": True,
        "need_word_time_stamp": config.need_word_time_stamp,
    }
    return ChunkedASR(
        asr_class=JianYingASR, audio_path=audio_path, asr_kwargs=asr_kwargs
    )


def _create_bijian_asr(audio_path: str, config: TranscribeConfig) -> ChunkedASR:
    """Create Bijian ASR instance with chunking support."""
    asr_kwargs = {
        "use_cache": True,
        "need_word_time_stamp": config.need_word_time_stamp,
    }
    return ChunkedASR(asr_class=BcutASR, audio_path=audio_path, asr_kwargs=asr_kwargs)


def _create_whisper_cpp_asr(audio_path: str, config: TranscribeConfig) -> ChunkedASR:
    """Create WhisperCpp ASR instance with chunking support."""
    asr_kwargs = {
        "use_cache": True,
        "need_word_time_stamp": config.need_word_time_stamp,
        "language": config.transcribe_language,
        "whisper_model": config.whisper_model.value if config.whisper_model else None,
    }
    return ChunkedASR(
        asr_class=WhisperCppASR,
        audio_path=audio_path,
        asr_kwargs=asr_kwargs,
        chunk_concurrency=1,  # Avoid concurrent local model loads.
        chunk_length=60 * 20,
    )


def _create_whisper_api_asr(audio_path: str, config: TranscribeConfig) -> ChunkedASR | AlignedAPI | NativeASR:
    """Create Whisper API ASR instance with chunking support."""
    profile = resolve_profile(
        config.whisper_api_model or "whisper-1",
        config.whisper_api_request_profile, config.whisper_api_provider,
    )
    if not profile.timestamp_levels:
        return AlignedAPI(audio_path, config)
    asr_kwargs = {
        "provider": config.whisper_api_provider,
        "request_profile": config.whisper_api_request_profile,
        "use_cache": True,
        "need_word_time_stamp": config.need_word_time_stamp,
        "language": config.transcribe_language,
        "whisper_model": config.whisper_api_model or "whisper-1",
        "api_key": config.whisper_api_key or "",
        "base_url": config.whisper_api_base or "",
        "prompt": config.whisper_api_prompt or "",
    }
    return ChunkedASR(
        asr_class=WhisperAPI, audio_path=audio_path, asr_kwargs=asr_kwargs
    )


def _create_faster_whisper_asr(audio_path: str, config: TranscribeConfig) -> ChunkedASR:
    """Create FasterWhisper ASR instance with chunking support."""
    asr_kwargs = {
        "use_cache": True,
        "need_word_time_stamp": config.need_word_time_stamp,
        "faster_whisper_program": config.faster_whisper_program or "",
        "language": config.transcribe_language,
        "whisper_model": (
            config.faster_whisper_model.value if config.faster_whisper_model else "base"
        ),
        "model_dir": config.faster_whisper_model_dir or "",
        "device": config.faster_whisper_device,
        "vad_filter": config.faster_whisper_vad_filter,
        "vad_threshold": config.faster_whisper_vad_threshold,
        "vad_method": (
            config.faster_whisper_vad_method.value
            if config.faster_whisper_vad_method
            else ""
        ),
        "ff_mdx_kim2": config.faster_whisper_ff_mdx_kim2,
        "one_word": config.faster_whisper_one_word,
        "prompt": config.faster_whisper_prompt,
    }
    return ChunkedASR(
        asr_class=FasterWhisperASR,
        audio_path=audio_path,
        asr_kwargs=asr_kwargs,
        chunk_concurrency=1,  # Avoid concurrent local model loads.
        chunk_length=60 * 20,
    )


if __name__ == "__main__":
    # Example usage.
    from videocaptioner.core.entities import WhisperModelEnum

    # Create configuration.
    config = TranscribeConfig(
        transcribe_model=TranscribeModelEnum.WHISPER_CPP,
        transcribe_language="zh",
        whisper_model=WhisperModelEnum.MEDIUM,
    )

    # Transcribe audio.
    audio_file = "test.wav"

    def progress_callback(progress: int, message: str):
        print(f"Progress: {progress}%, Message: {message}")

    result = transcribe(audio_file, config, callback=progress_callback)
    print(result)

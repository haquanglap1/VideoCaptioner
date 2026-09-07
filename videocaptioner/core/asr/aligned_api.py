"""Text-only API recognition followed by strict Chinese alignment in a job-owned process."""

from __future__ import annotations

from typing import Callable

from videocaptioner.core.entities import TranscribeConfig
from videocaptioner.core.utils.cache import get_asr_cache, is_cache_enabled

from .alignment.audio import decode_audio, split_audio, verify_acoustic_support, wav_bytes
from .alignment.contract import (
    AlignmentError,
    alignment_key,
    chinese_language,
    merge_chunks,
    validate_alignment,
)
from .alignment.runtime import AlignmentRuntime, locate_runtime
from .api_profiles import ASRAPIError, fingerprint, normalize_endpoint, resolve_profile
from .api_transcription import (
    build_request,
    effective_language,
    effective_prompt,
    parse_response,
    submit_cancellable,
)
from .asr_data import ASRData


class AlignedAPI:
    def __init__(self, audio_path: str, config: TranscribeConfig):
        self.config = config
        self.audio_path = audio_path
        # Preflight before reading/splitting audio; heavy health runs in run(), already in a worker.
        chinese_language(config.transcribe_language)
        self.layout = locate_runtime()
        self.endpoint = normalize_endpoint(config.whisper_api_base or "")
        if not (config.whisper_api_key or "").strip():
            raise ASRAPIError("ASR API key must be set.")

    def run(self, callback: Callable[[int, str], None] | None = None) -> ASRData:
        config = self.config
        progress = 0

        def check():
            if callback:
                callback(progress, "Chinese alignment")

        runtime = AlignmentRuntime(self.layout)
        try:
            runtime.start(config.transcribe_language, check)
            audio = decode_audio(self.audio_path, check)
            chunks = split_audio(audio, check)
            model = config.whisper_api_model or "whisper-1"
            profile = resolve_profile(model, config.whisper_api_request_profile, config.whisper_api_provider)
            language = effective_language(config.transcribe_language)
            prompt = effective_prompt(language, config.whisper_api_prompt or "")
            cache = get_asr_cache()
            results = []
            for index, (chunk, offset) in enumerate(chunks):
                check()
                binary = wav_bytes(chunk)
                key = "ASRText:" + fingerprint(binary, self.endpoint, model, language, prompt,
                                                profile, False, config.whisper_api_provider)
                response = cache.get(key) if is_cache_enabled() else None
                if response is None:
                    response = submit_cancellable(self.endpoint, config.whisper_api_key or "", build_request(
                        binary, model, profile, language=language, prompt=prompt), check)
                    # Persist only parsed text. Alignment has an independent revision/policy cache.
                    response = {"text": parse_response(response).text}
                    cache.set(key, response, expire=86400 * 2)
                check()
                text = parse_response(response).text
                align_key = alignment_key(binary, text, language)
                items = cache.get(align_key) if is_cache_enabled() else None
                if items is None:
                    items = runtime.align(binary, text, check) if text else []
                result = validate_alignment(text, items, len(chunk), offset)
                if not text and chunk.rms > 104:
                    raise AlignmentError("empty transcript on audible input")
                verify_acoustic_support(chunk, result.spans)
                cache.set(align_key, items, expire=86400 * 2)
                results.append(result)
                progress = (index + 1) * 100 // len(chunks)
                check()
            return merge_chunks(results, len(audio), config.need_word_time_stamp)
        finally:
            runtime.close()

"""Text-only API recognition followed by strict Chinese alignment in a job-owned process."""

from __future__ import annotations

from dataclasses import replace
from typing import Callable
from uuid import uuid4

from videocaptioner.core.entities import TranscribeConfig
from videocaptioner.core.utils.cache import get_asr_cache, is_cache_enabled

from .alignment.audio import decode_audio, split_audio, verify_acoustic_support, wav_bytes
from .alignment.contract import (
    AlignmentError,
    alignment_key,
    chinese_language,
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
from .audio_identity import identify_audio
from .local.pipeline import retain_review
from .local.review import LocalReview
from .local.runtime import LocalRuntime, LocalRuntimeError, locate
from .metadata import StageProvenance
from .native_result import native_cues


class AlignedAPI:
    def __init__(self, audio_path: str, config: TranscribeConfig):
        self.config = config
        self.audio_path = audio_path
        # Preflight before reading/splitting audio; heavy health runs in run(), already in a worker.
        chinese_language(config.transcribe_language)
        self.local_layout = locate("aligner", config.local_asr.runtime_root) if config.local_asr.runtime_root else None
        self.layout = None if self.local_layout else locate_runtime()
        self.endpoint = normalize_endpoint(config.whisper_api_base or "")
        if not (config.whisper_api_key or "").strip():
            raise ASRAPIError("ASR API key must be set.")

    def run(self, callback: Callable[[int, str], None] | None = None) -> ASRData:
        config = self.config
        progress = 0

        def check():
            if callback:
                callback(progress, "Chinese alignment")

        if self.local_layout:
            self.local_layout = locate("aligner", config.local_asr.runtime_root, verify=True, check=check)
        runtime = (LocalRuntime(self.local_layout, config.local_asr.timeout) if self.local_layout
                   else AlignmentRuntime(self.layout))
        try:
            if isinstance(runtime, LocalRuntime):
                runtime.start(check)
            else:
                runtime.start(config.transcribe_language, check)
            audio = decode_audio(self.audio_path, check)
            identity = identify_audio(audio, check)
            chunks = split_audio(audio, check)
            model = config.whisper_api_model or "whisper-1"
            profile = resolve_profile(model, config.whisper_api_request_profile, config.whisper_api_provider)
            language = effective_language(config.transcribe_language)
            prompt = effective_prompt(language, config.whisper_api_prompt or "")
            cache = get_asr_cache()
            texts, raw = [], []
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
                texts.append(text)
                progress = (index + 1) * 45 // len(chunks)
            # Preserve the whole recognition before alignment can reject any chunk.
            failure, rejected = "", []
            for index, ((chunk, offset), text) in enumerate(zip(chunks, texts)):
                check()
                binary = wav_bytes(chunk)
                align_key = alignment_key(binary, text, language)
                items = cache.get(align_key) if is_cache_enabled() else None
                try:
                    if items is None:
                        if not text:
                            items = []
                        elif isinstance(runtime, LocalRuntime):
                            items = runtime.request(binary, text, check)
                        else:
                            items = runtime.align(binary, text, check)
                    if not isinstance(items, list) or any(not isinstance(i, dict) or not isinstance(i.get("text"), str) for i in items):
                        raise AlignmentError("malformed alignment response")
                    raw.append(items)
                    result = validate_alignment(text, items, len(chunk), offset)
                    if not text and chunk.rms > 104:
                        raise AlignmentError("empty transcript on audible input")
                    try:
                        verify_acoustic_support(chunk, result.spans)
                    except AlignmentError:
                        rejected.append(index)
                        raise
                except (AlignmentError, LocalRuntimeError) as exc:
                    check()
                    failure = str(exc)
                    break
                cache.set(align_key, items, expire=86400 * 2)
                progress = 45 + (index + 1) * 55 // len(chunks)
                check()
            review = LocalReview.capture_chunks(
                stage=StageProvenance("whisper-api", model, "", "api-profile-v1"), scope=uuid4().hex,
                durations=[(offset, len(chunk)) for chunk, offset in chunks], texts=texts, raw=raw,
                word_timing=True, audio_identity=identity)
            review = replace(review, pending_diarization=config.local_asr.diarize,
                             recognition_complete=all(text or chunk.rms <= 104 for (chunk, _), text in zip(chunks, texts)),
                             acoustic_rejected=tuple(t for i in rejected for t in review.chunks[i].token_ids))
            if failure:
                retain_review(review, failure)
            try:
                data = review.resume()
            except ValueError as exc:
                retain_review(review, str(exc))
            return data if config.need_word_time_stamp or config.local_asr.diarize else native_cues(data)
        finally:
            runtime.close()

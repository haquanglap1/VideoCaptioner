"""Sequential recognition → strict alignment → optional whole-job speaker association."""

import hashlib
import json
from dataclasses import replace
from uuid import uuid4

from videocaptioner.core.utils.cache import get_asr_cache, is_cache_enabled

from ..alignment.audio import decode_audio, split_audio, verify_acoustic_support, wav_bytes
from ..alignment.contract import (
    MODEL_REPOSITORY,
    MODEL_REVISION,
    POLICY,
    AlignmentError,
    chinese_language,
    validate_alignment,
)
from ..asr_data import ASRData
from ..audio_identity import identify_audio, require_audio_match
from ..metadata import ASRMetadata, StageProvenance
from ..native_result import native_cues
from ..review import NativeReviewRequired
from .diarization import (
    assemble_diarized_cues,
    associate,
    diarization_key,
    validate_model_spans,
    validate_source,
)
from .profiles import MODELS, RECOGNITION_POLICY, LocalASRConfig
from .review import LocalReview
from .runtime import LocalRuntime, LocalRuntimeError, locate


def stage_key(stage: str, audio: bytes, model_id: str, options: object) -> str:
    model = MODELS[model_id]
    payload = [hashlib.sha256(audio).hexdigest(), model.repository, model.revision, options]
    return f"local-{stage}:v1-" + hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def retain_review(review: LocalReview, reason: str):
    try:
        path = review.save_new()
    except OSError:
        path = None
    raise NativeReviewRequired(review, reason, path)


class QwenLocalASR:
    def __init__(self, audio_path: str, config):
        self.audio_path, self.config = audio_path, config
        self.options = config.local_asr
        chinese_language(config.transcribe_language)
        self.recognition_layout = locate(self.options.model, self.options.runtime_root)
        self.alignment_layout = locate("aligner", self.options.runtime_root)

    def run(self, callback=None) -> ASRData:
        options = self.options
        stage, progress = "Local recognition", 0

        def check():
            if callback:
                callback(progress, stage)

        audio = decode_audio(self.audio_path, check)
        identity = identify_audio(audio, check)
        self.recognition_layout = locate(options.model, options.runtime_root, verify=True, check=check)
        self.alignment_layout = locate("aligner", options.runtime_root, verify=True, check=check)
        chunks = split_audio(audio, check, options.chunk_ms)
        cache = get_asr_cache() if is_cache_enabled() else None
        texts, raw = [], []
        model = MODELS[options.model]
        provenance = StageProvenance("qwen-local", model.repository, model.revision, RECOGNITION_POLICY)
        scope = uuid4().hex
        runtime = LocalRuntime(self.recognition_layout, options.timeout)
        try:
            for index, (chunk, _) in enumerate(chunks):
                check()
                binary = wav_bytes(chunk)
                key = stage_key("recognition", binary, options.model, [RECOGNITION_POLICY, "Chinese", "cuda-bfloat16-sdpa", 8192, options.chunk_ms])
                response = cache.get(key) if cache is not None else None
                if response is None:
                    if runtime.state != "ready":
                        runtime.start(check)
                    response = runtime.request(binary, check=check)
                if not isinstance(response, dict) or not isinstance(response.get("text"), str):
                    raise LocalRuntimeError("Malformed Qwen recognition response.")
                text = response["text"]
                if not text and chunk.rms > 104:
                    raise AlignmentError("empty transcript on audible input")
                texts.append(text)
                if cache is not None:
                    cache.set(key, {"text": text}, expire=86400 * 2)
                progress = (index + 1) * 45 // len(chunks)
        finally:
            runtime.close()
        stage = "Strict Chinese alignment"
        runtime = LocalRuntime(self.alignment_layout, options.timeout)
        failure, rejected_chunks = "", []
        try:
            for index, ((chunk, offset), text) in enumerate(zip(chunks, texts)):
                check()
                binary = wav_bytes(chunk)
                key = stage_key("alignment", binary, "aligner", [POLICY, text, "Chinese", "cuda-bfloat16-sdpa"])
                items = cache.get(key) if cache is not None else None
                if items is None:
                    if text and runtime.state != "ready":
                        runtime.start(check)
                    items = runtime.request(binary, text, check) if text else []
                if not isinstance(items, list) or any(not isinstance(i, dict) or not isinstance(i.get("text"), str) for i in items):
                    raise LocalRuntimeError("Malformed alignment response.")
                raw.append(items)
                result = validate_alignment(text, items, len(chunk), offset)
                try:
                    verify_acoustic_support(chunk, result.spans)
                except AlignmentError:
                    rejected_chunks.append(index)
                    raise
                if cache is not None:
                    cache.set(key, items, expire=86400 * 2)
                progress = 45 + (index + 1) * 45 // len(chunks)
        except (AlignmentError, LocalRuntimeError) as exc:
            check()  # Cancellation must not publish a review or a successful result.
            failure = str(exc)
        finally:
            runtime.close()
        review = LocalReview.capture_chunks(stage=provenance, scope=scope,
                    durations=[(offset, len(chunk)) for chunk, offset in chunks], texts=texts, raw=raw,
                    word_timing=True, audio_identity=identity)
        review = replace(review, pending_diarization=options.diarize)
        if rejected_chunks:
            review = replace(review, acoustic_rejected=tuple(t for i in rejected_chunks for t in review.chunks[i].token_ids))
        if failure:
            retain_review(review, failure)
        try:
            data = review.resume()
        except ValueError as exc:
            retain_review(review, str(exc))
        check()
        # Keep measured word boundaries until speaker association has run.
        return data if self.config.need_word_time_stamp or options.diarize else native_cues(data)


def diarization_preflight(options: LocalASRConfig, *, check=lambda: None, verify=False):
    return locate("community-1", options.diarization_root, verify=verify, check=check)


def add_local_speakers(audio_path: str, data: ASRData, config, *, aligned: bool, callback=None,
                       recognition_stage: StageProvenance | None = None) -> ASRData:
    def check():
        if callback:
            callback(95, "Local whole-recording diarization")

    options = config.local_asr
    audio = decode_audio(audio_path, check)
    require_audio_match(data.audio_identity, identify_audio(audio, check))
    validate_source(data, len(audio))
    binary = wav_bytes(audio)
    scope = uuid4().hex
    recognition = (data.segments[0].metadata.recognition if data.segments and data.segments[0].metadata else None)
    recognition = recognition or recognition_stage or StageProvenance("whisper-api", config.whisper_api_model or "whisper-1", "", "api-profile-v1")
    if aligned:
        stage = StageProvenance("qwen-aligner", MODEL_REPOSITORY, MODEL_REVISION, POLICY)
        cues = []
        for seg in data.segments:
            cue = seg.clone()
            if cue.metadata is None:
                cue.metadata = ASRMetadata(recognition.provider, scope, timing="aligned", recognition=recognition, alignment=stage)
            cues.append(cue)
        data = data.with_segments(cues)
    cache = get_asr_cache() if is_cache_enabled() else None
    key = diarization_key(hashlib.sha256(binary).hexdigest(), data)
    raw = cache.get(key) if cache is not None else None
    runtime = LocalRuntime(diarization_preflight(options, check=check, verify=True), options.timeout)
    try:
        if raw is None:
            runtime.start(check)
            raw = runtime.request(binary, check=check)
        spans = validate_model_spans(raw, len(audio), samples=int(audio.frame_count()))
        assemble = associate if config.need_word_time_stamp else assemble_diarized_cues
        result = assemble(data, spans, len(audio), scope, recognition)
        result.pending_diarization = False
        check()
        # Ambiguous associations remain usable with unknown speakers; they are not success-cache entries.
        if cache is not None and all(s.metadata and s.metadata.diarization and
                                     s.metadata.diarization.status == "assigned" for s in result.segments):
            cache.set(key, raw, expire=86400 * 2)
        return result
    finally:
        runtime.close()

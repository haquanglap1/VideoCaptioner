"""Independent speech recognition, optional subtitle alignment and speaker association."""

import hashlib
import json
from dataclasses import replace
from uuid import uuid4

from videocaptioner.core.utils.cache import get_asr_cache, is_cache_enabled

from ..alignment.audio import decode_audio, verify_acoustic_support, wav_bytes
from ..alignment.contract import (
    MODEL_REPOSITORY,
    MODEL_REVISION,
    POLICY,
    AlignmentError,
    chinese_language,
    validate_alignment,
)
from ..api_transcription import TranscriptionResult
from ..asr_data import ASRData
from ..audio_identity import identify_audio, require_audio_match
from ..metadata import ASRMetadata, StageProvenance
from ..review import NativeReviewRequired
from .audio import split_recognition_audio
from .diarization import (
    assemble_diarized_cues,
    associate,
    diarization_key,
    validate_model_spans,
    validate_source,
)
from .prepare import ensure_model
from .profiles import MODELS, RECOGNITION_POLICY, LocalASRConfig
from .review import LocalReview
from .runtime import (
    LocalRuntime,
    LocalRuntimeError,
    LocalRuntimeGenerationLimit,
    LocalRuntimeTimeout,
    locate,
)
from .sentence_fallback import sentence_subtitles
from .sentence_timing import PRACTICAL_SENTENCE_POLICY, SENTENCE_POLICIES, sentence_cues


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
        self.recognition_layout = None

    def run(self, callback=None) -> ASRData:
        result = self._run(callback, align=True)
        assert isinstance(result, ASRData)
        return result

    def recognize(self, callback=None) -> TranscriptionResult:
        """Return complete text without requiring or loading the aligner."""
        result = self._run(callback, align=False)
        assert isinstance(result, TranscriptionResult)
        return result

    def _run(self, callback, *, align: bool) -> ASRData | TranscriptionResult:
        options = self.options
        stage, progress = "Local recognition", 0

        def check():
            if callback:
                callback(progress, stage)

        audio = decode_audio(self.audio_path, check)
        identity = identify_audio(audio, check)
        def prepare(model_id):
            nonlocal stage
            try:
                return locate(model_id, options.runtime_root, verify=True, check=check)
            except LocalRuntimeError:
                check()

            def preparation_progress(message):
                nonlocal stage
                stage = message
                check()

            try:
                return ensure_model(model_id, options.runtime_root, check=check, progress=preparation_progress)
            except OSError:
                raise LocalRuntimeError("Model preparation could not finish; check storage, network and uv, then retry.") from None

        self.recognition_layout = prepare(options.model)
        stage = "Local recognition"
        chunks = split_recognition_audio(audio, check, options.chunk_ms)
        cache = get_asr_cache() if is_cache_enabled() else None
        texts, raw = [], []
        model = MODELS[options.model]
        provenance = StageProvenance("qwen-local", model.repository, model.revision, RECOGNITION_POLICY)
        scope = uuid4().hex
        runtime = LocalRuntime(self.recognition_layout, options.timeout)
        try:
            index = 0
            while index < len(chunks):
                chunk, offset = chunks[index]
                stage = f"Local recognition: chunk {index + 1}/{len(chunks)}"
                check()
                binary = wav_bytes(chunk)
                key = stage_key("recognition", binary, options.model, [RECOGNITION_POLICY, "Chinese", "cuda-bfloat16-sdpa", 8192, options.chunk_ms])
                response = cache.get(key) if cache is not None else None
                if response is None:
                    retry_key = stage_key("recognition-retry", binary, options.model, [options.timeout, "halve-once-v1"])
                    retry = cache.get(retry_key) if cache is not None else False
                    if retry and len(chunk) > 15_000:
                        pieces = split_recognition_audio(chunk, check, 15_000)
                        chunks[index:index + 1] = [(part, offset + at) for part, at in pieces]
                        continue
                    if runtime.state != "ready":
                        runtime.start(check)
                    try:
                        response = runtime.request(binary, check=check)
                    except (LocalRuntimeTimeout, LocalRuntimeGenerationLimit):
                        check()
                        if len(chunk) <= 15_000:
                            raise
                        if cache is not None:
                            cache.set(retry_key, True, expire=86400 * 2)
                        pieces = split_recognition_audio(chunk, check, 15_000)
                        chunks[index:index + 1] = [(part, offset + at) for part, at in pieces]
                        stage = "Retrying the incomplete chunk in smaller recognition windows"
                        check()
                        continue
                if not isinstance(response, dict) or not isinstance(response.get("text"), str):
                    raise LocalRuntimeError("Malformed Qwen recognition response.")
                text = response["text"]
                if not text and chunk.rms > 104:
                    raise AlignmentError("empty transcript on audible input")
                texts.append(text)
                if cache is not None:
                    cache.set(key, {"text": text}, expire=86400 * 2)
                progress = (index + 1) * (45 if align else 100) // len(chunks)
                index += 1
        except (LocalRuntimeError, AlignmentError):
            check()
            if texts:
                partial = LocalReview.capture_chunks(stage=provenance, scope=scope,
                    durations=[(offset, len(chunk)) for chunk, offset in chunks],
                    texts=texts + [""] * (len(chunks) - len(texts)), raw=[], word_timing=True,
                    audio_identity=identity)
                retain_review(replace(partial, recognition_complete=False),
                              "Recognition is incomplete. Completed chunks were retained; retry reuses available cached chunks.")
            raise
        finally:
            runtime.close()
        check()
        if not align:
            return TranscriptionResult(text="".join(texts))
        word_timing = self.config.need_word_time_stamp
        policy = POLICY if word_timing else PRACTICAL_SENTENCE_POLICY
        stage = "Strict Chinese alignment" if word_timing else "Chinese sentence alignment"
        alignment_runtime = None
        failure, rejected_tokens = "", []
        try:
            alignment_layout = prepare("aligner")
            stage = "Strict Chinese alignment" if word_timing else "Chinese sentence alignment"
            alignment_runtime = LocalRuntime(alignment_layout, options.timeout)
            for index, ((chunk, offset), text) in enumerate(zip(chunks, texts)):
                check()
                binary = wav_bytes(chunk)
                key = stage_key("alignment", binary, "aligner", [policy, text, "Chinese", "cuda-bfloat16-sdpa"])
                items = cache.get(key) if cache is not None else None
                raw_key = stage_key("alignment-raw", binary, "aligner", ["raw-v1", text, "Chinese", "cuda-bfloat16-sdpa"])
                if items is None and cache is not None:
                    items = cache.get(raw_key)
                if items is None:
                    if text and alignment_runtime.state != "ready":
                        alignment_runtime.start(check)
                    items = alignment_runtime.request(binary, text, check) if text else []
                if not isinstance(items, list) or any(not isinstance(i, dict) or not isinstance(i.get("text"), str) for i in items):
                    raise LocalRuntimeError("Malformed alignment response.")
                raw.append(items)
                if cache is not None:
                    # Raw predictions are reusable evidence, not validated subtitle output.
                    cache.set(raw_key, items, expire=86400 * 2)
                anchors = ()
                try:
                    if word_timing:
                        anchors = validate_alignment(text, items, len(chunk), offset).spans
                    else:
                        cues = sentence_cues(text, items, len(chunk), policy=policy)
                        anchors = tuple(cue.span for cue in cues)
                    verify_acoustic_support(chunk, anchors)
                except AlignmentError:
                    check()
                    if anchors:
                        rejected_tokens.extend((index, token) for token in range(len(items)))
                    if word_timing:
                        raise
                    continue
                if cache is not None:
                    cache.set(key, items, expire=86400 * 2)
                progress = 45 + (index + 1) * 45 // len(chunks)
        except (AlignmentError, LocalRuntimeError) as exc:
            check()  # Cancellation must not publish a review or a successful result.
            failure = str(exc)
        finally:
            if alignment_runtime is not None:
                alignment_runtime.close()
        review = LocalReview.capture_chunks(stage=provenance, scope=scope,
                    durations=[(offset, len(chunk)) for chunk, offset in chunks], texts=texts, raw=raw,
                    word_timing=word_timing, audio_identity=identity)
        review = replace(review, pending_diarization=options.diarize, alignment_policy=policy)
        if rejected_tokens:
            review = replace(review, acoustic_rejected=tuple(review.chunks[i].token_ids[t] for i, t in rejected_tokens))
        if not word_timing:
            try:
                return sentence_subtitles(audio, review, self.config, callback)
            except (ValueError, RuntimeError, OSError) as exc:
                check()
                retain_review(review, str(exc))
        if failure:
            retain_review(review, failure)
        try:
            data = review.resume()
        except ValueError as exc:
            retain_review(review, str(exc))
        check()
        return data


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
        sentence_aligned = any(s.metadata and s.metadata.alignment and
                               s.metadata.alignment.policy in SENTENCE_POLICIES for s in data)
        assemble = associate if config.need_word_time_stamp or sentence_aligned else assemble_diarized_cues
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

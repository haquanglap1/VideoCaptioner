"""Sentence export with bounded, local Whisper replacement of failed regions."""

import hashlib
import json
import subprocess
import tempfile
import time
from pathlib import Path

from videocaptioner.core.utils.cache import get_asr_cache, is_cache_enabled
from videocaptioner.core.utils.gpu_lease import GPULease
from videocaptioner.core.utils.subprocess_helper import _NO_WINDOW, child_environment

from ..alignment.audio import stop_process, verify_acoustic_support, wav_bytes
from ..alignment.contract import MODEL_REPOSITORY, MODEL_REVISION, AlignmentError
from ..asr_data import ASRData, ASRDataSeg
from ..audio_identity import identify_audio, require_audio_match
from ..faster_whisper import FasterWhisperASR
from ..metadata import ASRMetadata, StageProvenance
from .review import LocalReview
from .sentence_timing import PRACTICAL_SENTENCE_POLICY, sentence_cues

FALLBACK_POLICY = "qwen-sentence-whisper-fallback-v1"


def fallback_cue_count(data: ASRData) -> int:
    return sum(bool(s.metadata and s.metadata.recognition and
                    s.metadata.recognition.policy == FALLBACK_POLICY) for s in data)


class WhisperSentenceFallback:
    def __init__(self, config):
        self.config = config
        self.revision = None

    def __call__(self, audio, check) -> tuple[ASRData, StageProvenance]:
        from videocaptioner.config import MODEL_PATH

        config = self.config
        model = config.faster_whisper_model.value if config.faster_whisper_model else "large-v3"
        root = Path(config.faster_whisper_model_dir or MODEL_PATH)
        model_path = root / f"faster-whisper-{model}"
        # An automatic fallback must use an installed model, never trigger a download.
        if not all((model_path / name).is_file() for name in ("model.bin", "config.json", "tokenizer.json")):
            raise AlignmentError("Whisper fallback needs an installed model; select its directory in Faster-Whisper settings.")
        binary = wav_bytes(audio)
        engine = FasterWhisperASR(binary, config.faster_whisper_program or "", model,
            str(root.resolve()), language=config.transcribe_language, device=config.faster_whisper_device,
            need_word_time_stamp=False, vad_filter=config.faster_whisper_vad_filter,
            vad_threshold=config.faster_whisper_vad_threshold,
            vad_method=config.faster_whisper_vad_method.value if config.faster_whisper_vad_method else "",
            prompt=config.faster_whisper_prompt)
        if self.revision is None:
            digest = hashlib.sha256()
            for path in [Path(engine.faster_whisper_program), *sorted(model_path.iterdir())]:
                if path.is_file():
                    digest.update(path.name.encode())
                    with path.open("rb") as handle:
                        for block in iter(lambda: handle.read(1024 * 1024), b""):
                            check()
                            digest.update(block)
            self.revision = "sha256:" + digest.hexdigest()
        stage = StageProvenance("faster-whisper", model, self.revision, FALLBACK_POLICY)
        options = [FALLBACK_POLICY, self.revision, engine._build_command("")]
        key = "local-sentence-fallback:v1-" + hashlib.sha256(
            binary + json.dumps(options, sort_keys=True).encode()).hexdigest()
        cache = get_asr_cache() if is_cache_enabled() else None
        response = cache.get(key) if cache is not None else None
        check()
        if response is None:
            response = self._request(engine, binary, check)
        if not isinstance(response, str):
            raise AlignmentError("Malformed Whisper fallback result.")
        data = ASRData.from_srt(response)
        previous = 0
        if not data.segments:
            raise AlignmentError("Whisper fallback returned no speech for a region with Qwen text.")
        for seg in data:
            if not previous <= seg.start_time < seg.end_time <= len(audio):
                raise AlignmentError("Whisper fallback returned invalid sentence timing.")
            previous = seg.end_time
        check()
        if cache is not None:
            cache.set(key, response, expire=86400 * 2)
        return data, stage

    def _request(self, engine, binary, check) -> str:
        lease = GPULease()
        try:
            if engine.device != "cpu":
                lease.acquire()
            with tempfile.TemporaryDirectory(prefix="vc-sentence-fallback-") as directory:
                wav = Path(directory) / "audio.wav"
                wav.write_bytes(binary)
                with (Path(directory) / "worker.log").open("wb") as log:
                    check()
                    process = subprocess.Popen(engine._build_command(str(wav)), stdin=subprocess.DEVNULL,
                        stdout=log, stderr=subprocess.STDOUT, creationflags=_NO_WINDOW, env=child_environment())
                    try:
                        deadline = time.monotonic() + self.config.local_asr.timeout
                        while process.poll() is None:
                            check()
                            if time.monotonic() >= deadline:
                                raise AlignmentError("Whisper sentence fallback timed out; completed regions remain cached.")
                            try:
                                process.wait(timeout=0.1)
                            except subprocess.TimeoutExpired:
                                pass
                        check()
                        output = wav.with_suffix(".srt")
                        if process.returncode or not output.is_file():
                            raise AlignmentError("Whisper sentence fallback failed; check the installed executable/model.")
                        return output.read_text(encoding="utf-8-sig")
                    finally:
                        stop_process(process)
        finally:
            lease.close()


def sentence_subtitles(audio, review: LocalReview, config, callback=None) -> ASRData:
    """Retain usable Qwen sentences; replace failed regions with Whisper text AND timing."""
    if not review.recognition_complete or review.word_timing:
        raise AlignmentError("Sentence fallback requires complete recognition in sentence mode.")

    def check():
        if callback:
            callback(90, "Preparing sentence subtitles")

    require_audio_match(review.audio_identity, identify_audio(audio, check))
    if len(audio) != review.duration_ms:
        raise AlignmentError("Sentence review duration does not match the recording.")
    alignment = StageProvenance("qwen-aligner", MODEL_REPOSITORY, MODEL_REVISION, PRACTICAL_SENTENCE_POLICY)
    groups: list[list[ASRDataSeg] | None] = []
    boundary = 0
    for chunk in review.chunks:
        check()
        if chunk.offset_ms != boundary:
            raise AlignmentError("Incomplete sentence audio coverage.")
        boundary += chunk.duration_ms
        try:
            cues = sentence_cues(chunk.text, review._sentence_items(chunk), chunk.duration_ms,
                                 policy=PRACTICAL_SENTENCE_POLICY)
            verify_acoustic_support(audio[chunk.offset_ms:boundary], [c.span for c in cues])
        except AlignmentError:
            groups.append(None)
            continue
        result = []
        for cue in cues:
            ids = chunk.token_ids[cue.first_token:cue.stop_token]
            metadata = ASRMetadata(review.provider, review.scope, timing="aligned", token_ids=ids,
                                   recognition=review.recognition, alignment=alignment)
            result.append(ASRDataSeg(cue.span.text, cue.span.start_ms + chunk.offset_ms,
                cue.span.end_ms + chunk.offset_ms, metadata=metadata,
                cue_id=f"{review.provider}:{review.scope}:{ids[0]}"))
        groups.append(result)
    if boundary != review.duration_ms:
        raise AlignmentError("Incomplete sentence audio coverage.")

    # A very short tail needs the preceding chunk as speech context. Replace both
    # together, rather than cropping Whisper text against the Qwen transcript.
    for index in range(1, len(groups)):
        if groups[index] is None and review.chunks[index].duration_ms < 3000:
            groups[index - 1] = None
    fallback = WhisperSentenceFallback(config)
    index, used = 0, 0
    output = []
    while index < len(groups):
        if groups[index] is not None:
            output.extend(groups[index] or [])
            index += 1
            continue
        first = index
        start = review.chunks[first].offset_ms
        while index < len(groups) and groups[index] is None:
            chunk = review.chunks[index]
            if index > first and chunk.offset_ms + chunk.duration_ms - start > 60000 and chunk.duration_ms >= 3000:
                break
            index += 1
        last = review.chunks[index - 1]
        end = last.offset_ms + last.duration_ms

        def fallback_check():
            if callback:
                callback(90, f"Whisper fallback: replacing text and timing in chunks {first + 1}–{index}")

        data, recognition = fallback(audio[start:end], fallback_check)
        for number, seg in enumerate(data):
            metadata = ASRMetadata("faster-whisper", review.scope, timing="native", recognition=recognition)
            output.append(ASRDataSeg(seg.text, start + seg.start_time, start + seg.end_time,
                metadata=metadata, cue_id=f"faster-whisper:{review.scope}:fallback-{first}-{number}"))
        used += index - first
    check()
    if used:
        # Preserve the complete original Qwen text and raw timings outside the
        # successful hybrid result; never relabel them as Whisper recognition.
        review.save_new()
        if callback:
            callback(95, f"Subtitles ready; {used} chunks use Whisper text and timing. Original Qwen text retained in ASR review.")
    return ASRData(output, audio_identity=review.audio_identity, pending_diarization=review.pending_diarization)

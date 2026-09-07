"""Diarize an existing timed ASR result without another recognition/upload request."""

from pathlib import Path

from videocaptioner.cli import exit_codes as EXIT
from videocaptioner.cli import output
from videocaptioner.core.asr.asr_data import ASRData
from videocaptioner.core.asr.local.pipeline import add_local_speakers
from videocaptioner.core.asr.local.profiles import LocalASRConfig
from videocaptioner.core.asr.metadata import StageProvenance
from videocaptioner.core.entities import TranscribeConfig


def run(args) -> int:
    if Path(args.input).suffix.lower() not in (".json", ".srt"):
        output.error("Use timed ASR JSON or SRT; text-only recognition must be aligned first.")
        return EXIT.USAGE_ERROR
    if not Path(args.input).is_file() or not Path(args.audio).is_file():
        output.error("Timed subtitle input and original audio are required.")
        return EXIT.FILE_NOT_FOUND
    destination = Path(args.output)
    if destination.suffix.lower() != ".json" or destination.resolve() in (Path(args.input).resolve(), Path(args.audio).resolve()):
        output.error("Use a separate .json output to preserve speaker provenance.")
        return EXIT.USAGE_ERROR
    try:
        data = ASRData.from_subtitle_file(args.input)
        config = TranscribeConfig(need_word_time_stamp=True, local_asr=LocalASRConfig(
            diarize=True, diarization_root=args.runtime or "", timeout=args.timeout))
        result = add_local_speakers(args.audio, data, config, aligned=False,
                    recognition_stage=StageProvenance("imported", "timed-subtitles", "", "user-supplied-timing-v1"))
        result.save(str(destination))
        unknown = sum(s.metadata is not None and s.metadata.speaker is None for s in result)
        output.info(f"Local diarization complete: {len(result)} cues, {unknown} unknown/review associations. No ASR request was made.")
        return EXIT.SUCCESS
    except (ValueError, RuntimeError, OSError) as exc:
        output.error(str(exc))
        return EXIT.RUNTIME_ERROR

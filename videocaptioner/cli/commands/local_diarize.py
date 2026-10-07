"""Diarize an existing timed ASR result without another recognition/upload request."""

from pathlib import Path

from videocaptioner.cli import exit_codes as EXIT
from videocaptioner.cli import output
from videocaptioner.cli.config import get
from videocaptioner.core.asr.asr_data import ASRData
from videocaptioner.core.asr.local.pipeline import add_local_speakers
from videocaptioner.core.asr.local.profiles import LocalASRConfig
from videocaptioner.core.asr.metadata import StageProvenance
from videocaptioner.core.entities import TranscribeConfig


def naming_settings(config: dict, args, *, media_path: str):
    """LLM snapshot for --name-speakers from llm.* plus the series note and the media sidecar."""
    from videocaptioner.core.asr.local.speaker_naming import SpeakerNamingSettings
    from videocaptioner.core.llm.client import LLMCredentials
    from videocaptioner.core.translate.series_context import (
        compose_context_notes,
        load_video_context,
    )

    series_notes = get(config, "translate.series_context", "") or ""
    series_file = getattr(args, "series_context", None)
    if series_file:
        series_path = Path(series_file)
        if not series_path.is_file():
            raise FileNotFoundError(f"Series context file not found: {series_file}")
        series_notes = series_path.read_text(encoding="utf-8")
    return SpeakerNamingSettings(
        LLMCredentials(str(get(config, "llm.api_key", "") or ""), str(get(config, "llm.api_base", "") or "")),
        str(get(config, "llm.model", "") or ""), int(get(config, "llm.request_timeout", 120) or 120),
        compose_context_notes(load_video_context(media_path), series_notes))


def report_naming(data: ASRData) -> None:
    naming = data.speaker_naming
    if naming is None:
        return
    confirmed = sum(p.status == "confirmed" for p in naming.profiles)
    pending = len(naming.pending)
    output.info(f"Speaker naming: {len(naming.profiles)} clusters, {confirmed} confirmed, {pending} proposals to review"
                + (" (transcript sampled)" if naming.sampled else "") + ". JSON keeps the map; SRT never prints names.")
    for profile in naming.profiles:
        label = profile.name or "(unknown)"
        output.info(f"  {profile.label} -> {label} [{profile.status}, {profile.confidence:.2f}]"
                    + (f" {profile.role}" if profile.role else ""))


def run(args, config: dict | None = None) -> int:
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
    name_speakers = bool(getattr(args, "name_speakers", False))
    settings = None
    if name_speakers:
        try:
            settings = naming_settings(config or {}, args, media_path=args.audio)
        except FileNotFoundError as exc:
            output.error(str(exc))
            return EXIT.FILE_NOT_FOUND
        except ValueError as exc:
            output.error(str(exc))
            return EXIT.USAGE_ERROR
    try:
        data = ASRData.from_subtitle_file(args.input)
        if data.audio_identity is None:
            output.warn("No saved audio identity: recording association is unverified. Select the original audio; legacy input is not automatically verified.")
        config_obj = TranscribeConfig(need_word_time_stamp=True, local_asr=LocalASRConfig(
            diarize=True, diarization_root=args.runtime or "", timeout=args.timeout, name_speakers=name_speakers),
            speaker_naming=settings)
        result = add_local_speakers(args.audio, data, config_obj, aligned=False,
                    recognition_stage=StageProvenance("imported", "timed-subtitles", "", "user-supplied-timing-v1"))
        if settings is not None:
            from videocaptioner.core.asr.local.speaker_naming import name_speakers as request_names

            try:
                result = request_names(result, settings, notify=output.info)
            except (ValueError, RuntimeError) as exc:
                # Diarized subtitles are still worth saving; names can be requested again.
                output.warn(f"Speakers remain anonymous: {exc}")
        result.save(str(destination))
        if data.audio_identity is not None:
            output.info("Audio matches the saved whole-recording identity.")
        unknown = sum(s.metadata is not None and s.metadata.speaker is None for s in result)
        output.info(f"Local diarization complete: {len(result)} cues, {unknown} unknown/review associations. No ASR request was made.")
        report_naming(result)
        return EXIT.SUCCESS
    except (ValueError, RuntimeError, OSError) as exc:
        output.error(str(exc))
        return EXIT.RUNTIME_ERROR

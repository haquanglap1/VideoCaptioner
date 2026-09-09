"""transcribe command — convert audio/video to subtitles via ASR."""

import os
from argparse import Namespace
from pathlib import Path

from videocaptioner.cli import exit_codes as EXIT
from videocaptioner.cli import output
from videocaptioner.cli.config import get
from videocaptioner.cli.validators import validate_transcribe


def run(args: Namespace, config: dict) -> int:
    from videocaptioner.cli.validators import validate_media_input

    input_path = Path(args.input)
    if not input_path.exists():
        output.error(f"Input file not found: {input_path}")
        return EXIT.FILE_NOT_FOUND

    err = validate_media_input(input_path)
    if err is not None:
        return err

    if not validate_transcribe(config):
        return EXIT.USAGE_ERROR

    # Determine output path
    out_fmt = get(config, "output.format", "srt")
    if args.output:
        out = Path(args.output)
        # If output is a directory, auto-generate filename inside it
        if out.is_dir() or str(args.output).endswith("/"):
            out.mkdir(parents=True, exist_ok=True)
            output_path = str(out / f"{input_path.stem}.{out_fmt}")
        else:
            # Auto-append format extension if no extension given
            if not out.suffix:
                output_path = f"{args.output}.{out_fmt}"
            else:
                output_path = args.output
    else:
        output_path = str(input_path.with_suffix(f".{out_fmt}"))

    # Validate output format
    from videocaptioner.cli.validators import validate_output_format
    err = validate_output_format(Path(output_path))
    if err is not None:
        return err

    asr_engine = get(config, "transcribe.asr", "faster-whisper")
    language = get(config, "transcribe.language", "auto")

    verbose = getattr(args, "verbose", False)
    quiet = getattr(args, "quiet", False)

    if verbose:
        output.info(f"ASR engine: {asr_engine}")
        output.info(f"Language: {language}")

    # Whisper API credentials reach WhisperAPI through TranscribeConfig below;
    # they are deliberately not exported to os.environ.

    # Build TranscribeConfig
    from videocaptioner.core.asr.local.profiles import LocalASRConfig
    from videocaptioner.core.asr.native_profiles import NativeASRConfig
    from videocaptioner.core.entities import (
        FasterWhisperModelEnum,
        TranscribeConfig,
        TranscribeModelEnum,
        VadMethodEnum,
        WhisperModelEnum,
    )

    asr_map = {
        "qwen-local": TranscribeModelEnum.QWEN_LOCAL,
        "soniox": TranscribeModelEnum.SONIOX,
        "scribe": TranscribeModelEnum.SCRIBE,
        "faster-whisper": TranscribeModelEnum.FASTER_WHISPER,
        "whisper-api": TranscribeModelEnum.WHISPER_API,
        "bijian": TranscribeModelEnum.BIJIAN,
        "jianying": TranscribeModelEnum.JIANYING,
        "whisper-cpp": TranscribeModelEnum.WHISPER_CPP,
    }

    # Map CLI string values to enums
    fw_model_str = get(config, "transcribe.faster_whisper.model", "large-v3")
    fw_model_enum = next((m for m in FasterWhisperModelEnum if m.value == fw_model_str), None)

    vad_str = get(config, "transcribe.faster_whisper.vad_method", "silero-v4-fw")
    vad_map = {v.value.replace("_", "-"): v for v in VadMethodEnum}
    vad_enum = vad_map.get(vad_str.replace("_", "-"))

    # WhisperCpp model enum
    wcpp_model_str = get(config, "transcribe.whisper_cpp.model", "large-v2")
    wcpp_model_enum = next((m for m in WhisperModelEnum if m.value == wcpp_model_str), None)

    transcribe_config = TranscribeConfig(
        local_asr=LocalASRConfig(**get(config, "local_asr", {})),
        transcribe_model=asr_map.get(asr_engine),
        transcribe_language=language if language != "auto" else "",
        need_word_time_stamp=getattr(args, "word_timestamps", False),
        native_asr=NativeASRConfig(
            asr_engine, api_key=get(config, f"{asr_engine}.api_key", ""),
            api_base=get(config, f"{asr_engine}.api_base", ""), model=get(config, f"{asr_engine}.model", ""),
            diarize=get(config, f"{asr_engine}.diarize", True),
        ) if asr_engine in ("soniox", "scribe") else None,
        # FasterWhisper options
        faster_whisper_program=get(config, "transcribe.faster_whisper.program", "") or None,
        faster_whisper_model=fw_model_enum,
        faster_whisper_model_dir=get(config, "transcribe.faster_whisper.model_dir", "") or None,
        faster_whisper_device=get(config, "transcribe.faster_whisper.device", "auto"),
        faster_whisper_vad_filter=get(config, "transcribe.faster_whisper.vad_filter", True),
        faster_whisper_vad_method=vad_enum,
        faster_whisper_vad_threshold=get(config, "transcribe.faster_whisper.vad_threshold", 0.5),
        faster_whisper_ff_mdx_kim2=get(config, "transcribe.faster_whisper.voice_extraction", False),
        faster_whisper_one_word=True,
        faster_whisper_prompt=get(config, "transcribe.faster_whisper.prompt", ""),
        # WhisperCpp options
        whisper_model=wcpp_model_enum,
        # Whisper API options
        whisper_api_key=get(config, "whisper_api.api_key", ""),
        whisper_api_base=get(config, "whisper_api.api_base", ""),
        whisper_api_model=get(config, "whisper_api.model", "whisper-1"),
        whisper_api_prompt=get(config, "whisper_api.prompt", ""),
        whisper_api_provider=get(config, "whisper_api.provider", "custom"),
        whisper_api_request_profile=get(config, "whisper_api.request_profile", "auto"),
    )


    # Progress callback
    progress = None if quiet else output.ProgressLine(f"Transcribing [{asr_engine}]").start()

    def callback(pct: int, msg: str) -> None:
        if progress:
            progress.update(pct, f"Transcribing [{asr_engine}] {msg}")

    try:
        # Auto-convert video to audio if needed
        from videocaptioner.cli.validators import AUDIO_EXTENSIONS
        audio_path = str(input_path)
        temp_audio = None

        ext_lower = input_path.suffix.lstrip(".").lower()
        needs_conversion = ext_lower not in AUDIO_EXTENSIONS
        # whisper-cpp requires WAV format specifically
        if not needs_conversion and asr_engine == "whisper-cpp" and ext_lower != "wav":
            needs_conversion = True

        if needs_conversion:
            if verbose:
                output.info("Converting input to WAV audio...")
            import tempfile

            from videocaptioner.core.utils.video_utils import video2audio
            temp_audio = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
            temp_audio.close()
            if not video2audio(str(input_path), output=temp_audio.name):
                # Check if the temp file is empty (no audio track)
                if os.path.getsize(temp_audio.name) == 0:
                    output.error("Input video has no audio track")
                else:
                    output.error("Failed to extract audio from video. Is FFmpeg installed?")
                return EXIT.RUNTIME_ERROR
            audio_path = temp_audio.name

        from videocaptioner.core.asr.transcribe import recognize_text, transcribe
        from videocaptioner.core.translate.conversation import load_context
        context_path = get(config, "translate.conversation_context", "")
        context = load_context(context_path) if context_path else None
        if asr_engine == "qwen-local" and Path(output_path).suffix.lower() == ".txt":
            result = recognize_text(audio_path, transcribe_config, callback=callback)
            result.save_text(output_path)
            args.transcript_path = str(output_path)
            if transcribe_config.local_asr.diarize:
                output.warn("TXT contains speech text only; speaker association was not run.")
            if context is not None:
                output.warn("TXT cannot retain conversation context.")
            if progress:
                progress.finish(f"Speech recognition complete -> {output_path}")
            if quiet:
                print(output_path)
            return EXIT.SUCCESS
        asr_data = transcribe(audio_path, transcribe_config, callback=callback)
        if context is not None:
            asr_data.conversation_context = context
            output.warn("Context attached for review; a new ASR request does not reuse old speaker identities.")
            if not str(output_path).lower().endswith(".json"):
                output.warn("SRT/ASS/text cannot retain conversation context; use JSON to reopen it.")

        args.asr_data = asr_data

        # Save output
        asr_data.save(save_path=output_path)
        if asr_data.pending_diarization:
            output.warn("Subtitles saved; optional speaker association is still pending. Use local-diarize after preparing its model.")

        if progress:
            n = len(asr_data.segments)
            progress.finish(f"Transcription complete -> {output_path} ({n} segment{'' if n == 1 else 's'})")
        if quiet:
            print(output_path)
        return EXIT.SUCCESS

    except Exception as e:
        from videocaptioner.core.asr.review import NativeReviewRequired

        if isinstance(e, NativeReviewRequired):
            from videocaptioner.core.asr.api_transcription import TranscriptionResult
            from videocaptioner.core.asr.local.review import LocalReview

            if isinstance(e.review, LocalReview) and e.review.recognition_complete:
                try:
                    transcript = TranscriptionResult(e.review.text).save_text(
                        Path(output_path).with_suffix(".txt"), unique=True)
                    args.transcript_path = str(transcript)
                    output.warn(f"Speech recognition is complete and saved: {transcript}")
                    output.warn("The requested subtitles still need valid timing; recognition does not need to be repeated.")
                except OSError:
                    output.warn("Could not save a TXT copy; recognized speech remains in the local review.")
            review_path = e.path
            if getattr(args, "asr_review", None):
                try:
                    review_path = e.review.save(args.asr_review)
                except OSError:
                    output.error("Cannot save requested review path.")
            if review_path:
                output.warn(f"Recognition requires local review: {review_path}")
                output.hint("Open ASR review in the GUI or use 'asr-review'; do not transcribe/upload again.")
        msg = output.clean_error(str(e))
        if progress:
            progress.fail(msg)
        else:
            output.error(msg)
        if verbose:
            import traceback
            traceback.print_exc()
        return EXIT.RUNTIME_ERROR
    finally:
        if temp_audio is not None:
            try:
                os.unlink(temp_audio.name)
            except OSError:
                pass

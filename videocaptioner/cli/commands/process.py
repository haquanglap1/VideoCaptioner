"""process command — full pipeline: transcribe → optimize → translate → synthesize."""

from argparse import Namespace
from pathlib import Path

from videocaptioner.cli import exit_codes as EXIT
from videocaptioner.cli import output
from videocaptioner.cli.config import get


def run(args: Namespace, config: dict) -> int:
    input_path = args.input
    verbose = getattr(args, "verbose", False)
    quiet = getattr(args, "quiet", False)

    no_optimize = not get(config, "subtitle.optimize", True)
    no_translate = not get(config, "subtitle.translate", False)
    no_split = not get(config, "subtitle.split", True)
    no_synthesize = getattr(args, "no_synthesize", False)
    dubbing_enabled = getattr(args, "dub", False)

    # If user specified --translator or --target-language, enable translation
    if getattr(args, "translator", None) or getattr(args, "target_language", None):
        no_translate = False

    # URL input not yet supported
    is_url = input_path.startswith("http://") or input_path.startswith("https://")
    if is_url:
        output.error("URL input is not yet supported in the process pipeline")
        output.hint("Download first: videocaptioner download <url>")
        output.hint("Then: videocaptioner process <downloaded_file>")
        return EXIT.GENERAL_ERROR

    # Validate input file first (before expensive pre-flight checks)
    path = Path(input_path)
    if not path.exists():
        output.error(f"Input file not found: {path}")
        return EXIT.FILE_NOT_FOUND

    # Auto-detect audio files and skip synthesis
    audio_extensions = {"mp3", "wav", "flac", "m4a", "ogg", "opus", "aac", "wma"}
    if path.suffix.lstrip(".").lower() in audio_extensions and not no_synthesize:
        no_synthesize = True
        if not quiet:
            output.info("Audio file detected, skipping video synthesis")
    if path.suffix.lstrip(".").lower() in audio_extensions and dubbing_enabled:
        output.error("--dub requires a video input, not an audio-only file")
        return EXIT.USAGE_ERROR

    # Pre-flight validation
    from videocaptioner.cli.validators import validate_process
    if not validate_process(config, no_synthesize=no_synthesize):
        return EXIT.USAGE_ERROR

    out_arg = getattr(args, "output", None)
    if out_arg:
        out_path = Path(out_arg)
        # If it looks like a file path (has extension), use its parent as dir
        out_dir = out_path.parent if out_path.suffix else out_path
    else:
        out_dir = path.parent

    total_steps = 4 if dubbing_enabled else 3

    # Step 1: Transcribe
    if not quiet:
        output.info(f"Step 1/{total_steps}: Transcribing...")
    subtitle_path = str(out_dir / f"{path.stem}.srt")
    dubbing_subtitle_path = str(out_dir / f"{path.stem}_dubbing-target.srt")

    # Only use word timestamps if subtitle processing (split/optimize) will run
    need_word_ts = not (no_optimize and no_translate and no_split)
    tr_args = Namespace(
        input=str(path), output=subtitle_path, format="srt", word_timestamps=need_word_ts,
        verbose=verbose, quiet=quiet, config=getattr(args, "config", None),
        asr=getattr(args, "asr", None), language=getattr(args, "language", None),
        fw_model=None, fw_device=None, fw_vad_method=None, fw_vad_threshold=None,
        fw_voice_extraction=False, fw_prompt=None,
        whisper_api_key=getattr(args, "whisper_api_key", None),
        whisper_api_base=getattr(args, "whisper_api_base", None),
        whisper_model=None, whisper_prompt=None,
    )
    from videocaptioner.cli.commands.transcribe import run as transcribe_run
    ret = transcribe_run(tr_args, config)
    if ret != 0:
        return ret

    # Step 2: Subtitle (optimize + translate)
    if not no_optimize or not no_translate:
        if not quiet:
            output.info(f"Step 2/{total_steps}: Processing subtitles...")

        processed_path = str(out_dir / f"{path.stem}_processed.srt")
        sub_args = Namespace(
            input=subtitle_path, output=processed_path,
            format=get(config, "output.format", "srt"),
            no_optimize=no_optimize, no_translate=no_translate, no_split=no_split,
            verbose=verbose, quiet=quiet, config=getattr(args, "config", None),
            api_key=getattr(args, "api_key", None),
            api_base=getattr(args, "api_base", None),
            model=getattr(args, "model", None),
            translator=getattr(args, "translator", None),
            target_language=getattr(args, "target_language", None),
            reflect=getattr(args, "reflect", False),
            max_cjk=None, max_english=None,
            prompt=getattr(args, "prompt", None),
            prompt_file=getattr(args, "prompt_file", None),
            thread_num=getattr(args, "thread_num", None),
            batch_size=getattr(args, "batch_size", None),
            layout=getattr(args, "layout", None),
            dubbing_output=dubbing_subtitle_path if dubbing_enabled else None,
        )
        from videocaptioner.cli.commands.subtitle import run as subtitle_run
        ret = subtitle_run(sub_args, config)
        if ret != 0:
            return ret
        subtitle_path = processed_path
    else:
        if not quiet:
            output.info(f"Step 2/{total_steps}: Skipped (optimization and translation disabled)")
        if dubbing_enabled:
            from videocaptioner.core.asr.asr_data import ASRData
            from videocaptioner.core.entities import SubtitleLayoutEnum
            ASRData.from_subtitle_file(subtitle_path).to_srt(
                save_path=dubbing_subtitle_path,
                layout=SubtitleLayoutEnum.ONLY_TRANSLATE,
            )

    video_for_synthesis = str(path)
    if dubbing_enabled:
        if not quiet:
            output.info(f"Step 3/{total_steps}: Dubbing video...")
        dubbed_path = str(out_dir / f"{path.stem}_dubbed{path.suffix}")
        dub_args = Namespace(
            video=str(path),
            subtitle=dubbing_subtitle_path,
            output=dubbed_path,
            report=getattr(args, "report", None),
            verbose=verbose,
            quiet=quiet,
            suppress_result=True,
        )
        from videocaptioner.cli.commands.dub import run as dub_run
        ret = dub_run(dub_args, config)
        if ret != 0:
            return ret
        video_for_synthesis = dubbed_path

    # Step 3: Synthesize
    if not no_synthesize:
        if not quiet:
            step = 4 if dubbing_enabled else 3
            output.info(f"Step {step}/{total_steps}: Synthesizing video...")

        syn_args = Namespace(
            video=video_for_synthesis, subtitle=subtitle_path,
            output=str(out_dir / f"{path.stem}_captioned{path.suffix}"),
            subtitle_mode=getattr(args, "subtitle_mode", None),
            quality=getattr(args, "quality", None),
            style=None, layout=getattr(args, "layout", None),
            format=None, verbose=verbose, quiet=quiet,
            config=getattr(args, "config", None),
        )
        from videocaptioner.cli.commands.synthesize import run as synthesize_run
        ret = synthesize_run(syn_args, config)
        if ret != 0:
            return ret
    else:
        if not quiet:
            step = 4 if dubbing_enabled else 3
            output.info(f"Step {step}/{total_steps}: Skipped (synthesis disabled)")

    if not quiet:
        output.success("Pipeline complete!")
    return EXIT.SUCCESS

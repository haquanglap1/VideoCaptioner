"""Explicit local OmniVoice utilities: reviewed text export and draft reference ASR."""

from pathlib import Path

from videocaptioner.cli import exit_codes as EXIT
from videocaptioner.cli import output


def run(args, config):
    try:
        if args.action == "speak":
            from videocaptioner.cli.commands.dub import build_dubbing_config
            from videocaptioner.core.tts.omnivoice.text_audio import export_text_audio
            text = Path(args.input).read_text(encoding="utf-8-sig")
            result = export_text_audio(text, args.output, build_dubbing_config(config))
            output.info(f"WAV: {result.audio_path}\nSRT: {result.subtitle_path}")
        else:
            from videocaptioner.core.tts.omnivoice.reference import (
                ReferenceASROptions,
                transcribe_reference,
            )
            target = Path(args.output)
            if target.exists():
                raise ValueError("Choose a new transcript path; existing files are preserved")
            options = ReferenceASROptions(program=args.program, model_dir=args.model_dir, model=args.model,
                device=args.device, language=args.language, timeout=args.timeout)
            result = transcribe_reference(args.input, options)
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("x", encoding="utf-8") as handle:
                handle.write(result.text + "\n")
            output.info(f"Draft transcript for review: {target}")
        return EXIT.SUCCESS
    except Exception as exc:
        output.error(str(exc))
        return EXIT.RUNTIME_ERROR

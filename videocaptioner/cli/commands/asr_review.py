"""Inspect, explicitly edit, and resume a complete local recognition response."""

from argparse import Namespace
from pathlib import Path

from videocaptioner.cli import exit_codes as EXIT
from videocaptioner.cli import output
from videocaptioner.core.asr.audio_identity import verify_audio_file
from videocaptioner.core.asr.review import NativeReview


def run(args: Namespace, config: dict) -> int:
    if not Path(args.input).is_file():
        output.error("ASR review file not found.")
        return EXIT.FILE_NOT_FOUND
    try:
        if getattr(args, "audio", None) and any(
                destination and Path(destination).resolve() == Path(args.audio).resolve()
                for destination in (args.output, args.save_review)):
            output.error("Review and subtitle output must not replace the selected audio.")
            return EXIT.USAGE_ERROR
        review = NativeReview.load(args.input)
        if getattr(args, "audio", None):
            verified = verify_audio_file(review.audio_identity, args.audio)
            if verified:
                output.info("Audio matches the saved whole-recording identity.")
        if review.audio_identity is None:
            output.warn("No saved audio identity: recording association is unverified.")
        elif not getattr(args, "audio", None):
            output.warn("Audio identity retained; source has not been checked in this review. Use --audio to verify locally.")
        for value in args.set_timing or []:
            try:
                token_id, start, end = value.split(":")
                review = review.edit_timing(token_id, int(start), int(end))
            except ValueError:
                output.error("Use --set-timing TOKEN_ID:START_MS:END_MS with valid audio bounds.")
                return EXIT.USAGE_ERROR
        if args.save_review:
            if args.output and Path(args.output).resolve() == Path(args.save_review).resolve():
                output.error("Review and subtitle output must use separate paths.")
                return EXIT.USAGE_ERROR
            review.save(args.save_review)
        if args.output and Path(args.output).resolve() == Path(args.input).resolve():
            output.error("Subtitle output must not replace the review input.")
            return EXIT.USAGE_ERROR
        for issue in review.issues():
            # Transcript is private; inspect it explicitly in the saved JSON or GUI.
            output.warn(f"{issue.token_id} (token {issue.index + 1}): {issue.reason}")
        data = review.resume()
        if getattr(review, "pending_diarization", False):
            output.warn("Timing review only: local diarization is still pending. Save JSON, then use local-diarize with the original audio.")
        if args.output:
            if Path(args.output).suffix.lower() not in (".srt", ".json"):
                output.error("Review resume supports .json or .srt output.")
                return EXIT.USAGE_ERROR
            data.save(args.output)
            output.info(f"Validated full local result: {len(data)} cues -> {args.output}")
        else:
            output.info(f"Validated full local result: {len(data)} cues. Use -o to export.")
        return EXIT.SUCCESS
    except (OSError, ValueError) as exc:
        output.error(str(exc))
        return EXIT.RUNTIME_ERROR

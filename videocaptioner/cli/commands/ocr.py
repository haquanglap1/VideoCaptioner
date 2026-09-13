"""Local OCR, direct export and scan resume; no model installation or vision requests."""

from __future__ import annotations

import hashlib
from argparse import Namespace
from pathlib import Path

from videocaptioner.cli import exit_codes as EXIT
from videocaptioner.cli import output
from videocaptioner.core.ocr.cache import cache_limit_bytes, manage_cache
from videocaptioner.core.ocr.codec import atomic_json, atomic_text
from videocaptioner.core.ocr.document import OcrConfig, OcrDocument
from videocaptioner.core.ocr.geometry import Roi
from videocaptioner.core.ocr.identity import VisualSourceIdentity, verify_visual_file
from videocaptioner.core.ocr.installation import default_runtime, inspect_installation, resources
from videocaptioner.core.ocr.models import OcrError, Selection
from videocaptioner.core.ocr.profile import OcrProfileSnapshot
from videocaptioner.core.ocr.resume import validate_resume
from videocaptioner.core.ocr.runtime import OcrRuntimeMissing
from videocaptioner.core.ocr.service import jobs_directory, run_cpu_ocr


def _paths(inputs: list[Path], destinations: list[str | None], protected: Path | None = None) -> None:
    outputs = [Path(p).resolve() for p in destinations if p]
    if len(set(outputs)) != len(outputs):
        raise OcrError("OCR checkpoint, subtitles and report need separate output paths")
    for path in outputs:
        if (path in [p.resolve() for p in inputs]
                or any(path.exists() and p.exists() and path.samefile(p) for p in inputs)
                or (protected is not None and path.is_relative_to(protected.resolve()))):
            raise OcrError("OCR outputs must not replace source, checkpoint input or runtime files")
    for index, path in enumerate(outputs):
        if any(path.exists() and p.exists() and path.samefile(p) for p in outputs[:index]):
            raise OcrError("OCR outputs must not alias the same file")


def _export(document: OcrDocument, source: VisualSourceIdentity, destination: str | None) -> int:
    for issue in document.export_issues:
        output.warn(issue)
    if document.export_issues:
        output.warn("OCR scan is incomplete or invalid; no subtitle output was created.")
        return EXIT.RUNTIME_ERROR
    data = document.resume(source)
    if destination:
        target = Path(destination)
        if target.suffix.lower() == ".json":
            atomic_json(target, data.to_document())
        else:
            atomic_text(target, data.to_srt())
        output.info(f"Exported {len(data)} OCR cues. JSON preserves visual provenance; SRT keeps text/time only.")
    return EXIT.SUCCESS


def _validate_suffixes(args: Namespace) -> None:
    if args.output and Path(args.output).suffix.lower() not in (".json", ".srt"):
        raise OcrError("OCR export supports .json or .srt")
    for value in (getattr(args, "review", None), getattr(args, "save_review", None), getattr(args, "report", None)):
        if value and Path(value).suffix.lower() != ".json":
            raise OcrError("OCR checkpoint/report output must use .json")


def run(args: Namespace, config: dict) -> int:
    source = Path(args.input)
    if not source.is_file():
        output.error("OCR video not found.")
        return EXIT.FILE_NOT_FOUND
    root = Path(args.ocr_runtime) if args.ocr_runtime else default_runtime()
    bridge = Path(args.ocr_bridge) if args.ocr_bridge else resources() / "ocr_stream_worker.py"
    try:
        _validate_suffixes(args)
        if not args.output and not args.review:
            raise OcrError("Choose --output for subtitles or --checkpoint to save OCR data")
        cache_limit_bytes(args.cache_mib)
        _paths([source, bridge], [args.review, args.output, args.report], root)
        roi_values = [float(v) for v in args.roi.split(",")]
        if len(roi_values) != 4:
            raise OcrError("ROI needs normalized X,Y,WIDTH,HEIGHT")
        if not bridge.is_file() or not (root / "profile.json").is_file():
            output.error("Installed OCR runtime/profile and explicit streaming bridge are required.")
            return EXIT.DEPENDENCY_MISSING
        expected = args.profile_sha256 or inspect_installation(root).profile_sha256
        settings = OcrConfig(Roi(*roi_values), Selection(args.start_ms, args.end_ms), expected,
                             hashlib.sha256(bridge.read_bytes()).hexdigest(), args.language,
                             profile_snapshot=OcrProfileSnapshot.from_bytes((root / "profile.json").read_bytes(),
                                                                            expected))
    except (OSError, ValueError, TypeError):
        output.error("Invalid OCR selection, ROI, profile or output paths.")
        return EXIT.USAGE_ERROR
    return _scan(args, source, settings, root, bridge)


def resume_scan(args: Namespace, config: dict) -> int:
    source, saved = Path(args.source), Path(args.input)
    if not source.is_file() or not saved.is_file():
        output.error("OCR checkpoint and original video are required.")
        return EXIT.FILE_NOT_FOUND
    root = Path(args.ocr_runtime) if args.ocr_runtime else default_runtime()
    bridge = Path(args.ocr_bridge) if args.ocr_bridge else resources() / "ocr_stream_worker.py"
    try:
        _validate_suffixes(args)
        if not args.output and not args.review:
            raise OcrError("Choose --output for subtitles or --checkpoint to save OCR data")
        cache_limit_bytes(args.cache_mib)
        _paths([source, saved, bridge], [args.review, args.output, args.report], root)
        document = OcrDocument.load(saved)
        validate_resume(document, document.config)
    except (OSError, ValueError):
        output.error("Invalid or completed OCR checkpoint; preserve the input and choose a separate output.")
        return EXIT.USAGE_ERROR
    return _scan(args, source, document.config, root, bridge, document)


def _scan(args: Namespace, source: Path, settings: OcrConfig, root: Path, bridge: Path,
          resume_document: OcrDocument | None = None) -> int:
    try:
        document = run_cpu_ocr(source, settings, root, bridge, max_requests=args.max_requests,
                               timeout=args.timeout, ffmpeg=args.ffmpeg, ffprobe=args.ffprobe,
                               checkpoint=lambda doc: doc.save(args.review) if args.review else None, cache_mib=args.cache_mib,
                               progress=lambda _percent, message: output.info(message), resume_document=resume_document)
        if args.report:
            atomic_json(Path(args.report), {"schema": "ocr-report-v1", "document_id": document.id,
                                           "complete": document.complete, "metrics": document.to_dict()["metrics"],
                                           "pending_issues": list(document.pending_issues),
                                           "export_issues": list(document.export_issues), "stage_times_overlap": True})
        return _export(document, document.visual_source, args.output)
    except OcrRuntimeMissing:
        output.error("OCR runtime is missing; select an already installed runtime.")
        return EXIT.DEPENDENCY_MISSING
    except (OSError, ValueError, RuntimeError):
        output.error("OCR processing failed; any saved partial checkpoint remains incomplete. No model was installed.")
        return EXIT.RUNTIME_ERROR


def cache(args: Namespace, config: dict) -> int:
    try:
        info = manage_cache(clear=args.action == "clear")
    except OcrError as exc:
        output.error(str(exc))
        return EXIT.RUNTIME_ERROR
    if args.action == "clear":
        output.info(f"Cleared {info.entries} cached OCR reads. Saved OCR documents and models are unchanged.")
    else:
        output.info(f"OCR cache: {info.entries} reads, {info.payload_bytes} payload bytes, "
                    f"{info.database_bytes} database bytes (including SQLite metadata).")
    return EXIT.SUCCESS


def review(args: Namespace, config: dict) -> int:
    if not Path(args.input).is_file() or not Path(args.source).is_file():
        output.error("Saved OCR data and original video are required.")
        return EXIT.FILE_NOT_FOUND
    try:
        _validate_suffixes(args)
        _paths([Path(args.input), Path(args.source)], [args.save_review, args.output])
        if (args.select_candidate or args.set_timing) and (not args.note or not args.save_review):
            raise OcrError("Review changes require --note and --save-review")
    except ValueError as exc:
        output.error(str(exc))
        return EXIT.USAGE_ERROR
    try:
        document = OcrDocument.load(args.input)
        verified = verify_visual_file(document.visual_source, Path(args.source), jobs_directory(), ffprobe=args.ffprobe)
        for choice in args.select_candidate or []:
            cue_id, candidate_id = choice.split(":")
            cue = next((c for c in document.cues if c.id == cue_id), None)
            if cue is None:
                raise OcrError("Unknown OCR cue")
            document = document.replace_cue(cue.select_candidate(candidate_id, args.note))
        for timing in args.set_timing or []:
            cue_id, start, end = timing.split(":")
            cue = next((c for c in document.cues if c.id == cue_id), None)
            if cue is None:
                raise OcrError("Unknown OCR cue")
            document = document.replace_cue(cue.review_timing(int(start), int(end), args.note))
        if args.save_review:
            document.save(args.save_review)
        return _export(document, verified, args.output)
    except (OSError, ValueError):
        output.error("Saved OCR could not be exported; check source identity, candidate IDs and timing.")
        return EXIT.RUNTIME_ERROR

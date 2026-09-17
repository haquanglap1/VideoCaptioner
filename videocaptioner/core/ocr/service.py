"""Source OCR service shared by CLI and future workers, with injectable recognition."""

from __future__ import annotations

import time
from contextlib import ExitStack
from dataclasses import replace
from pathlib import Path
from typing import Callable

from .cache import DEFAULT_CACHE_MIB, cache_directory, cache_limit_bytes, read_cache
from .codec import digest
from .consensus import CacheScope
from .decoder import RoiDecoder, probe_video
from .document import OcrConfig, OcrDocument, OcrMetrics, cue_from_region, document_id
from .identity import VisualSourceIdentity
from .models import Check, EngineRead, OcrError, RoiFrame, VisualDecision
from .pipeline import OcrPipeline, Recognizer
from .profile import OcrProfileSnapshot
from .resume import ResumeBoundary, validate_resume
from .runtime import CpuOcrRuntime
from .source import video_snapshot
from .tracking import CHARACTER_TRACKING_WORKERS


def jobs_directory() -> Path:
    from videocaptioner.config import APPDATA_PATH

    return Path(APPDATA_PATH) / "ocr" / "jobs"


def scan_video(source: Path, config: OcrConfig, recognizer: Recognizer, *, jobs_root: Path,
               ffmpeg: str = "ffmpeg", ffprobe: str = "ffprobe", check: Check = lambda: None,
               checkpoint: Callable[[OcrDocument], None] = lambda _: None,
               progress: Callable[[int, str], None] = lambda *_: None,
               expected_source_sha256: str = "", cache_root: Path | None = None,
               cache_mib: int = DEFAULT_CACHE_MIB, resume_document: OcrDocument | None = None,
               visual_reader: Callable[[RoiFrame, EngineRead | None], VisualDecision] | None = None) -> OcrDocument:
    cache_bytes = cache_limit_bytes(cache_mib)
    if (config.tracking_policy in CHARACTER_TRACKING_WORKERS) != (visual_reader is not None):
        raise OcrError("OCR tracking reader does not match its saved policy")
    boundary = None
    if resume_document is not None:
        validate_resume(resume_document, config)
        boundary = ResumeBoundary(resume_document)
    begun = time.monotonic()
    with video_snapshot(source, jobs_root, check) as snapshot:
        if expected_source_sha256 and snapshot.sha256 != expected_source_sha256:
            raise OcrError("Video đã thay đổi sau khi chọn ROI; tải lại ảnh nguồn trước khi OCR.")
        info = probe_video(snapshot.path, ffprobe, check)
        identity = VisualSourceIdentity.from_snapshot(snapshot, info, config.selection)
        if resume_document is not None:
            resume_document.visual_source.require_match(identity)
        scope = CacheScope(snapshot.sha256, config.read_revision, digest([identity.to_dict(), digest(config)]))
        decoder = RoiDecoder(snapshot.path, info, config.roi, ffmpeg=ffmpeg, check=check,
                             seek_pts=boundary.seek_pts if boundary else None)
        identifier = document_id(identity, config)
        cues = list(resume_document.cues) if resume_document is not None else []
        complete = False
        with read_cache(scope, cache_root, cache_bytes, check=check,
                        warning=lambda message: progress(0, message)) as cache:
            def frame_progress(end_ms):
                if visual_reader:
                    percent = int(100 * (end_ms - config.selection.start_ms)
                                  / (config.selection.end_ms - config.selection.start_ms))
                    progress(min(99, percent), f"Đang theo dõi hình chữ: {float(end_ms) / 1000:.2f}s.")

            pipeline = OcrPipeline(recognizer, cache, check=check, line_selection=config.line_selection,
                                   visual_reader=visual_reader, frame_progress=frame_progress,
                                   consensus_policy=config.consensus_policy)
            try:
                if boundary:
                    position = boundary.start_ms if boundary.start_ms is not None else config.selection.start_ms
                    progress(0, f"Giữ {len(cues)} câu đã lưu; kiểm điểm nối từ {float(position) / 1000:.3f}s.")
                for region in pipeline.run(decoder, config.selection,
                                           start_ms=boundary.start_ms if boundary else None,
                                           initial_issues=boundary.initial_issues if boundary else (),
                                           accept_region=boundary.accept if boundary else lambda _: True):
                    cues.append(cue_from_region(identifier, region))
                    percent = int(100 * (region.end_ms - config.selection.start_ms)
                                  / (config.selection.end_ms - config.selection.start_ms))
                    progress(min(99, percent), f"Đã đọc {len(cues)} nhóm chữ.")
                check()
                if boundary:
                    boundary.finish()
                complete = True
            finally:
                decoder.close()
                metrics = pipeline.metrics
                document = OcrDocument(identifier, identity, config, tuple(cues), complete,
                                       OcrMetrics(metrics.roi_frames, metrics.tracks, metrics.candidate_crops,
                                                  metrics.fresh_calls, metrics.cache_hits, metrics.pipeline_wall_s,
                                                  metrics.tracking_s, metrics.recognition_call_s,
                                                  time.monotonic() - begun))
                checkpoint(document)
        return document


def run_cpu_ocr(source: Path, config: OcrConfig, runtime_root: Path, bridge: Path, *,
                max_requests: int = 1000, timeout: float = 30,
                ffmpeg: str = "ffmpeg", ffprobe: str = "ffprobe", check: Check = lambda: None,
                checkpoint: Callable[[OcrDocument], None] = lambda _: None,
                progress: Callable[[int, str], None] = lambda *_: None,
                expected_source_sha256: str = "", cache_mib: int = DEFAULT_CACHE_MIB,
                resume_document: OcrDocument | None = None, recognizer_root: Path | None = None) -> OcrDocument:
    cache_limit_bytes(cache_mib)
    if resume_document is not None:
        validate_resume(resume_document, config)
    begun = time.monotonic()
    gpu = None
    if bool(config.recognizer) != (recognizer_root is not None):
        raise OcrError("Select the recognizer runtime matching this OCR checkpoint")
    if config.recognizer is not None:
        from .vl import PaddleVlRuntime, inspect_vl

        original_check = check

        def candidate_check():
            original_check()
            if time.monotonic() - begun >= 360:
                raise OcrError("OCR candidate job deadline exhausted")

        check = candidate_check
        max_requests = min(max_requests, 40)
        assert recognizer_root is not None
        installation = inspect_vl(recognizer_root, check)
        if installation.profile != config.recognizer:
            raise OcrError("OCR recognizer changed after the config snapshot")
        gpu = PaddleVlRuntime(installation, jobs_directory(), timeout=min(timeout, 90),
                             max_requests=max_requests, check=check)
    jobs = jobs_directory()
    runtime = CpuOcrRuntime(runtime_root, bridge, jobs, config.profile_sha256, max_requests=max_requests,
                            timeout=timeout, check=check, expected_profile=config.profile_snapshot)
    latest: OcrDocument | None = None

    def capture(document: OcrDocument) -> None:
        nonlocal latest
        latest = document

    try:
        with ExitStack() as stack:
            stack.enter_context(runtime)
            recognizer: Recognizer = runtime
            if gpu is not None:
                from .vl import VlRecognizer

                stack.enter_context(gpu)
                assert config.line_selection is not None
                recognizer = VlRecognizer(runtime, gpu, config.line_selection, config.read_revision, max_requests)
            if (runtime.bridge_sha256 != config.bridge_sha256
                    or OcrProfileSnapshot.from_bytes((runtime_root / "profile.json").read_bytes(), config.profile_sha256)
                    != config.profile_snapshot):
                raise OcrError("OCR bridge or profile changed after the config snapshot")
            def track(frame, raw):
                # The generator's input rectangle is not detector geometry. Reuse only
                # the original CTC boxes so cached reads preserve the old tracker.
                if gpu is not None and raw is not None:
                    raw = EngineRead(raw.generation.geometry_lines if raw.generation else (), config.profile_sha256)
                assert config.line_selection is not None
                return runtime.track(frame, config.line_selection.anchors[0], raw, check)

            scan_video(source, config, recognizer, jobs_root=jobs, ffmpeg=ffmpeg,
                       ffprobe=ffprobe, check=check, checkpoint=capture, progress=progress,
                       expected_source_sha256=expected_source_sha256,
                       cache_root=cache_directory() if cache_mib else None, cache_mib=cache_mib,
                       resume_document=resume_document,
                       visual_reader=track
                       if config.tracking_policy in CHARACTER_TRACKING_WORKERS and config.line_selection else None)
    finally:
        if latest is not None:
            metrics = runtime.metrics
            latest = replace(latest, metrics=replace(latest.metrics, job_wall_s=time.monotonic() - begun,
                worker_requests=metrics.requests, worker_responses=metrics.completed,
                detector_attempts=metrics.started_inference_calls["det"],
                recognizer_attempts=metrics.started_inference_calls["rec"],
                classifier_attempts=metrics.started_inference_calls["cls"], worker_inference_s=metrics.inference_s,
                worker_process_wall_s=metrics.process_wall_s,
                tracking_requests=metrics.tracking_requests if config.tracking_policy in CHARACTER_TRACKING_WORKERS else None,
                visual_batches=metrics.visual_batches if config.tracking_policy in CHARACTER_TRACKING_WORKERS else None,
                gpu_requests=gpu.metrics.requests if gpu else None,
                gpu_responses=gpu.metrics.completed if gpu else None,
                gpu_recognizer_attempts=gpu.metrics.started_inference_calls["rec"] if gpu else None,
                gpu_inference_s=gpu.metrics.inference_s if gpu else None,
                gpu_process_wall_s=gpu.metrics.process_wall_s if gpu else None))
            checkpoint(latest)
    assert latest is not None
    return latest

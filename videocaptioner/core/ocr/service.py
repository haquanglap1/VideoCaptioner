"""Source OCR service shared by CLI and future workers, with injectable recognition."""

from __future__ import annotations

import time
from dataclasses import replace
from pathlib import Path
from typing import Callable

from .cache import DEFAULT_CACHE_MIB, cache_directory, cache_limit_bytes, read_cache
from .codec import digest
from .consensus import CacheScope
from .decoder import RoiDecoder, probe_video
from .document import OcrConfig, OcrDocument, OcrMetrics, cue_from_region, document_id
from .identity import VisualSourceIdentity
from .models import Check, OcrError
from .pipeline import OcrPipeline, Recognizer
from .profile import OcrProfileSnapshot
from .resume import ResumeBoundary, validate_resume
from .runtime import CpuOcrRuntime
from .source import video_snapshot


def jobs_directory() -> Path:
    from videocaptioner.config import APPDATA_PATH

    return Path(APPDATA_PATH) / "ocr" / "jobs"


def scan_video(source: Path, config: OcrConfig, recognizer: Recognizer, *, jobs_root: Path,
               ffmpeg: str = "ffmpeg", ffprobe: str = "ffprobe", check: Check = lambda: None,
               checkpoint: Callable[[OcrDocument], None] = lambda _: None,
               progress: Callable[[int, str], None] = lambda *_: None,
               expected_source_sha256: str = "", cache_root: Path | None = None,
               cache_mib: int = DEFAULT_CACHE_MIB, resume_document: OcrDocument | None = None) -> OcrDocument:
    cache_bytes = cache_limit_bytes(cache_mib)
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
        scope = CacheScope(snapshot.sha256, config.profile_sha256, digest([identity.to_dict(), digest(config)]))
        decoder = RoiDecoder(snapshot.path, info, config.roi, ffmpeg=ffmpeg, check=check,
                             seek_pts=boundary.seek_pts if boundary else None)
        identifier = document_id(identity, config)
        cues = list(resume_document.cues) if resume_document is not None else []
        complete = False
        with read_cache(scope, cache_root, cache_bytes, check=check,
                        warning=lambda message: progress(0, message)) as cache:
            pipeline = OcrPipeline(recognizer, cache, check=check, line_selection=config.line_selection)
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
                resume_document: OcrDocument | None = None) -> OcrDocument:
    cache_limit_bytes(cache_mib)
    if resume_document is not None:
        validate_resume(resume_document, config)
    jobs = jobs_directory()
    runtime = CpuOcrRuntime(runtime_root, bridge, jobs, config.profile_sha256, max_requests=max_requests,
                            timeout=timeout, check=check, expected_profile=config.profile_snapshot)
    begun = time.monotonic()
    latest: OcrDocument | None = None

    def capture(document: OcrDocument) -> None:
        nonlocal latest
        latest = document

    try:
        with runtime:
            if (runtime.bridge_sha256 != config.bridge_sha256
                    or OcrProfileSnapshot.from_bytes((runtime_root / "profile.json").read_bytes(), config.profile_sha256)
                    != config.profile_snapshot):
                raise OcrError("OCR bridge or profile changed after the config snapshot")
            scan_video(source, config, runtime, jobs_root=jobs, ffmpeg=ffmpeg,
                       ffprobe=ffprobe, check=check, checkpoint=capture, progress=progress,
                       expected_source_sha256=expected_source_sha256,
                       cache_root=cache_directory() if cache_mib else None, cache_mib=cache_mib,
                       resume_document=resume_document)
    finally:
        if latest is not None:
            metrics = runtime.metrics
            latest = replace(latest, metrics=replace(latest.metrics, job_wall_s=time.monotonic() - begun,
                worker_requests=metrics.requests, worker_responses=metrics.completed,
                detector_attempts=metrics.started_inference_calls["det"],
                recognizer_attempts=metrics.started_inference_calls["rec"],
                classifier_attempts=metrics.started_inference_calls["cls"], worker_inference_s=metrics.inference_s,
                worker_process_wall_s=metrics.process_wall_s))
            checkpoint(latest)
    assert latest is not None
    return latest

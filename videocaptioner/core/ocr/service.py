"""Source OCR service shared by CLI and future workers, with injectable recognition."""

from __future__ import annotations

import time
from dataclasses import replace
from pathlib import Path
from typing import Callable

from .codec import digest
from .consensus import CacheScope, ReadCache
from .decoder import RoiDecoder, probe_video
from .document import OcrConfig, OcrDocument, OcrMetrics, cue_from_region, document_id
from .identity import VisualSourceIdentity
from .models import Check, OcrError
from .pipeline import OcrPipeline, Recognizer
from .profile import OcrProfileSnapshot
from .runtime import CpuOcrRuntime
from .source import video_snapshot


def jobs_directory() -> Path:
    from videocaptioner.config import APPDATA_PATH

    return Path(APPDATA_PATH) / "ocr" / "jobs"


def scan_video(source: Path, config: OcrConfig, recognizer: Recognizer, *, jobs_root: Path,
               ffmpeg: str = "ffmpeg", ffprobe: str = "ffprobe", check: Check = lambda: None,
               checkpoint: Callable[[OcrDocument], None] = lambda _: None,
               progress: Callable[[int, str], None] = lambda *_: None,
               expected_source_sha256: str = "") -> OcrDocument:
    begun = time.monotonic()
    with video_snapshot(source, jobs_root, check) as snapshot:
        if expected_source_sha256 and snapshot.sha256 != expected_source_sha256:
            raise OcrError("Video đã thay đổi sau khi chọn ROI; tải lại ảnh nguồn trước khi OCR.")
        info = probe_video(snapshot.path, ffprobe, check)
        identity = VisualSourceIdentity.from_snapshot(snapshot, info, config.selection)
        scope = CacheScope(snapshot.sha256, config.profile_sha256, digest([identity.to_dict(), digest(config)]))
        decoder = RoiDecoder(snapshot.path, info, config.roi, ffmpeg=ffmpeg, check=check)
        pipeline = OcrPipeline(recognizer, ReadCache(scope), check=check)
        identifier = document_id(identity, config)
        cues = []
        complete = False
        try:
            for region in pipeline.run(decoder, config.selection):
                cues.append(cue_from_region(identifier, region))
                percent = int(100 * (region.end_ms - config.selection.start_ms)
                              / (config.selection.end_ms - config.selection.start_ms))
                progress(min(99, percent), f"Đã đọc {len(cues)} nhóm chữ; đang giữ dữ liệu review.")
            check()
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
                expected_source_sha256: str = "") -> OcrDocument:
    jobs = jobs_directory()
    runtime = CpuOcrRuntime(runtime_root, bridge, jobs, config.profile_sha256, max_requests=max_requests,
                            timeout=timeout, check=check)
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
                       expected_source_sha256=expected_source_sha256)
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

"""Run the OCR-2 streaming domain with the already installed CPU runtime.

Private evidence only: all results keep review state; this is not the public OCR CLI.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import threading
import time
from dataclasses import asdict
from pathlib import Path

import psutil

from videocaptioner.core.ocr.consensus import CacheScope, ReadCache
from videocaptioner.core.ocr.decoder import RoiDecoder, probe_video
from videocaptioner.core.ocr.geometry import Roi
from videocaptioner.core.ocr.models import Selection
from videocaptioner.core.ocr.pipeline import OcrPipeline
from videocaptioner.core.ocr.runtime import CpuOcrRuntime
from videocaptioner.core.ocr.source import video_snapshot


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("source", "runtime", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--roi", required=True)
    parser.add_argument("--start-ms", type=int, required=True)
    parser.add_argument("--end-ms", type=int, required=True)
    parser.add_argument("--ffmpeg", default="ffmpeg")
    parser.add_argument("--ffprobe", default="ffprobe")
    parser.add_argument("--max-calls", type=int, default=39)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    begun = time.perf_counter()
    roi = Roi(*[float(v) for v in args.roi.split(",")])
    selection = Selection(args.start_ms, args.end_ms)
    bridge = Path(__file__).with_name("ocr_stream_worker.py")
    profile = Path(__file__).with_name("ocr_pilot_data") / "profile.json"
    profile_hash = digest(profile)
    runtime = CpuOcrRuntime(args.runtime, bridge, args.output / "jobs", profile_hash, max_requests=args.max_calls)
    decoder = None
    pipeline = None
    stop = threading.Event()
    peaks = {"host_sampled_rss_bytes": 0, "worker_tree_sampled_rss_bytes": 0,
             "ffmpeg_sampled_rss_bytes": 0}

    def monitor():
        while not stop.wait(0.005):
            peaks["host_sampled_rss_bytes"] = max(peaks["host_sampled_rss_bytes"], psutil.Process().memory_info().rss)
            for name, owner in (("worker_tree_sampled_rss_bytes", runtime), ("ffmpeg_sampled_rss_bytes", decoder)):
                if owner is None or owner.process is None:
                    continue
                try:
                    process = psutil.Process(owner.process.pid)
                    rss = process.memory_info().rss + sum(p.memory_info().rss for p in process.children(recursive=True))
                    peaks[name] = max(peaks[name], rss)
                except psutil.Error:
                    pass

    monitor_thread = threading.Thread(target=monitor)
    monitor_thread.start()
    metrics = {"schema": "ocr2-cpu-streaming-pilot-v1", "status": "running", "profile_sha256": profile_hash,
               "bridge_sha256": digest(bridge), "roi": asdict(roi), "selection": asdict(selection),
               "vision_api_calls": 0, "provider_usage": None, "provider_cost": None}
    try:
        with video_snapshot(args.source, args.output / "jobs") as snapshot:
            metrics["snapshot_sha256"] = snapshot.sha256
            metrics["snapshot_bytes"] = snapshot.size_bytes
            info = probe_video(snapshot.path, args.ffprobe)
            metrics["source_time_base"] = str(info.time_base)
            metrics["source_timeline_origin_s"] = str(info.timeline_origin)
            policy = {"geometry": asdict(info.geometry), "roi": asdict(roi), "selection": asdict(selection),
                      "tracking": "edge-tiles-ocr2-v1", "consensus": "exact-read-uncalibrated-v1",
                      "bridge_sha256": digest(bridge)}
            policy_hash = hashlib.sha256(json.dumps(policy, sort_keys=True, default=str).encode()).hexdigest()
            cache = ReadCache(CacheScope(snapshot.sha256, profile_hash, policy_hash))
            decoder = RoiDecoder(snapshot.path, info, roi, ffmpeg=args.ffmpeg)
            pipeline = OcrPipeline(runtime, cache)
            with runtime, (args.output / "regions.jsonl").open("x", encoding="utf-8") as output:
                for index, region in enumerate(pipeline.run(decoder, selection), 1):
                    output.write(json.dumps({"id": index, **asdict(region)}, ensure_ascii=False, default=str) + "\n")
                    output.flush()
                    print(json.dumps({"track": index, "start_ms": str(region.start_ms),
                                      "end_ms": str(region.end_ms), "review": region.needs_review}), flush=True)
            metrics["cache_serialized_bytes"] = cache.size
        metrics["status"] = "review_required"
    except Exception as error:
        metrics["status"] = "error"
        metrics["error_type"] = type(error).__name__
        raise
    finally:
        runtime.close()
        if decoder is not None:
            decoder.close()
        stop.set()
        monitor_thread.join()
        metrics["pipeline"] = asdict(pipeline.metrics) if pipeline else None
        metrics["runtime"] = asdict(runtime.metrics)
        metrics["decode"] = asdict(decoder.metrics) if decoder else None
        metrics["sampled_memory"] = peaks
        metrics["host_peak_wset_bytes"] = getattr(psutil.Process().memory_info(), "peak_wset", None)
        metrics["pilot_wall_s"] = time.perf_counter() - begun
        metrics["wall_scope"] = "After argument parsing; includes snapshot/probe/load/decode/inference/close, excludes host imports"
        metrics["stage_times_overlap"] = True
        metrics["readers_joined"] = all(not r.is_alive() for r in runtime.readers + (decoder.readers if decoder else []))
        metrics["job_files_cleaned"] = not any((args.output / "jobs").iterdir())
        (args.output / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
        print(json.dumps({"status": metrics["status"], "pilot_wall_s": metrics["pilot_wall_s"]}), flush=True)


if __name__ == "__main__":
    main()

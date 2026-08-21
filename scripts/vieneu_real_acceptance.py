#!/usr/bin/env python3
"""Run real managed VieNeu GPU acceptance without persisting text or credentials."""

from __future__ import annotations

import argparse
import io
import json
import time
import wave
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

from videocaptioner.core.tts.vieneu.model_updater import VieNeuModelPaths, VieNeuStateStore
from videocaptioner.core.tts.vieneu.runtime_manager import VieNeuRuntimeManager
from videocaptioner.core.tts.vieneu.service import VieNeuManagedService


def wav_info(data: bytes) -> dict[str, float | int]:
    with wave.open(io.BytesIO(data), "rb") as wav:
        rate = wav.getframerate()
        frames = wav.getnframes()
        channels = wav.getnchannels()
    duration = frames / rate if rate else 0.0
    if rate != 48_000 or channels < 1 or not 0.05 <= duration <= 15:
        raise RuntimeError("VieNeu WAV acceptance failed")
    return {"sample_rate": rate, "channels": channels, "duration": round(duration, 4)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime", required=True)
    parser.add_argument("--bridge", required=True)
    parser.add_argument("--model-root", default="AppData/models/vieneu")
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--output", default="AppData/vieneu-real-acceptance.json")
    args = parser.parse_args()

    store = VieNeuStateStore(VieNeuModelPaths.under(args.model_root))
    service = VieNeuManagedService(
        manager=VieNeuRuntimeManager(),
        store=store,
        explicit_runtime=args.runtime,
        explicit_bridge=args.bridge,
    )
    started = time.perf_counter()
    identity = service.ensure_ready()
    cold_seconds = time.perf_counter() - started
    pid = service.manager.process_id
    warm_started = time.perf_counter()
    warm_identity = service.ensure_ready()
    warm_seconds = time.perf_counter() - warm_started
    voices = service.voices()
    if len(voices) < 1 or warm_identity is not identity or service.manager.process_id != pid:
        raise RuntimeError("VieNeu warm-session acceptance failed")
    voice = str(voices[0]["id"])
    endpoint = identity.endpoint.rstrip("/") + "/audio/speech"
    headers = {"Authorization": f"Bearer {identity.session_token}"}

    def request_audio(index: int):
        # Fixed synthetic acceptance sentence; only its character count reaches logs.
        response = requests.post(
            endpoint,
            headers=headers,
            json={
                "model": identity.model_revision,
                "input": f"Xin chào, đây là phép thử số {index + 1}.",
                "voice": voice,
                "response_format": "wav",
                "speed": 1.0,
            },
            timeout=180,
        )
        response.raise_for_status()
        return wav_info(response.content)

    concurrent_started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=max(1, args.concurrency)) as executor:
        wavs = list(executor.map(request_audio, range(max(1, args.concurrency))))
    concurrent_seconds = time.perf_counter() - concurrent_started
    batch_lines = [line for line in service.manager._log_tail if "batch requests=" in line]
    result = {
        "protocol_version": identity.protocol_version,
        "runtime_version": identity.runtime_version,
        "model_revision": identity.model_revision,
        "backend": identity.backend,
        "sample_rate": identity.sample_rate,
        "voice_count": len(voices),
        "cold_start_seconds": round(cold_seconds, 4),
        "warm_start_seconds": round(warm_seconds, 6),
        "concurrency": max(1, args.concurrency),
        "concurrent_seconds": round(concurrent_seconds, 4),
        "wav_results": wavs,
        "batch_observed": any("requests=1" not in line for line in batch_lines),
        "owned_processes_before_shutdown": service.manager.owned_processes_alive(),
    }
    service.shutdown()
    result["owned_processes_after_shutdown"] = service.manager.owned_processes_alive()
    if result["owned_processes_after_shutdown"]:
        raise RuntimeError("VieNeu sidecar process cleanup failed")
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

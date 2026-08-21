#!/usr/bin/env python3
"""Authenticated OpenAI-compatible bridge for the managed VieNeu sidecar.

This file runs only under ``runtime/vieneu/python.exe``. VideoCaptioner's Qt
process never imports VieNeu, CUDA, ONNX, FastAPI, or Uvicorn.
"""

from __future__ import annotations

import argparse
import asyncio
import hmac
import io
import json
import logging
import os
import re
import sys
import time
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf
import uvicorn
from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import JSONResponse, Response
from starlette.concurrency import run_in_threadpool

SERVICE_ID = "videocaptioner-vieneu"
PROTOCOL_VERSION = "vieneu-runtime-protocol-v1"
BRIDGE_VERSION = "1.0.0"

TTS = None
SERVER: uvicorn.Server | None = None
SCHEDULER = None
SESSION_TOKEN = ""
SESSION_ID = ""
IDENTITY: dict[str, Any] = {}
DEFAULT_VOICE = ""
STOPPING = False

_TOKEN_RE = re.compile(r"(?i)bearer\s+\S+|(?:token|api[_ -]?key)\s*[:=]\s*\S+")
_PATH_RE = re.compile(r"(?i)\b[A-Z]:\\[^\r\n\t]+")


def safe_error(error: object) -> str:
    text = " ".join(str(error or "Unknown bridge error").split())
    text = _TOKEN_RE.sub("credential=***", text)
    text = _PATH_RE.sub("<local-path>", text)
    return text[:800]


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("vieneu.bridge")


def encode_wav(samples: np.ndarray, sample_rate: int) -> bytes:
    buffer = io.BytesIO()
    sf.write(buffer, np.asarray(samples, dtype=np.float32), sample_rate, format="WAV")
    return buffer.getvalue()


def apply_speed(samples: np.ndarray, speed: float) -> np.ndarray:
    speed = max(0.25, min(4.0, float(speed or 1.0)))
    if abs(speed - 1.0) < 1e-3:
        return samples
    import librosa

    return librosa.effects.time_stretch(
        np.ascontiguousarray(samples, dtype=np.float32), rate=speed
    )


def voice_list() -> list[dict[str, str]]:
    output = []
    for label, voice_id in TTS.list_preset_voices():
        output.append({"id": str(voice_id), "name": str(label)})
    return output


def infer_one(text: str, voice: str, speed: float) -> np.ndarray:
    samples = TTS.infer(text, voice=voice)
    return apply_speed(samples, speed)


def infer_group(items: list[tuple[str, str, float]]) -> list[np.ndarray]:
    """Batch requests with the same voice; never share unsafe Qt-side model state."""
    results: list[np.ndarray | None] = [None] * len(items)
    by_voice: dict[str, list[tuple[int, str, float]]] = {}
    for index, (text, voice, speed) in enumerate(items):
        by_voice.setdefault(voice, []).append((index, text, speed))
    for voice, group in by_voice.items():
        texts = [entry[1] for entry in group]
        if len(texts) > 1 and hasattr(TTS, "infer_batch"):
            generated = TTS.infer_batch(texts, voice=voice, batch_size=len(texts))
        else:
            generated = [TTS.infer(text, voice=voice) for text in texts]
        for (index, _text, speed), samples in zip(group, generated):
            results[index] = apply_speed(samples, speed)
    return [
        sample if sample is not None else np.zeros(0, dtype=np.float32)
        for sample in results
    ]


class BatchScheduler:
    def __init__(self, *, max_batch: int, max_wait: float):
        self.max_batch = max(1, int(max_batch))
        self.max_wait = max(0.0, float(max_wait))
        self.queue: asyncio.Queue = asyncio.Queue()
        self.task: asyncio.Task | None = None
        self.stopping = False

    def start(self) -> None:
        self.task = asyncio.create_task(self._run(), name="vieneu-batch-scheduler")

    async def submit(self, text: str, voice: str, speed: float) -> np.ndarray:
        if self.stopping:
            raise RuntimeError("VieNeu scheduler is stopping")
        future = asyncio.get_running_loop().create_future()
        await self.queue.put((text, voice, speed, future))
        return await future

    async def _run(self) -> None:
        while not self.stopping:
            first = await self.queue.get()
            batch = [first]
            deadline = time.monotonic() + self.max_wait
            while len(batch) < self.max_batch:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                try:
                    batch.append(await asyncio.wait_for(self.queue.get(), remaining))
                except asyncio.TimeoutError:
                    break
            compact = [(text, voice, speed) for text, voice, speed, _future in batch]
            futures = [future for _text, _voice, _speed, future in batch]
            log.info(
                "batch requests=%d voices=%d",
                len(compact),
                len({voice for _text, voice, _speed in compact}),
            )
            try:
                generated = await run_in_threadpool(infer_group, compact)
                for samples, future in zip(generated, futures):
                    if not future.done():
                        future.set_result(samples)
            except Exception as exc:
                for future in futures:
                    if not future.done():
                        future.set_exception(exc)

    async def close(self) -> None:
        self.stopping = True
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass


router = APIRouter()


@router.get("/health")
async def health():
    return {**IDENTITY, "ready": not STOPPING}


@router.get("/voices")
@router.get("/audio/voices")
async def voices():
    items = voice_list()
    return {"object": "list", "voices": items, "data": items}


@router.get("/models")
async def models():
    items = [
        {"id": voice["id"], "name": voice["name"], "object": "model", "owned_by": "vieneu"}
        for voice in voice_list()
    ]
    return {"object": "list", "data": items}


@router.post("/audio/speech")
async def speech(request: Request):
    if STOPPING:
        return JSONResponse({"error": "runtime is stopping"}, status_code=503)
    payload = await request.json()
    text = str(payload.get("input") or payload.get("text") or "")
    if not text.strip():
        return JSONResponse({"error": "empty input"}, status_code=400)
    voices_available = voice_list()
    valid = {voice["id"] for voice in voices_available}
    voice = str(payload.get("voice") or DEFAULT_VOICE)
    if voice not in valid:
        voice = DEFAULT_VOICE
    try:
        speed = float(payload.get("speed", 1.0) or 1.0)
    except (TypeError, ValueError):
        speed = 1.0
    log.info("speech request voice=%s chars=%d", voice, len(text))
    try:
        if SCHEDULER:
            samples = await SCHEDULER.submit(text, voice, speed)
        else:
            samples = await run_in_threadpool(infer_one, text, voice, speed)
        return Response(
            content=encode_wav(samples, int(IDENTITY["sample_rate"])),
            media_type="audio/wav",
        )
    except Exception as exc:
        log.error("speech failed: %s", safe_error(exc))
        return JSONResponse({"error": safe_error(exc)}, status_code=500)


@router.post("/shutdown")
async def shutdown():
    global STOPPING
    STOPPING = True
    if SERVER:
        SERVER.should_exit = True
    return {"status": "stopping"}


def build_app(max_batch: int, max_wait: float) -> FastAPI:
    app = FastAPI(title="VideoCaptioner VieNeu managed bridge")

    @app.middleware("http")
    async def authenticate(request: Request, call_next):
        supplied = request.headers.get("authorization", "")
        expected = f"Bearer {SESSION_TOKEN}"
        if not SESSION_TOKEN or not hmac.compare_digest(supplied, expected):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        return await call_next(request)

    for prefix in ("", "/v1", "/api/v1"):
        app.include_router(router, prefix=prefix)

    @app.on_event("startup")
    async def startup_scheduler():
        global SCHEDULER
        SCHEDULER = BatchScheduler(max_batch=max_batch, max_wait=max_wait)
        SCHEDULER.start()

    @app.on_event("shutdown")
    async def shutdown_scheduler():
        if SCHEDULER:
            await SCHEDULER.close()
        close = getattr(TTS, "close", None)
        if callable(close):
            close()

    return app


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", required=True, type=int)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--token-env", required=True)
    parser.add_argument("--model-snapshot", required=True)
    parser.add_argument("--model-repository", required=True)
    parser.add_argument("--model-revision", required=True)
    parser.add_argument("--model-subfolder", default="update")
    parser.add_argument("--backend", default="pytorch", choices=["auto", "pytorch", "onnx"])
    parser.add_argument("--tokenizer-snapshot", required=True)
    parser.add_argument("--tokenizer-revision", required=True)
    parser.add_argument("--codec-snapshot", required=True)
    parser.add_argument("--codec-revision", required=True)
    parser.add_argument("--max-batch", type=int, default=16)
    parser.add_argument("--max-wait", type=float, default=0.03)
    return parser.parse_args()


def main() -> int:
    global TTS, SERVER, SESSION_TOKEN, SESSION_ID, IDENTITY, DEFAULT_VOICE
    args = parse_args()
    if args.host != "127.0.0.1":
        raise ValueError("Managed VieNeu bridge is loopback-only")
    SESSION_TOKEN = os.environ.get(args.token_env, "")
    if len(SESSION_TOKEN) < 24:
        raise ValueError("Managed session token is missing or too short")
    SESSION_ID = args.session_id
    model_snapshot = Path(args.model_snapshot).resolve()
    tokenizer_snapshot = Path(args.tokenizer_snapshot).resolve()
    codec_snapshot = Path(args.codec_snapshot).resolve()
    for name, path in (
        ("model", model_snapshot),
        ("tokenizer", tokenizer_snapshot),
        ("codec", codec_snapshot),
    ):
        if not path.is_dir():
            raise FileNotFoundError(f"Managed {name} snapshot is missing")

    from vieneu import Vieneu

    TTS = Vieneu(
        mode="v3turbo",
        backbone_repo=str(model_snapshot),
        model_subfolder=args.model_subfolder,
        moss_tokenizer=str(tokenizer_snapshot),
        backend=args.backend,
        max_batch_size=max(1, args.max_batch),
    )
    voices_available = voice_list()
    if not voices_available:
        raise RuntimeError("VieNeu runtime loaded without preset voices")
    DEFAULT_VOICE = voices_available[0]["id"]
    try:
        runtime_version = version("vieneu")
    except PackageNotFoundError:
        runtime_version = "unknown"
    IDENTITY = {
        "service_id": SERVICE_ID,
        "protocol_version": PROTOCOL_VERSION,
        "bridge_version": BRIDGE_VERSION,
        "session_id": SESSION_ID,
        "runtime_version": runtime_version,
        "model_repository": args.model_repository,
        "model_revision": args.model_revision,
        "model_subfolder": args.model_subfolder,
        "backend": str(getattr(TTS, "backend", args.backend)),
        "sample_rate": int(TTS.sample_rate),
        "tokenizer_revision": args.tokenizer_revision,
        "codec_revision": args.codec_revision,
    }
    log.info(
        "runtime ready backend=%s revision=%s sample_rate=%s voices=%d",
        IDENTITY["backend"],
        str(args.model_revision)[:12],
        IDENTITY["sample_rate"],
        len(voices_available),
    )
    config = uvicorn.Config(
        build_app(args.max_batch, args.max_wait),
        host="127.0.0.1",
        port=args.port,
        log_level="warning",
        access_log=False,
    )
    SERVER = uvicorn.Server(config)
    SERVER.run()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception as exc:
        print(
            json.dumps(
                {"event": "fatal", "error": safe_error(exc)},
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            file=sys.stderr,
            flush=True,
        )
        raise SystemExit(2)

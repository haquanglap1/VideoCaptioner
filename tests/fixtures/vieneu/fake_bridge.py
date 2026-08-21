#!/usr/bin/env python3
"""Tiny authenticated VieNeu protocol fixture; no external dependency."""

from __future__ import annotations

import argparse
import io
import json
import os
import struct
import subprocess
import sys
import threading
import time
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


def wav_bytes(*, bad: bool = False) -> bytes:
    if bad:
        return b"not-a-wave"
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(48_000)
        frames = [int(1200 * ((index % 24) / 24.0 - 0.5)) for index in range(12_000)]
        wav.writeframes(b"".join(struct.pack("<h", sample) for sample in frames))
    return buffer.getvalue()


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host")
    parser.add_argument("--port", type=int)
    parser.add_argument("--session-id")
    parser.add_argument("--token-env")
    parser.add_argument("--model-snapshot")
    parser.add_argument("--model-repository")
    parser.add_argument("--model-revision")
    parser.add_argument("--model-subfolder")
    parser.add_argument("--backend")
    parser.add_argument("--tokenizer-snapshot")
    parser.add_argument("--tokenizer-revision", default="")
    parser.add_argument("--codec-snapshot")
    parser.add_argument("--codec-revision", default="")
    parser.add_argument("--max-batch")
    parser.add_argument("--max-wait")
    parser.add_argument("--ready-delay", type=float, default=0.0)
    parser.add_argument("--wrong-service", action="store_true")
    parser.add_argument("--bad-wav", action="store_true")
    parser.add_argument("--empty-voices", action="store_true")
    parser.add_argument("--crash-once-marker")
    parser.add_argument("--spawn-child-marker")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    token = os.environ.get(args.token_env, "")
    if args.crash_once_marker:
        marker = Path(args.crash_once_marker)
        if not marker.exists():
            marker.write_text("crashed", encoding="utf-8")
            return 17
    child = None
    if args.spawn_child_marker:
        child = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(120)"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        Path(args.spawn_child_marker).write_text(str(child.pid), encoding="utf-8")
    if args.ready_delay:
        time.sleep(args.ready_delay)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, _format, *_args):
            return

        def authorized(self) -> bool:
            if self.headers.get("Authorization", "") != f"Bearer {token}":
                self.send_json({"error": "unauthorized"}, 401)
                return False
            return True

        def send_json(self, payload, status=200):
            data = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if not self.authorized():
                return
            route = self.path.removeprefix("/v1").removeprefix("/api/v1")
            if route == "/health":
                self.send_json(
                    {
                        "service_id": "wrong-service" if args.wrong_service else "videocaptioner-vieneu",
                        "protocol_version": "vieneu-runtime-protocol-v1",
                        "session_id": args.session_id,
                        "runtime_version": "fake-runtime-1",
                        "model_repository": args.model_repository,
                        "model_revision": args.model_revision,
                        "model_subfolder": args.model_subfolder,
                        "backend": args.backend,
                        "sample_rate": 48_000,
                        "tokenizer_revision": args.tokenizer_revision,
                        "codec_revision": args.codec_revision,
                        "ready": True,
                    }
                )
            elif route in {"/voices", "/audio/voices", "/models"}:
                voices = [] if args.empty_voices else [{"id": "fake-voice", "name": "Fake Voice"}]
                self.send_json({"object": "list", "voices": voices, "data": voices})
            else:
                self.send_json({"error": "not found"}, 404)

        def do_POST(self):
            if not self.authorized():
                return
            route = self.path.removeprefix("/v1").removeprefix("/api/v1")
            length = int(self.headers.get("Content-Length", "0") or 0)
            if length:
                self.rfile.read(length)
            if route == "/audio/speech":
                data = wav_bytes(bad=args.bad_wav)
                self.send_response(200)
                self.send_header("Content-Type", "audio/wav")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            elif route == "/shutdown":
                self.send_json({"status": "stopping"})
                threading.Thread(target=server.shutdown, daemon=True).start()
            else:
                self.send_json({"error": "not found"}, 404)

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    try:
        server.serve_forever(poll_interval=0.05)
    finally:
        server.server_close()
        # Deliberately leave child running; manager ownership cleanup must handle it.
        del child
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

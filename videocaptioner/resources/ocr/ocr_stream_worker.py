"""Offline CPU OCR worker for the source pilot's supervised, single-frame RPC.

Run with the existing isolated Python and an explicit bridge path. This script is not
installed into or substituted for the older measured pilot/portable runtime.
"""

from __future__ import annotations

# pyright: reportMissingImports=false
# Engine imports are verified in the pinned external runtime, never the Qt host.
import argparse
import hashlib
import importlib.metadata
import json
import socket
import sys
import time
import traceback
from pathlib import Path

PROTOCOL = "ocr-stream-v1"
MAX_FRAME_BYTES = 32 * 1024 * 1024


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def emit(payload):
    # -I ignores PYTHONIOENCODING; Windows pipe text encoding may otherwise be cp1252.
    sys.stdout.buffer.write(json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8") + b"\n")
    sys.stdout.buffer.flush()


class CpuEngine:
    def __init__(self, root, profile_sha256):
        self.started = time.perf_counter()
        self.network_attempts = 0
        self.request_id = 0
        self.counts = {"det": 0, "rec": 0, "cls": 0}

        def no_network(*_args, **_kwargs):
            self.network_attempts += 1
            raise RuntimeError("OCR network disabled")

        socket.socket.connect = no_network
        socket.socket.connect_ex = no_network
        socket.create_connection = no_network
        socket.getaddrinfo = no_network
        if digest(root / "profile.json") != profile_sha256:
            raise ValueError("Profile mismatch")
        profile = json.loads((root / "profile.json").read_text(encoding="utf-8"))
        for name, version in profile["packages"].items():
            if importlib.metadata.version(name) != version:
                raise ValueError("Package version mismatch")
        for model in profile["models"].values():
            path = root / "weights" / model["file"]
            if path.parent.resolve() != (root / "weights").resolve() or digest(path) != model["sha256"]:
                raise ValueError("Model hash mismatch")
        self.verify_s = time.perf_counter() - self.started
        imported = time.perf_counter()
        import psutil
        from rapidocr import EngineType, LangCls, LangDet, LangRec, ModelType, OCRVersion, RapidOCR
        from rapidocr.utils.download_file import DownloadFile

        DownloadFile.run = no_network
        self.psutil = psutil
        self.import_s = time.perf_counter() - imported
        params = dict(profile["params"])
        for section, model_type, version, language in (
            ("Det", ModelType.MOBILE, OCRVersion.PPOCRV5, LangDet.CH),
            ("Rec", ModelType.SERVER, OCRVersion.PPOCRV5, LangRec.CH),
            ("Cls", ModelType.MOBILE, OCRVersion.PPOCRV4, LangCls.CH),
        ):
            params.update({f"{section}.engine_type": EngineType.ONNXRUNTIME,
                           f"{section}.model_type": model_type, f"{section}.ocr_version": version,
                           f"{section}.lang_type": language,
                           f"{section}.model_path": str(root / "weights" / profile["models"][section.lower()]["file"])})
        loaded = time.perf_counter()
        self.engine = RapidOCR(params=params)
        self.load_s = time.perf_counter() - loaded
        dictionary = self.engine.text_rec.session.get_character_list()
        blob = json.dumps(dictionary, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if (len(dictionary) != profile["dictionary_count"]
                or hashlib.sha256(blob).hexdigest() != profile["dictionary_sha256"]):
            raise ValueError("Dictionary mismatch")
        self.profile_sha256 = profile_sha256
        self.dictionary_sha256 = profile["dictionary_sha256"]
        for name in self.counts:
            session = getattr(self.engine, "text_" + name).session.session
            if session.get_providers() != ["CPUExecutionProvider"]:
                raise ValueError("Expected CPU only")
            original = session.run

            def counted(*args, _name=name, _original=original, **kwargs):
                self.counts[_name] += 1
                emit({"status": "inference", "request_id": self.request_id,
                      "stage": _name, "inference_calls": dict(self.counts)})
                return _original(*args, **kwargs)

            session.run = counted

    def metrics(self):
        memory = self.psutil.Process().memory_info()
        return {"verify_s": self.verify_s, "import_s": self.import_s, "load_s": self.load_s,
                "inference_calls": dict(self.counts), "network_attempts": self.network_attempts,
                "rss_bytes": memory.rss, "peak_wset_bytes": getattr(memory, "peak_wset", None),
                "worker_wall_s": time.perf_counter() - self.started}

    def recognize(self, raw, width, height, request_id):
        import numpy as np

        self.request_id = request_id
        # RapidOCR's array contract is BGR. Decoder transport stays canonical RGB.
        bgr = np.frombuffer(raw, dtype=np.uint8).reshape(height, width, 3)[:, :, ::-1].copy()
        start = time.perf_counter()
        result = self.engine(bgr, use_cls=False, text_score=0.0)
        inference_s = time.perf_counter() - start
        texts = list(result.txts) if result.txts is not None else []
        scores = [float(v) for v in result.scores] if result.scores is not None else []
        boxes = result.boxes.tolist() if result.boxes is not None else []
        if len(texts) != len(scores) or len(texts) != len(boxes) or len(texts) > 32:
            raise ValueError("Invalid engine lines")
        if self.network_attempts or self.counts["cls"]:
            raise ValueError("Offline CPU policy violated")
        return {"lines": [{"text": text, "score": score, "box": box}
                          for text, score, box in zip(texts, scores, boxes)],
                "revision": self.profile_sha256,
                "inference_s": inference_s,
                "stage_s": [float(v) if v is not None else None for v in result.elapse_list]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--job-dir", type=Path, required=True)
    parser.add_argument("--profile-sha256", required=True)
    args = parser.parse_args()
    engine = CpuEngine(args.root, args.profile_sha256)
    emit({"status": "ready", "protocol": PROTOCOL, "profile_sha256": args.profile_sha256,
          "bridge_sha256": digest(__file__), "dictionary_sha256": engine.dictionary_sha256,
          "provider": "CPUExecutionProvider", "metrics": engine.metrics()})
    expected = 1
    while True:
        line = sys.stdin.buffer.readline(8193)
        if not line:
            return 0
        if len(line) > 8192 or not line.endswith(b"\n"):
            raise ValueError("Invalid request size")
        request = json.loads(line)
        if request.get("op") == "close":
            emit({"status": "closed", "metrics": engine.metrics()})
            return 0
        width, height, request_id = request.get("width"), request.get("height"), request.get("request_id")
        if (request.get("op") != "recognize" or type(request_id) is not int or request_id != expected
                or type(width) is not int or type(height) is not int or min(width, height) <= 0
                or width * height * 3 > MAX_FRAME_BYTES):
            raise ValueError("Invalid frame request")
        path = args.job_dir / "frame.rgb"
        if path.stat().st_size != width * height * 3:
            raise ValueError("Invalid frame size")
        raw = path.read_bytes()
        sha256 = hashlib.sha256(raw).hexdigest()
        if sha256 != request.get("crop_sha256"):
            raise ValueError("Frame hash mismatch")
        result = engine.recognize(raw, width, height, request_id)
        del raw
        emit({"status": "result", "request_id": request_id, "crop_sha256": sha256,
              "result": result, "metrics": engine.metrics()})
        expected += 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        emit({"status": "error", "error_type": type(error).__name__,
              "trace": [{"file": Path(frame.filename).name, "line": frame.lineno, "function": frame.name}
                        for frame in traceback.extract_tb(error.__traceback__)[-5:]]})
        raise SystemExit(2) from None

"""Optional single-line visual tracking companion for the pinned offline OCR worker.

The original recognition bridge stays byte-identical so old checkpoints can resume.
Model imports and inference remain in the isolated runtime, never the Qt process.
"""

from __future__ import annotations

# pyright: reportMissingImports=false
import argparse
import hashlib
import importlib.util
import json
import math
import sys
import traceback
from pathlib import Path

BASE_WORKER_SHA256 = "9203a0ce1e7175e215a1ba008fc1a14cd11bd836ea42c7a53a131ce20937bcc5"
FEATURE_NAME = b"p2o.pd_op.transpose.8.0"
MAX_FRAME_BYTES = 32 * 1024 * 1024


def _varint(data, offset):
    value = 0
    for shift in range(0, 70, 7):
        if offset >= len(data):
            raise ValueError("Truncated model field")
        byte = data[offset]
        offset += 1
        value |= (byte & 127) << shift
        if byte < 128:
            return value, offset
    raise ValueError("Invalid model field")


def _fields(data):
    offset = 0
    while offset < len(data):
        start = offset
        tag, offset = _varint(data, offset)
        number, wire = tag >> 3, tag & 7
        if not number:
            raise ValueError("Invalid model tag")
        if wire == 0:
            value, offset = _varint(data, offset)
        else:
            if wire == 2:
                size, offset = _varint(data, offset)
            elif wire in (1, 5):
                size = 8 if wire == 1 else 4
            else:
                raise ValueError("Unsupported model wire type")
            if offset + size > len(data):
                raise ValueError("Truncated model payload")
            value = data[offset:offset + size]
            offset += size
        yield number, wire, value, data[start:offset]


def _encode_varint(value):
    output = bytearray()
    while value > 127:
        output.append((value & 127) | 128)
        value >>= 7
    output.append(value)
    return bytes(output)


def _field(number, value):
    return _encode_varint(number * 8 + 2) + _encode_varint(len(value)) + value


def feature_model(model):
    """Expose the existing encoder output without modifying any weights or nodes.

    Wire fields follow https://github.com/onnx/onnx/blob/main/onnx/onnx.proto.
    Only the already SHA-verified PP-OCRv6 medium graph is supported.
    """
    graph = next(value for number, _, value, _ in _fields(model) if number == 7)
    info = next((value for number, _, value, _ in _fields(graph) if number == 13
                 and any(n == 1 and v == FEATURE_NAME for n, _, v, _ in _fields(value))), None)
    if info is None:
        raise ValueError("Unsupported recognition feature graph")
    graph += _field(12, info)
    return b"".join(_field(7, graph) if number == 7 else raw for number, _, _, raw in _fields(model))


def validate_boxes(boxes, width, height):
    if not isinstance(boxes, list) or len(boxes) > 32:
        raise ValueError("Invalid tracking boxes")
    for box in boxes:
        if (not isinstance(box, (list, tuple)) or len(box) != 4
                or any(not isinstance(p, (list, tuple)) or len(p) != 2 for p in box)
                or any(type(v) not in (int, float) or not math.isfinite(v) for p in box for v in p)
                or any(not 0 <= x <= width or not 0 <= y <= height for x, y in box)):
            raise ValueError("Invalid tracking box coordinates")


def foreground_ranges(boxes, width, height, anchor):
    crossing = [box for box in boxes if min(p[1] for p in box) <= anchor * height <= max(p[1] for p in box)]
    largest = max((max(p[1] for p in b) - min(p[1] for p in b) for b in crossing), default=0)
    return [(max(0, min(p[0] for p in b) - largest / 2), min(width, max(p[0] for p in b) + largest / 2))
            for b in crossing if max(p[1] for p in b) - min(p[1] for p in b) >= max(.4 * height, .75 * largest)]


class CharacterTracker:
    def __init__(self, root, engine):
        import cv2
        import numpy as np
        import onnxruntime as ort
        from PIL import Image

        self.cv2, self.np, self.Image, self.engine = cv2, np, Image, engine
        if (engine.stages.get("Rec.ocr_version") != "PP-OCRv6"
                or engine.stages.get("Rec.model_type") != "medium"):
            raise ValueError("Character tracking requires PP-OCRv6 medium")
        profile = json.loads((root / "profile.json").read_bytes())
        model = root / "weights" / profile["models"]["rec"]["file"]
        original = model.read_bytes()
        if hashlib.sha256(original).hexdigest() != profile["models"]["rec"]["sha256"]:
            raise ValueError("Tracking model hash mismatch")
        options = ort.SessionOptions()
        options.intra_op_num_threads = 4
        options.inter_op_num_threads = 1
        options.log_severity_level = 3
        self.session = ort.InferenceSession(feature_model(original), sess_options=options,
                                            providers=["CPUExecutionProvider"])
        self.previous = None
        self.geometry = None
        self.anchor = None
        self.batches = 0

    def observe(self, raw, width, height, anchor, known_boxes, request_id):
        np, cv2 = self.np, self.cv2
        if min(width, height) < 16 or math.ceil(width / height) > 128:
            raise ValueError("Invalid ROI geometry for character tracking")
        if type(anchor) not in (int, float) or not math.isfinite(anchor) or not 0 < anchor < 1:
            raise ValueError("Invalid tracking line position")
        if self.geometry is not None and ((width, height) != self.geometry or anchor != self.anchor):
            raise ValueError("Tracking geometry changed within a job")
        self.geometry, self.anchor = (width, height), anchor
        rgb = np.frombuffer(raw, dtype=np.uint8).reshape(height, width, 3)
        self.engine.request_id = request_id
        if known_boxes is None:
            try:
                result = self.engine.engine(rgb[:, :, ::-1].copy(), use_det=True, use_rec=False,
                                            use_cls=False, text_score=0.0)
                boxes = result.boxes.tolist() if result.boxes is not None else []
            finally:
                self.engine.engine.use_rec = True
        else:
            boxes = known_boxes
        validate_boxes(boxes, width, height)
        ranges = foreground_ranges(boxes, width, height, anchor)
        if not ranges:
            changed = self.previous is not None
            self.previous = None
            return {"present": False, "changed": changed, "uncertain": False, "quality": 0.0}

        gray = np.array(self.Image.fromarray(rgb).convert("L"))
        mode = int(np.bincount(gray.ravel(), minlength=256).argmax())
        columns = np.array([any(lo <= x <= hi for lo, hi in ranges) for x in range(width)])
        dark_ink = mode - float(np.median(gray[:, columns].min(axis=0))) if columns.any() else 64
        light_ink = float(np.median(gray[:, columns].max(axis=0))) - mode if columns.any() else 0
        if columns.any() and max(dark_ink, light_ink) < 4:
            # A single narrow glyph need not occupy half of its padded horizontal support.
            dark_ink = mode - float(gray[:, columns].min())
            light_ink = float(gray[:, columns].max()) - mode
        contrast = max(4, min(64, max(dark_ink, light_ink)))
        lower = mode if light_ink > dark_ink else mode - contrast
        normalized = np.uint8(np.clip((gray.astype("float32") - lower) * 255 / contrast, 0, 255))
        normalized = np.repeat(normalized[:, :, None], 3, axis=2)
        padded = cv2.copyMakeBorder(normalized, 0, 0, 2 * height, 2 * height, cv2.BORDER_REPLICATE)
        tensors = []
        for x in range(0, width, height):
            tile = cv2.resize(padded[:, x:x + 4 * height], (192, 48)).astype("float32") / 127.5 - 1
            tensors.append(tile.transpose(2, 0, 1))
        probabilities, features = self.session.run(
            ["fetch_name_0", FEATURE_NAME.decode()], {self.session.get_inputs()[0].name: np.stack(tensors)})
        self.batches += 1
        # The central six positions cover [x, x + height], including both ROI edges.
        vectors = features[:, 12:18, :].reshape(-1, features.shape[-1])
        probabilities = probabilities[:, 12:18, :].reshape(-1, probabilities.shape[-1])
        vectors = vectors / np.maximum(np.linalg.norm(vectors, axis=-1, keepdims=True), 1e-9)
        classes, scores = probabilities.argmax(axis=-1), probabilities.max(axis=-1)
        centers = [x + (j + .5) * height / 6 for x in range(0, width, height) for j in range(6)]
        valid = np.array([x < width and any(lo <= x <= hi for lo, hi in ranges) for x in centers])
        space = probabilities.shape[-1] - 1
        character = (classes != 0) & (classes != space)
        quality = float(scores[valid & character].mean()) if np.any(valid & character) else 0.0
        quality *= contrast / 64  # Preserve fade evidence that contrast normalization deliberately removes.
        current = vectors, classes, scores, valid
        changed, uncertain = True, False
        if self.previous is not None:
            previous, old_classes, old_scores, old_valid = self.previous
            distance = 1 - np.sum(previous * vectors, axis=-1)
            possible = (distance > .45) & (valid | old_valid)
            reliable = ((scores >= .9) & (old_scores >= .9)
                        & (character | ((old_classes != 0) & (old_classes != space))))
            changed = bool(np.any(possible & reliable))
            # Uncertain visual changes are retained as timing uncertainty, never as approval.
            uncertain = bool(np.any(possible)) and not changed
        self.previous = current
        return {"present": True, "changed": changed, "uncertain": uncertain, "quality": quality}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--job-dir", type=Path, required=True)
    parser.add_argument("--profile-sha256", required=True)
    args = parser.parse_args()
    base_path = Path(__file__).with_name("ocr_stream_worker.py")
    if hashlib.sha256(base_path.read_bytes()).hexdigest() != BASE_WORKER_SHA256:
        raise ValueError("Recognition bridge dependency changed")
    spec = importlib.util.spec_from_file_location("ocr_base_worker", base_path)
    if spec is None or spec.loader is None:
        raise ValueError("Recognition bridge unavailable")
    base = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(base)
    engine = base.CpuEngine(args.root, args.profile_sha256)
    tracker = CharacterTracker(args.root, engine)

    def metrics():
        return {**engine.metrics(), "visual_batches": tracker.batches}

    base.emit({"status": "ready", "protocol": base.PROTOCOL, "profile_sha256": args.profile_sha256,
               "bridge_sha256": base.digest(__file__), "dictionary_sha256": engine.dictionary_sha256,
               "stages": engine.stages, "provider": "CPUExecutionProvider", "metrics": metrics()})
    expected = 1
    while True:
        line = sys.stdin.buffer.readline(8193)
        if not line:
            return 0
        if len(line) > 8192 or not line.endswith(b"\n"):
            raise ValueError("Invalid request size")
        request = json.loads(line)
        if request.get("op") == "close":
            base.emit({"status": "closed", "metrics": metrics()})
            return 0
        width, height, request_id = request.get("width"), request.get("height"), request.get("request_id")
        if (request.get("op") not in ("recognize", "track") or type(request_id) is not int or request_id != expected
                or type(width) is not int or type(height) is not int or min(width, height) <= 0
                or width * height * 3 > MAX_FRAME_BYTES):
            raise ValueError("Invalid frame request")
        path = args.job_dir / "frame.rgb"
        if path.stat().st_size != width * height * 3:
            raise ValueError("Invalid frame size")
        raw = path.read_bytes()
        crop_hash = hashlib.sha256(raw).hexdigest()
        if crop_hash != request.get("crop_sha256"):
            raise ValueError("Frame hash mismatch")
        if request["op"] == "track":
            result = tracker.observe(raw, width, height, request.get("anchor"), request.get("known_boxes"), request_id)
        else:
            result = engine.recognize(raw, width, height, request_id)
        del raw
        base.emit({"status": "result", "request_id": request_id, "crop_sha256": crop_hash,
                   "result": result, "metrics": metrics()})
        expected += 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        payload = {"status": "error", "error_type": type(error).__name__,
                   "trace": [{"file": Path(frame.filename).name, "line": frame.lineno, "function": frame.name}
                             for frame in traceback.extract_tb(error.__traceback__)[-5:]]}
        sys.stdout.buffer.write(json.dumps(payload).encode("utf-8") + b"\n")
        sys.stdout.buffer.flush()
        raise SystemExit(2) from None

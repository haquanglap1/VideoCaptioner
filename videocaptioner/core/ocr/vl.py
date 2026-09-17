"""Opt-in PaddleOCR-VL worker with CPU geometry, raw output and bounded ownership."""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, replace
from pathlib import Path

from PIL import Image

from videocaptioner.core.utils.gpu_lease import GPULease

from .codec import digest, read_json
from .consensus import validate_read
from .line_selection import LineSelectionPolicy
from .models import Check, EngineRead, GenerationRead, OcrError, ReadLine, RoiFrame
from .runtime import CpuOcrRuntime, OcrRuntimeMissing
from .vl_profile import VlProfile


def resources() -> Path:
    return Path(__file__).resolve().parents[2] / "resources/ocr"


@dataclass(frozen=True)
class VlInstallation:
    root: Path
    python: Path
    model: Path
    dependencies: Path
    profile: VlProfile


def file_hash(path: Path, check: Check = lambda: None) -> str:
    result = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            check()
            result.update(block)
    return result.hexdigest()


def inspect_vl(root: Path, check: Check = lambda: None) -> VlInstallation:
    """Read explicit local paths and verify pinned files without importing GPU packages."""
    check()
    try:
        manifest = read_json(root / "paddle-vl-runtime.json")
        if set(manifest) != {"schema", "python", "model", "dependencies"} or manifest["schema"] != "paddle-vl-runtime-v1":
            raise OcrError("Invalid PaddleOCR-VL runtime manifest")
        paths = [(root / manifest[key]).resolve() for key in ("python", "model", "dependencies")]
        python, model, dependencies = paths
        if not python.is_file() or not model.is_dir() or not dependencies.is_dir():
            raise OcrRuntimeMissing("PaddleOCR-VL candidate runtime is missing")
        recipe_path = resources() / "paddle-vl.json"
        recipe = read_json(recipe_path)
        for name, expected in recipe["model_files"].items():
            if Path(name).name != name or file_hash(model / name, check) != expected:
                raise OcrError("PaddleOCR-VL model or processor hash mismatch")
        profile = VlProfile(recipe["id"], file_hash(recipe_path), file_hash(resources() / "paddle_vl_worker.py"))
        return VlInstallation(root.resolve(), python, model, dependencies, profile)
    except (OSError, KeyError, TypeError):
        raise OcrRuntimeMissing("Select a verified local PaddleOCR-VL runtime manifest directory") from None


def crop_line(frame: RoiFrame, geometry: EngineRead, policy: LineSelectionPolicy):
    """One whole selected line with geometric margin; never pass CTC text to the VLM."""
    validate_read(geometry)
    indices = policy.select(geometry, frame.height)
    if not indices:
        return None
    boxes = [geometry.lines[i].box for i in indices]
    left, top = min(x for b in boxes for x, _ in b), min(y for b in boxes for _, y in b)
    right, bottom = max(x for b in boxes for x, _ in b), max(y for b in boxes for _, y in b)
    height = bottom - top
    bounds = (max(0, math.floor(left - height / 2)), max(0, math.floor(top - height / 4)),
              min(frame.width, math.ceil(right + height / 2)), min(frame.height, math.ceil(bottom + height / 4)))
    image = Image.frombytes("RGB", (frame.width, frame.height), frame.rgb).crop(bounds)
    return replace(frame, width=image.width, height=image.height, rgb=image.tobytes()), bounds


def parse_generation(payload: dict, crop: RoiFrame, bounds: tuple[int, int, int, int],
                     revision: str, geometry: tuple[ReadLine, ...]) -> EngineRead:
    try:
        validate_read(EngineRead(geometry, revision))
        if (payload["eos"] is not True or not isinstance(payload["text"], str)
                or not math.isfinite(payload["inference_s"]) or payload["inference_s"] < 0):
            raise ValueError
        evidence = GenerationRead(tuple(payload["token_ids"]), payload["raw_decode"],
                                  hashlib.sha256(crop.rgb).hexdigest(), bounds, geometry, payload["eos_token_id"])
        left, top, right, bottom = bounds
        lines = ((ReadLine(payload["text"], 0., ((left, top), (right, top), (right, bottom), (left, bottom))),)
                 if payload["text"] else ())
        raw = EngineRead(lines, revision, evidence)
        validate_read(raw)
        return raw
    except (KeyError, TypeError, ValueError, OverflowError):
        raise OcrError("Invalid or truncated PaddleOCR-VL generation; raw result was not cached") from None


class PaddleVlRuntime(CpuOcrRuntime):
    def __init__(self, installation: VlInstallation, jobs_root: Path, *, timeout: float = 30, max_requests=40,
                 check: Check = lambda: None):
        super().__init__(installation.root, resources() / "paddle_vl_worker.py", jobs_root,
                         digest(installation.profile), timeout=timeout, max_requests=max_requests, check=check)
        self.installation = installation
        self.lease = GPULease()

    def start(self):
        self.check()
        if self.state != "new":
            raise OcrError("PaddleOCR-VL worker is not a fresh session")
        current = inspect_vl(self.root, self.check)
        if current != self.installation:
            raise OcrError("PaddleOCR-VL runtime changed after inspection")
        self.bridge_sha256 = current.profile.worker_sha256
        self.lease.acquire()
        return self._launch([str(current.python), "-I", "-B", str(self.bridge)], "CUDAExecutionProvider")

    def generate(self, crop: RoiFrame, bounds, revision: str, geometry, check: Check) -> EngineRead:
        try:
            payload = self._request(crop, check, "recognize")
            result = parse_generation(payload, crop, bounds, revision, geometry)
            self.metrics.inference_s += payload["inference_s"]
            self.metrics.completed += 1
            return result
        except BaseException:
            self.close()
            raise

    def close(self):
        try:
            super().close()
        finally:
            self.lease.close()


class VlRecognizer:
    def __init__(self, cpu: CpuOcrRuntime, gpu: PaddleVlRuntime, policy: LineSelectionPolicy,
                 revision: str, max_requests: int):
        self.cpu, self.gpu, self.policy = cpu, gpu, policy
        self.revision, self.max_requests = revision, max_requests

    def __call__(self, frame: RoiFrame, check: Check) -> EngineRead:
        if self.cpu.metrics.requests + self.gpu.metrics.requests >= self.max_requests:
            raise OcrError("OCR candidate recognition request budget exhausted")
        geometry = self.cpu(frame, check)
        selected = crop_line(frame, geometry, self.policy)
        if selected is None:
            return EngineRead((), self.revision)
        if self.cpu.metrics.requests + self.gpu.metrics.requests >= self.max_requests:
            raise OcrError("OCR candidate recognition request budget exhausted")
        crop, bounds = selected
        return self.gpu.generate(crop, bounds, self.revision, geometry.lines, check)

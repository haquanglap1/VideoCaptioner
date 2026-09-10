"""Bounded, cancellable source previews and exact candidate crop verification."""

from __future__ import annotations

import hashlib
import io
import os
import subprocess
import time
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

from PIL import Image

from videocaptioner.core.utils.subprocess_helper import _NO_WINDOW, child_environment

from .decoder import probe_video, stop_owned_process
from .document import OcrCandidate, OcrDocument
from .geometry import Roi
from .identity import VisualSourceIdentity
from .models import Check, OcrError, VideoInfo
from .source import video_snapshot


@dataclass(frozen=True)
class OcrPreview:
    png: bytes
    video: VideoInfo
    source_sha256: str


def _frame(source: Path, info: VideoInfo, roi: Roi, predicate: str, ffmpeg: str, check: Check) -> bytes:
    rect = roi.pixels(*info.geometry.display_size)
    size = rect.width * rect.height * 3
    if size > 32 * 1024 * 1024:
        raise OcrError("Vùng ảnh quá lớn để xem trước OCR.")
    filters = [f"select='{predicate}'", *info.geometry.filters(roi)]
    command = [ffmpeg, "-v", "error", "-nostdin", "-copyts", "-noautorotate", "-threads", "1",
               "-i", str(source), "-map", f"0:{info.stream_index}", "-an", "-sn", "-dn",
               "-vf", ",".join(filters), "-frames:v", "1", "-threads", "1", "-pix_fmt", "rgb24",
               "-f", "rawvideo", "pipe:1"]
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                               env=child_environment(), creationflags=_NO_WINDOW, start_new_session=os.name != "nt")
    deadline = time.monotonic() + 60
    try:
        while True:
            check()
            if time.monotonic() > deadline:
                raise OcrError("Xem trước OCR quá thời gian chờ.")
            try:
                raw, _ = process.communicate(timeout=.05)
                break
            except subprocess.TimeoutExpired:
                continue
        if process.returncode or len(raw) != size:
            raise OcrError("Không tìm được frame nguồn cho vị trí đã chọn.")
        return raw
    finally:
        stop_owned_process(process)
        if process.stdout:
            process.stdout.close()


def _png(raw: bytes, width: int, height: int) -> bytes:
    image = Image.frombytes("RGB", (width, height), raw)
    image.thumbnail((960, 540))
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def preview_video(source: Path, position_ms: int, jobs_root: Path, *, ffmpeg: str = "ffmpeg",
                  ffprobe: str = "ffprobe", check: Check = lambda: None) -> OcrPreview:
    if type(position_ms) is not int or position_ms < 0:
        raise OcrError("Vị trí xem trước không hợp lệ.")
    with video_snapshot(source, jobs_root, check) as snapshot:
        info = probe_video(snapshot.path, ffprobe, check)
        # Preview chooses the first frame at/after this point. It is not a timing measurement.
        ticks = (info.timeline_origin + Fraction(position_ms, 1000)) / info.time_base
        predicate = f"gte(pts,{ticks.numerator}/{ticks.denominator})"
        raw = _frame(snapshot.path, info, Roi(0, 0, 1, 1), predicate, ffmpeg, check)
        return OcrPreview(_png(raw, *info.geometry.display_size), info, snapshot.sha256)


def preview_candidate(source: Path, document: OcrDocument, candidate: OcrCandidate, jobs_root: Path, *,
                      ffmpeg: str = "ffmpeg", ffprobe: str = "ffprobe", check: Check = lambda: None) -> OcrPreview:
    if not any(candidate in cue.candidates for cue in document.cues):
        raise OcrError("Crop không thuộc tài liệu OCR đang mở.")
    with video_snapshot(source, jobs_root, check) as snapshot:
        info = probe_video(snapshot.path, ffprobe, check)
        document.visual_source.require_match(VisualSourceIdentity.from_snapshot(snapshot, info, document.config.selection))
        raw = _frame(snapshot.path, info, document.config.roi, f"eq(pts,{candidate.frame_pts})", ffmpeg, check)
        if hashlib.sha256(raw).hexdigest() != candidate.crop_sha256:
            raise OcrError("Crop không khớp ảnh OCR đã đọc; không thể dùng làm bằng chứng duyệt.")
        rect = document.config.roi.pixels(*info.geometry.display_size)
        return OcrPreview(_png(raw, rect.width, rect.height), info, snapshot.sha256)

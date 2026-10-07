"""Contact-sheet OCR through the configured OpenAI-compatible vision model.

Local work is only FFmpeg decode and edge tracking; no ONNX model runs. Each request carries
one PNG sheet of numbered subtitle crops and returns one text per row. Nothing but the crops,
the row count and the language hint leaves the machine; credentials never reach documents.
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import time
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Callable, Sequence

from PIL import Image, ImageDraw, ImageFont

from videocaptioner.core.llm.client import LLMCredentials
from videocaptioner.core.llm.owned_request import OwnedLLMRequest
from videocaptioner.core.llm.request_policy import validate_request_timeout

from .cache import DEFAULT_CACHE_MIB, cache_directory
from .codec import _unique, digest
from .consensus import validate_read
from .document import OcrConfig, OcrDocument
from .geometry import Roi
from .models import Check, EngineRead, OcrError, ReadLine, RoiFrame, Selection
from .resume import validate_resume
from .service import jobs_directory, scan_video
from .tracking import text_bounds
from .vision_profile import MAX_ROWS, PROFILE_ID, VisionProfile

PROMPT = """You are an exact OCR transcriber for burned-in video subtitles.
The user message contains one image: a contact sheet of numbered rows. Each row is one cropped
frame of the subtitle area of a video; the number in the left margin is the row index, starting at 1.
Return only a JSON object: {"rows":[{"index":1,"text":"..."}, ...]} with exactly one entry per row,
in ascending index order. No Markdown fences, comments or extra fields.
Rules for "text":
- Copy exactly the characters of the subtitle shown in that row. Keep the script as displayed (never
  convert between simplified and traditional Chinese), keep the original punctuation (full-width or
  half-width), digits and spacing.
- If the row shows two subtitle lines stacked, join them with "\\n" in reading order.
- Ignore watermarks, logos, channel names, timestamps, interface text and background text that is not
  the subtitle.
- Use "" when the row contains no readable subtitle text.
- Never translate, correct spelling or grammar, complete sentences or guess characters you cannot
  read; drop an unreadable character instead of inventing one."""
PROMPT_SHA256 = hashlib.sha256(PROMPT.encode("utf-8")).hexdigest()
SHEET_VERSION = "vision-sheet-png-v1"
DEFAULT_ROWS, DEFAULT_WIDTH = 16, 1024
GUTTER, SEPARATOR, MAX_SHEET_HEIGHT = 72, 6, 3600
MIN_REGION_MS, MERGE_GAP_MS = 100, 150
# Reasoning models spend completion tokens on hidden reasoning before the JSON; leave headroom.
COMPLETION_BASE, COMPLETION_PER_ROW, COMPLETION_MAX = 3000, 120, 12000
MAX_UPSCALE = 3.0
TRACKING = "text-strokes-v1"
MAX_TEXT_CHARS = 1024


def vision_profile(model: str, rows: int = DEFAULT_ROWS, width: int = DEFAULT_WIDTH, crops: int = 1) -> VisionProfile:
    return VisionProfile(PROFILE_ID, model.strip() if isinstance(model, str) else model, rows, width, crops,
                         PROMPT_SHA256)


def vision_config(roi: Roi, selection: Selection, profile: VisionProfile, language: str = "zh",
                  tracking: str = TRACKING) -> OcrConfig:
    """Identity without any local runtime: the prompt/sheet recipe and the model pin every read."""
    if tracking not in ("edge-tiles-ocr2-v1", "text-strokes-v1"):
        raise OcrError("Vision OCR tracks subtitles by glyph strokes or edge tiles")
    return OcrConfig(roi, selection, digest(profile), digest([SHEET_VERSION, PROMPT_SHA256]), language,
                     tracking_policy=tracking, vision=profile)  # type: ignore[arg-type]


def focus_crop(frame: RoiFrame) -> tuple[RoiFrame, tuple[int, int, int, int]]:
    """Crop to the glyph strokes so the sheet shows large text; the whole ROI when none are found."""
    bounds = text_bounds(frame)
    if bounds is None or bounds == (0, 0, frame.width, frame.height):
        return frame, (0, 0, frame.width, frame.height)
    image = Image.frombytes("RGB", (frame.width, frame.height), frame.rgb).crop(bounds)
    return replace(frame, width=image.width, height=image.height, rgb=image.tobytes()), bounds


@dataclass(frozen=True)
class VisionSettings:
    credentials: LLMCredentials = field(repr=False)
    profile: VisionProfile
    timeout: int = 120
    max_requests: int = 400
    sheets_dir: Path | None = None  # Diagnostics: PNG sheets and replies, never credentials or paths.

    def __post_init__(self):
        validate_request_timeout(self.timeout)
        if not self.credentials.is_complete:
            raise OcrError("Cấu hình dịch vụ LLM, model và API key trong Cài đặt trước khi đọc phụ đề bằng AI.")
        if type(self.max_requests) is not int or not 1 <= self.max_requests <= 100000:
            raise OcrError("Vision OCR request budget must be 1..100000")


@dataclass
class VisionMetrics:
    requests: int = 0
    completed: int = 0
    rows: int = 0
    retries: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    sheet_bytes: int = 0
    empty_reads: int = 0


def _label_font(size: int):
    try:
        return ImageFont.load_default(size=size)
    except (OSError, TypeError, ValueError):
        return ImageFont.load_default()


def _scaled(frame: RoiFrame, width: int) -> tuple[int, int]:
    scale = min(width / frame.width, MAX_UPSCALE)
    return max(1, round(frame.width * scale)), max(1, round(frame.height * scale))


def render_sheet(frames: Sequence[RoiFrame], width: int) -> tuple[bytes, tuple[tuple[int, int, int, int], ...]]:
    """Stack crops vertically with a numbered white gutter; returns PNG bytes and row bounds."""
    if not 1 <= len(frames) <= MAX_ROWS:
        raise OcrError("Vision OCR sheets hold 1..40 rows")
    sizes = [_scaled(frame, width) for frame in frames]
    height = sum(h for _, h in sizes) + SEPARATOR * (len(frames) + 1)
    sheet = Image.new("RGB", (GUTTER + width + SEPARATOR, height), (128, 128, 128))
    draw = ImageDraw.Draw(sheet)
    bounds = []
    top = SEPARATOR
    for index, (frame, (w, h)) in enumerate(zip(frames, sizes), 1):
        image = Image.frombytes("RGB", (frame.width, frame.height), frame.rgb)
        if (w, h) != (frame.width, frame.height):
            image = image.resize((w, h), Image.Resampling.LANCZOS)
        draw.rectangle((0, top, GUTTER - 1, top + h - 1), fill=(255, 255, 255))
        font = _label_font(max(18, min(40, round(h * 0.6))))
        label = str(index)
        box = draw.textbbox((0, 0), label, font=font)
        draw.text(((GUTTER - (box[2] - box[0])) // 2 - box[0], top + (h - (box[3] - box[1])) // 2 - box[1]),
                  label, fill=(0, 0, 0), font=font)
        sheet.paste(image, (GUTTER, top))
        bounds.append((GUTTER, top, GUTTER + w, top + h))
        top += h + SEPARATOR
    buffer = io.BytesIO()
    sheet.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue(), tuple(bounds)


def parse_rows(content: Any, count: int) -> tuple[str, ...]:
    """Strict reply contract: exactly one text per row, in order; nothing is repaired or inferred."""
    if not isinstance(content, str) or len(content) > 256 * 1024:
        raise OcrError("Vision OCR reply is missing or oversized")
    text = content.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        if len(lines) < 2 or not lines[-1].strip().startswith("```"):
            raise OcrError("Vision OCR reply is truncated")
        text = "\n".join(lines[1:-1]).strip()
    try:
        payload = json.loads(text, object_pairs_hook=_unique)
    except ValueError:
        raise OcrError("Vision OCR reply is not JSON") from None
    if not isinstance(payload, dict) or set(payload) != {"rows"} or not isinstance(payload["rows"], list):
        raise OcrError("Vision OCR reply must contain only rows")
    rows = payload["rows"]
    if len(rows) != count:
        raise OcrError("Vision OCR reply row count does not match the sheet")
    texts = []
    for position, row in enumerate(rows, 1):
        if (not isinstance(row, dict) or set(row) != {"index", "text"} or type(row["index"]) is not int
                or row["index"] != position or not isinstance(row["text"], str)
                or len(row["text"]) > MAX_TEXT_CHARS):
            raise OcrError("Vision OCR reply has an invalid row")
        value = row["text"].replace("\r\n", "\n").replace("\r", "\n")
        if any(ord(c) < 32 and c != "\n" for c in value):
            raise OcrError("Vision OCR reply contains control characters")
        texts.append("\n".join(line.strip() for line in value.split("\n") if line.strip()))
    return tuple(texts)


def _read(bounds: tuple[int, int, int, int], text: str, revision: str) -> EngineRead:
    left, top, right, bottom = (float(v) for v in bounds)
    box = ((left, top), (right, top), (right, bottom), (left, bottom))
    lines = tuple(ReadLine(line, 0., box) for line in text.split("\n") if line.strip())
    raw = EngineRead(lines, revision)
    validate_read(raw)
    return raw


def _token_count(usage: Any, name: str) -> int:
    value = getattr(usage, name, None)
    return value if type(value) is int and value >= 0 else 0


class VisionRecognizer:
    """One sheet per request with one explicit retry; the budget counts every attempt."""

    def __init__(self, settings: VisionSettings, revision: str, *, language: str = "zh",
                 notify: Callable[[str], None] = lambda _: None,
                 request: Callable[..., Any] | None = None):
        self.settings, self.revision, self.language, self.notify = settings, revision, language, notify
        self.rows_per_request = settings.profile.rows
        self.metrics = VisionMetrics()
        self.request = request
        self.sheets = 0

    def _groups(self, frames: Sequence[RoiFrame]) -> list[list[RoiFrame]]:
        groups: list[list[RoiFrame]] = []
        height = 0
        for frame in frames:
            _, h = _scaled(frame, self.settings.profile.width)
            if not groups or len(groups[-1]) >= self.rows_per_request or height + h + SEPARATOR > MAX_SHEET_HEIGHT:
                groups.append([])
                height = 0
            groups[-1].append(frame)
            height += h + SEPARATOR
        return groups

    def _send(self, png: bytes, count: int, check: Check) -> str:
        if self.metrics.requests >= self.settings.max_requests:
            raise OcrError("Vision OCR request budget exhausted; raise the limit or resume the checkpoint")
        self.metrics.requests += 1

        def cancelled():
            try:
                check()
                return False
            except Exception:
                return True

        send = self.request or OwnedLLMRequest(self.settings.credentials, self.settings.timeout, cancelled,
                                               log_content=False)
        data = "data:image/png;base64," + base64.b64encode(png).decode("ascii")
        response = send(
            messages=[{"role": "system", "content": PROMPT},
                      {"role": "user", "content": [
                          {"type": "text", "text": f"Rows: {count}. Subtitle language: {self.language}."},
                          {"type": "image_url", "image_url": {"url": data}}]}],
            model=self.settings.profile.model,
            max_completion_tokens=min(COMPLETION_MAX, COMPLETION_BASE + COMPLETION_PER_ROW * count),
        )
        check()
        usage = getattr(response, "usage", None)
        self.metrics.prompt_tokens += _token_count(usage, "prompt_tokens")
        self.metrics.completion_tokens += _token_count(usage, "completion_tokens")
        try:
            choice = response.choices[0]
            content = choice.message.content
        except (AttributeError, IndexError, TypeError):
            raise OcrError("Vision OCR reply is missing") from None
        if getattr(choice, "finish_reason", "stop") not in (None, "stop"):
            reasoning = getattr(getattr(usage, "completion_tokens_details", None), "reasoning_tokens", None)
            if not (isinstance(content, str) and content.strip()) or reasoning:
                raise OcrError("Model dùng hết hạn mức token cho suy luận ẩn mà chưa trả chữ; chọn model không "
                               "suy luận cho OCR hoặc giảm Số crop mỗi lượt gửi AI")
            raise OcrError("Vision OCR reply was cut off")
        return content

    def _record(self, png: bytes, frames: Sequence[RoiFrame], reply: str | None, error: str) -> None:
        directory = self.settings.sheets_dir
        if directory is None:
            return
        self.sheets += 1
        directory.mkdir(parents=True, exist_ok=True)
        (directory / f"sheet-{self.sheets:04d}.png").write_bytes(png)
        record = {"schema": "ocr-vision-sheet-v1", "model": self.settings.profile.model, "rows": len(frames),
                  "pts": [frame.pts for frame in frames], "reply": reply, "error": error}
        (directory / f"sheet-{self.sheets:04d}.json").write_text(
            json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def _sheet(self, frames: Sequence[RoiFrame], check: Check) -> list[EngineRead]:
        focused = [focus_crop(frame) for frame in frames]
        png, _ = render_sheet([crop for crop, _ in focused], self.settings.profile.width)
        self.metrics.sheet_bytes += len(png)
        self.notify(f"Đang gửi tờ ảnh {len(frames)} dòng tới {self.settings.profile.model}…")
        reply, failure = None, ""
        for attempt in range(2):
            check()
            try:
                reply = self._send(png, len(frames), check)
                texts = parse_rows(reply, len(frames))
                break
            except OcrError as exc:
                failure = str(exc)
            except Exception as exc:
                check()
                # Provider/SDK errors can carry private HTTP bodies; keep only the class name.
                failure = f"Vision OCR request failed ({type(exc).__name__})"
            if attempt == 0:
                self.metrics.retries += 1
        else:
            self._record(png, frames, reply, failure)
            raise OcrError(failure + "; checkpoint giữ các câu đã đọc, có thể tiếp tục quét sau.")
        self._record(png, frames, reply, "")
        self.metrics.completed += 1
        self.metrics.rows += len(frames)
        reads = []
        for (_crop, bounds), text in zip(focused, texts):
            if not text:
                self.metrics.empty_reads += 1
            reads.append(_read(bounds, text, self.revision))
        return reads

    def recognize_many(self, frames: Sequence[RoiFrame], check: Check) -> list[EngineRead]:
        reads: list[EngineRead] = []
        for group in self._groups(frames):
            reads.extend(self._sheet(group, check))
        return reads

    def __call__(self, frame: RoiFrame, check: Check) -> EngineRead:
        return self.recognize_many([frame], check)[0]


def run_vision_ocr(source: Path, config: OcrConfig, settings: VisionSettings, *,
                   ffmpeg: str = "ffmpeg", ffprobe: str = "ffprobe", check: Check = lambda: None,
                   checkpoint: Callable[[OcrDocument], None] = lambda _: None,
                   progress: Callable[[int, str], None] = lambda *_: None,
                   expected_source_sha256: str = "", cache_mib: int = DEFAULT_CACHE_MIB,
                   resume_document: OcrDocument | None = None) -> OcrDocument:
    if config.vision is None or config.vision != settings.profile:
        raise OcrError("Vision OCR settings do not match the saved configuration (model, rows, width or crops)")
    if resume_document is not None:
        validate_resume(resume_document, config)
    begun = time.monotonic()
    recognizer = VisionRecognizer(settings, config.read_revision, language=config.language,
                                  notify=lambda message: progress(0, message))
    latest: OcrDocument | None = None

    def capture(document: OcrDocument) -> None:
        nonlocal latest
        latest = document

    try:
        scan_video(source, config, recognizer, jobs_root=jobs_directory(), ffmpeg=ffmpeg, ffprobe=ffprobe,
                   check=check, checkpoint=capture, progress=progress,
                   expected_source_sha256=expected_source_sha256,
                   cache_root=cache_directory() if cache_mib else None, cache_mib=cache_mib,
                   resume_document=resume_document, candidate_limit=config.vision.crops, drop_empty=True,
                   min_region_ms=MIN_REGION_MS)
    finally:
        if latest is not None:
            metrics = recognizer.metrics
            latest = replace(latest, metrics=replace(
                latest.metrics, job_wall_s=time.monotonic() - begun,
                worker_requests=metrics.requests, worker_responses=metrics.completed,
                vision_requests=metrics.requests, vision_rows=metrics.rows, vision_retries=metrics.retries,
                vision_prompt_tokens=metrics.prompt_tokens, vision_completion_tokens=metrics.completion_tokens,
                vision_sheet_bytes=metrics.sheet_bytes))
            checkpoint(latest)
    assert latest is not None
    return latest

"""Completed video receipts, checked before acquiring a TTS runtime or rendering."""

import json
import os
import re
import tempfile
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from videocaptioner.core.asr.asr_data import ASRData
from videocaptioner.core.subtitle.reuse import file_digest
from videocaptioner.core.translate.dialogue import DialogueDocument, fingerprint
from videocaptioner.core.utils.video_resolution import output_dimensions
from videocaptioner.core.utils.video_utils import get_video_info

SCHEMA = "completed-video-v1"


@dataclass(frozen=True)
class CompletedVideo:
    output: str
    captions: str = ""
    origin: str = "receipt"


def video_identity(video: str, subtitle: str, config, display: str | None = None, check=lambda: None) -> str:
    """Exclude operational settings and secrets, retaining every output option."""
    ignored = {"api_key", "rewrite_api_key", "rewrite_api_base", "rewrite_model", "rewrite_timeout",
               "report_path", "tts_concurrency", "cache_enabled", "reuse_completed", "enabled",
               "use_cache", "timeout", "batch_size", "batch_max_chars", "managed_tts_identity"}

    def normalize(value) -> Any:
        if isinstance(value, Enum):
            return value.value
        if isinstance(value, dict):
            return {key: normalize(item) for key, item in value.items() if key not in ignored}
        if isinstance(value, (list, tuple)):
            return [normalize(item) for item in value]
        return value

    options = normalize(asdict(config))
    reference = options.get("omnivoice", {}).get("reference_audio", "")
    if reference:
        options["omnivoice"]["reference_audio"] = file_digest(Path(reference), check)
    elif options.get("tts_provider") == "OmniVoice Local":
        from videocaptioner.core.tts.omnivoice.voices import resolve_voice
        selected = resolve_voice((options.get("tts_config") or {}).get("voice") or "auto")
        if selected:
            options["voice_reference"] = fingerprint({"audio": selected.sha256, "text": selected.transcript,
                                                       "language": selected.language})
    return fingerprint({"schema": SCHEMA, "video": file_digest(Path(video), check),
                        "subtitle": file_digest(Path(subtitle), check),
                        "display": file_digest(Path(display), check) if display else "", "config": options})


def receipt_path(output: str, stage="dubbing") -> Path:
    return Path(output).with_suffix(f".{stage}-completed.json")


def _local(root: Path, name: str) -> Path:
    path = root / name
    if not name or Path(name).is_absolute() or not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("Invalid completed video location")
    return path


def load_video(receipt: Path, identity: str, check=lambda: None, *, root: Path | None = None) -> CompletedVideo | None:
    try:
        if receipt.stat().st_size > 65536:
            return None
        data = json.loads(receipt.read_text(encoding="utf-8"))
        if data["schema"] != SCHEMA or data["identity"] != identity:
            return None
        output = _local(root or receipt.parent, data["output"])
        if output.stat().st_size == 0 or file_digest(output, check) != data["output_sha256"]:
            return None
        captions = _local(root or receipt.parent, data["captions"]) if data["captions"] else None
        if captions and file_digest(captions, check) != data["captions_sha256"]:
            return None
        check()
        return CompletedVideo(str(output), str(captions) if captions else "")
    except (OSError, ValueError, TypeError, KeyError):
        return None


def save_video(receipt: Path, identity: str, result: CompletedVideo, check=lambda: None, *, root: Path | None = None):
    output = Path(result.output)
    if not output.is_file() or output.stat().st_size == 0:
        return
    captions = Path(result.captions) if result.captions else None
    body = {"schema": SCHEMA, "identity": identity, "origin": result.origin,
            "output": output.relative_to(root or receipt.parent).as_posix(), "output_sha256": file_digest(output, check),
            "captions": captions.relative_to(root or receipt.parent).as_posix() if captions else "",
            "captions_sha256": file_digest(captions, check) if captions else ""}
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=receipt.parent, suffix=".tmp", delete=False) as f:
        staged = Path(f.name)
        json.dump(body, f, ensure_ascii=False)
    try:
        check()
        os.replace(staged, receipt)
    finally:
        staged.unlink(missing_ok=True)


def load_legacy_video(video: str, subtitle: str, output: str, config, check=lambda: None) -> CompletedVideo | None:
    """Recognize old app exports by source ID/name, playback text and media shape.

    Old files have no historical voice/mix fingerprint. This one-time adoption
    cannot prove those settings; new receipts bind the current selection.
    """
    if receipt_path(output).exists() or not subtitle.endswith(".json"):
        return None
    source = Path(video)
    match = re.search(r"\[(BV[0-9A-Za-z]+)\]", source.stem)
    prefix = re.escape(match.group(0) if match else source.stem)
    pattern = re.compile((r".*" if match else "") + prefix + r"_dubbed(?: \(\d+\))?\.mp4$")
    try:
        dialogue = DialogueDocument.load(subtitle)
        expected = "".join("".join(block.text.split()) for block in dialogue.blocks)
        if not expected:
            return None
        source_info = None
        for candidate in sorted(Path(output).parent.glob("*.mp4"), key=lambda p: p.stat().st_mtime_ns, reverse=True):
            check()
            captions = candidate.parent / (candidate.stem + "-subtitles") / "playback.srt"
            if (not pattern.fullmatch(candidate.name) or candidate.resolve() == source.resolve()
                    or not captions.is_file() or candidate.stat().st_mtime_ns < max(source.stat().st_mtime_ns, Path(subtitle).stat().st_mtime_ns)):
                continue
            data = ASRData.from_subtitle_file(str(captions))
            if "".join("".join(segment.text.split()) for segment in data) != expected:
                continue
            source_info = source_info or get_video_info(video)
            info = get_video_info(str(candidate))
            if not info or not source_info or not info.audio_codec or not info.width:
                continue
            if abs(info.duration_seconds - source_info.duration_seconds / config.video_speed) > 1:
                continue
            if (info.width, info.height) != output_dimensions(source_info.width, source_info.height, config.output_resolution):
                continue
            if any(s.end_time / 1000 > info.duration_seconds + .1 for s in data):
                continue
            return CompletedVideo(str(candidate), str(captions), "legacy-name-text-media")
    except (OSError, ValueError, KeyError, TypeError):
        return None
    return None

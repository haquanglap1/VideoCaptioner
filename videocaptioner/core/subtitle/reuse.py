"""Source-bound completed subtitles, independent of request concurrency and model."""

import hashlib
import json
import math
import os
import tempfile
from contextlib import nullcontext
from dataclasses import dataclass
from pathlib import Path

from videocaptioner.core.asr.asr_data import ASRData
from videocaptioner.core.entities import SubtitleConfig, SubtitleLayoutEnum
from videocaptioner.core.translate.dialogue import DialogueDocument, fingerprint

SCHEMA = "completed-subtitles-v1"


@dataclass(frozen=True)
class CompletedSubtitles:
    data: ASRData
    dialogue: DialogueDocument | None = None
    dialogue_path: Path | None = None
    origin: str = "checkpoint"
    identity: str = ""


def file_digest(path: Path, check=lambda: None) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            check()
            digest.update(chunk)
    check()
    return digest.hexdigest()


def source_identity(source: ASRData, video_path: str | None, config: SubtitleConfig, check=lambda: None) -> str:
    video = Path(video_path) if video_path else None
    return fingerprint({"schema": SCHEMA, "input": source.to_document(),
                        "video": file_digest(video, check) if video and video.is_file() else "",
                        "language": config.target_language.value if config.target_language else "",
                        "dialogue": config.dialogue_translation})


def checkpoint_path(output_path: str) -> Path:
    return Path(output_path).with_suffix(".completed.json")


def _complete(data: ASRData) -> bool:
    return bool(data.segments) and all(
        isinstance(s.text, str) and s.text.strip() and isinstance(s.translated_text, str) and s.translated_text.strip()
        and math.isfinite(s.start_time) and math.isfinite(s.end_time) and 0 <= s.start_time < s.end_time
        for s in data.segments)


def _sibling(root: Path, name: str) -> Path:
    if not isinstance(name, str) or not name or Path(name).name != name or any(c in name for c in "/\\:"):
        raise ValueError("Invalid subtitle checkpoint filename")
    return root / name


def load_completed(output_path: str, identity: str, check=lambda: None) -> CompletedSubtitles | None:
    path = checkpoint_path(output_path)
    try:
        check()
        if not path.is_file() or path.stat().st_size > 32 * 1024 * 1024:
            return None
        saved = json.loads(path.read_text(encoding="utf-8-sig"))
        if saved["schema"] != SCHEMA or identity not in (saved["identity"], saved.get("processed_identity", "")):
            return None
        body = saved["result"]
        if fingerprint(body) != saved["result_sha256"] or body["data"].get("schema_version"):
            return None
        if Path(output_path).name not in saved["files"]:
            return None
        for name, digest in saved["files"].items():
            if file_digest(_sibling(path.parent, name), check) != digest:
                return None
        data = ASRData.from_json(body["data"])
        if not _complete(data):
            return None
        dialogue = DialogueDocument.from_dict(body["dialogue"]) if body["dialogue"] else None
        dialogue_path = _sibling(path.parent, saved["dialogue_file"]) if saved["dialogue_file"] else None
        check()
        return CompletedSubtitles(data, dialogue, dialogue_path, identity=saved["identity"])
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return None


def load_existing_dialogue(output_path: str, video_path: str | None, source: ASRData,
                           config: SubtitleConfig, check=lambda: None) -> CompletedSubtitles | None:
    """Import older app output pairs by name/language and unchanged-video timestamps.

    Old exports do not contain the raw ASR fingerprint. Only the app's exact
    display/dialogue pair is eligible; arbitrary SRT files are never guessed.
    """
    output = Path(output_path)
    video = Path(video_path) if video_path else None
    if (not config.dialogue_translation or not config.target_language or not source.segments
            or source.has_metadata or source.events or source.conversation_context.enabled
            or source.audio_identity or source.visual_source or source.pending_diarization
            or not video or not video.is_file() or not output.is_file() or checkpoint_path(output_path).exists()):
        return None
    video_stat = video.stat()
    paths = [output.with_suffix(".dialogue.json"), *(p for p in output.parent.iterdir()
              if p.name.startswith(output.stem + ".dialogue-") and p.suffix == ".json")]
    for path in sorted((p for p in paths if p.is_file()), key=lambda p: p.stat().st_mtime_ns, reverse=True):
        check()
        try:
            # A replaced/edited input must not inherit a translation from the old video.
            if max(video_stat.st_mtime_ns, getattr(video_stat, "st_birthtime_ns", video_stat.st_ctime_ns)) > path.stat().st_mtime_ns:
                continue
            dialogue = DialogueDocument.load(path)
            if dialogue.target_language != config.target_language.value:
                continue
            data = dialogue.subtitle_data()
            if not _complete(data) or max(s.end_time for s in data) > max(s.end_time for s in source) + 2:
                continue
            text = output.read_text(encoding="utf-8-sig").replace("\r\n", "\n").strip()
            if not any(text == data.to_srt(layout=layout).strip() for layout in SubtitleLayoutEnum):
                continue
            return CompletedSubtitles(data, dialogue, path, "existing-dialogue")
        except (OSError, ValueError, TypeError, KeyError, AttributeError):
            continue
    return None


def save_completed(output_path: str, identity: str, result: CompletedSubtitles, check=lambda: None, *,
                   commit_lock=None, processed_identity: str = "") -> None:
    if not _complete(result.data):
        return
    output = Path(output_path)
    files = {output.name: file_digest(output, check)}
    dialogue_name = ""
    if result.dialogue_path:
        if result.dialogue_path.parent.resolve() != output.parent.resolve():
            raise ValueError("Dialogue checkpoint must be beside the display subtitle")
        dialogue_name = result.dialogue_path.name
        files[dialogue_name] = file_digest(result.dialogue_path, check)
    body = {"data": result.data.to_document(), "dialogue": result.dialogue.to_dict() if result.dialogue else None}
    payload = {"schema": SCHEMA, "identity": result.identity or identity, "processed_identity": processed_identity,
               "result": body, "result_sha256": fingerprint(body),
               "files": files, "dialogue_file": dialogue_name, "origin": result.origin}
    check()
    path = checkpoint_path(output_path)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, suffix=".json", encoding="utf-8", delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(payload, stream, ensure_ascii=False)
        with commit_lock if commit_lock is not None else nullcontext():
            check()
            os.replace(temporary, path)
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)

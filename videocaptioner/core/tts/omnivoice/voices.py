"""Named OmniVoice references; WAV bytes and transcript define the speaker identity."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
import time
import wave
from dataclasses import dataclass, field
from pathlib import Path
from uuid import uuid4

from videocaptioner.config import APPDATA_PATH
from videocaptioner.core.asr.alignment.audio import stop_process
from videocaptioner.core.utils.subprocess_helper import _NO_WINDOW, child_environment

from .config import resources

SCHEMA = "omnivoice-voices-v1"
ALIASES = {"female": "vi-female-1", "male": "vi-male-1"}
BUILTIN_IDS = ("vi-female-1", "vi-female-2", "vi-male-1", "vi-male-2")


def library_root() -> Path:
    return APPDATA_PATH / "voices" / "omnivoice"


@dataclass(frozen=True)
class VoiceProfile:
    voice_id: str
    name: str
    language: str
    audio_path: Path = field(repr=False)
    transcript: str = field(repr=False)
    sha256: str
    builtin: bool = False

    def verify(self) -> None:
        if (not self.audio_path.is_file() or self.audio_path.stat().st_size > 50 * 1024 * 1024
                or hashlib.sha256(self.audio_path.read_bytes()).hexdigest() != self.sha256):
            raise ValueError("Giọng mẫu bị thiếu hoặc đã thay đổi; hãy lưu lại giọng từ audio gốc.")


def _profile(data: dict, root: Path, *, builtin: bool = False) -> VoiceProfile:
    voice_id = str(data["voice_id"])
    if not re.fullmatch(r"[a-z0-9-]{1,80}", voice_id):
        raise ValueError("Invalid OmniVoice voice ID")
    filename = f"{voice_id}.wav" if builtin else "reference.wav"
    if (not str(data["name"]).strip() or not str(data["transcript"]).strip()
            or not re.fullmatch(r"[a-f0-9]{64}", str(data["sha256"]))):
        raise ValueError("Invalid OmniVoice voice metadata")
    return VoiceProfile(voice_id, str(data["name"]), str(data["language"]),
        root / filename, str(data["transcript"]), str(data["sha256"]), builtin)


def list_voices() -> list[VoiceProfile]:
    root = resources() / "voices"
    catalog = json.loads((root / "catalog.json").read_text(encoding="utf-8"))
    if catalog.get("schema") != SCHEMA:
        raise ValueError("Invalid OmniVoice voice catalog")
    profiles = [_profile(item, root, builtin=True) for item in catalog["voices"]]
    for path in sorted(library_root().glob("saved-*/profile.json")):
        try:
            item = json.loads(path.read_text(encoding="utf-8"))
            if item.get("schema") == SCHEMA and item.get("voice_id") == path.parent.name:
                profiles.append(_profile(item, path.parent))
        except (OSError, ValueError, KeyError, TypeError):
            # A broken private profile must not hide the bundled catalog.
            continue
    return profiles


def resolve_voice(voice_id: str) -> VoiceProfile | None:
    voice_id = ALIASES.get(voice_id, voice_id)
    if voice_id == "auto":
        return None
    for profile in list_voices():
        if profile.voice_id == voice_id:
            profile.verify()
            return profile
    raise ValueError("Không tìm thấy giọng OmniVoice đã chọn; chọn lại trong thư viện giọng.")


def save_voice(name: str, audio: str, transcript: str, language: str, *, check=lambda: None) -> VoiceProfile:
    """Copy and normalize a reference without cropping speech or changing its speed."""
    name, transcript, language = name.strip(), transcript.strip(), language.strip()
    source = Path(audio)
    if not name or len(name) > 60 or not transcript or len(transcript) > 4000 or not language:
        raise ValueError("Nhập tên giọng (tối đa 60 ký tự), lời mẫu và ngôn ngữ.")
    if not source.is_file() or source.stat().st_size > 50 * 1024 * 1024:
        raise ValueError("Chọn audio giọng mẫu nhỏ hơn 50 MiB.")
    check()
    root = library_root()
    root.mkdir(parents=True, exist_ok=True)
    voice_id = "saved-" + uuid4().hex
    with tempfile.TemporaryDirectory(prefix=".import-", dir=root) as temporary:
        staging = Path(temporary) / voice_id
        staging.mkdir()
        output = staging / "reference.wav"
        process = subprocess.Popen(["ffmpeg", "-nostdin", "-v", "error", "-i", str(source.resolve()),
            "-map", "0:a:0", "-vn", "-ac", "1", "-ar", "24000", "-c:a", "pcm_s16le", str(output)],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            env=child_environment(), creationflags=_NO_WINDOW)
        try:
            deadline = time.monotonic() + 60
            while process.poll() is None:
                check()
                if time.monotonic() >= deadline:
                    raise ValueError("Đọc audio giọng mẫu quá thời gian cho phép.")
                time.sleep(0.05)
            if process.returncode:
                raise ValueError("Không đọc được audio giọng mẫu.")
        finally:
            stop_process(process)
        with wave.open(str(output), "rb") as handle:
            duration = handle.getnframes() / handle.getframerate()
            if not 3 <= duration <= 10:
                raise ValueError("Giọng mẫu cần dài 3–10 giây; chọn đoạn một người nói, rõ tiếng.")
            if not any(handle.readframes(handle.getnframes())):
                raise ValueError("Audio giọng mẫu chỉ có khoảng lặng.")
        check()
        data = dict(schema=SCHEMA, voice_id=voice_id, name=name, language=language,
            transcript=transcript, sha256=hashlib.sha256(output.read_bytes()).hexdigest())
        (staging / "profile.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.rename(staging, root / voice_id)
    return _profile(data, root / voice_id)

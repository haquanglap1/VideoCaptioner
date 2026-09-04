"""Versioned, credential-free domain models for managed VieNeu Local."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

VIENEU_PROTOCOL_VERSION = "vieneu-runtime-protocol-v1"
VIENEU_STATE_SCHEMA = "vieneu-model-state-v1"
VIENEU_SERVICE_ID = "videocaptioner-vieneu"
DEFAULT_VIENEU_MODEL_REPO = "pnnbao-ump/VieNeu-TTS-v3-Turbo"
DEFAULT_MODEL_SUBFOLDER = "update"
DEFAULT_MOSS_REPO = "OpenMOSS-Team/MOSS-Audio-Tokenizer-Nano"
DEFAULT_SAMPLE_RATE = 48_000

_REVISION_RE = re.compile(r"^[0-9a-fA-F]{7,64}$")
_BEARER_RE = re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+\-/=]+")
_TOKEN_RE = re.compile(
    r"(?i)(session[-_ ]?token|api[-_ ]?key|authorization|token)\s*[:=]\s*[^\s,;]+"
)
_WINDOWS_PATH_RE = re.compile(r"(?i)\b[A-Z]:\\[^\r\n\t]+")
_URL_CREDENTIAL_RE = re.compile(r"(?i)(https?://)([^/@\s]+)@")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def validate_revision(value: str, *, allow_empty: bool = True) -> str:
    value = str(value or "").strip().lower()
    if not value and allow_empty:
        return ""
    if not _REVISION_RE.fullmatch(value):
        raise ValueError(f"Invalid immutable model revision: {value!r}")
    return value


def validate_relative_reference(value: str) -> str:
    value = str(value or "").replace("\\", "/").strip()
    if not value:
        return ""
    path = Path(value)
    # Check both flavours explicitly: on POSIX ``Path("C:/x")`` is neither
    # absolute nor has a drive, yet it is still not a relative reference.
    if (
        PurePosixPath(value).is_absolute()
        or PureWindowsPath(value).is_absolute()
        or PureWindowsPath(value).drive
    ):
        raise ValueError("VieNeu model state references must be relative")
    if any(part == ".." for part in path.parts):
        raise ValueError("VieNeu model state references cannot escape the model root")
    return path.as_posix()


def sanitize_error(error: object, *, limit: int = 800) -> str:
    """Return one actionable line without token, URL credential, or local path."""
    text = " ".join(str(error or "Unknown VieNeu error").split())
    text = _BEARER_RE.sub("Bearer ***", text)
    text = _TOKEN_RE.sub(lambda match: f"{match.group(1)}=***", text)
    text = _URL_CREDENTIAL_RE.sub(r"\1***@", text)
    text = _WINDOWS_PATH_RE.sub("<local-path>", text)
    return text[: max(80, int(limit))]


class VieNeuRuntimeState(str, Enum):
    STOPPED = "stopped"
    STARTING = "starting"
    READY = "ready"
    BUSY = "busy"
    UPDATING = "updating"
    STOPPING = "stopping"
    FAILED = "failed"


@dataclass(frozen=True)
class VieNeuHealth:
    service_id: str
    protocol_version: str
    session_id: str
    runtime_version: str
    model_repository: str
    model_revision: str
    backend: str
    sample_rate: int
    ready: bool
    model_subfolder: str = DEFAULT_MODEL_SUBFOLDER
    tokenizer_revision: str = ""
    codec_revision: str = ""

    @classmethod
    def from_payload(
        cls,
        payload: dict[str, Any],
        *,
        expected_session_id: str = "",
        expected_revision: str = "",
    ) -> "VieNeuHealth":
        health = cls(
            service_id=str(payload.get("service_id", "")),
            protocol_version=str(payload.get("protocol_version", "")),
            session_id=str(payload.get("session_id", "")),
            runtime_version=str(payload.get("runtime_version", "")),
            model_repository=str(payload.get("model_repository", "")),
            model_revision=validate_revision(str(payload.get("model_revision", ""))),
            backend=str(payload.get("backend", "")),
            sample_rate=int(payload.get("sample_rate", 0) or 0),
            ready=bool(payload.get("ready", False)),
            model_subfolder=str(payload.get("model_subfolder", DEFAULT_MODEL_SUBFOLDER)),
            tokenizer_revision=str(payload.get("tokenizer_revision", "")),
            codec_revision=str(payload.get("codec_revision", "")),
        )
        if health.service_id != VIENEU_SERVICE_ID:
            raise ValueError(f"Wrong VieNeu service identity: {health.service_id or '<missing>'}")
        if health.protocol_version != VIENEU_PROTOCOL_VERSION:
            raise ValueError(
                f"Unsupported VieNeu protocol: {health.protocol_version or '<missing>'}"
            )
        if expected_session_id and health.session_id != expected_session_id:
            raise ValueError("VieNeu session identity mismatch")
        if expected_revision and health.model_revision != validate_revision(expected_revision):
            raise ValueError("VieNeu model revision mismatch")
        if not health.runtime_version or not health.backend:
            raise ValueError("VieNeu health is missing runtime/backend identity")
        if health.sample_rate <= 0:
            raise ValueError("VieNeu health reported an invalid sample rate")
        if not health.ready:
            raise ValueError("VieNeu runtime is not ready")
        return health


@dataclass
class VieNeuModelState:
    repository_id: str = DEFAULT_VIENEU_MODEL_REPO
    channel: str = "stable"
    active_revision: str = ""
    previous_revision: str = ""
    candidate_revision: str = ""
    active_snapshot: str = ""
    previous_snapshot: str = ""
    candidate_snapshot: str = ""
    rejected_revisions: dict[str, dict[str, str]] = field(default_factory=dict)
    active_backend: str = "pytorch"
    model_subfolder: str = DEFAULT_MODEL_SUBFOLDER
    runtime_version: str = ""
    tokenizer_repository: str = DEFAULT_MOSS_REPO
    tokenizer_revision: str = ""
    tokenizer_snapshot: str = ""
    codec_repository: str = DEFAULT_MOSS_REPO
    codec_revision: str = ""
    codec_snapshot: str = ""
    last_check_at: str = ""
    last_download_at: str = ""
    last_validation_at: str = ""
    last_activation_at: str = ""
    last_error: str = ""
    schema_version: str = VIENEU_STATE_SCHEMA

    def validate(self) -> None:
        if self.schema_version != VIENEU_STATE_SCHEMA:
            raise ValueError(f"Unsupported VieNeu state schema: {self.schema_version}")
        if not self.repository_id or "/" not in self.repository_id:
            raise ValueError("VieNeu repository_id must be a Hugging Face repository ID")
        for revision in (
            self.active_revision,
            self.previous_revision,
            self.candidate_revision,
            self.tokenizer_revision,
            self.codec_revision,
        ):
            validate_revision(revision)
        for revision, entry in self.rejected_revisions.items():
            validate_revision(revision, allow_empty=False)
            if not isinstance(entry, dict):
                raise ValueError("Rejected VieNeu revisions must contain structured metadata")
        for reference in (
            self.active_snapshot,
            self.previous_snapshot,
            self.candidate_snapshot,
            self.tokenizer_snapshot,
            self.codec_snapshot,
        ):
            validate_relative_reference(reference)
        self.last_error = sanitize_error(self.last_error) if self.last_error else ""

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        data = asdict(self)
        data["last_error"] = sanitize_error(self.last_error) if self.last_error else ""
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "VieNeuModelState":
        state = cls(
            repository_id=str(data.get("repository_id", DEFAULT_VIENEU_MODEL_REPO)),
            channel=str(data.get("channel", "stable")),
            active_revision=str(data.get("active_revision", "")),
            previous_revision=str(data.get("previous_revision", "")),
            candidate_revision=str(data.get("candidate_revision", "")),
            active_snapshot=str(data.get("active_snapshot", "")),
            previous_snapshot=str(data.get("previous_snapshot", "")),
            candidate_snapshot=str(data.get("candidate_snapshot", "")),
            rejected_revisions=dict(data.get("rejected_revisions", {}) or {}),
            active_backend=str(data.get("active_backend", "pytorch")),
            model_subfolder=str(data.get("model_subfolder", DEFAULT_MODEL_SUBFOLDER)),
            runtime_version=str(data.get("runtime_version", "")),
            tokenizer_repository=str(data.get("tokenizer_repository", DEFAULT_MOSS_REPO)),
            tokenizer_revision=str(data.get("tokenizer_revision", "")),
            tokenizer_snapshot=str(data.get("tokenizer_snapshot", "")),
            codec_repository=str(data.get("codec_repository", DEFAULT_MOSS_REPO)),
            codec_revision=str(data.get("codec_revision", "")),
            codec_snapshot=str(data.get("codec_snapshot", "")),
            last_check_at=str(data.get("last_check_at", "")),
            last_download_at=str(data.get("last_download_at", "")),
            last_validation_at=str(data.get("last_validation_at", "")),
            last_activation_at=str(data.get("last_activation_at", "")),
            last_error=str(data.get("last_error", "")),
            schema_version=str(data.get("schema_version", "")),
        )
        state.validate()
        return state

    def reject(self, revision: str, reason: object) -> None:
        revision = validate_revision(revision, allow_empty=False)
        self.rejected_revisions[revision] = {
            "rejected_at": utc_now_iso(),
            "reason": sanitize_error(reason),
        }
        if self.candidate_revision == revision:
            self.candidate_revision = ""
            self.candidate_snapshot = ""
        self.last_error = sanitize_error(reason)

"""Resolved managed endpoint and immutable cache/report identity."""

from __future__ import annotations

from dataclasses import dataclass

from .models import VieNeuHealth


@dataclass(frozen=True)
class VieNeuClientIdentity:
    endpoint: str
    session_token: str
    session_id: str
    service_id: str
    protocol_version: str
    runtime_version: str
    model_repository: str
    model_revision: str
    backend: str
    sample_rate: int
    model_subfolder: str = "update"
    tokenizer_revision: str = ""
    codec_revision: str = ""

    @classmethod
    def from_health(
        cls,
        endpoint: str,
        session_token: str,
        health: VieNeuHealth,
    ) -> "VieNeuClientIdentity":
        return cls(
            endpoint=endpoint.rstrip("/") + "/",
            session_token=session_token,
            session_id=health.session_id,
            service_id=health.service_id,
            protocol_version=health.protocol_version,
            runtime_version=health.runtime_version,
            model_repository=health.model_repository,
            model_revision=health.model_revision,
            backend=health.backend,
            sample_rate=health.sample_rate,
            model_subfolder=health.model_subfolder,
            tokenizer_revision=health.tokenizer_revision,
            codec_revision=health.codec_revision,
        )

    def cache_identity(self) -> dict[str, str | int]:
        """Credential-free identity that changes for runtime/model/backend updates."""
        return {
            "service_id": self.service_id,
            "protocol_version": self.protocol_version,
            "runtime_version": self.runtime_version,
            "model_repository": self.model_repository,
            "model_revision": self.model_revision,
            "model_subfolder": self.model_subfolder,
            "backend": self.backend,
            "sample_rate": self.sample_rate,
            "tokenizer_revision": self.tokenizer_revision,
            "codec_revision": self.codec_revision,
        }

    def report_identity(self) -> dict[str, str | int]:
        return self.cache_identity()

"""Portable, credential-free snapshot of the engine recipe used for a document."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from videocaptioner.resources.ocr.ocr_stream_worker import (
    LEGACY_STAGES,
    STAGE_FIELDS,
    stage_parameters,
    validate_stage,
)

from .codec import decode, encode, sha256
from .models import OcrError

Parameter = bool | int | float | str | tuple[float, ...]


@dataclass(frozen=True)
class OcrStageProfile:
    stage: str
    engine_type: str
    ocr_version: str
    model_type: str
    lang_type: str
    model_sha256: str
    dictionary_sha256: str | None
    dictionary_count: int | None


@dataclass(frozen=True)
class OcrProfileSnapshot:
    id: str
    packages: tuple[tuple[str, str], ...]
    model_hashes: tuple[tuple[str, str], ...]
    dictionary_sha256: str
    dictionary_count: int
    parameters: tuple[tuple[str, Parameter], ...]
    preprocessing: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        sha256(self.dictionary_sha256)
        if not self.id or self.dictionary_count <= 0:
            raise OcrError("Invalid OCR profile snapshot")
        if not self.packages or {k for k, _ in self.model_hashes} != {"det", "rec", "cls"}:
            raise OcrError("Missing OCR engine pins")
        for _, value in self.model_hashes:
            sha256(value)
        for values in (self.packages, self.model_hashes, self.parameters, self.preprocessing):
            if len(values) != len({k for k, _ in values}):
                raise OcrError("Duplicate OCR profile fields")
        # Store new stage pins in the existing parameter snapshot so old documents
        # retain their exact serialization, config digest and stable cue IDs.
        params = dict(self.parameters)
        keys = {f"{stage.title()}.{key}" for stage in LEGACY_STAGES for key in STAGE_FIELDS}
        if keys.intersection(params):
            if not keys.issubset(params):
                raise OcrError("Missing OCR stage metadata")
            try:
                for stage in LEGACY_STAGES:
                    validate_stage(stage, {key: params[f"{stage.title()}.{key}"] for key in STAGE_FIELDS})
            except (ValueError, TypeError):
                raise OcrError("Invalid OCR stage metadata") from None

    @property
    def stages(self) -> tuple[OcrStageProfile, ...]:
        params, hashes = dict(self.parameters), dict(self.model_hashes)
        return tuple(OcrStageProfile(stage, *(str(params.get(f"{stage.title()}.{key}", default))
                     for key, default in zip(STAGE_FIELDS, ("onnxruntime", *legacy))), hashes[stage],
                     self.dictionary_sha256 if stage == "rec" else None,
                     self.dictionary_count if stage == "rec" else None)
                     for stage, legacy in LEGACY_STAGES.items())

    @property
    def stage_parameters(self) -> dict[str, str]:
        return {f"{stage.stage.title()}.{key}": getattr(stage, key)
                for stage in self.stages for key in STAGE_FIELDS}

    @classmethod
    def from_bytes(cls, raw: bytes, expected_sha256: str) -> OcrProfileSnapshot:
        if len(raw) > 65536 or hashlib.sha256(raw).hexdigest() != expected_sha256:
            raise OcrError("OCR profile bytes do not match the expected SHA-256")
        try:
            value = json.loads(raw)
            stages = stage_parameters(value)
            def pairs(mapping: dict[str, Any]) -> tuple:
                return tuple(sorted(mapping.items()))

            params = {k: tuple(float(n) for n in v) if isinstance(v, list) else v
                      for k, v in value["params"].items()}
            preprocessing = dict(value["preprocessing"])
            if value["schema"] == "ocr-profile-v2":
                params.update(stages)
                preprocessing["dictionary"] = value["dictionary"]
            profile = cls(value["id"], pairs(value["packages"]),
                          pairs({k: v["sha256"] for k, v in value["models"].items()}),
                          value["dictionary_sha256"], value["dictionary_count"], pairs(params),
                          pairs(preprocessing))
            return decode(cls, encode(profile))
        except (ValueError, TypeError, KeyError, AttributeError, UnicodeError):
            raise OcrError("Invalid OCR engine recipe") from None

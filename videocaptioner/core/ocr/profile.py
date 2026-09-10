"""Portable, credential-free snapshot of the engine recipe used for a document."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from .codec import decode, encode, sha256
from .models import OcrError

Parameter = bool | int | float | str | tuple[float, ...]


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

    @classmethod
    def from_bytes(cls, raw: bytes, expected_sha256: str) -> OcrProfileSnapshot:
        if len(raw) > 65536 or hashlib.sha256(raw).hexdigest() != expected_sha256:
            raise OcrError("OCR profile bytes do not match the expected SHA-256")
        try:
            value = json.loads(raw)
            if value["schema"] != "ocr-pilot-profile-v1":
                raise ValueError
            def pairs(mapping: dict[str, Any]) -> tuple:
                return tuple(sorted(mapping.items()))

            params = {k: tuple(float(n) for n in v) if isinstance(v, list) else v
                      for k, v in value["params"].items()}
            profile = cls(value["id"], pairs(value["packages"]),
                          pairs({k: v["sha256"] for k, v in value["models"].items()}),
                          value["dictionary_sha256"], value["dictionary_count"], pairs(params),
                          pairs(value["preprocessing"]))
            return decode(cls, encode(profile))
        except (ValueError, TypeError, KeyError, AttributeError, UnicodeError):
            raise OcrError("Invalid OCR engine recipe") from None

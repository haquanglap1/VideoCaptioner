"""Strict JSON encoding for the small, closed OCR dataclass schema."""

from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
import types
from dataclasses import fields, is_dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any, Literal, TypeVar, Union, get_args, get_origin, get_type_hints

from .models import OcrError

T = TypeVar("T")
MAX_DOCUMENT_BYTES = 32 * 1024 * 1024


def encode(value: Any) -> Any:
    if isinstance(value, Fraction):
        return [value.numerator, value.denominator]
    if is_dataclass(value) and not isinstance(value, type):
        return {f.name: encode(getattr(value, f.name)) for f in fields(value)
                if not (f.metadata.get("omit_none") and getattr(value, f.name) is None)}
    if isinstance(value, (tuple, list)):
        return [encode(item) for item in value]
    return value


def _decode(kind: Any, value: Any) -> Any:
    origin, args = get_origin(kind), get_args(kind)
    if origin in (Union, types.UnionType):
        for option in args:
            try:
                return _decode(option, value)
            except (ValueError, TypeError):
                pass
        raise OcrError("Invalid optional OCR field")
    if origin is Literal:
        if value not in args or not any(type(value) is type(a) for a in args):
            raise OcrError("Unknown OCR schema or policy")
        return value
    if origin is tuple:
        if not isinstance(value, list):
            raise OcrError("Expected OCR array")
        if len(args) == 2 and args[1] is Ellipsis:
            return tuple(_decode(args[0], item) for item in value)
        if len(value) != len(args):
            raise OcrError("Invalid OCR tuple length")
        return tuple(_decode(t, item) for t, item in zip(args, value))
    if kind is Fraction:
        if (not isinstance(value, list) or len(value) != 2
                or any(type(v) is not int for v in value) or value[1] <= 0):
            raise OcrError("Invalid exact OCR time")
        return Fraction(*value)
    if is_dataclass(kind):
        names = {f.name for f in fields(kind)}
        optional = {f.name for f in fields(kind) if f.metadata.get("omit_none")}
        if not isinstance(value, dict) or not names - optional <= set(value) <= names:
            raise OcrError("Missing or unknown OCR field")
        hints = get_type_hints(kind)
        return kind(**{name: _decode(hints[name], v) for name, v in value.items()})
    if kind is float:
        if type(value) not in (int, float) or not math.isfinite(value):
            raise OcrError("Invalid OCR number")
        return float(value)
    if kind not in (str, int, bool, type(None)) or type(value) is not kind:
        raise OcrError("Invalid OCR field type")
    return value


def decode(kind: type[T], value: Any) -> T:
    try:
        return _decode(kind, value)
    except (ValueError, TypeError, KeyError, OverflowError, RecursionError):
        raise OcrError("Invalid OCR document data") from None


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(encode(value), sort_keys=True, ensure_ascii=False,
                                     allow_nan=False, separators=(",", ":")).encode("utf-8")).hexdigest()


def sha256(value: str) -> None:
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise OcrError("Invalid OCR SHA-256")


def _unique(pairs: list[tuple[str, Any]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise OcrError("Duplicate OCR JSON field")
        result[key] = value
    return result


def read_json(path: Path) -> Any:
    try:
        with path.open("rb") as stream:
            raw = stream.read(MAX_DOCUMENT_BYTES + 1)
        if len(raw) > MAX_DOCUMENT_BYTES:
            raise OcrError("OCR document exceeds size limit")
        return json.loads(raw, object_pairs_hook=_unique)
    except (UnicodeError, RecursionError, json.JSONDecodeError):
        raise OcrError("Invalid OCR JSON") from None


def atomic_json(path: Path, value: Any) -> None:
    atomic_text(path, json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + "\n")


def atomic_text(path: Path, content: str) -> None:
    payload = content.encode("utf-8")
    if len(payload) > MAX_DOCUMENT_BYTES:
        raise OcrError("OCR output exceeds size limit")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".ocr-", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)

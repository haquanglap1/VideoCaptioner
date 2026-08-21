"""Public ASR API with lazy imports.

Importing a lightweight ASR submodule must not load every provider (and the
OpenAI client) during GUI startup. The public package API stays unchanged;
objects are imported only when callers actually request them.
"""

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .bcut import BcutASR as BcutASR
    from .chunked_asr import ChunkedASR as ChunkedASR
    from .faster_whisper import FasterWhisperASR as FasterWhisperASR
    from .jianying import JianYingASR as JianYingASR
    from .status import ASRStatus as ASRStatus
    from .transcribe import transcribe as transcribe
    from .whisper_api import WhisperAPI as WhisperAPI
    from .whisper_cpp import WhisperCppASR as WhisperCppASR

_EXPORTS = {
    "BcutASR": (".bcut", "BcutASR"),
    "ChunkedASR": (".chunked_asr", "ChunkedASR"),
    "FasterWhisperASR": (".faster_whisper", "FasterWhisperASR"),
    "JianYingASR": (".jianying", "JianYingASR"),
    "WhisperAPI": (".whisper_api", "WhisperAPI"),
    "WhisperCppASR": (".whisper_cpp", "WhisperCppASR"),
    "transcribe": (".transcribe", "transcribe"),
    "ASRStatus": (".status", "ASRStatus"),
}

__all__ = [
    "BcutASR",
    "ChunkedASR",
    "FasterWhisperASR",
    "JianYingASR",
    "WhisperAPI",
    "WhisperCppASR",
    "transcribe",
    "ASRStatus",
]


def __getattr__(name: str) -> Any:
    try:
        module_name, attribute = _EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from exc
    value = getattr(import_module(module_name, __name__), attribute)
    globals()[name] = value
    return value

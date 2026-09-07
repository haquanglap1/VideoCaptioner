"""Shared request, response and transport policy for ASR and connection probes."""

import math
import time
from dataclasses import dataclass, field
from typing import Any

import httpx
import openai

from .api_profiles import ASRAPIError, MissingTimingError, RequestProfile, normalize_endpoint
from .asr_data import ASRDataSeg

TIMEOUT = httpx.Timeout(120.0, connect=10.0, pool=10.0)
MAX_ATTEMPTS = 3
DEFAULT_ZH_PROMPT = "你好，我们需要使用简体中文，以下是普通话的句子"


def effective_language(language: str) -> str:
    return "" if language.strip().lower() in ("", "auto") else language.strip()


def effective_prompt(language: str, prompt: str) -> str:
    return prompt or (DEFAULT_ZH_PROMPT if language == "zh" else "")


def audio_attachment(audio: bytes, limit: int) -> tuple[str, bytes, str]:
    if not audio:
        raise ASRAPIError("Audio upload is empty.")
    if len(audio) > limit:
        raise ASRAPIError(f"Audio exceeds the {limit} byte upload limit. Compress or split the audio.")
    if audio[:4] == b"RIFF" and audio[8:12] == b"WAVE":
        ext, mime = "wav", "audio/wav"
    elif audio.startswith(b"fLaC"):
        ext, mime = "flac", "audio/flac"
    elif audio.startswith(b"ID3") or (len(audio) > 1 and audio[0] == 255 and audio[1] & 0xE0 == 0xE0
                                               and audio[1] & 0x06 != 0 and audio[1] & 0x18 != 0x08):
        ext, mime = "mp3", "audio/mpeg"
    elif audio[4:8] == b"ftyp":
        ext, mime = "m4a", "audio/mp4"
    else:
        raise ASRAPIError("Unsupported audio bytes. Convert to WAV, MP3, FLAC or M4A before upload.")
    return f"audio.{ext}", audio, mime


def build_request(audio: bytes, model: str, profile: RequestProfile, *,
                  language: str = "", prompt: str = "", word_timing: bool = False) -> dict[str, Any]:
    language = effective_language(language)
    prompt = effective_prompt(language, prompt)
    result: dict[str, Any] = {
        "model": model.strip(), "response_format": profile.response_format,
        "file": audio_attachment(audio, profile.max_upload_bytes),
    }
    if profile.timestamp_levels:
        result["timestamp_granularities"] = ["word", "segment"] if word_timing else ["segment"]
    if language and profile.supports_language:
        result["language"] = language
    if prompt and profile.supports_prompt:
        result["prompt"] = prompt
    return result


@dataclass
class TranscriptionResult:
    text: str = field(repr=False)
    words: list[ASRDataSeg] = field(default_factory=list, repr=False)
    segments: list[ASRDataSeg] = field(default_factory=list, repr=False)

    @property
    def timing_level(self) -> str:
        return "word" if self.words else "segment" if self.segments else "none"

    def subtitle_segments(self, word_timing: bool) -> list[ASRDataSeg]:
        if word_timing:
            if self.words:
                return self.words
            if self.segments:
                raise MissingTimingError(
                    "The response has segment timestamps only. Disable word timestamps to use "
                    "sentence timing, or use a model with word timestamps."
                )
        elif self.segments or self.words:
            return self.segments or self.words
        if self.text:
            raise MissingTimingError("Recognition returned text without timestamps; subtitle export needs alignment (S2).")
        return []


def _spans(value: Any, text_key: str) -> list[ASRDataSeg]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ASRAPIError("Malformed transcription timestamp list.")
    spans = []
    for item in value:
        if not isinstance(item, dict) or not isinstance(item.get(text_key), str):
            raise ASRAPIError("Malformed transcription timestamp entry.")
        try:
            start, end = item["start"], item["end"]
            if isinstance(start, bool) or isinstance(end, bool) or start is None or end is None:
                raise ValueError
            start, end = float(start), float(end)
            if not math.isfinite(start) or not math.isfinite(end) or start < 0 or end < start:
                raise ValueError
        except (KeyError, ValueError, TypeError, OverflowError):
            raise ASRAPIError("Malformed or missing transcription timestamps.") from None
        text = item[text_key].strip()
        if text:
            spans.append(ASRDataSeg(text=text, start_time=int(start * 1000), end_time=int(end * 1000)))
    return spans


def parse_response(response: Any) -> TranscriptionResult:
    if not isinstance(response, dict) or not any(k in response for k in ("text", "words", "segments")):
        raise ASRAPIError("Expected a transcription JSON object with text or timestamps. Check the API route/profile.")
    text = response.get("text", "")
    if not isinstance(text, str):
        raise ASRAPIError("Malformed transcription text.")
    words = _spans(response.get("words"), "word")
    segments = _spans(response.get("segments"), "text")
    return TranscriptionResult(text.strip() or " ".join(s.text for s in (segments or words)), words, segments)


def create_client(base_url: str, api_key: str) -> openai.OpenAI:
    endpoint = normalize_endpoint(base_url)
    if not api_key.strip():
        raise ASRAPIError("ASR API key must be set.")
    return openai.OpenAI(
        base_url=endpoint, api_key=api_key.strip(), timeout=TIMEOUT, max_retries=0,
        http_client=openai.DefaultHttpxClient(follow_redirects=False, timeout=TIMEOUT),
    )


def submit_transcription(client: openai.OpenAI, request: dict[str, Any]) -> dict:
    """Bound retries here so server Retry-After cannot stall a GUI worker indefinitely."""
    message = "ASR request failed."
    for attempt in range(MAX_ATTEMPTS):
        retry = False
        try:
            completion = client.audio.transcriptions.create(**request)
            response = completion if isinstance(completion, dict) else (
                completion.to_dict() if not isinstance(completion, str) else completion
            )
            parse_response(response)
            assert isinstance(response, dict)
            return response
        except openai.APIStatusError as exc:
            code = exc.status_code
            retry = code == 429 or code >= 500
            reasons = {
                400: "Invalid ASR request. Check model and request profile.",
                401: "ASR authentication failed. Check the API key.",
                403: "ASR access denied. Check provider/model permissions.",
                404: "ASR route or model not found. Check Base URL and model access.",
                413: "ASR upload rejected as too large. Compress or split the audio.",
                429: "ASR rate limit reached. Try again later.",
            }
            message = reasons.get(code, f"ASR service returned HTTP {code}.")
        except openai.APITimeoutError:
            retry, message = True, "ASR request timed out. Try a shorter audio clip."
        except openai.APIConnectionError:
            retry, message = True, "ASR connection failed. Check network and Base URL."
        except ASRAPIError:
            raise
        except Exception:
            raise ASRAPIError("Invalid ASR service response. Check the API route/profile.") from None
        if not retry or attempt == MAX_ATTEMPTS - 1:
            break
        time.sleep(0.5 * (attempt + 1))
    # Raise outside the handler: upstream logger.exception must not include raw provider errors.
    raise ASRAPIError(message)

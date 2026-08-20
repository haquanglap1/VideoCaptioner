"""Timing-aware TTS wording rewrite using the existing LLM client."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Callable

from videocaptioner.core.dubbing.models import DubbingGroup
from videocaptioner.core.llm import call_llm
from videocaptioner.core.prompts import get_prompt
from videocaptioner.core.utils.cache import get_llm_cache

PROMPT_VERSION = "dubbing-rewrite-v1"
_PROTECTED_RE = re.compile(
    r"(?:[$€£¥]\s?\d+(?:[.,]\d+)*|\d+(?:[.,]\d+)?\s?(?:%|kg|g|km|m|cm|mm|km/h|mph|°C|°F|GB|MB|TB|Hz|kHz|MHz|GHz)?|\b[A-Za-z]+\d+[A-Za-z0-9-]*\b)",
    re.IGNORECASE,
)
_NEGATIONS = {
    "not", "no", "never", "without", "không", "chưa", "đừng", "chẳng", "无", "不", "没", "ない"
}


@dataclass(frozen=True)
class RewriteRequest:
    group_id: str
    source_language: str
    target_language: str
    source_text: str
    subtitle_text: str
    available_duration: float
    measured_duration: float
    measured_fit_ratio: float
    target_spoken_unit_budget: int
    attempt_number: int
    custom_style_prompt: str = ""


def generate_rewrite_cache_key(request: RewriteRequest, model: str, rescue: bool) -> str:
    payload = {
        "prompt_version": PROMPT_VERSION,
        "source_signature": hashlib.sha256(request.source_text.encode("utf-8")).hexdigest(),
        "subtitle_text": request.subtitle_text,
        "available_duration": round(request.available_duration, 3),
        "measured_duration": round(request.measured_duration, 3),
        "target_spoken_unit_budget": request.target_spoken_unit_budget,
        "attempt_number": request.attempt_number,
        "style": request.custom_style_prompt,
        "model": model,
        "rescue": rescue,
    }
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def _protected_tokens(text: str) -> set[str]:
    return {token.casefold().replace(" ", "") for token in _PROTECTED_RE.findall(text)}


def _negation_markers(text: str) -> set[str]:
    lowered = text.casefold()
    return {marker for marker in _NEGATIONS if re.search(rf"(?<!\w){re.escape(marker)}(?!\w)", lowered)}


def validate_rewrite_response(
    raw: str,
    request: RewriteRequest,
    *,
    rescue: bool,
) -> str:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("Rewrite response must be strict JSON without markdown") from exc
    if not isinstance(data, dict) or set(data) != {"group_id", "tts_text", "preserved_terms"}:
        raise ValueError("Rewrite response has an invalid schema")
    if data["group_id"] != request.group_id:
        raise ValueError("Rewrite response group_id does not match")
    text = data["tts_text"]
    if not isinstance(text, str) or not text.strip():
        raise ValueError("Rewrite response tts_text is empty")
    if not isinstance(data["preserved_terms"], list):
        raise ValueError("Rewrite response preserved_terms must be a list")
    original_tokens = _protected_tokens(request.subtitle_text)
    if not original_tokens.issubset(_protected_tokens(text)):
        raise ValueError("Rewrite removed a number, unit, currency, percentage, or product token")
    original_negations = _negation_markers(request.subtitle_text)
    if original_negations and not _negation_markers(text):
        raise ValueError("Rewrite removed an explicit negation marker")
    if rescue and text.strip().casefold() == request.subtitle_text.strip().casefold():
        raise ValueError("Rescue rewrite did not shorten or change the spoken text")
    return text.strip()


class TimingRewriteService:
    def __init__(
        self,
        model: str,
        *,
        caller: Callable[..., Any] = call_llm,
        cache: Any = None,
    ):
        self.model = model
        self.caller = caller
        self.cache = cache if cache is not None else get_llm_cache()

    @property
    def configured(self) -> bool:
        return bool(self.model.strip())

    def rewrite(self, request: RewriteRequest, *, rescue: bool) -> str | None:
        if not self.configured:
            return None
        key = f"dubbing-rewrite:{generate_rewrite_cache_key(request, self.model, rescue)}"
        cached = self.cache.get(key, default=None) if self.cache is not None else None
        if isinstance(cached, str):
            return cached
        prompt_name = "dubbing/rescue" if rescue else "dubbing/initial"
        messages = [
            {"role": "system", "content": get_prompt(prompt_name)},
            {
                "role": "user",
                "content": json.dumps(request.__dict__, ensure_ascii=False, sort_keys=True),
            },
        ]
        response = self.caller(messages=messages, model=self.model, temperature=0.1)
        raw = response.choices[0].message.content
        if not isinstance(raw, str):
            raise ValueError("LLM returned empty rewrite content")
        text = validate_rewrite_response(raw, request, rescue=rescue)
        if self.cache is not None:
            self.cache.set(key, text, expire=86400 * 7)
        return text


def request_for_group(
    group: DubbingGroup,
    *,
    source_language: str,
    target_language: str,
    attempt_number: int,
    custom_style_prompt: str = "",
) -> RewriteRequest:
    ratio = group.fit_ratio if group.fit_ratio > 0 else 1.0
    current_units = max(1, len(group.tts_text.split()))
    target_units = max(1, round(current_units / max(ratio, 1.0)))
    return RewriteRequest(
        group_id=group.group_id,
        source_language=source_language,
        target_language=target_language,
        source_text=group.source_text,
        subtitle_text=group.tts_text,
        available_duration=group.available_duration,
        measured_duration=group.measured_duration,
        measured_fit_ratio=group.fit_ratio,
        target_spoken_unit_budget=target_units,
        attempt_number=attempt_number,
        custom_style_prompt=custom_style_prompt,
    )

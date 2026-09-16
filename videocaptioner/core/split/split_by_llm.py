"""Lossless LLM segmentation into coherent spoken clauses."""
import json
import re
import unicodedata
from typing import List, Tuple

from ..llm import call_llm
from ..prompts import get_prompt
from ..utils.logger import setup_logger
from ..utils.text_utils import count_words, is_mainly_cjk

logger = setup_logger("split_by_llm")
MAX_STEPS = 2
_PROTECTED_TOKEN_RE = re.compile(
    r"(?:https?://|www\.)\S+|[\w.+-]+@[\w.-]+\.\w+"
    r"|\d+(?:[.,:/-]\d+)+|[^\W\d_]+(?:['’\-][^\W\d_]+)+",
    re.UNICODE,
)


def source_spans_for_split(text: str, parts: List[str]) -> List[Tuple[int, int]]:
    """Map all proposed parts to source spans, allowing whitespace normalization only."""
    if not parts or any(not isinstance(part, str) or not part.strip() for part in parts):
        raise ValueError("Every segment must contain source text; empty segments are not allowed.")
    positions = [i for i, char in enumerate(text) if not char.isspace()]
    source = "".join(text[i] for i in positions)
    proposed = "".join("".join(part.split()) for part in parts)
    if not source or source != proposed:
        raise ValueError("Source content changed. Keep every word, number, repetition and punctuation in order.")

    protected = list(_PROTECTED_TOKEN_RE.finditer(text))
    spans = []
    consumed = start = 0
    for part in parts:
        consumed += len("".join(part.split()))
        end = positions[consumed] if consumed < len(positions) else len(text)
        if consumed < len(positions):
            left = positions[consumed - 1]
            a, b = text[left], text[end]
            a_word = a.isalnum() or unicodedata.category(a).startswith("M")
            b_word = b.isalnum() or unicodedata.category(b).startswith("M")
            if (end == left + 1 and a_word and b_word
                    and not is_mainly_cjk(a) and not is_mainly_cjk(b)):
                raise ValueError("A boundary cuts inside a word or identifier. Break only between complete units.")
            if any(match.start() < end < match.end() for match in protected):
                raise ValueError("A boundary cuts a number, contraction, URL or other protected token.")
        spans.append((start, end))
        start = end
    return spans


def split_by_llm(
    text: str,
    model: str = "gpt-4o-mini",
    max_word_count_cjk: int = 18,
    max_word_count_english: int = 12,
    request=None,
) -> List[str]:
    """Request sentence/clause boundaries without allowing a rewrite of the speech."""
    if not text.strip():
        return []
    try:
        return _split_with_agent_loop(text, model, max_word_count_cjk, max_word_count_english, request)
    except Exception as exc:
        logger.warning("LLM segmentation failed (%s); preserving original text.", type(exc).__name__)
        return [text]


def _split_with_agent_loop(text, model, max_word_count_cjk, max_word_count_english, request=None):
    system_prompt = get_prompt("split/sentence", max_word_count_cjk=max_word_count_cjk,
                               max_word_count_english=max_word_count_english)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": json.dumps({"transcript": text}, ensure_ascii=False)},
    ]
    for step in range(MAX_STEPS):
        response = (request or call_llm)(messages=messages, model=model, temperature=0.1)
        content = response.choices[0].message.content
        parts = [part.strip() for part in content.split("<br>")] if isinstance(content, str) else []
        valid, reason = _validate_split_result(text, parts, max_word_count_cjk, max_word_count_english)
        if valid:
            # Use the source slices, not the model's whitespace or reconstructed words.
            return [text[start:end].strip() for start, end in source_spans_for_split(text, parts)]
        logger.warning("Split validation failed (attempt %d/%d): %s", step + 1, MAX_STEPS, reason)
        if isinstance(content, str):
            messages.append({"role": "assistant", "content": content})
        messages.append({"role": "user", "content": (
            f"Invalid segmentation: {reason}\n"
            "Return the COMPLETE original transcript with only legal <br> boundaries. "
            "Preserve complete sentences when they fit; never remove or rewrite speech to meet a limit. "
            "No explanation, Markdown, SSML, labels or empty segments."
        )})
    logger.warning("No valid LLM segmentation after %d attempts; preserving original text.", MAX_STEPS)
    return [text]


def _validate_split_result(original_text: str, split_result: List[str],
                           max_word_count_cjk: int, max_word_count_english: int) -> Tuple[bool, str]:
    """Require complete source coverage and legal boundaries before applying timing."""
    try:
        spans = source_spans_for_split(original_text, split_result)
    except ValueError as exc:
        return False, str(exc)
    for index, (start, end) in enumerate(spans, 1):
        part = original_text[start:end].strip()
        size = count_words(part)
        limit = max_word_count_cjk if is_mainly_cjk(part) else max_word_count_english
        if size == 0:
            return False, f"Segment {index} contains only punctuation; attach it to its sentence."
        if size > limit:
            return False, (f"Segment {index} has {size} units, above the {limit} limit. "
                           "Split at a complete clause boundary and return ALL segments.")
    return True, ""

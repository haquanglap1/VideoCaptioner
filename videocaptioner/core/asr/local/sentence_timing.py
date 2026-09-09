"""Cue boundaries from raw aligner anchors, independent of interior word timing."""

from dataclasses import dataclass

from ..alignment.contract import MAX_AUDIO_MS, AlignmentError, AlignmentSpan, lexical

SENTENCE_POLICY = "qwen-sentence-anchors-v1"
PRACTICAL_SENTENCE_POLICY = "qwen-sentence-practical-v1"
SENTENCE_POLICIES = (SENTENCE_POLICY, PRACTICAL_SENTENCE_POLICY)
MAX_CUE_CHARS = 40
MAX_CUE_MS = 15_000
SENTENCE_ENDS = frozenset("。！？.!?；;\n")


@dataclass(frozen=True)
class SentenceCue:
    span: AlignmentSpan
    # Half-open indices refer to the unchanged raw token sequence.
    first_token: int
    stop_token: int
    anchors: tuple[AlignmentSpan, AlignmentSpan]


def sentence_cues(text: str, items: object, duration_ms: int, *, policy: str = SENTENCE_POLICY) -> tuple[SentenceCue, ...]:
    """Partition text before inspecting times; never modify the raw predictions.

    Legacy reviews retain strict boundary-token guards. Practical sentence mode
    uses only the first start and last end; the caller checks whole-cue audio.
    """
    if policy not in SENTENCE_POLICIES:
        raise AlignmentError("unknown sentence timing policy")
    if type(duration_ms) is not int or not 0 < duration_ms <= MAX_AUDIO_MS:
        raise AlignmentError("invalid sentence audio duration")
    if not isinstance(items, list):
        raise AlignmentError("malformed spans")
    source = lexical(text)
    if not source:
        if text.strip() or items:
            raise AlignmentError("punctuation-only or unmatched silence")
        return ()
    positions = [i for i, char in enumerate(text) if lexical(char)]
    parts, times = [], []
    cursor, original = 0, 0
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get("text"), str):
            raise AlignmentError("malformed spans")
        token = lexical(item["text"])
        if not token or source[cursor:cursor + len(token)] != token:
            raise AlignmentError("unmatched or duplicated text")
        cursor += len(token)
        stop = positions[cursor] if cursor < len(positions) else len(text)
        parts.append(text[original:stop])
        times.append((item.get("start_ms"), item.get("end_ms")))
        original = stop
    if cursor != len(source) or "".join(parts) != text:
        raise AlignmentError("unmatched text")

    # Groups depend only on original text and token boundaries, never on a failure.
    groups, first, length = [], 0, 0
    for index, part in enumerate(parts):
        if index > first and length + len(part) > MAX_CUE_CHARS:
            groups.append((first, index))
            first, length = index, 0
        length += len(part)
        if any(char in SENTENCE_ENDS for char in part):
            groups.append((first, index + 1))
            first, length = index + 1, 0
    if first < len(parts):
        groups.append((first, len(parts)))

    cues, previous_end = [], 0
    for first, stop in groups:
        prediction = times[first:stop]
        if any(type(value) is not int for pair in prediction for value in pair):
            raise AlignmentError("sentence timestamp is not canonical milliseconds")
        start, first_end = prediction[0]
        last_start, end = prediction[-1]
        if not 0 <= start < end <= duration_ms:
            raise AlignmentError("invalid sentence boundary anchor")
        if policy == SENTENCE_POLICY and not (start < first_end <= end and start <= last_start < end):
            raise AlignmentError("invalid sentence boundary anchor")
        if start < previous_end:
            raise AlignmentError("overlapping sentence boundaries")
        if end - start > MAX_CUE_MS:
            raise AlignmentError("sentence boundary interval exceeds cue limit")
        if policy == SENTENCE_POLICY and any(not start <= value <= end for pair in prediction for value in pair):
            raise AlignmentError("interior timestamp outside sentence anchors")
        content = "".join(parts[first:stop])
        cues.append(SentenceCue(AlignmentSpan(content, start, end), first, stop,
                               (AlignmentSpan(parts[first], start, first_end),
                                AlignmentSpan(parts[stop - 1], last_start, end))))
        previous_end = end
    return tuple(cues)

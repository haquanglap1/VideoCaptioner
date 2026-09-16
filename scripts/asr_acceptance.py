"""Read labeled speech references and score ASR/diarization without model dependencies."""

from __future__ import annotations

import argparse
import json
import math
import re
import unicodedata
from bisect import bisect_left, bisect_right
from collections import Counter
from dataclasses import asdict, dataclass, field
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path
from statistics import median


@dataclass(frozen=True)
class ReferenceSegment:
    speaker: str
    start_ms: int
    end_ms: int
    text: str = field(repr=False)


@dataclass(frozen=True)
class SpeakerSpan:
    speaker: str
    start_ms: int
    end_ms: int


@dataclass(frozen=True)
class TimedText:
    start_ms: int
    end_ms: int
    text: str = field(repr=False)


_TOKENS = re.compile(r'\s+|"(?:""|[^"])*"|<exists>|[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?|[A-Za-z_]+|[][=:?]')
_MARKERS = re.compile(r"\((?:SIL|~|/OVERLAP)\)", re.IGNORECASE)


def lexical(text: str, *, reference: bool = False) -> str:
    """Preserve script, case and numbers; omit punctuation and known reference markup."""
    if reference:
        text = _MARKERS.sub("", text)
    return "".join(c for c in text if c == "'" or unicodedata.category(c)[0] in "LN")


class _Reader:
    def __init__(self, text: str):
        self.tokens = []
        previous = 0
        for match in _TOKENS.finditer(text):
            if match.start() != previous:
                raise ValueError("Unexpected TextGrid syntax")
            previous = match.end()
            token = match.group()
            if not token.isspace():
                self.tokens.append(token)
        if previous != len(text):
            raise ValueError("Truncated TextGrid syntax")
        self.index = 0

    def take(self) -> str:
        if self.index >= len(self.tokens):
            raise ValueError("Incomplete TextGrid")
        result = self.tokens[self.index]
        self.index += 1
        return result

    def expect(self, value: str) -> None:
        if self.take() != value:
            raise ValueError("Unexpected TextGrid field")

    def string(self) -> str:
        token = self.take()
        if not token.startswith('"') or not token.endswith('"'):
            raise ValueError("Expected quoted TextGrid string")
        return token[1:-1].replace('""', '"')

    def number(self) -> Decimal:
        try:
            value = Decimal(self.take())
        except InvalidOperation:
            raise ValueError("Invalid TextGrid number") from None
        if not value.is_finite():
            raise ValueError("Nonfinite TextGrid time")
        return value

    def integer(self) -> int:
        value = self.number()
        if value != int(value) or not 0 <= value <= 1_000_000:
            raise ValueError("Invalid TextGrid count")
        return int(value)

    def field(self, name: str) -> None:
        self.expect(name)
        self.expect("=")


def _milliseconds(value: Decimal) -> int:
    return int((value * 1000).to_integral_value(rounding=ROUND_HALF_UP))


def parse_textgrid(text: str) -> tuple[int, list[ReferenceSegment]]:
    """Parse long-format Praat IntervalTiers, including escaped and multiline text."""
    reader = _Reader(text.lstrip("\ufeff"))
    for value in ("File", "type", "="):
        reader.expect(value)
    if reader.string() != "ooTextFile":
        raise ValueError("Only long-format TextGrid is supported")
    for value in ("Object", "class", "="):
        reader.expect(value)
    if reader.string() != "TextGrid":
        raise ValueError("Expected TextGrid object")
    reader.field("xmin")
    if reader.number() != 0:
        raise ValueError("Reference timeline must start at zero")
    reader.field("xmax")
    maximum = reader.number()
    if maximum <= 0:
        raise ValueError("Invalid recording duration")
    for value in ("tiers", "?", "<exists>"):
        reader.expect(value)
    reader.field("size")
    tier_count = reader.integer()
    if tier_count > 128:
        raise ValueError("Too many reference tiers")
    for value in ("item", "[", "]", ":"):
        reader.expect(value)
    segments = []
    speakers = set()
    for index in range(1, tier_count + 1):
        reader.expect("item")
        reader.expect("[")
        if reader.integer() != index:
            raise ValueError("TextGrid tier index mismatch")
        reader.expect("]")
        reader.expect(":")
        reader.field("class")
        if reader.string() != "IntervalTier":
            raise ValueError("Unsupported reference tier type")
        reader.field("name")
        speaker = reader.string()
        if not speaker or speaker in speakers:
            raise ValueError("Missing or duplicate speaker tier")
        speakers.add(speaker)
        reader.field("xmin")
        minimum = reader.number()
        reader.field("xmax")
        tier_maximum = reader.number()
        if not 0 <= minimum <= tier_maximum <= maximum:
            raise ValueError("Tier outside recording")
        reader.expect("intervals")
        reader.expect(":")
        reader.field("size")
        interval_count = reader.integer()
        previous = minimum
        for interval in range(1, interval_count + 1):
            reader.expect("intervals")
            reader.expect("[")
            if reader.integer() != interval:
                raise ValueError("TextGrid interval index mismatch")
            reader.expect("]")
            reader.expect(":")
            reader.field("xmin")
            start = reader.number()
            reader.field("xmax")
            end = reader.number()
            reader.field("text")
            content = reader.string()
            if not previous <= start <= end <= tier_maximum:
                raise ValueError("Invalid or overlapping interval within a reference tier")
            previous = end
            if lexical(content, reference=True):
                if start == end or _milliseconds(start) >= _milliseconds(end):
                    raise ValueError("Nonempty reference has no positive interval")
                segments.append(ReferenceSegment(speaker, _milliseconds(start), _milliseconds(end), content))
    if reader.index != len(reader.tokens):
        raise ValueError("Unexpected trailing TextGrid fields")
    return _milliseconds(maximum), sorted(segments, key=lambda s: (s.start_ms, s.end_ms, s.speaker))


def edit_distance(reference: str, hypothesis: str) -> int:
    """Levenshtein distance with memory bounded by the shorter sequence."""
    if len(reference) < len(hypothesis):
        reference, hypothesis = hypothesis, reference
    previous = list(range(len(hypothesis) + 1))
    for row, a in enumerate(reference, 1):
        current = [row]
        for column, b in enumerate(hypothesis, 1):
            current.append(min(current[-1] + 1, previous[column] + 1, previous[column - 1] + (a != b)))
        previous = current
    return previous[-1]


def character_error(reference: str, hypothesis: str) -> dict:
    source, predicted = lexical(reference, reference=True), lexical(hypothesis)
    errors = edit_distance(source, predicted)
    return {"errors": errors, "reference_characters": len(source), "hypothesis_characters": len(predicted),
            "cer": errors / len(source) if source else None,
            "empty_reference_insertions": len(predicted) if not source else 0,
            "policy": "unicode-lexical-v1-keep-script-case-numbers"}


def utterance_timing(reference: list[ReferenceSegment], hypothesis: list[TimedText], duration_ms: int) -> dict:
    """Score measured endpoints only where a unique full reference text matches word boundaries."""
    if type(duration_ms) is not int or duration_ms <= 0:
        raise ValueError("Invalid recording duration")
    if any(type(s.start_ms) is not int or type(s.end_ms) is not int or
           not 0 <= s.start_ms < s.end_ms <= duration_ms for s in [*reference, *hypothesis]):
        raise ValueError("Invalid measured timing")
    text = ""
    starts, ends = {}, {}
    for span in hypothesis:
        content = lexical(span.text)
        if content:
            starts[len(text)] = span.start_ms
            text += content
            ends[len(text)] = span.end_ms
    refs = [lexical(s.text, reference=True) for s in reference]
    errors = []
    reasons = Counter()
    for index, (span, content) in enumerate(zip(reference, refs)):
        if len(content) < 4:
            reasons["short_reference"] += 1
            continue
        position = text.find(content)
        if position < 0:
            reasons["no_exact_match"] += 1
        elif sum(content in other for other in refs) != 1 or text.find(content, position + 1) >= 0:
            reasons["ambiguous_text_match"] += 1
        elif position not in starts or position + len(content) not in ends:
            reasons["inside_hypothesis_word"] += 1
        else:
            errors.append({"reference_index": index, "start_error_ms": starts[position] - span.start_ms,
                           "end_error_ms": ends[position + len(content)] - span.end_ms})
    absolute = sorted(abs(item[key]) for item in errors for key in ("start_error_ms", "end_error_ms"))
    return {"policy": "unique-exact-utterance-at-measured-word-boundaries-v1", "reference_utterances": len(reference),
            "matched_utterances": len(errors), "unmatched_reasons": dict(reasons), "errors": errors,
            "median_absolute_ms": median(absolute) if absolute else None,
            "p95_absolute_ms": absolute[math.ceil(.95 * len(absolute)) - 1] if absolute else None,
            "p95_method": "nearest-rank", "coverage": len(errors) / len(reference) if reference else None,
            "limitation": "Exact-text subset only; reference utterance endpoints do not validate character timing."}


def maximum_assignment(weights: list[list[float]]) -> list[tuple[int, int]]:
    """Maximum-weight one-to-one assignment, padding unmatched labels with zero weight."""
    rows = len(weights)
    columns = len(weights[0]) if rows else 0
    if any(len(row) != columns or any(not math.isfinite(v) or v < 0 for v in row) for row in weights):
        raise ValueError("Invalid assignment matrix")
    size = max(rows, columns)
    if not size:
        return []
    u, v, p, way = [0.0] * (size + 1), [0.0] * (size + 1), [0] * (size + 1), [0] * (size + 1)
    for i in range(1, size + 1):
        p[0] = i
        minimum, used = [float("inf")] * (size + 1), [False] * (size + 1)
        j0 = 0
        while True:
            used[j0] = True
            i0, delta, j1 = p[j0], float("inf"), 0
            for j in range(1, size + 1):
                if used[j]:
                    continue
                weight = weights[i0 - 1][j - 1] if i0 <= rows and j <= columns else 0
                cost = -weight - u[i0] - v[j]
                if cost < minimum[j]:
                    minimum[j], way[j] = cost, j0
                if minimum[j] < delta:
                    delta, j1 = minimum[j], j
            for j in range(size + 1):
                if used[j]:
                    u[p[j]] += delta
                    v[j] -= delta
                else:
                    minimum[j] -= delta
            j0 = j1
            if p[j0] == 0:
                break
        while True:
            j1 = way[j0]
            p[j0] = p[j1]
            j0 = j1
            if j0 == 0:
                break
    return [(p[j] - 1, j - 1) for j in range(1, size + 1) if p[j] <= rows and j <= columns]


def diarization_error(reference: list[SpeakerSpan], hypothesis: list[SpeakerSpan],
                      duration_ms: int, *, collar_ms: int = 250) -> dict:
    """Score speaker time; collar is total width centered on reference boundaries."""
    if type(duration_ms) is not int or duration_ms <= 0 or type(collar_ms) is not int or collar_ms < 0:
        raise ValueError("Invalid scoring duration or collar")
    events = {0: [], duration_ms: []}
    for group, spans in (("ref", reference), ("hyp", hypothesis)):
        for span in spans:
            if (not isinstance(span.speaker, str) or not span.speaker or type(span.start_ms) is not int or type(span.end_ms) is not int
                    or not 0 <= span.start_ms < span.end_ms <= duration_ms):
                raise ValueError("Invalid speaker span")
            events.setdefault(span.start_ms, []).append((group, span.speaker, 1))
            events.setdefault(span.end_ms, []).append((group, span.speaker, -1))
            if group == "ref" and collar_ms:
                for boundary in (span.start_ms, span.end_ms):
                    events.setdefault(max(0, boundary - collar_ms / 2), []).append(("collar", "", 1))
                    events.setdefault(min(duration_ms, boundary + collar_ms / 2), []).append(("collar", "", -1))
    active = {"ref": Counter(), "hyp": Counter()}
    collar = 0
    atoms = []
    points = sorted(events)
    for start, end in zip(points, points[1:]):
        for group, speaker, change in events[start]:
            if group == "collar":
                collar += change
            else:
                active[group][speaker] += change
        if collar == 0:
            atoms.append((end - start, {s for s, count in active["ref"].items() if count > 0},
                          {s for s, count in active["hyp"].items() if count > 0}))
    refs, hyps = sorted({s.speaker for s in reference}), sorted({s.speaker for s in hypothesis})
    weights = [[sum(dt for dt, r, h in atoms if ref in r and hyp in h) for hyp in hyps] for ref in refs]
    mapping = {hyps[j]: refs[i] for i, j in maximum_assignment(weights)}
    missed = false_alarm = confusion = speaker_time = 0
    for dt, ref, hyp in atoms:
        correct = len(ref & {mapping.get(s) for s in hyp})
        speaker_time += dt * len(ref)
        missed += dt * max(0, len(ref) - len(hyp))
        false_alarm += dt * max(0, len(hyp) - len(ref))
        confusion += dt * (min(len(ref), len(hyp)) - correct)
    return {"missed_speaker_ms": missed, "false_alarm_speaker_ms": false_alarm,
            "confusion_speaker_ms": confusion, "reference_speaker_ms": speaker_time,
            "der": (missed + false_alarm + confusion) / speaker_time if speaker_time else None,
            "collar_ms": collar_ms, "collar_semantics": "total-width-centered", "skip_overlap": False, "mapping": mapping}


def select_windows(segments: list[ReferenceSegment], duration_ms: int,
                   count: int = 4, target_ms: int = 125_000) -> list[tuple[int, int]]:
    """Choose disjoint windows whose boundaries do not cut any labeled utterance."""
    boundaries = [0, duration_ms]
    end = 0
    for segment in sorted(segments, key=lambda s: s.start_ms):
        if segment.start_ms >= end:
            boundaries.append((end + segment.start_ms) // 2)
        end = max(end, segment.end_ms)
    if end < duration_ms:
        boundaries.append((end + duration_ms) // 2)
    boundaries = sorted(set(boundaries))
    ordered = sorted(segments, key=lambda s: s.start_ms)
    starts = [s.start_ms for s in ordered]
    characters = [0]
    for segment in ordered:
        characters.append(characters[-1] + len(lexical(segment.text, reference=True)))
    windows = []
    previous_end = 0
    for index in range(count):
        anchor = max(0, duration_ms - target_ms) * index // max(count - 1, 1)
        candidates = []
        for start in boundaries:
            if start < previous_end:
                continue
            for stop in boundaries[bisect_left(boundaries, start + 105_000):bisect_right(boundaries, start + 150_000)]:
                if characters[bisect_left(starts, stop)] - characters[bisect_left(starts, start)] < 100:
                    continue
                candidates.append((abs(start - anchor) + abs(stop - start - target_ms), start, stop))
        if candidates:
            _, start, stop = min(candidates)
            windows.append((start, stop))
            previous_end = stop
    return windows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("textgrid", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    content = args.textgrid.read_bytes()
    encoding = "utf-16" if content.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig"
    duration, segments = parse_textgrid(content.decode(encoding))
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump({"duration_ms": duration, "segments": [asdict(s) for s in segments]}, handle,
                  ensure_ascii=False, indent=2)
    print(json.dumps({"duration_ms": duration, "segments": len(segments), "speakers": len({s.speaker for s in segments})}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Opt-in whole-read selection when two frames witness a detector-clipped dot tail."""

from __future__ import annotations

import hashlib
import math
from typing import cast

from PIL import Image, ImageChops, ImageFilter

from .consensus import CandidateRead, Consensus, choose_read
from .models import RoiFrame

POLICY = "witnessed-punctuation-v2"


def _box(read: CandidateRead) -> tuple[float, float, float, float] | None:
    indices = read.selected_line_indices
    if indices is None:
        indices = tuple(range(len(read.raw.lines)))
    if len(indices) != 1:
        return None
    points = read.raw.lines[indices[0]].box
    xs, ys = zip(*points)
    return min(xs), min(ys), max(xs), max(ys)


def _dots(frame: RoiFrame, area: tuple[int, int, int, int], line_height: float) -> list[set[tuple[int, int]]]:
    # Bright, compact dots only. Other punctuation/fonts retain v1 selection.
    image = Image.frombytes("RGB", (frame.width, frame.height), frame.rgb).convert("L").crop(area)
    contrast = ImageChops.subtract(image, image.filter(ImageFilter.MinFilter(11)))
    pixels = image.load()
    local = contrast.load()
    assert pixels is not None and local is not None
    pending = {(x, y) for y in range(image.height) for x in range(image.width)
               if cast(int, pixels[x, y]) >= 224 and cast(int, local[x, y]) >= 48}
    dots = []
    while pending:
        seed = pending.pop()
        component, todo = {seed}, [seed]
        while todo:
            x, y = todo.pop()
            for point in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                if point in pending:
                    pending.remove(point)
                    component.add(point)
                    todo.append(point)
        xs, ys = zip(*component)
        width, height = max(xs) - min(xs) + 1, max(ys) - min(ys) + 1
        middle = (min(ys) + max(ys)) / 2
        if (2 <= len(component) and max(width, height) <= line_height * .3
                and .5 <= width / height <= 2
                and abs(middle - image.height / 2) <= line_height * .25):
            dots.append(component)
    return sorted(dots, key=lambda points: min(x for x, _ in points))


def _witness(short: CandidateRead, long: CandidateRead, first: RoiFrame, last: RoiFrame) -> bool:
    if not short.text.strip() or not long.text.startswith(short.text):
        return False
    tail = long.text[len(short.text):]
    if not tail or set(tail) - {".", "…"}:
        return False
    count = tail.count(".") + 3 * tail.count("…")
    if not 2 <= count <= 8:
        return False
    a, b = _box(short), _box(long)
    if a is None or b is None:
        return False
    height = min(a[3] - a[1], b[3] - b[1])
    if (height < 10 or abs(a[0] - b[0]) > height * .15
            or max(abs(a[1] - b[1]), abs(a[3] - b[3])) > height * .15
            or not height * .5 <= b[2] - a[2] <= height * 4):
        return False
    if (first.width, first.height) != (last.width, last.height) or first.pts == last.pts:
        return False
    area = (math.ceil(a[2]), math.floor(min(a[1], b[1])), math.ceil(b[2]), math.ceil(max(a[3], b[3])))
    if not (0 <= area[0] < area[2] <= first.width and 0 <= area[1] < area[3] <= first.height):
        return False
    left, right = _dots(first, area, height), _dots(last, area, height)
    if len(left) != count or len(right) != count:
        return False
    # A new/removed/shifted dot is a transition, not evidence of detector omission.
    return all(len(x & y) / len(x | y) >= .6 for x, y in zip(left, right))


def choose_witnessed_read(candidates: tuple[CandidateRead, ...], frames: tuple[RoiFrame, ...]) -> Consensus:
    baseline = choose_read(candidates)
    if baseline.selected_index is None or "model_revision_mismatch" in baseline.issues:
        return baseline
    by_pts = {frame.pts: frame for frame in frames}
    for candidate in candidates:
        frame = by_pts.get(candidate.frame_pts)
        if frame is None or hashlib.sha256(frame.rgb).hexdigest() != candidate.crop_sha256:
            return baseline
    short = candidates[baseline.selected_index]
    matches = [i for i, candidate in enumerate(candidates)
               if _witness(short, candidate, by_pts[short.frame_pts], by_pts[candidate.frame_pts])]
    # Conflicting witnessed tails remain a disagreement; never concatenate raw text.
    if not matches or len({candidates[i].text for i in matches}) != 1:
        return baseline
    selected = max(matches, key=lambda i: (candidates[i].min_score, -i))
    return Consensus(selected, candidates[selected].text, baseline.issues)

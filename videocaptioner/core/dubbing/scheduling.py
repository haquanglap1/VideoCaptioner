"""Plan sequential speech with bounded drift and one steady tempo for the whole job."""

import math
from dataclasses import dataclass

from .models import DubbingGroup


@dataclass(frozen=True)
class ReadingSlot:
    start: float
    speed: float


def sequential_slots(groups: list[DubbingGroup], *, video_duration: float,
                     max_speed: float, max_delay: float, gap: float) -> list[ReadingSlot]:
    """Prefer native tempo, otherwise use one minimal shared acceleration.

    FFmpeg can differ slightly from duration / speed. Reserve 30 ms when
    stretching; the caller must validate the actual rendered WAV durations.
    """
    if not math.isfinite(video_duration) or video_duration <= 0:
        raise ValueError("Sequential dubbing needs the real video duration")
    if not 1 <= max_speed <= 1.5 or not 0 <= max_delay <= 10 or not 0 <= gap <= 5:
        raise ValueError("Invalid sequential dubbing limits")
    if any(not math.isfinite(g.measured_duration) or g.measured_duration <= 0 for g in groups):
        raise ValueError("Sequential dubbing requires measured audio")
    def schedule(speed):
        slots, previous_end, fits = [], -gap, True
        padding = 0.03 if speed > 1.0 else 0.0
        for group in groups:
            start = max(group.start_time, previous_end + gap)
            slots.append(ReadingSlot(start, speed))
            previous_end = start + group.measured_duration / speed + padding
            fits = fits and start <= group.start_time + max_delay and previous_end <= video_duration
        return slots, fits

    normal, fits = schedule(1.0)
    if fits or max_speed < 1.01:
        return normal
    if not schedule(max_speed)[1]:
        return schedule(max_speed)[0]  # Actual-wave validation will request review.
    low, high = 1.01, max_speed
    for _ in range(20):
        middle = (low + high) / 2
        if schedule(middle)[1]:
            high = middle
        else:
            low = middle
    return schedule(high)[0]

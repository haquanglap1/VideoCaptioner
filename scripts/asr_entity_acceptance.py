"""Locate labeled text spans across all minimum-edit transcript correspondences.

Inputs use the caller's fixed lexical policy. This measures textual correspondence,
never acoustic timing, speaker identity or the correctness of the reference itself.
"""

from array import array
from dataclasses import dataclass, field


@dataclass(frozen=True)
class EntityLabel:
    start: int
    end: int
    target: str = field(repr=False)
    accepted_forms: tuple[str, ...] = field(default=(), repr=False)


def _distances(reference: str, hypothesis: str) -> list[array]:
    rows = [array("I", range(len(hypothesis) + 1))]
    for i, source in enumerate(reference, 1):
        previous = rows[-1]
        current = array("I", [i])
        for j, predicted in enumerate(hypothesis, 1):
            current.append(min(current[-1] + 1, previous[j] + 1,
                               previous[j - 1] + (source != predicted)))
        rows.append(current)
    return rows


def optimal_boundary_positions(
    reference: str, hypothesis: str, boundaries: set[int], *, max_cells: int = 4_000_000,
) -> dict[int, list[int]]:
    """Return every hypothesis position reached at each boundary on an optimal path.

    Insertions can give several positions even along a single path. Preserve that
    uncertainty instead of resolving ties in favor of a successful entity match.
    """
    if any(type(i) is not int or not 0 <= i <= len(reference) for i in boundaries):
        raise ValueError("Reference boundary is outside the transcript")
    if type(max_cells) is not int or max_cells < 1:
        raise ValueError("max_cells must be a positive integer")
    if (len(reference) + 1) * (len(hypothesis) + 1) > max_cells:
        raise ValueError("Transcript pair exceeds the correspondence matrix limit")
    if not boundaries:
        return {}
    forward = _distances(reference, hypothesis)
    backward = _distances(reference[::-1], hypothesis[::-1])
    distance = forward[-1][-1]
    return {
        i: [j for j in range(len(hypothesis) + 1)
            if forward[i][j] + backward[len(reference) - i][len(hypothesis) - j] == distance]
        for i in sorted(boundaries)
    }


def score_entities(reference: str, hypothesis: str, labels: list[EntityLabel]) -> list[dict]:
    """Score only spans whose two boundaries agree across all minimum-edit paths.

    Alternate forms must be supplied explicitly by the reference rubric. A
    different local form is not automatically a wrong numeric value or identity.
    """
    for label in labels:
        if (type(label.start) is not int or type(label.end) is not int
                or not 0 <= label.start < label.end <= len(reference)
                or reference[label.start:label.end] != label.target):
            raise ValueError("Entity label does not match its reference span")
        if any(not isinstance(form, str) or not form for form in label.accepted_forms):
            raise ValueError("Accepted entity forms must be nonempty strings")
    positions = optimal_boundary_positions(reference, hypothesis, {i for label in labels for i in (label.start, label.end)})
    results = []
    for label in labels:
        starts, ends = positions[label.start], positions[label.end]
        row = {"reference_start": label.start, "reference_end": label.end,
               "hypothesis_start_candidates": starts, "hypothesis_end_candidates": ends,
               "status": "ambiguous", "matched": None, "observed": None}
        if len(starts) == len(ends) == 1:
            observed = hypothesis[starts[0]:ends[0]]
            if observed == label.target:
                status = "exact"
            elif observed in label.accepted_forms:
                status = "equivalent_form"
            else:
                status = "different" if observed else "omitted"
            row.update(status=status, observed=observed, matched=status in ("exact", "equivalent_form"))
        results.append(row)
    return results

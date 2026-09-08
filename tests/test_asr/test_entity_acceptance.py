"""Synthetic checks: repeated mentions, numeric forms, and edit-path ambiguity."""

import itertools

import pytest

from scripts.asr_entity_acceptance import EntityLabel, optimal_boundary_positions, score_entities


def test_matching_mention_elsewhere_does_not_credit_labeled_mention():
    reference, hypothesis = "甲说京东乙说淘宝", "甲说淘宝乙说京东"
    result = score_entities(reference, hypothesis, [EntityLabel(2, 4, "京东")])[0]
    assert result["matched"] is False
    assert result["observed"] == "淘宝"


def test_numeric_equivalence_requires_explicit_unit_preserving_rubric():
    label = EntityLabel(1, 6, "一百零五元", ("105元",))
    assert score_entities("价一百零五元整", "价105元整", [label])[0]["status"] == "equivalent_form"
    assert score_entities("价一百零五元整", "价105整", [label])[0]["matched"] is False
    assert score_entities("价一百零五元整", "价105元整", [EntityLabel(1, 6, "一百零五元")])[0]["matched"] is False


def test_repeated_reference_mentions_are_not_arbitrarily_assigned():
    result = score_entities("甲甲", "甲", [EntityLabel(0, 1, "甲"), EntityLabel(1, 2, "甲")])
    assert all(row["status"] == "ambiguous" and row["matched"] is None for row in result)


def test_insertions_at_a_boundary_remain_ambiguous():
    result = score_entities("甲乙", "甲丙乙", [EntityLabel(0, 1, "甲")])[0]
    assert result["status"] == "ambiguous"
    assert result["hypothesis_end_candidates"] == [1, 2]


def test_exact_omitted_and_script_difference_are_separate():
    label = EntityLabel(0, 1, "現")
    assert score_entities("現", "現", [label])[0]["status"] == "exact"
    assert score_entities("現", "", [label])[0]["status"] == "omitted"
    assert score_entities("現", "现", [label])[0]["status"] == "different"


@pytest.mark.parametrize("label", [EntityLabel(-1, 1, "甲"), EntityLabel(0, 2, "甲"),
                                  EntityLabel(0, 0, ""), EntityLabel(0, 1, "乙"), EntityLabel(True, 2, "乙")])
def test_stale_or_invalid_reference_label_is_rejected(label):
    with pytest.raises(ValueError, match="reference span"):
        score_entities("甲乙", "甲乙", [label])


def test_matrix_work_is_bounded_before_allocation():
    with pytest.raises(ValueError, match="matrix limit"):
        optimal_boundary_positions("甲" * 100, "甲" * 100, {1}, max_cells=100)
    assert score_entities("甲", "乙", []) == []


def _enumerated_optimal_vertices(reference, hypothesis):
    paths = []

    def visit(i, j, cost, vertices):
        vertices = vertices + [(i, j)]
        if i == len(reference) and j == len(hypothesis):
            paths.append((cost, vertices))
            return
        if i < len(reference):
            visit(i + 1, j, cost + 1, vertices)
        if j < len(hypothesis):
            visit(i, j + 1, cost + 1, vertices)
        if i < len(reference) and j < len(hypothesis):
            visit(i + 1, j + 1, cost + (reference[i] != hypothesis[j]), vertices)

    visit(0, 0, 0, [])
    best = min(cost for cost, _ in paths)
    return {i: sorted({j for cost, vertices in paths if cost == best for row, j in vertices if row == i})
            for i in range(len(reference) + 1)}


def test_all_optimal_boundaries_match_exhaustive_edit_path_enumeration():
    strings = ["".join(chars) for size in range(4) for chars in itertools.product("ab", repeat=size)]
    for reference, hypothesis in itertools.product(strings, repeat=2):
        assert optimal_boundary_positions(reference, hypothesis, set(range(len(reference) + 1))) == _enumerated_optimal_vertices(reference, hypothesis)

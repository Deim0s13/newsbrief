"""Tests for rule-based viewpoint gap detection (#229, ADR-0023, v0.9.1).

Pure logic, no DB/LLM -- app.perspective_gaps.detect_perspective_gaps()
operates only on already-constructed ArticlePerspective values.
"""

from app.entities import ArticlePerspective
from app.perspective_gaps import detect_perspective_gaps


def _p(**kwargs) -> ArticlePerspective:
    kwargs.setdefault("applicable", True)
    return ArticlePerspective(**kwargs)


class TestDetectPerspectiveGaps:
    def test_empty_list_returns_no_gaps(self):
        assert detect_perspective_gaps([]) == []

    def test_all_none_returns_no_gaps(self):
        assert detect_perspective_gaps([None, None]) == []

    def test_all_not_applicable_returns_no_gaps(self):
        perspectives = [_p(applicable=False, stakeholder="business") for _ in range(3)]
        assert detect_perspective_gaps(perspectives) == []

    def test_single_article_below_threshold_no_gap(self):
        """One opinionated article shouldn't be enough signal to flag a gap."""
        perspectives = [_p(stakeholder="business")]
        assert detect_perspective_gaps(perspectives) == []

    def test_one_sided_stakeholder_flags_gap(self):
        perspectives = [_p(stakeholder="business"), _p(stakeholder="business")]
        gaps = detect_perspective_gaps(perspectives)
        assert len(gaps) == 1
        assert gaps[0] == {
            "dimension": "stakeholder",
            "present": ["business"],
            "missing": "consumer or labor viewpoint",
        }

    def test_balanced_stakeholder_no_gap(self):
        perspectives = [_p(stakeholder="business"), _p(stakeholder="consumer")]
        assert detect_perspective_gaps(perspectives) == []

    def test_stakeholder_gap_reversed_direction(self):
        perspectives = [_p(stakeholder="labor"), _p(stakeholder="consumer")]
        gaps = detect_perspective_gaps(perspectives)
        assert len(gaps) == 1
        assert gaps[0]["missing"] == "business viewpoint"
        assert gaps[0]["present"] == ["consumer", "labor"]

    def test_neutral_stakeholder_values_dont_fill_either_side(self):
        """regulatory/environmental count toward the signal threshold but
        aren't "business" or "consumer/labor" -- a business-only cluster
        plus a regulatory article should still flag the consumer/labor gap."""
        perspectives = [_p(stakeholder="business"), _p(stakeholder="regulatory")]
        gaps = detect_perspective_gaps(perspectives)
        assert len(gaps) == 1
        assert gaps[0]["dimension"] == "stakeholder"
        assert gaps[0]["missing"] == "consumer or labor viewpoint"

    def test_one_sided_political_leaning_flags_gap(self):
        perspectives = [
            _p(political_leaning="left"),
            _p(political_leaning="center-left"),
        ]
        gaps = detect_perspective_gaps(perspectives)
        assert len(gaps) == 1
        assert gaps[0] == {
            "dimension": "political_leaning",
            "present": ["center-left", "left"],
            "missing": "right-leaning viewpoint",
        }

    def test_balanced_political_leaning_no_gap(self):
        perspectives = [
            _p(political_leaning="left"),
            _p(political_leaning="right"),
        ]
        assert detect_perspective_gaps(perspectives) == []

    def test_center_only_political_leaning_no_gap(self):
        """Center doesn't belong to either side, so it can't itself trigger
        a gap (there's no "side" present to be one-sided about)."""
        perspectives = [
            _p(political_leaning="center"),
            _p(political_leaning="center"),
        ]
        assert detect_perspective_gaps(perspectives) == []

    def test_one_sided_regional_flags_gap(self):
        perspectives = [_p(regional="local"), _p(regional="local")]
        gaps = detect_perspective_gaps(perspectives)
        assert len(gaps) == 1
        assert gaps[0] == {
            "dimension": "regional",
            "present": ["local"],
            "missing": "international viewpoint",
        }

    def test_national_only_regional_no_gap(self):
        """national is the neutral middle ground between local/international."""
        perspectives = [_p(regional="national"), _p(regional="national")]
        assert detect_perspective_gaps(perspectives) == []

    def test_multiple_dimensions_can_each_flag_a_gap(self):
        perspectives = [
            _p(stakeholder="business", political_leaning="left", regional="local"),
            _p(
                stakeholder="business",
                political_leaning="center-left",
                regional="local",
            ),
        ]
        gaps = detect_perspective_gaps(perspectives)
        dimensions = {g["dimension"] for g in gaps}
        assert dimensions == {"stakeholder", "political_leaning", "regional"}

    def test_none_entries_mixed_with_valid_ones_are_ignored(self):
        perspectives = [
            None,
            _p(stakeholder="business"),
            None,
            _p(stakeholder="business"),
        ]
        gaps = detect_perspective_gaps(perspectives)
        assert len(gaps) == 1
        assert gaps[0]["dimension"] == "stakeholder"

    def test_missing_dimension_values_dont_count_toward_threshold(self):
        """Two applicable articles, but neither has a stakeholder value set
        -- shouldn't meet the threshold for that dimension."""
        perspectives = [
            _p(political_leaning="left"),
            _p(political_leaning="left"),
        ]
        gaps = detect_perspective_gaps(perspectives)
        assert all(g["dimension"] != "stakeholder" for g in gaps)

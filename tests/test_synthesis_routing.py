"""
Tests for synthesis routing and context quality (#290).

Covers:
- classify_cluster_path(): simple clusters → 'standard', complex → 'deep'
- Routing thresholds (article count, topic diversity)
- Confidence gate decisions at boundary values
- Publish gate field mapping for all three decisions

These are pure-unit tests (no DB, no LLM) — they run in CI without external deps.
"""

from __future__ import annotations

import pytest

from app.context_manager import classify_cluster_path
from app.processing_states import StoryProcessingState
from app.publish_gate import (
    GateDecision,
    evaluate_confidence,
    gate_result_to_story_fields,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _articles(n: int, topic: str = "tech") -> list[dict]:
    return [{"id": i, "topic": topic, "title": f"Article {i}"} for i in range(n)]


def _diverse_articles(topics: list[str]) -> list[dict]:
    return [
        {"id": i, "topic": t, "title": f"Article {i}"} for i, t in enumerate(topics)
    ]


# ---------------------------------------------------------------------------
# classify_cluster_path — article count threshold
# ---------------------------------------------------------------------------


class TestClassifyClusterPathByArticleCount:
    """deep_min_articles default is 6 (from model_config.json)."""

    def test_empty_cluster_is_standard(self) -> None:
        assert classify_cluster_path([]) == "standard"

    def test_single_article_is_standard(self) -> None:
        assert classify_cluster_path(_articles(1)) == "standard"

    def test_five_articles_same_topic_is_standard(self) -> None:
        # 5 articles, 0% diversity (same topic) → standard
        assert classify_cluster_path(_articles(5)) == "standard"

    def test_six_articles_triggers_deep(self) -> None:
        # At threshold: 6 articles → deep regardless of topic
        assert classify_cluster_path(_articles(6)) == "deep"

    def test_ten_articles_is_deep(self) -> None:
        assert classify_cluster_path(_articles(10)) == "deep"


# ---------------------------------------------------------------------------
# classify_cluster_path — topic diversity threshold
# ---------------------------------------------------------------------------


class TestClassifyClusterPathByTopicDiversity:
    """deep_min_topic_diversity default is 0.6 (from model_config.json)."""

    def test_all_same_topic_below_threshold(self) -> None:
        # 5 articles, 1/5 = 0.2 diversity → standard
        articles = _diverse_articles(["AI", "AI", "AI", "AI", "AI"])
        assert classify_cluster_path(articles) == "standard"

    def test_two_out_of_three_unique_is_above_threshold(self) -> None:
        # 3 articles, 2 unique topics: 2/3 ≈ 0.67 > 0.6 → deep
        articles = _diverse_articles(["AI", "Security", "Security"])
        assert classify_cluster_path(articles) == "deep"

    def test_fully_diverse_topics_is_deep(self) -> None:
        # 4 articles, 4 unique topics: 1.0 diversity → deep
        articles = _diverse_articles(["AI", "Security", "Cloud", "Business"])
        assert classify_cluster_path(articles) == "deep"

    def test_just_below_diversity_threshold_is_standard(self) -> None:
        # 5 articles, 2 unique topics: 2/5 = 0.4 < 0.6 → standard
        articles = _diverse_articles(["AI", "AI", "AI", "Security", "Security"])
        assert classify_cluster_path(articles) == "standard"

    def test_exactly_at_diversity_threshold_is_deep(self) -> None:
        # 5 articles, 3 unique topics: 3/5 = 0.6 = threshold → deep
        articles = _diverse_articles(["AI", "AI", "Security", "Security", "Cloud"])
        assert classify_cluster_path(articles) == "deep"

    def test_missing_topic_field_treated_as_empty(self) -> None:
        # Articles with no topic → empty strings are stripped; no unique topics → standard
        articles = [{"id": i, "topic": ""} for i in range(3)]
        assert classify_cluster_path(articles) == "standard"

    def test_mixed_present_and_missing_topics(self) -> None:
        # 4 articles: 2 with topic, 2 without → only 2 count for diversity
        articles = [
            {"id": 0, "topic": "AI"},
            {"id": 1, "topic": "Security"},
            {"id": 2, "topic": ""},
            {"id": 3, "topic": ""},
        ]
        # 2 topics out of 2 articles with topics = 1.0 → deep
        assert classify_cluster_path(articles) == "deep"


# ---------------------------------------------------------------------------
# classify_cluster_path — count takes priority over diversity
# ---------------------------------------------------------------------------


class TestClassifyClusterPathPriority:
    """Article count check runs before topic diversity — either triggers deep."""

    def test_large_homogeneous_cluster_is_deep(self) -> None:
        # 6 same-topic articles → deep via count, even though diversity is 0
        articles = _diverse_articles(["AI"] * 6)
        assert classify_cluster_path(articles) == "deep"

    def test_small_diverse_cluster_is_deep_via_diversity(self) -> None:
        # 3 articles with 3 different topics → deep via diversity
        articles = _diverse_articles(["AI", "Security", "Cloud"])
        assert classify_cluster_path(articles) == "deep"

    def test_small_homogeneous_cluster_is_standard(self) -> None:
        # 3 same-topic articles → standard (neither count nor diversity trigger)
        articles = _diverse_articles(["AI", "AI", "AI"])
        assert classify_cluster_path(articles) == "standard"


# ---------------------------------------------------------------------------
# Publish gate — threshold boundary tests
# ---------------------------------------------------------------------------


class TestPublishGateBoundaries:
    """Verify HOLD/WARN/PUBLISH boundaries are exactly where configured."""

    # Default thresholds: hold=0.4, warn=0.65

    def test_score_zero_is_held(self) -> None:
        assert evaluate_confidence(0.0) == GateDecision.HOLD

    def test_score_just_below_hold_threshold_is_held(self) -> None:
        assert evaluate_confidence(0.399) == GateDecision.HOLD

    def test_score_at_hold_threshold_is_warned(self) -> None:
        # 0.4 is NOT below hold_threshold → WARN (hold < score)
        assert evaluate_confidence(0.4) == GateDecision.WARN

    def test_score_just_above_hold_is_warned(self) -> None:
        assert evaluate_confidence(0.401) == GateDecision.WARN

    def test_score_just_below_warn_threshold_is_warned(self) -> None:
        assert evaluate_confidence(0.649) == GateDecision.WARN

    def test_score_at_warn_threshold_is_published(self) -> None:
        # 0.65 is NOT below warn_threshold → PUBLISH
        assert evaluate_confidence(0.65) == GateDecision.PUBLISH

    def test_score_just_above_warn_is_published(self) -> None:
        assert evaluate_confidence(0.651) == GateDecision.PUBLISH

    def test_score_one_is_published(self) -> None:
        assert evaluate_confidence(1.0) == GateDecision.PUBLISH

    def test_none_score_always_publishes(self) -> None:
        assert evaluate_confidence(None) == GateDecision.PUBLISH

    def test_negative_score_is_held(self) -> None:
        # Edge case: negative score stays in HOLD range
        assert evaluate_confidence(-0.1) == GateDecision.HOLD


# ---------------------------------------------------------------------------
# Publish gate — field mapping
# ---------------------------------------------------------------------------


class TestPublishGateFieldMapping:
    """gate_result_to_story_fields must produce the exact DB values expected."""

    def test_hold_sets_held_status_and_failed_state(self) -> None:
        fields = gate_result_to_story_fields(GateDecision.HOLD)
        assert fields["status"] == "held"
        assert fields["processing_state"] == StoryProcessingState.FAILED.value
        assert fields["failure_stage"] == "confidence_gate"
        assert fields["confidence_warning"] is False

    def test_warn_sets_active_status_and_published_state_with_warning(self) -> None:
        fields = gate_result_to_story_fields(GateDecision.WARN)
        assert fields["status"] == "active"
        assert fields["processing_state"] == StoryProcessingState.PUBLISHED.value
        assert fields["failure_stage"] is None
        assert fields["confidence_warning"] is True

    def test_publish_sets_active_status_without_warning(self) -> None:
        fields = gate_result_to_story_fields(GateDecision.PUBLISH)
        assert fields["status"] == "active"
        assert fields["processing_state"] == StoryProcessingState.PUBLISHED.value
        assert fields["failure_stage"] is None
        assert fields["confidence_warning"] is False

    def test_all_decisions_have_required_keys(self) -> None:
        required = {"status", "processing_state", "failure_stage", "confidence_warning"}
        for decision in GateDecision:
            fields = gate_result_to_story_fields(decision)
            assert required.issubset(
                fields.keys()
            ), f"Decision {decision} missing keys: {required - fields.keys()}"

    def test_held_story_processing_state_matches_enum(self) -> None:
        fields = gate_result_to_story_fields(GateDecision.HOLD)
        # Value must match the string stored in the DB column
        assert fields["processing_state"] == "failed"

    def test_published_story_processing_state_matches_enum(self) -> None:
        for decision in (GateDecision.WARN, GateDecision.PUBLISH):
            fields = gate_result_to_story_fields(decision)
            assert fields["processing_state"] == "published"

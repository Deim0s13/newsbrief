"""
Tests for interest-based story ranking.
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest


class TestTopicNormalization:
    """Tests for topic name normalization."""

    def test_normalize_ai_ml_variations(self):
        from app.interests import _normalize_topic

        assert _normalize_topic("AI/ML") == "ai-ml"
        assert _normalize_topic("ai/ml") == "ai-ml"
        assert _normalize_topic("AI") == "ai-ml"
        assert _normalize_topic("ML") == "ai-ml"
        assert _normalize_topic("Machine Learning") == "ai-ml"

    def test_normalize_politics_variations(self):
        from app.interests import _normalize_topic

        assert _normalize_topic("Politics") == "politics"
        assert _normalize_topic("politics") == "politics"
        assert _normalize_topic("International Relations") == "politics"
        assert _normalize_topic("UK News") == "politics"

    def test_normalize_devtools_variations(self):
        from app.interests import _normalize_topic

        assert _normalize_topic("Software Development") == "devtools"
        assert _normalize_topic("Programming") == "devtools"
        assert _normalize_topic("DevTools") == "devtools"

    def test_normalize_cloud_variations(self):
        from app.interests import _normalize_topic

        assert _normalize_topic("Cloud Computing") == "cloud-k8s"
        assert _normalize_topic("Kubernetes") == "cloud-k8s"
        assert _normalize_topic("K8s") == "cloud-k8s"

    def test_normalize_unknown_returns_lowercase(self):
        from app.interests import _normalize_topic

        assert _normalize_topic("Unknown Topic") == "unknown topic"
        assert _normalize_topic("RANDOM") == "random"

    def test_normalize_strips_whitespace(self):
        from app.interests import _normalize_topic

        assert _normalize_topic("  AI/ML  ") == "ai-ml"
        assert _normalize_topic("\tPolitics\n") == "politics"


class TestInterestScoreCalculation:
    """Tests for interest score calculation."""

    def test_calculate_interest_score_high_interest_topics(self):
        from app.interests import calculate_interest_score

        # AI/ML has weight 1.5 in default config
        score = calculate_interest_score(["AI/ML"])
        assert score == 1.5

    def test_calculate_interest_score_low_interest_topics(self):
        from app.interests import calculate_interest_score

        # Politics has weight 0.5 in default config
        score = calculate_interest_score(["Politics"])
        assert score == 0.5

    def test_calculate_interest_score_multiple_topics_average(self):
        from app.interests import calculate_interest_score

        # AI/ML (1.5) + Security (1.2) = 2.7 / 2 = 1.35
        score = calculate_interest_score(["AI/ML", "Security"])
        assert score == pytest.approx(1.35, rel=0.01)

    def test_calculate_interest_score_empty_topics_returns_default(self):
        from app.interests import calculate_interest_score

        score = calculate_interest_score([])
        assert score == 1.0  # default_weight

    def test_calculate_interest_score_unknown_topic_uses_default(self):
        from app.interests import calculate_interest_score

        # Unknown topic should use default_weight (1.0)
        score = calculate_interest_score(["Unknown Topic"])
        assert score == 1.0


class TestBlendedScoreCalculation:
    """Tests for blended score calculation."""

    def test_calculate_blended_score_basic(self):
        from app.interests import calculate_blended_score

        # importance=0.8, interest=1.0 (normalized to 0.5)
        # blended = (0.8 * 0.6) + (0.5 * 0.4) = 0.48 + 0.2 = 0.68
        score = calculate_blended_score(0.8, 1.0)
        assert score == pytest.approx(0.68, rel=0.01)

    def test_calculate_blended_score_high_interest(self):
        from app.interests import calculate_blended_score

        # importance=0.5, interest=2.0 (normalized to 1.0)
        # blended = (0.5 * 0.6) + (1.0 * 0.4) = 0.3 + 0.4 = 0.7
        score = calculate_blended_score(0.5, 2.0)
        assert score == pytest.approx(0.7, rel=0.01)

    def test_calculate_blended_score_low_interest(self):
        from app.interests import calculate_blended_score

        # importance=0.9, interest=0.3 (normalized to 0.15)
        # blended = (0.9 * 0.6) + (0.15 * 0.4) = 0.54 + 0.06 = 0.6
        score = calculate_blended_score(0.9, 0.3)
        assert score == pytest.approx(0.6, rel=0.01)

    def test_calculate_blended_score_caps_interest_at_max(self):
        from app.interests import calculate_blended_score

        # Interest score above max should be capped at 1.0 after normalization
        score1 = calculate_blended_score(0.5, 2.0)  # At max
        score2 = calculate_blended_score(0.5, 3.0)  # Above max
        assert score1 == score2  # Both should cap at normalized 1.0


class TestStoryBlendedScore:
    """Tests for convenience function combining interest and blending."""

    def test_get_story_blended_score_high_interest(self):
        from app.interests import get_story_blended_score

        # High importance + high interest topics
        score = get_story_blended_score(0.8, ["AI/ML", "Security"])
        # interest = 1.35, normalized = 0.675
        # blended = (0.8 * 0.6) + (0.675 * 0.4) = 0.48 + 0.27 = 0.75
        assert score == pytest.approx(0.75, rel=0.02)

    def test_get_story_blended_score_low_interest(self):
        from app.interests import get_story_blended_score

        # High importance + low interest topics
        score = get_story_blended_score(0.8, ["Politics", "Sports"])
        # interest = 0.4, normalized = 0.2
        # blended = (0.8 * 0.6) + (0.2 * 0.4) = 0.48 + 0.08 = 0.56
        assert score == pytest.approx(0.56, rel=0.02)

    def test_high_interest_beats_low_interest_same_importance(self):
        from app.interests import get_story_blended_score

        high_interest = get_story_blended_score(0.8, ["AI/ML"])
        low_interest = get_story_blended_score(0.8, ["Politics"])

        assert high_interest > low_interest


class TestConfigLoading:
    """Tests for configuration loading."""

    def test_load_interests_config_returns_dict(self):
        from app.interests import load_interests_config

        config = load_interests_config()
        assert isinstance(config, dict)
        assert "enabled" in config
        assert "topic_weights" in config

    def test_is_interest_ranking_enabled(self):
        from app.interests import is_interest_ranking_enabled

        # Default config has enabled=True
        assert is_interest_ranking_enabled() is True

    def test_get_blend_weights_returns_tuple(self):
        from app.interests import get_blend_weights

        importance_weight, interest_weight = get_blend_weights()
        assert importance_weight == pytest.approx(0.6)
        assert interest_weight == pytest.approx(0.4)
        assert importance_weight + interest_weight == pytest.approx(1.0)

    def test_get_topic_weight_known_topic(self):
        from app.interests import get_topic_weight

        assert get_topic_weight("ai-ml") == 1.5
        assert get_topic_weight("politics") == 0.5

    def test_get_topic_weight_unknown_returns_default(self):
        from app.interests import get_topic_weight

        assert get_topic_weight("unknown-topic") == 1.0


class TestInterestsSummary:
    """Tests for interests summary."""

    def test_get_interests_summary_structure(self):
        from app.interests import get_interests_summary

        summary = get_interests_summary()
        assert "enabled" in summary
        assert "blend" in summary
        assert "topic_weights" in summary
        assert "default_weight" in summary

    def test_get_interests_summary_has_topics(self):
        from app.interests import get_interests_summary

        summary = get_interests_summary()
        topic_weights = summary["topic_weights"]
        assert "ai-ml" in topic_weights
        assert "politics" in topic_weights
        assert "security" in topic_weights


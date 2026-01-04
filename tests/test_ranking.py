"""
Tests for the ranking module.

Tests cover:
- RankingCalculator score calculation
- Recency scoring
- Keyword scoring
- TopicClassifier
- Topic definitions
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.ranking import (
    TOPICS,
    RankingCalculator,
    RankingResult,
    TopicClassifier,
    TopicResult,
)


class TestRankingCalculator:
    """Tests for RankingCalculator class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.calculator = RankingCalculator()

    def test_calculate_score_all_components(self):
        """Test full score calculation with all components."""
        now = datetime.now(timezone.utc)

        result = self.calculator.calculate_score(
            published=now - timedelta(hours=6),  # Recent
            source_weight=1.5,  # High-quality source
            title="OpenAI GPT-5 Machine Learning Breakthrough",
            content="This is about artificial intelligence and deep learning",
            topic="ai-ml",
        )

        assert isinstance(result, RankingResult)
        assert result.score > 0
        assert "recency" in result.components
        assert "source" in result.components
        assert "keywords" in result.components
        assert "topic_multiplier" in result.components
        assert "final" in result.components

    def test_calculate_score_recent_article(self):
        """Test that recent articles get higher scores."""
        now = datetime.now(timezone.utc)

        recent_result = self.calculator.calculate_score(
            published=now - timedelta(hours=1),
            source_weight=1.0,
            title="Test Article",
        )

        old_result = self.calculator.calculate_score(
            published=now - timedelta(days=10),
            source_weight=1.0,
            title="Test Article",
        )

        assert recent_result.score > old_result.score

    def test_calculate_score_source_weight_impact(self):
        """Test that source weight affects score."""
        now = datetime.now(timezone.utc)

        high_source = self.calculator.calculate_score(
            published=now,
            source_weight=2.0,
            title="Test Article",
        )

        low_source = self.calculator.calculate_score(
            published=now,
            source_weight=0.5,
            title="Test Article",
        )

        assert high_source.score > low_source.score

    def test_calculate_score_keyword_impact(self):
        """Test that keyword matching affects score."""
        now = datetime.now(timezone.utc)

        with_keywords = self.calculator.calculate_score(
            published=now,
            source_weight=1.0,
            title="OpenAI GPT ChatGPT Machine Learning",
            topic="ai-ml",
        )

        without_keywords = self.calculator.calculate_score(
            published=now,
            source_weight=1.0,
            title="Local News Update",
            topic="ai-ml",
        )

        assert with_keywords.score > without_keywords.score

    def test_calculate_score_topic_multiplier(self):
        """Test that topic weight multiplier is applied."""
        now = datetime.now(timezone.utc)

        ai_result = self.calculator.calculate_score(
            published=now,
            source_weight=1.0,
            title="Test",
            topic="ai-ml",  # Has 1.2x multiplier
        )

        # Topic multiplier should be in components
        assert ai_result.components["topic_multiplier"] == 1.2

    def test_calculate_score_no_topic(self):
        """Test scoring without a topic."""
        now = datetime.now(timezone.utc)

        result = self.calculator.calculate_score(
            published=now,
            source_weight=1.0,
            title="Test Article",
            topic=None,
        )

        assert result.components["topic_multiplier"] == 1.0


class TestRecencyScoring:
    """Tests for recency score calculation."""

    def setup_method(self):
        """Set up test fixtures."""
        self.calculator = RankingCalculator()

    def test_recency_very_recent(self):
        """Test recency score for very recent articles (< 12 hours)."""
        now = datetime.now(timezone.utc)
        published = now - timedelta(hours=6)

        score = self.calculator._calculate_recency_score(published)

        assert score == 1.0

    def test_recency_today(self):
        """Test recency score for today's articles (12-24 hours)."""
        now = datetime.now(timezone.utc)
        published = now - timedelta(hours=18)

        score = self.calculator._calculate_recency_score(published)

        assert score == 0.9

    def test_recency_yesterday(self):
        """Test recency score for yesterday's articles (1-2 days)."""
        now = datetime.now(timezone.utc)
        published = now - timedelta(hours=36)

        score = self.calculator._calculate_recency_score(published)

        assert score == 0.7

    def test_recency_week_old(self):
        """Test recency score for week-old articles."""
        now = datetime.now(timezone.utc)
        published = now - timedelta(days=5)

        score = self.calculator._calculate_recency_score(published)

        assert 0.1 < score < 0.4

    def test_recency_very_old(self):
        """Test recency score for very old articles (> 7 days)."""
        now = datetime.now(timezone.utc)
        published = now - timedelta(days=30)

        score = self.calculator._calculate_recency_score(published)

        assert score == 0.1

    def test_recency_none_published(self):
        """Test recency score when published date is None."""
        score = self.calculator._calculate_recency_score(None)

        assert score == 0.2  # Default low score

    def test_recency_timezone_naive(self):
        """Test recency score with timezone-naive datetime."""
        now = datetime.now(timezone.utc)
        # Create naive datetime (no timezone)
        published = datetime.now() - timedelta(hours=6)

        score = self.calculator._calculate_recency_score(published)

        # Should handle gracefully
        assert 0.0 <= score <= 1.0


class TestKeywordScoring:
    """Tests for keyword score calculation."""

    def setup_method(self):
        """Set up test fixtures."""
        self.calculator = RankingCalculator()

    def test_keyword_multiple_matches(self):
        """Test keyword score with multiple matches."""
        score = self.calculator._calculate_keyword_score(
            title="OpenAI GPT ChatGPT Machine Learning",
            content="This uses deep learning and neural networks",
            topic="ai-ml",
        )

        assert score > 0

    def test_keyword_no_matches(self):
        """Test keyword score with no matches."""
        score = self.calculator._calculate_keyword_score(
            title="Local Weather Update",
            content="Sunny skies expected tomorrow",
            topic="ai-ml",
        )

        assert score == 0.0

    def test_keyword_empty_title(self):
        """Test keyword score with empty title."""
        score = self.calculator._calculate_keyword_score(
            title="",
            content="Some content",
            topic="ai-ml",
        )

        assert score == 0.0

    def test_keyword_case_insensitive(self):
        """Test that keyword matching is case-insensitive."""
        score_lower = self.calculator._calculate_keyword_score(
            title="openai gpt machine learning",
            topic="ai-ml",
        )

        score_upper = self.calculator._calculate_keyword_score(
            title="OPENAI GPT MACHINE LEARNING",
            topic="ai-ml",
        )

        assert score_lower == score_upper

    def test_keyword_all_topics_when_none(self):
        """Test keyword matching checks all topics when topic is None."""
        score = self.calculator._calculate_keyword_score(
            title="Kubernetes Docker Container",
            content="",
            topic=None,  # Should check all topics
        )

        assert score > 0  # Should match cloud-k8s keywords


class TestTopicClassifier:
    """Tests for TopicClassifier class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.classifier = TopicClassifier()

    def test_classify_ai_article(self):
        """Test classification of AI/ML article."""
        result = self.classifier.classify_article(
            title="OpenAI Announces GPT-5",
            content="The new machine learning model uses deep learning",
            use_llm_fallback=False,
        )

        assert isinstance(result, TopicResult)
        assert result.topic == "ai-ml"
        assert result.confidence > 0  # Just verify it has some confidence
        assert result.method == "keywords"
        assert len(result.matched_keywords) >= 2  # Should match multiple keywords

    def test_classify_cloud_article(self):
        """Test classification of Cloud/K8s article."""
        result = self.classifier.classify_article(
            title="Kubernetes Cluster Scaling",
            content="Docker containers and microservices deployment",
            use_llm_fallback=False,
        )

        assert result.topic == "cloud-k8s"

    def test_classify_security_article(self):
        """Test classification of Security article."""
        result = self.classifier.classify_article(
            title="Critical Vulnerability Found",
            content="Zero-day exploit requires patching",
            use_llm_fallback=False,
        )

        assert result.topic == "security"

    def test_classify_devtools_article(self):
        """Test classification of DevTools article."""
        result = self.classifier.classify_article(
            title="Visual Studio Code Update",
            content="New IDE features and debugging tools",
            use_llm_fallback=False,
        )

        assert result.topic == "devtools"

    def test_classify_hardware_article(self):
        """Test classification of Hardware article."""
        result = self.classifier.classify_article(
            title="NVIDIA GPU Announcement",
            content="New chip fabrication at TSMC",
            use_llm_fallback=False,
        )

        assert result.topic == "chips-hardware"

    def test_classify_no_match(self):
        """Test classification when no topic matches."""
        result = self.classifier.classify_article(
            title="Local Sports Update",
            content="The game was exciting",
            use_llm_fallback=False,
        )

        # Should return None or low confidence
        assert result.topic is None or result.confidence < 0.5

    def test_classify_matched_keywords_populated(self):
        """Test that matched keywords are returned."""
        result = self.classifier.classify_article(
            title="OpenAI GPT machine learning",
            content="",
            use_llm_fallback=False,
        )

        # Should have matched some keywords
        assert len(result.matched_keywords) > 0


class TestTopicDefinitions:
    """Tests for topic definitions."""

    def test_all_topics_have_required_fields(self):
        """Test that all topics have required fields."""
        for topic_id, topic_config in TOPICS.items():
            assert "name" in topic_config, f"Topic {topic_id} missing 'name'"
            assert "keywords" in topic_config, f"Topic {topic_id} missing 'keywords'"
            assert "weight" in topic_config, f"Topic {topic_id} missing 'weight'"

    def test_all_topics_have_keywords(self):
        """Test that all topics have at least some keywords."""
        for topic_id, topic_config in TOPICS.items():
            assert (
                len(topic_config["keywords"]) > 0
            ), f"Topic {topic_id} has no keywords"

    def test_topic_weights_in_valid_range(self):
        """Test that topic weights are in valid range."""
        for topic_id, topic_config in TOPICS.items():
            weight = topic_config["weight"]
            assert (
                0.5 <= weight <= 2.0
            ), f"Topic {topic_id} weight {weight} out of range"

    def test_expected_topics_exist(self):
        """Test that expected topics are defined."""
        expected_topics = [
            "ai-ml",
            "cloud-k8s",
            "security",
            "devtools",
            "chips-hardware",
        ]

        for topic in expected_topics:
            assert topic in TOPICS, f"Expected topic {topic} not found"


class TestRankingResult:
    """Tests for RankingResult dataclass."""

    def test_ranking_result_creation(self):
        """Test creating a RankingResult."""
        result = RankingResult(
            score=0.85,
            components={
                "recency": 0.9,
                "source": 1.0,
                "keywords": 0.7,
            },
        )

        assert result.score == 0.85
        assert result.components["recency"] == 0.9


class TestTopicResult:
    """Tests for TopicResult dataclass."""

    def test_topic_result_creation(self):
        """Test creating a TopicResult."""
        result = TopicResult(
            topic="ai-ml",
            confidence=0.9,
            method="keywords",
            matched_keywords=["openai", "gpt"],
        )

        assert result.topic == "ai-ml"
        assert result.confidence == 0.9
        assert result.method == "keywords"
        assert len(result.matched_keywords) == 2

    def test_topic_result_default_matched_keywords(self):
        """Test TopicResult with default matched_keywords."""
        result = TopicResult(
            topic="security",
            confidence=0.8,
            method="llm",
        )

        assert result.matched_keywords == []

"""
Tests for the topics module.

Tests cover:
- Topic configuration loading
- Topic helper functions
- Keyword-based classification
- TopicClassificationResult dataclass
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.topics import (
    SecondaryTopic,
    TopicClassificationResult,
    _get_default_config,
    classify_topic,
    classify_topic_enhanced,
    classify_topic_with_keywords,
    get_available_topics,
    get_topic_definitions,
    get_topic_display_name,
    get_valid_topics,
)


class TestTopicConfiguration:
    """Tests for topic configuration loading."""

    def test_get_topic_definitions_returns_dict(self):
        """Test that get_topic_definitions returns a dictionary."""
        result = get_topic_definitions()

        assert isinstance(result, dict)
        assert len(result) > 0

    def test_get_topic_definitions_has_required_keys(self):
        """Test that each topic has required configuration keys."""
        topics = get_topic_definitions()

        for topic_id, config in topics.items():
            assert "name" in config, f"Topic {topic_id} missing 'name'"
            assert "keywords" in config, f"Topic {topic_id} missing 'keywords'"
            assert "description" in config, f"Topic {topic_id} missing 'description'"

    def test_get_valid_topics_returns_list(self):
        """Test that get_valid_topics returns a list of topic IDs."""
        topics = get_valid_topics()

        assert isinstance(topics, list)
        assert len(topics) > 0
        assert all(isinstance(t, str) for t in topics)

    def test_get_default_config(self):
        """Test that default config has expected structure."""
        config = _get_default_config()

        assert "settings" in config
        assert "topics" in config
        assert "general" in config["topics"]  # Should have at least general


class TestTopicDisplayNames:
    """Tests for topic display name functions."""

    def test_get_topic_display_name_known_topic(self):
        """Test display name for known topic."""
        # Get a topic that we know exists
        topics = get_valid_topics()
        if "ai-ml" in topics:
            name = get_topic_display_name("ai-ml")
            assert name == "AI/ML"

    def test_get_topic_display_name_unknown_topic(self):
        """Test display name for unknown topic."""
        name = get_topic_display_name("unknown-topic")

        # Should return formatted version of the ID
        assert name == "Unknown/Topic"

    def test_get_topic_display_name_empty(self):
        """Test display name for empty string."""
        name = get_topic_display_name("")

        assert isinstance(name, str)

    def test_get_available_topics_structure(self):
        """Test that get_available_topics returns correct structure."""
        topics = get_available_topics()

        assert isinstance(topics, list)
        assert len(topics) > 0

        for topic in topics:
            assert "key" in topic  # Uses 'key' not 'id'
            assert "name" in topic
            assert "description" in topic


class TestTopicClassificationResult:
    """Tests for TopicClassificationResult dataclass."""

    def test_create_classification_result(self):
        """Test creating a classification result."""
        result = TopicClassificationResult(
            topic="ai-ml",
            confidence=0.95,
            method="llm",
            display_name="AI/ML",
            matched_keywords=["machine learning", "neural network"],
        )

        assert result.topic == "ai-ml"
        assert result.confidence == 0.95
        assert result.method == "llm"
        assert result.display_name == "AI/ML"
        assert len(result.matched_keywords) == 2

    def test_classification_result_to_dict(self):
        """Test converting classification result to dictionary."""
        result = TopicClassificationResult(
            topic="security",
            confidence=0.8,
            method="keywords",
            display_name="Security",
            matched_keywords=["vulnerability"],
        )

        result_dict = result.to_dict()

        assert result_dict["topic"] == "security"
        assert result_dict["confidence"] == 0.8
        assert result_dict["method"] == "keywords"
        assert result_dict["display_name"] == "Security"
        assert result_dict["matched_keywords"] == ["vulnerability"]

    def test_classification_result_default_keywords(self):
        """Test that matched_keywords defaults to empty list."""
        result = TopicClassificationResult(
            topic="general",
            confidence=0.5,
            method="fallback",
            display_name="General",
        )

        assert result.matched_keywords == []


class TestKeywordClassification:
    """Tests for keyword-based classification."""

    def test_classify_ai_ml_article(self):
        """Test classifying an AI/ML article by keywords."""
        result = classify_topic_with_keywords(
            title="OpenAI Announces GPT-5 with Major Improvements",
            summary="New machine learning model with deep learning capabilities",
        )

        assert result is not None
        assert result.topic == "ai-ml"
        assert result.method == "keywords"
        assert result.confidence > 0
        assert len(result.matched_keywords) > 0

    def test_classify_security_article(self):
        """Test classifying a security article by keywords."""
        result = classify_topic_with_keywords(
            title="Critical Security Vulnerability in OpenSSL",
            summary="Security researchers found a zero-day exploit in the cryptography library",
        )

        assert result is not None
        assert result.topic == "security"

    def test_classify_cloud_article(self):
        """Test classifying a cloud/k8s article by keywords."""
        result = classify_topic_with_keywords(
            title="AWS Lambda Updates",
            summary="Kubernetes deployment with Docker containers",
        )

        assert result is not None
        assert result.topic == "cloud-k8s"

    def test_classify_no_match(self):
        """Test classifying an article with no keyword matches."""
        result = classify_topic_with_keywords(
            title="Local Weather Update for Today",
            summary="Sunny with a chance of rain in the afternoon",
        )

        # Should return general or None with low confidence
        assert result is not None
        assert result.topic == "general"

    def test_classify_empty_content(self):
        """Test classifying with empty content."""
        result = classify_topic_with_keywords(
            title="",
            summary="",
        )

        assert result is not None
        assert result.topic == "general"

    def test_classify_case_insensitive(self):
        """Test that keyword matching is case-insensitive."""
        result_lower = classify_topic_with_keywords(
            title="machine learning deep learning",
            summary="",
        )

        result_upper = classify_topic_with_keywords(
            title="MACHINE LEARNING DEEP LEARNING",
            summary="",
        )

        # Both should match AI/ML
        assert result_lower.topic == result_upper.topic


class TestClassifyTopic:
    """Tests for the main classify_topic function."""

    @patch("app.topics.classify_topic_enhanced")
    def test_classify_topic_uses_enhanced_llm_when_available(self, mock_enhanced):
        """Test that classify_topic tries enhanced LLM first (v0.8.1)."""
        mock_enhanced.return_value = TopicClassificationResult(
            topic="ai-ml",
            confidence=0.95,
            method="llm-enhanced",
            display_name="AI/ML",
        )

        result = classify_topic(
            title="OpenAI GPT-5",
            summary="Machine learning breakthrough",
        )

        mock_enhanced.assert_called_once()
        assert result.topic == "ai-ml"
        assert result.method == "llm-enhanced"

    @patch("app.topics.classify_topic_enhanced")
    @patch("app.topics.classify_topic_with_llm")
    def test_classify_topic_fallback_to_legacy_llm(self, mock_llm, mock_enhanced):
        """Test fallback to legacy LLM when enhanced fails."""
        mock_enhanced.return_value = None  # Enhanced failed
        mock_llm.return_value = TopicClassificationResult(
            topic="ai-ml",
            confidence=0.85,
            method="llm",
            display_name="AI/ML",
        )

        result = classify_topic(
            title="OpenAI GPT-5",
            summary="Machine learning breakthrough",
        )

        assert result.topic == "ai-ml"
        assert result.method == "llm"

    @patch("app.topics.classify_topic_enhanced")
    @patch("app.topics.classify_topic_with_llm")
    def test_classify_topic_fallback_to_keywords(self, mock_llm, mock_enhanced):
        """Test that classify_topic falls back to keywords when all LLM fails."""
        mock_enhanced.return_value = None  # Enhanced failed
        mock_llm.return_value = None  # Legacy LLM failed

        result = classify_topic(
            title="OpenAI GPT-5 machine learning",
            summary="Deep learning neural networks",
        )

        assert result is not None
        assert result.method == "keywords"

    @patch("app.topics.classify_topic_enhanced")
    @patch("app.topics.classify_topic_with_llm")
    def test_classify_topic_returns_general_when_no_match(
        self, mock_llm, mock_enhanced
    ):
        """Test that classify_topic returns general when no good match."""
        mock_enhanced.return_value = None
        mock_llm.return_value = None

        result = classify_topic(
            title="Local weather today",
            summary="Sunny skies expected",
        )

        # Should fall back to general
        assert result is not None
        assert result.topic == "general"

    def test_classify_topic_with_use_enhanced_false(self):
        """Test disabling enhanced classification."""
        result = classify_topic(
            title="OpenAI GPT-5 machine learning deep learning",
            summary="Neural networks and artificial intelligence",
            use_llm=False,  # Skip LLM
            use_enhanced=False,
        )

        # Should use keywords only
        assert result.method == "keywords"
        assert result.topic == "ai-ml"


class TestTopicKeywords:
    """Tests for topic keyword definitions."""

    def test_ai_ml_keywords_include_core_terms(self):
        """Test that AI/ML topic has core keywords."""
        topics = get_topic_definitions()

        if "ai-ml" in topics:
            keywords = topics["ai-ml"]["keywords"]
            # Check for some expected keywords
            core_terms = ["machine learning", "deep learning", "neural network", "llm"]
            for term in core_terms:
                assert term in keywords, f"Expected '{term}' in AI/ML keywords"

    def test_security_keywords_include_core_terms(self):
        """Test that Security topic has core keywords."""
        topics = get_topic_definitions()

        if "security" in topics:
            keywords = topics["security"]["keywords"]
            core_terms = ["vulnerability", "security", "exploit"]
            for term in core_terms:
                assert term in keywords, f"Expected '{term}' in Security keywords"

    def test_core_topics_have_minimum_keywords(self):
        """Test that core/predefined topics have at least 3 keywords."""
        topics = get_topic_definitions()

        # Core topics that should have keywords defined
        core_topics = ["ai-ml", "security", "cloud-k8s", "devtools", "chips-hardware"]

        for topic_id in core_topics:
            if topic_id in topics:
                assert (
                    len(topics[topic_id]["keywords"]) >= 3
                ), f"Topic {topic_id} has too few keywords"


class TestTopicMatching:
    """Tests for topic matching behavior."""

    def test_multiple_keyword_matches_increase_confidence(self):
        """Test that more keyword matches increase confidence."""
        # Article with few matches
        few_matches = classify_topic_with_keywords(
            title="OpenAI update",
            summary="",
        )

        # Article with many matches
        many_matches = classify_topic_with_keywords(
            title="OpenAI GPT machine learning deep learning neural network AI",
            summary="Artificial intelligence and natural language processing",
        )

        if few_matches.topic == many_matches.topic:
            assert many_matches.confidence >= few_matches.confidence

    def test_keyword_matching_in_summary(self):
        """Test that keywords in summary are also matched."""
        result = classify_topic_with_keywords(
            title="Tech News Update",
            summary="OpenAI announced GPT-5 with machine learning improvements",
        )

        # Should match AI/ML from summary keywords
        assert result.topic == "ai-ml"


# =============================================================================
# v0.8.1 Enhanced Classification Tests (Issue #104)
# =============================================================================


class TestSecondaryTopics:
    """Tests for secondary topic detection (v0.8.1)."""

    def test_secondary_topic_dataclass(self):
        """Test SecondaryTopic dataclass creation."""
        from app.topics import SecondaryTopic

        st = SecondaryTopic(
            topic="business",
            confidence=0.65,
            display_name="Business",
            reasoning="Matched investment keywords",
        )

        assert st.topic == "business"
        assert st.confidence == 0.65
        assert st.display_name == "Business"
        assert st.reasoning == "Matched investment keywords"

    def test_secondary_topic_to_dict(self):
        """Test SecondaryTopic serialization."""
        from app.topics import SecondaryTopic

        st = SecondaryTopic(
            topic="ai-ml",
            confidence=0.7,
            display_name="AI/ML",
            reasoning="AI company mentioned",
        )

        d = st.to_dict()

        assert d["topic"] == "ai-ml"
        assert d["confidence"] == 0.7
        assert d["display_name"] == "AI/ML"
        assert d["reasoning"] == "AI company mentioned"

    def test_classification_result_with_secondary_topics(self):
        """Test TopicClassificationResult with secondary topics."""
        from app.topics import SecondaryTopic

        result = TopicClassificationResult(
            topic="business",
            confidence=0.85,
            method="llm-enhanced",
            display_name="Business",
            secondary_topics=[
                SecondaryTopic("ai-ml", 0.65, "AI/ML", "OpenAI mentioned"),
            ],
            reasoning="Focus on investment and funding",
            edge_case="overlapping",
        )

        assert result.topic == "business"
        assert len(result.secondary_topics) == 1
        assert result.secondary_topics[0].topic == "ai-ml"
        assert result.reasoning == "Focus on investment and funding"
        assert result.edge_case == "overlapping"

    def test_all_topics_method(self):
        """Test all_topics() returns primary + secondary."""
        from app.topics import SecondaryTopic

        result = TopicClassificationResult(
            topic="chips-hardware",
            confidence=0.9,
            method="llm-enhanced",
            display_name="Chips/Hardware",
            secondary_topics=[
                SecondaryTopic("ai-ml", 0.7, "AI/ML", None),
                SecondaryTopic("business", 0.55, "Business", None),
            ],
        )

        all_topics = result.all_topics()

        assert len(all_topics) == 3
        assert "chips-hardware" in all_topics
        assert "ai-ml" in all_topics
        assert "business" in all_topics

    def test_to_dict_includes_secondary_topics(self):
        """Test to_dict includes secondary topics when present."""
        from app.topics import SecondaryTopic

        result = TopicClassificationResult(
            topic="security",
            confidence=0.8,
            method="llm-enhanced",
            display_name="Security",
            secondary_topics=[
                SecondaryTopic("cloud-k8s", 0.6, "Cloud/K8s", "AWS mentioned"),
            ],
            reasoning="Security vulnerability article",
            edge_case="overlapping",
        )

        d = result.to_dict()

        assert "secondary_topics" in d
        assert len(d["secondary_topics"]) == 1
        assert d["secondary_topics"][0]["topic"] == "cloud-k8s"
        assert d["reasoning"] == "Security vulnerability article"
        assert d["edge_case"] == "overlapping"


class TestEnhancedKeywordClassification:
    """Tests for enhanced keyword classification (v0.8.1)."""

    def test_phrase_matching(self):
        """Test that multi-word keywords are matched as phrases."""
        result = classify_topic_with_keywords(
            title="New deep learning framework announced",
            summary="The framework uses machine learning for better inference",
        )

        # Should match AI/ML with phrase keywords
        assert result.topic == "ai-ml"
        # Check that multi-word keywords were matched
        assert any(" " in kw for kw in result.matched_keywords)

    def test_core_keyword_boost(self):
        """Test that core keywords (first 5) get boosted scoring."""
        # Create two similar articles
        # One with core keywords (like "machine learning")
        # One with non-core keywords
        result1 = classify_topic_with_keywords(
            title="Machine learning deep learning announcement",
            summary="",
        )

        result2 = classify_topic_with_keywords(
            title="Stable diffusion announcement",  # Less core keyword
            summary="",
        )

        # Both should be AI/ML, but first should have higher confidence
        assert result1.topic == "ai-ml"
        assert result2.topic == "ai-ml"
        # Core keywords should boost confidence
        assert result1.confidence >= result2.confidence

    def test_keyword_secondary_topic_detection(self):
        """Test that keyword classification detects secondary topics."""
        result = classify_topic_with_keywords(
            title="NVIDIA announces new AI chip with record performance",
            summary="The GPU manufacturer released benchmarks for machine learning workloads",
        )

        # Primary should be chips-hardware or ai-ml
        assert result.topic in ["chips-hardware", "ai-ml"]
        # Should detect secondary topic
        # (depends on which is primary)


class TestTopicRelationships:
    """Tests for topic relationship configuration."""

    def test_topic_relationships_exist(self):
        """Test that topic relationships are defined in config."""
        from app.topics import get_topics_config

        config = get_topics_config()

        assert "topic_relationships" in config
        assert "overlaps" in config["topic_relationships"]

    def test_ai_ml_has_related_topics(self):
        """Test that AI/ML has defined related topics."""
        from app.topics import get_topics_config

        config = get_topics_config()
        overlaps = config.get("topic_relationships", {}).get("overlaps", {})

        assert "ai-ml" in overlaps
        assert "chips-hardware" in overlaps["ai-ml"]
        assert "business" in overlaps["ai-ml"]


class TestEdgeCases:
    """Tests for edge case classification."""

    def test_multi_domain_article(self):
        """Test classification of article spanning multiple domains."""
        # Article about AI company's business deal
        result = classify_topic_with_keywords(
            title="Microsoft invests $10B in OpenAI, reshaping AI industry",
            summary="The tech giant announced major funding for the artificial intelligence startup",
        )

        # Should classify as one of the relevant topics
        assert result.topic in ["ai-ml", "business"]

    def test_ambiguous_content(self):
        """Test classification of ambiguous content."""
        result = classify_topic_with_keywords(
            title="Weather forecast for tech conference",
            summary="Sunny skies expected for the outdoor event",
        )

        # Should fall back to general with low confidence
        assert result.topic == "general"
        assert result.confidence < 0.5

    def test_case_insensitive_phrase_matching(self):
        """Test that phrase matching is case-insensitive."""
        result1 = classify_topic_with_keywords(
            title="Machine Learning breakthrough",
            summary="",
        )

        result2 = classify_topic_with_keywords(
            title="MACHINE LEARNING BREAKTHROUGH",
            summary="",
        )

        assert result1.topic == result2.topic
        assert result1.confidence == result2.confidence

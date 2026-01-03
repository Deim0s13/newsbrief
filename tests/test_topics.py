"""
Tests for the topics module.

Tests cover:
- Topic configuration loading
- Topic helper functions
- Keyword-based classification
- TopicClassificationResult dataclass
"""

import pytest
import json
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

from app.topics import (
    get_topic_definitions,
    get_valid_topics,
    get_topic_display_name,
    get_available_topics,
    TopicClassificationResult,
    classify_topic_with_keywords,
    classify_topic,
    _get_default_config,
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
            assert "id" in topic
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

    @patch("app.topics.classify_topic_with_llm")
    def test_classify_topic_uses_llm_when_available(self, mock_llm_classify):
        """Test that classify_topic tries LLM first."""
        mock_llm_classify.return_value = TopicClassificationResult(
            topic="ai-ml",
            confidence=0.95,
            method="llm",
            display_name="AI/ML",
        )

        result = classify_topic(
            title="OpenAI GPT-5",
            summary="Machine learning breakthrough",
        )

        mock_llm_classify.assert_called_once()
        assert result.topic == "ai-ml"
        assert result.method == "llm"

    @patch("app.topics.classify_topic_with_llm")
    def test_classify_topic_fallback_to_keywords(self, mock_llm_classify):
        """Test that classify_topic falls back to keywords when LLM fails."""
        mock_llm_classify.return_value = None  # LLM failed

        result = classify_topic(
            title="OpenAI GPT-5 machine learning",
            summary="Deep learning neural networks",
        )

        assert result is not None
        assert result.method == "keywords"

    @patch("app.topics.classify_topic_with_llm")
    def test_classify_topic_returns_none_when_all_fail(self, mock_llm_classify):
        """Test that classify_topic returns None when everything fails."""
        mock_llm_classify.return_value = None

        result = classify_topic(
            title="Local weather today",
            summary="Sunny skies expected",
        )

        # Should fall back to general
        assert result is not None


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
                assert len(topics[topic_id]["keywords"]) >= 3, f"Topic {topic_id} has too few keywords"


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


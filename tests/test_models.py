#!/usr/bin/env python3
"""
Test script for story model validation and JSON serialization.
Validates that StoryOut validators and serialization helpers work correctly.
"""
from datetime import datetime

import pytest

from app.models import (
    StoryOut,
    deserialize_story_json_field,
    serialize_story_json_field,
)


def test_valid_story():
    """Test that valid story data passes validation."""
    story = StoryOut(
        id=1,
        title="Google Announces Gemini 2.0 with Multimodal Capabilities",
        synthesis="Google unveiled Gemini 2.0 today, their next-generation AI model featuring native image and video understanding. The model shows significant improvements over GPT-4.",
        key_points=[
            "Released December 2024",
            "Native multimodal processing",
            "2x faster than Gemini 1.5",
        ],
        article_count=5,
        importance_score=0.85,
        freshness_score=0.92,
        generated_at=datetime.now(),
    )
    assert story.title == "Google Announces Gemini 2.0 with Multimodal Capabilities"


def test_title_too_short():
    """Test that title < 10 chars fails."""
    with pytest.raises(ValueError, match="at least 10 characters"):
        StoryOut(
            id=1,
            title="Short",
            synthesis="A" * 100,
            key_points=["A", "B", "C"],
            article_count=1,
            generated_at=datetime.now(),
        )


def test_title_too_long():
    """Test that title > 200 chars fails."""
    with pytest.raises(ValueError, match="must not exceed 200"):
        StoryOut(
            id=1,
            title="A" * 250,
            synthesis="B" * 100,
            key_points=["A", "B", "C"],
            article_count=1,
            generated_at=datetime.now(),
        )


def test_synthesis_too_short():
    """Test that synthesis < 50 chars fails."""
    with pytest.raises(ValueError, match="at least 50 characters"):
        StoryOut(
            id=1,
            title="Valid Title Here",
            synthesis="Too short",
            key_points=["A", "B", "C"],
            article_count=1,
            generated_at=datetime.now(),
        )


def test_synthesis_long_quality_output():
    """Test that long synthesis from quality models (up to 5000 chars) is accepted."""
    # Simulate quality model output (~2000 chars)
    long_synthesis = "A comprehensive analysis. " * 80  # ~2080 chars
    story = StoryOut(
        id=1,
        title="Quality Model Generated Story",
        synthesis=long_synthesis,
        key_points=["Point 1", "Point 2", "Point 3"],
        article_count=3,
        generated_at=datetime.now(),
    )
    assert len(story.synthesis) > 1000, "Long synthesis should be accepted"


def test_synthesis_too_long():
    """Test that synthesis > 5000 chars fails."""
    with pytest.raises(ValueError, match="must not exceed 5000"):
        StoryOut(
            id=1,
            title="Valid Title Here",
            synthesis="A" * 5500,  # Exceeds 5000 limit
            key_points=["A", "B", "C"],
            article_count=1,
            generated_at=datetime.now(),
        )


def test_key_points_too_few():
    """Test that < 3 key points gets auto-padded (lenient for LLM inconsistency)."""
    story = StoryOut(
        id=1,
        title="Valid Title Here",
        synthesis="A" * 100,
        key_points=["Only one", "Only two"],
        article_count=1,
        generated_at=datetime.now(),
    )
    assert (
        len(story.key_points) == 3
    ), f"Expected 3 key points (padded), got {len(story.key_points)}"


def test_key_points_empty_list_does_not_hang():
    """Zero key points must still terminate padding, not loop forever (regression)."""
    story = StoryOut(
        id=1,
        title="Valid Title Here",
        synthesis="A" * 100,
        key_points=[],
        article_count=1,
        generated_at=datetime.now(),
    )
    assert (
        len(story.key_points) == 3
    ), f"Expected 3 key points (padded), got {len(story.key_points)}"


def test_key_points_too_many():
    """Test that > 8 key points gets auto-truncated (lenient for LLM inconsistency)."""
    story = StoryOut(
        id=1,
        title="Valid Title Here",
        synthesis="A" * 100,
        key_points=["1", "2", "3", "4", "5", "6", "7", "8", "9", "10"],
        article_count=1,
        generated_at=datetime.now(),
    )
    assert (
        len(story.key_points) == 8
    ), f"Expected 8 key points (truncated), got {len(story.key_points)}"


def test_importance_score_out_of_range():
    """Test that score > 1.0 fails."""
    with pytest.raises(ValueError, match="between 0.0 and 1.0"):
        StoryOut(
            id=1,
            title="Valid Title Here",
            synthesis="A" * 100,
            key_points=["A", "B", "C"],
            article_count=1,
            importance_score=1.5,
            generated_at=datetime.now(),
        )


def test_freshness_score_negative():
    """Test that score < 0.0 fails."""
    with pytest.raises(ValueError, match="between 0.0 and 1.0"):
        StoryOut(
            id=1,
            title="Valid Title Here",
            synthesis="A" * 100,
            key_points=["A", "B", "C"],
            article_count=1,
            freshness_score=-0.1,
            generated_at=datetime.now(),
        )


def test_article_count_zero():
    """Test that article_count < 1 fails."""
    with pytest.raises(ValueError, match="at least 1 article"):
        StoryOut(
            id=1,
            title="Valid Title Here",
            synthesis="A" * 100,
            key_points=["A", "B", "C"],
            article_count=0,
            generated_at=datetime.now(),
        )


def test_whitespace_stripping():
    """Test that whitespace is stripped from title and synthesis."""
    story = StoryOut(
        id=1,
        title="  Title With Whitespace  ",
        synthesis="  " + ("A" * 100) + "  ",
        key_points=["  Point 1  ", "  Point 2  ", "  Point 3  "],
        article_count=1,
        generated_at=datetime.now(),
    )
    assert story.title == "Title With Whitespace", "Title not stripped"
    assert story.synthesis == "A" * 100, "Synthesis not stripped"
    assert story.key_points == [
        "Point 1",
        "Point 2",
        "Point 3",
    ], "Key points not stripped"


def test_json_serialization_roundtrip():
    """Test JSON serialization and deserialization."""
    topics = ["AI/ML", "Cloud", "Security"]
    json_str = serialize_story_json_field(topics)
    result = deserialize_story_json_field(json_str)
    assert result == topics, f"Round-trip failed: {result} != {topics}"


def test_json_none_input():
    """Test that None input returns empty list."""
    result = deserialize_story_json_field(None)
    assert result == [], f"None should return empty list, got: {result}"


def test_json_invalid_input():
    """Test that invalid JSON returns empty list."""
    result = deserialize_story_json_field("invalid{json")
    assert result == [], f"Invalid JSON should return empty list, got: {result}"


def test_json_unicode():
    """Test Unicode handling in JSON fields."""
    topics = ["AI/ML", "日本語", "Español", "🚀"]
    json_str = serialize_story_json_field(topics)
    result = deserialize_story_json_field(json_str)
    assert result == topics, f"Unicode round-trip failed: {result} != {topics}"


def test_json_empty_list():
    """Test empty list serialization."""
    json_str = serialize_story_json_field([])
    result = deserialize_story_json_field(json_str)
    assert result == [], f"Empty list round-trip failed: {result}"

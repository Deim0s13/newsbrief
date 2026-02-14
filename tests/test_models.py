#!/usr/bin/env python3
"""
Test script for story model validation and JSON serialization.
Validates that StoryOut validators and serialization helpers work correctly.
"""
from datetime import datetime

from app.models import (
    StoryOut,
    deserialize_story_json_field,
    serialize_story_json_field,
)


def test_valid_story():
    """Test that valid story data passes validation."""
    try:
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
        return True, "Valid story creation"
    except Exception as e:
        return False, f"Valid story creation: {e}"


def test_title_too_short():
    """Test that title < 10 chars fails."""
    try:
        StoryOut(
            id=1,
            title="Short",
            synthesis="A" * 100,
            key_points=["A", "B", "C"],
            article_count=1,
            generated_at=datetime.now(),
        )
        return False, "Title too short - should have raised ValueError"
    except ValueError as e:
        if "at least 10 characters" in str(e):
            return True, "Title too short validation"
        return False, f"Wrong error message: {e}"


def test_title_too_long():
    """Test that title > 200 chars fails."""
    try:
        StoryOut(
            id=1,
            title="A" * 250,
            synthesis="B" * 100,
            key_points=["A", "B", "C"],
            article_count=1,
            generated_at=datetime.now(),
        )
        return False, "Title too long - should have raised ValueError"
    except ValueError as e:
        if "must not exceed 200" in str(e):
            return True, "Title too long validation"
        return False, f"Wrong error message: {e}"


def test_synthesis_too_short():
    """Test that synthesis < 50 chars fails."""
    try:
        StoryOut(
            id=1,
            title="Valid Title Here",
            synthesis="Too short",
            key_points=["A", "B", "C"],
            article_count=1,
            generated_at=datetime.now(),
        )
        return False, "Synthesis too short - should have raised ValueError"
    except ValueError as e:
        if "at least 50 characters" in str(e):
            return True, "Synthesis too short validation"
        return False, f"Wrong error message: {e}"


def test_synthesis_long_quality_output():
    """Test that long synthesis from quality models (up to 5000 chars) is accepted."""
    try:
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
        return True, "Long synthesis (quality model) validation"
    except Exception as e:
        return False, f"Long synthesis rejected: {e}"


def test_synthesis_too_long():
    """Test that synthesis > 5000 chars fails."""
    try:
        StoryOut(
            id=1,
            title="Valid Title Here",
            synthesis="A" * 5500,  # Exceeds 5000 limit
            key_points=["A", "B", "C"],
            article_count=1,
            generated_at=datetime.now(),
        )
        return False, "Synthesis too long - should have raised ValueError"
    except ValueError as e:
        if "must not exceed 5000" in str(e):
            return True, "Synthesis too long validation"
        return False, f"Wrong error message: {e}"


def test_key_points_too_few():
    """Test that < 3 key points gets auto-padded (lenient for LLM inconsistency)."""
    try:
        story = StoryOut(
            id=1,
            title="Valid Title Here",
            synthesis="A" * 100,
            key_points=["Only one", "Only two"],
            article_count=1,
            generated_at=datetime.now(),
        )
        # Should auto-pad to 3 key points
        if len(story.key_points) == 3:
            return True, "Key points minimum validation (auto-padded)"
        return False, f"Expected 3 key points (padded), got {len(story.key_points)}"
    except Exception as e:
        return False, f"Unexpected error: {e}"


def test_key_points_too_many():
    """Test that > 8 key points gets auto-truncated (lenient for LLM inconsistency)."""
    try:
        story = StoryOut(
            id=1,
            title="Valid Title Here",
            synthesis="A" * 100,
            key_points=["1", "2", "3", "4", "5", "6", "7", "8", "9", "10"],
            article_count=1,
            generated_at=datetime.now(),
        )
        # Should auto-truncate to 8 key points
        if len(story.key_points) == 8:
            return True, "Key points maximum validation (auto-truncated)"
        return False, f"Expected 8 key points (truncated), got {len(story.key_points)}"
    except Exception as e:
        return False, f"Unexpected error: {e}"


def test_importance_score_out_of_range():
    """Test that score > 1.0 fails."""
    try:
        StoryOut(
            id=1,
            title="Valid Title Here",
            synthesis="A" * 100,
            key_points=["A", "B", "C"],
            article_count=1,
            importance_score=1.5,
            generated_at=datetime.now(),
        )
        return False, "Score > 1.0 - should have raised ValueError"
    except ValueError as e:
        if "between 0.0 and 1.0" in str(e):
            return True, "Importance score range validation"
        return False, f"Wrong error message: {e}"


def test_freshness_score_negative():
    """Test that score < 0.0 fails."""
    try:
        StoryOut(
            id=1,
            title="Valid Title Here",
            synthesis="A" * 100,
            key_points=["A", "B", "C"],
            article_count=1,
            freshness_score=-0.1,
            generated_at=datetime.now(),
        )
        return False, "Score < 0.0 - should have raised ValueError"
    except ValueError as e:
        if "between 0.0 and 1.0" in str(e):
            return True, "Freshness score range validation"
        return False, f"Wrong error message: {e}"


def test_article_count_zero():
    """Test that article_count < 1 fails."""
    try:
        StoryOut(
            id=1,
            title="Valid Title Here",
            synthesis="A" * 100,
            key_points=["A", "B", "C"],
            article_count=0,
            generated_at=datetime.now(),
        )
        return False, "Article count 0 - should have raised ValueError"
    except ValueError as e:
        if "at least 1 article" in str(e):
            return True, "Article count minimum validation"
        return False, f"Wrong error message: {e}"


def test_whitespace_stripping():
    """Test that whitespace is stripped from title and synthesis."""
    try:
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
        return True, "Whitespace stripping"
    except Exception as e:
        return False, f"Whitespace stripping: {e}"


def test_json_serialization_roundtrip():
    """Test JSON serialization and deserialization."""
    try:
        topics = ["AI/ML", "Cloud", "Security"]
        json_str = serialize_story_json_field(topics)
        result = deserialize_story_json_field(json_str)
        assert result == topics, f"Round-trip failed: {result} != {topics}"
        return True, "JSON serialization round-trip"
    except Exception as e:
        return False, f"JSON round-trip: {e}"


def test_json_none_input():
    """Test that None input returns empty list."""
    try:
        result = deserialize_story_json_field(None)
        assert result == [], f"None should return empty list, got: {result}"
        return True, "JSON None input handling"
    except Exception as e:
        return False, f"JSON None handling: {e}"


def test_json_invalid_input():
    """Test that invalid JSON returns empty list."""
    try:
        result = deserialize_story_json_field("invalid{json")
        assert result == [], f"Invalid JSON should return empty list, got: {result}"
        return True, "JSON invalid input handling"
    except Exception as e:
        return False, f"JSON invalid handling: {e}"


def test_json_unicode():
    """Test Unicode handling in JSON fields."""
    try:
        topics = ["AI/ML", "日本語", "Español", "🚀"]
        json_str = serialize_story_json_field(topics)
        result = deserialize_story_json_field(json_str)
        assert result == topics, f"Unicode round-trip failed: {result} != {topics}"
        return True, "JSON Unicode handling"
    except Exception as e:
        return False, f"JSON Unicode: {e}"


def test_json_empty_list():
    """Test empty list serialization."""
    try:
        json_str = serialize_story_json_field([])
        result = deserialize_story_json_field(json_str)
        assert result == [], f"Empty list round-trip failed: {result}"
        return True, "JSON empty list handling"
    except Exception as e:
        return False, f"JSON empty list: {e}"


def main():
    """Run all tests and report results."""
    print("🧪 Testing Story Model Validation and Serialization\n")
    print("=" * 60)

    tests = [
        # Validation tests
        test_valid_story,
        test_title_too_short,
        test_title_too_long,
        test_synthesis_too_short,
        test_synthesis_long_quality_output,
        test_synthesis_too_long,
        test_key_points_too_few,
        test_key_points_too_many,
        test_importance_score_out_of_range,
        test_freshness_score_negative,
        test_article_count_zero,
        test_whitespace_stripping,
        # JSON serialization tests
        test_json_serialization_roundtrip,
        test_json_none_input,
        test_json_invalid_input,
        test_json_unicode,
        test_json_empty_list,
    ]

    passed = 0
    failed = 0

    for test in tests:
        success, message = test()
        if success:
            print(f"✅ {message}")
            passed += 1
        else:
            print(f"❌ {message}")
            failed += 1

    print("=" * 60)
    print(f"\n📊 Summary: {passed}/{len(tests)} tests passed")

    if failed > 0:
        print(f"❌ {failed} tests failed")
        return 1
    else:
        print("✅ All tests passed!")
        return 0


if __name__ == "__main__":
    exit(main())

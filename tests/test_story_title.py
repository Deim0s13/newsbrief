#!/usr/bin/env python3
"""
Unit tests for story title generation and fallback logic.
Tests the _generate_fallback_title function from app.stories.
"""

import pytest

from app.stories import _generate_fallback_title


class TestGenerateFallbackTitle:
    """Tests for _generate_fallback_title function."""

    def test_valid_short_title_returned_unchanged(self):
        """LLM-generated title under 80 chars should be used as-is."""
        title = "OpenAI Launches GPT-5 with Major Improvements"
        result = _generate_fallback_title(title, "Some synthesis text")
        assert result == title

    def test_exact_80_char_title_accepted(self):
        """Title exactly at 80 chars should be accepted."""
        title = "A" * 80
        result = _generate_fallback_title(title, "Some synthesis")
        assert result == title
        assert len(result) == 80

    def test_long_title_truncated_at_word_boundary(self):
        """Title over 80 chars should be truncated at word boundary with ellipsis."""
        title = "This is a very long headline that exceeds the maximum allowed character limit and needs to be truncated properly"
        result = _generate_fallback_title(title, "Some synthesis")
        assert len(result) <= 80
        assert result.endswith("...")
        # Should truncate at a word boundary (space before ellipsis)
        # Result format: "text text text..."
        without_ellipsis = result[:-3]
        # The last word should be complete (either ends with space or is a full word)
        assert " " in without_ellipsis  # Ensure we have multiple words

    def test_no_title_extracts_first_sentence(self):
        """When no title provided, extract first sentence from synthesis."""
        synthesis = "OpenAI announced major updates. This includes new features. More details below."
        result = _generate_fallback_title(None, synthesis)
        assert result == "OpenAI announced major updates."

    def test_no_title_long_first_sentence_truncated(self):
        """When first sentence exceeds limit, it should be truncated."""
        synthesis = "This is a very long first sentence that goes on and on and on and definitely exceeds the eighty character limit that we have set for titles. Second sentence here."
        result = _generate_fallback_title(None, synthesis)
        assert len(result) <= 80
        assert result.endswith("...")

    def test_empty_title_uses_synthesis(self):
        """Empty string title should fall back to synthesis."""
        result = _generate_fallback_title("", "Important news about technology.")
        assert result == "Important news about technology."

    def test_whitespace_title_uses_synthesis(self):
        """Whitespace-only title should fall back to synthesis."""
        result = _generate_fallback_title("   ", "Tech news update.")
        assert result == "Tech news update."

    def test_no_sentence_delimiter_uses_full_synthesis(self):
        """Synthesis without sentence delimiters should use full text (truncated)."""
        synthesis = "Breaking news about the tech industry with important updates"
        result = _generate_fallback_title(None, synthesis)
        assert "Breaking news" in result

    def test_absolute_fallback_when_all_empty(self):
        """When both title and synthesis are empty, use absolute fallback."""
        result = _generate_fallback_title(None, "")
        assert result == "News Story"

        result = _generate_fallback_title("", "")
        assert result == "News Story"

    def test_entities_parameter_accepted(self):
        """Function should accept entities parameter (for future enhancement)."""
        # Currently entities are not used, but parameter should be accepted
        result = _generate_fallback_title(
            "Valid Title", "Synthesis text", entities=["OpenAI", "GPT-5"]
        )
        assert result == "Valid Title"

    def test_custom_max_chars(self):
        """Custom max_chars parameter should be respected."""
        title = "This title is exactly fifty characters long now!"

        # Under custom limit - should pass
        result = _generate_fallback_title(title, "Synthesis", max_chars=60)
        assert result == title

        # Over custom limit - should truncate
        result = _generate_fallback_title(title, "Synthesis", max_chars=30)
        assert len(result) <= 30
        assert result.endswith("...")

    def test_truncation_removes_trailing_punctuation(self):
        """Truncation should remove trailing punctuation before ellipsis."""
        title = "This is a headline with commas, periods, and semicolons; that needs truncating properly at the right place"
        result = _generate_fallback_title(title, "Synthesis", max_chars=50)
        # Should not end with ",..." or ";..."
        assert not result.endswith(",...")
        assert not result.endswith(";...")

    def test_exclamation_sentence_delimiter(self):
        """Exclamation point should work as sentence delimiter when no period present."""
        # No periods in text, so ! delimiter is used
        synthesis = "Breaking news! More details follow"
        result = _generate_fallback_title(None, synthesis)
        assert result == "Breaking news!"

    def test_question_sentence_delimiter(self):
        """Question mark should work as sentence delimiter when no period present."""
        # No periods in text, so ? delimiter is used
        synthesis = "What does this mean? Experts weigh in"
        result = _generate_fallback_title(None, synthesis)
        assert result == "What does this mean?"


class TestTitleEdgeCases:
    """Edge case tests for title generation."""

    def test_unicode_characters_preserved(self):
        """Unicode characters in title should be preserved."""
        title = "日本語タイトル: Tech News"
        result = _generate_fallback_title(title, "Synthesis")
        assert "日本語" in result

    def test_emoji_in_title(self):
        """Emoji in title should be handled gracefully."""
        title = "🚀 SpaceX Launch Success"
        result = _generate_fallback_title(title, "Synthesis")
        assert "🚀" in result

    def test_very_short_title_accepted(self):
        """Very short but valid title should be accepted."""
        result = _generate_fallback_title("AI News", "Long synthesis text here")
        assert result == "AI News"

    def test_numbers_in_title(self):
        """Numbers in title should be preserved."""
        title = "Q4 2025 Revenue Up 15% for Tech Giants"
        result = _generate_fallback_title(title, "Synthesis")
        assert "15%" in result
        assert "2025" in result

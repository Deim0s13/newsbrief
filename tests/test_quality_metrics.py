#!/usr/bin/env python3
"""
Unit tests for quality metrics calculation and tracking.

Tests the quality scoring functions from app/quality_metrics.py.
Part of Issue #105: Add output quality metrics and tracking.
"""

from dataclasses import dataclass
from typing import List, Optional

import pytest


# Mock LLMParseMetrics for testing without importing the full module
@dataclass
class MockParseMetrics:
    """Mock of LLMParseMetrics for testing."""

    success: bool = True
    strategy_used: str = "direct"
    repairs_made: Optional[List[str]] = None
    retry_count: int = 0
    error_category: Optional[str] = None
    error_message: Optional[str] = None
    total_time_ms: int = 100

    def __post_init__(self):
        if self.repairs_made is None:
            self.repairs_made = []


class TestScoreCompleteness:
    """Tests for score_completeness function."""

    def test_perfect_completeness(self):
        """Full synthesis with all fields scores high."""
        from app.quality_metrics import score_completeness

        synthesis = {
            "key_points": ["Point 1", "Point 2", "Point 3"],
            "synthesis": "A" * 500,  # Good length
            "why_it_matters": "This is important because...",
            "topics": ["AI", "Security"],
        }
        score = score_completeness(synthesis)
        assert score >= 0.9

    def test_minimal_completeness(self):
        """Minimal synthesis scores low."""
        from app.quality_metrics import score_completeness

        synthesis = {
            "key_points": [],
            "synthesis": "Short",
            "why_it_matters": "",
            "topics": [],
        }
        score = score_completeness(synthesis)
        assert score < 0.3

    def test_partial_completeness(self):
        """Partial fields give partial score."""
        from app.quality_metrics import score_completeness

        synthesis = {
            "key_points": ["Point 1", "Point 2"],
            "synthesis": "A" * 100,
            "why_it_matters": "",
            "topics": ["AI"],
        }
        score = score_completeness(synthesis)
        assert 0.3 <= score <= 0.7


class TestScoreCoverage:
    """Tests for score_coverage function."""

    def test_good_coverage(self):
        """Synthesis with appropriate length for article count scores well."""
        from app.quality_metrics import score_coverage

        synthesis = {
            "synthesis": "A" * 400,  # ~100 chars per article
        }
        score = score_coverage(synthesis, article_count=4)
        assert score >= 0.8

    def test_too_short(self):
        """Very short synthesis for many articles scores low."""
        from app.quality_metrics import score_coverage

        synthesis = {
            "synthesis": "A" * 50,
        }
        score = score_coverage(synthesis, article_count=10)
        assert score < 0.5

    def test_too_long(self):
        """Very long synthesis gets slight penalty."""
        from app.quality_metrics import score_coverage

        synthesis = {
            "synthesis": "A" * 5000,
        }
        score = score_coverage(synthesis, article_count=2)
        assert score < 1.0
        assert score >= 0.5  # Not too harsh

    def test_zero_articles(self):
        """Zero articles returns neutral score."""
        from app.quality_metrics import score_coverage

        synthesis = {"synthesis": "Some text"}
        score = score_coverage(synthesis, article_count=0)
        assert score == 0.5


class TestScoreEntityConsistency:
    """Tests for score_entity_consistency function."""

    def test_all_entities_present(self):
        """All entities in synthesis scores perfectly."""
        from app.quality_metrics import score_entity_consistency

        synthesis = {
            "synthesis": "Apple and Google announced a partnership with Microsoft.",
            "entities": ["Apple", "Google", "Microsoft"],
        }
        score = score_entity_consistency(synthesis)
        assert score == 1.0

    def test_no_entities_present(self):
        """No entities in synthesis scores zero."""
        from app.quality_metrics import score_entity_consistency

        synthesis = {
            "synthesis": "Some random text without any entities.",
            "entities": ["Apple", "Google", "Microsoft"],
        }
        score = score_entity_consistency(synthesis)
        assert score == 0.0

    def test_partial_entities(self):
        """Some entities present gives partial score."""
        from app.quality_metrics import score_entity_consistency

        synthesis = {
            "synthesis": "Apple announced something new.",
            "entities": ["Apple", "Google"],
        }
        score = score_entity_consistency(synthesis)
        assert score == 0.5

    def test_no_entities_list(self):
        """Empty entity list returns neutral score."""
        from app.quality_metrics import score_entity_consistency

        synthesis = {
            "synthesis": "Some text",
            "entities": [],
        }
        score = score_entity_consistency(synthesis)
        assert score == 0.5

    def test_case_insensitive(self):
        """Entity matching is case insensitive."""
        from app.quality_metrics import score_entity_consistency

        synthesis = {
            "synthesis": "APPLE and google are companies.",
            "entities": ["Apple", "Google"],
        }
        score = score_entity_consistency(synthesis)
        assert score == 1.0


class TestScoreParseSuccess:
    """Tests for score_parse_success function."""

    def test_direct_parse(self):
        """Direct parse with no repairs scores perfectly."""
        from app.quality_metrics import score_parse_success

        metrics = MockParseMetrics(success=True, strategy_used="direct")
        score = score_parse_success(metrics)
        assert score == 1.0

    def test_failed_parse(self):
        """Failed parse scores zero."""
        from app.quality_metrics import score_parse_success

        metrics = MockParseMetrics(success=False)
        score = score_parse_success(metrics)
        assert score == 0.0

    def test_markdown_block(self):
        """Markdown block strategy scores slightly lower."""
        from app.quality_metrics import score_parse_success

        metrics = MockParseMetrics(success=True, strategy_used="markdown_block")
        score = score_parse_success(metrics)
        assert score == 0.9

    def test_with_repairs(self):
        """Repairs reduce score."""
        from app.quality_metrics import score_parse_success

        metrics = MockParseMetrics(
            success=True,
            strategy_used="direct",
            repairs_made=["trailing_comma", "quotes"],
        )
        score = score_parse_success(metrics)
        assert score == 0.9  # 1.0 - 0.05 * 2

    def test_with_retries(self):
        """Retries reduce score."""
        from app.quality_metrics import score_parse_success

        metrics = MockParseMetrics(success=True, strategy_used="direct", retry_count=2)
        score = score_parse_success(metrics)
        assert score == 0.8  # 1.0 - 0.1 * 2


class TestScoreTitleQuality:
    """Tests for score_title_quality function."""

    def test_perfect_llm_title(self):
        """LLM-generated title of good length scores high."""
        from app.quality_metrics import score_title_quality

        synthesis = {"title": "Breaking: Major Tech Companies Announce Partnership"}
        score = score_title_quality(synthesis, title_source="llm")
        assert score >= 0.9

    def test_fallback_title(self):
        """Fallback title scores lower."""
        from app.quality_metrics import score_title_quality

        synthesis = {"title": "Breaking: Major Tech Companies Announce Partnership"}
        score = score_title_quality(synthesis, title_source="fallback")
        assert score < score_title_quality(synthesis, title_source="llm")

    def test_no_title(self):
        """No title scores zero."""
        from app.quality_metrics import score_title_quality

        synthesis = {"title": ""}
        score = score_title_quality(synthesis, title_source="llm")
        assert score == 0.0

    def test_very_long_title(self):
        """Very long title scores lower."""
        from app.quality_metrics import score_title_quality

        synthesis = {"title": "A" * 150}  # Too long
        score = score_title_quality(synthesis, title_source="llm")
        assert score < 0.8


class TestCalculateQualityScore:
    """Tests for the main calculate_quality_score function."""

    def test_high_quality_synthesis(self):
        """High quality synthesis scores high."""
        from app.quality_metrics import calculate_quality_score

        synthesis = {
            "title": "Major AI Breakthrough Announced by Leading Companies",
            "synthesis": "In a significant development, major tech companies have announced breakthroughs in artificial intelligence. "
            * 5,
            "key_points": [
                "Key point one about the announcement",
                "Key point two with more details",
                "Key point three explaining impact",
            ],
            "why_it_matters": "This matters because it represents a major shift in AI capabilities.",
            "topics": ["AI/ML", "Technology"],
            "entities": ["AI", "tech companies"],
        }
        metrics = MockParseMetrics(success=True, strategy_used="direct")
        breakdown = calculate_quality_score(
            synthesis, metrics, article_count=3, title_source="llm"
        )
        assert breakdown.overall >= 0.7
        assert breakdown.completeness >= 0.8
        assert breakdown.parse_success == 1.0

    def test_low_quality_synthesis(self):
        """Poor synthesis scores low."""
        from app.quality_metrics import calculate_quality_score

        synthesis = {
            "title": "",
            "synthesis": "Short.",
            "key_points": [],
            "why_it_matters": "",
            "topics": [],
            "entities": [],
        }
        metrics = MockParseMetrics(
            success=True, strategy_used="line_by_line", repairs_made=["many", "repairs"]
        )
        breakdown = calculate_quality_score(
            synthesis, metrics, article_count=5, title_source="fallback"
        )
        assert breakdown.overall < 0.4

    def test_quality_breakdown_to_dict(self):
        """Quality breakdown can be serialized to dict."""
        from app.quality_metrics import calculate_quality_score

        synthesis = {
            "title": "Test Title",
            "synthesis": "A" * 200,
            "key_points": ["Point 1", "Point 2", "Point 3"],
            "why_it_matters": "Important",
            "topics": ["Tech"],
            "entities": ["Test"],
        }
        metrics = MockParseMetrics(success=True, strategy_used="direct")
        breakdown = calculate_quality_score(
            synthesis, metrics, article_count=2, title_source="llm"
        )

        # Convert to dict
        d = breakdown.to_dict()
        assert "completeness" in d
        assert "coverage" in d
        assert "entity_consistency" in d
        assert "parse_success" in d
        assert "title_quality" in d
        assert "overall" in d


class TestQualityBreakdown:
    """Tests for QualityBreakdown dataclass."""

    def test_from_dict(self):
        """Can create breakdown from dict."""
        from app.quality_metrics import QualityBreakdown

        data = {
            "completeness": 0.8,
            "coverage": 0.7,
            "entity_consistency": 0.6,
            "parse_success": 0.9,
            "title_quality": 0.85,
            "overall": 0.77,
        }
        breakdown = QualityBreakdown.from_dict(data)
        assert breakdown.completeness == 0.8
        assert breakdown.overall == 0.77

    def test_round_trip(self):
        """Can convert to dict and back."""
        from app.quality_metrics import QualityBreakdown

        original = QualityBreakdown(
            completeness=0.8,
            coverage=0.7,
            entity_consistency=0.6,
            parse_success=0.9,
            title_quality=0.85,
            overall=0.77,
        )
        restored = QualityBreakdown.from_dict(original.to_dict())
        assert original.overall == restored.overall
        assert original.completeness == restored.completeness

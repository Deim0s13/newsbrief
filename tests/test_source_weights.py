"""
Tests for source quality weighting.
"""

import pytest


class TestDomainExtraction:
    """Tests for domain extraction from URLs."""

    def test_extract_domain_simple(self):
        from app.source_weights import _extract_domain

        assert _extract_domain("https://techcrunch.com/feed") == "techcrunch.com"
        assert _extract_domain("https://arstechnica.com/rss") == "arstechnica.com"

    def test_extract_domain_with_www(self):
        from app.source_weights import _extract_domain

        assert _extract_domain("https://www.wired.com/feed") == "wired.com"

    def test_extract_domain_with_subdomain(self):
        from app.source_weights import _extract_domain

        assert _extract_domain("https://news.ycombinator.com/rss") == "news.ycombinator.com"

    def test_extract_domain_empty(self):
        from app.source_weights import _extract_domain

        assert _extract_domain("") == ""
        assert _extract_domain("not-a-url") == ""


class TestFeedWeightLookup:
    """Tests for feed weight lookup by name."""

    def test_get_feed_weight_exact_match(self):
        from app.source_weights import get_feed_weight

        weight = get_feed_weight("Hacker News")
        assert weight == 1.5

    def test_get_feed_weight_case_insensitive(self):
        from app.source_weights import get_feed_weight

        weight = get_feed_weight("hacker news")
        assert weight == 1.5

    def test_get_feed_weight_unknown(self):
        from app.source_weights import get_feed_weight

        weight = get_feed_weight("Unknown Blog")
        assert weight is None


class TestDomainWeightLookup:
    """Tests for domain weight lookup by URL."""

    def test_get_domain_weight_exact(self):
        from app.source_weights import get_domain_weight

        weight = get_domain_weight("https://techcrunch.com/feed")
        assert weight == 1.2

    def test_get_domain_weight_with_subdomain(self):
        from app.source_weights import get_domain_weight

        weight = get_domain_weight("https://news.ycombinator.com/rss")
        # Should match news.ycombinator.com in config
        assert weight == 1.5

    def test_get_domain_weight_unknown(self):
        from app.source_weights import get_domain_weight

        weight = get_domain_weight("https://unknown-blog.com/feed")
        assert weight is None


class TestSourceWeightLookup:
    """Tests for combined source weight lookup."""

    def test_get_source_weight_feed_name_priority(self):
        from app.source_weights import get_source_weight

        # Feed name should take priority over domain
        weight = get_source_weight("Hacker News", "https://different-domain.com")
        assert weight == 1.5

    def test_get_source_weight_domain_fallback(self):
        from app.source_weights import get_source_weight

        # Unknown feed name, but known domain
        weight = get_source_weight("Unknown Feed", "https://techcrunch.com/feed")
        assert weight == 1.2

    def test_get_source_weight_default(self):
        from app.source_weights import get_source_weight

        # Both unknown
        weight = get_source_weight("Unknown Feed", "https://unknown.com/feed")
        assert weight == 1.0


class TestStorySourceWeight:
    """Tests for story-level source weight calculation."""

    def test_calculate_story_source_weight_single(self):
        from app.source_weights import calculate_story_source_weight

        weight = calculate_story_source_weight(["Hacker News"], ["https://hn.com"])
        assert weight == 1.5

    def test_calculate_story_source_weight_multiple(self):
        from app.source_weights import calculate_story_source_weight

        # HN (1.5) + Ars (1.3) + Unknown (1.0) = 3.8 / 3 = 1.27
        weight = calculate_story_source_weight(
            ["Hacker News", "Ars Technica", "Unknown"],
            ["https://hn.com", "https://ars.com", "https://unknown.com"],
        )
        assert weight == pytest.approx(1.27, rel=0.01)

    def test_calculate_story_source_weight_empty(self):
        from app.source_weights import calculate_story_source_weight

        weight = calculate_story_source_weight([], [])
        assert weight == 1.0  # default


class TestConfigLoading:
    """Tests for configuration loading."""

    def test_load_source_weights_config_returns_dict(self):
        from app.source_weights import load_source_weights_config

        config = load_source_weights_config()
        assert isinstance(config, dict)
        assert "enabled" in config
        assert "feed_weights" in config
        assert "domain_weights" in config

    def test_is_source_weighting_enabled(self):
        from app.source_weights import is_source_weighting_enabled

        # Default config has enabled=True
        assert is_source_weighting_enabled() is True

    def test_get_blend_weight(self):
        from app.source_weights import get_blend_weight

        weight = get_blend_weight()
        assert weight == 0.2  # 20% blend weight


class TestSourceWeightsSummary:
    """Tests for source weights summary."""

    def test_get_source_weights_summary_structure(self):
        from app.source_weights import get_source_weights_summary

        summary = get_source_weights_summary()
        assert "enabled" in summary
        assert "blend_weight" in summary
        assert "feed_weights_count" in summary
        assert "domain_weights_count" in summary
        assert "default_weight" in summary

    def test_get_source_weights_summary_has_sources(self):
        from app.source_weights import get_source_weights_summary

        summary = get_source_weights_summary()
        assert summary["feed_weights_count"] >= 10
        assert summary["domain_weights_count"] >= 10


class TestBlendedScoreWithSource:
    """Tests for blended score calculation with source weight."""

    def test_calculate_blended_score_three_dimensions(self):
        from app.interests import calculate_blended_score

        # importance=0.8, interest=1.0, source=1.0
        # (0.8 * 0.5) + (0.5 * 0.3) + (0.5 * 0.2) = 0.4 + 0.15 + 0.1 = 0.65
        score = calculate_blended_score(0.8, 1.0, 1.0)
        assert score == pytest.approx(0.65, rel=0.01)

    def test_high_source_weight_boosts_score(self):
        from app.interests import calculate_blended_score

        low_source = calculate_blended_score(0.5, 1.0, 0.5)
        high_source = calculate_blended_score(0.5, 1.0, 1.5)

        assert high_source > low_source

    def test_get_story_blended_score_with_source(self):
        from app.interests import get_story_blended_score

        # High interest topics + high source weight
        score1 = get_story_blended_score(0.7, ["AI/ML"], 1.5)
        # Low interest topics + low source weight
        score2 = get_story_blended_score(0.7, ["Politics"], 0.5)

        assert score1 > score2


"""Unit tests for story quality scoring (v0.6.1)."""

from datetime import UTC, datetime, timedelta

from app.stories import (_calculate_freshness_score,
                         _calculate_importance_score,
                         _calculate_source_quality_score,
                         _calculate_story_scores)


class TestImportanceScoring:
    """Test importance score calculation."""

    def test_importance_minimum(self):
        """Test minimum importance (1 article, 1 source, 0 entities)."""
        score = _calculate_importance_score(
            article_count=1,
            unique_source_count=1,
            entity_count=0,
        )

        # 0.4 * (1/10) + 0.3 * (1/5) + 0.3 * (0/10)
        # = 0.4 * 0.1 + 0.3 * 0.2 + 0
        # = 0.04 + 0.06 + 0
        # = 0.10
        assert abs(score - 0.10) < 0.01

    def test_importance_moderate(self):
        """Test moderate importance (5 articles, 3 sources, 5 entities)."""
        score = _calculate_importance_score(
            article_count=5,
            unique_source_count=3,
            entity_count=5,
        )

        # 0.4 * (5/10) + 0.3 * (3/5) + 0.3 * (5/10)
        # = 0.4 * 0.5 + 0.3 * 0.6 + 0.3 * 0.5
        # = 0.2 + 0.18 + 0.15
        # = 0.53
        assert abs(score - 0.53) < 0.01

    def test_importance_maximum(self):
        """Test maximum importance (10+ articles, 5+ sources, 10+ entities)."""
        score = _calculate_importance_score(
            article_count=15,  # Capped at 10
            unique_source_count=8,  # Capped at 5
            entity_count=20,  # Capped at 10
        )

        # All capped at 1.0
        # 0.4 * 1.0 + 0.3 * 1.0 + 0.3 * 1.0 = 1.0
        assert score == 1.0

    def test_importance_caps_applied(self):
        """Test that caps are properly applied."""
        score1 = _calculate_importance_score(10, 5, 10)
        score2 = _calculate_importance_score(100, 50, 100)

        # Both should cap at same max
        assert score1 == score2 == 1.0


class TestFreshnessScoring:
    """Test freshness score calculation with exponential decay."""

    def test_freshness_brand_new(self):
        """Test freshness for articles published just now."""
        now = datetime.now(UTC)
        score = _calculate_freshness_score([now, now, now])

        # Age ≈ 0, exp(-0/12) ≈ 1.0
        assert score > 0.99

    def test_freshness_12_hours_old(self):
        """Test freshness for articles 12 hours old (half-life)."""
        now = datetime.now(UTC)
        twelve_hours_ago = now - timedelta(hours=12)
        score = _calculate_freshness_score([twelve_hours_ago])

        # exp(-12/12) = exp(-1) ≈ 0.368
        assert abs(score - 0.368) < 0.01

    def test_freshness_24_hours_old(self):
        """Test freshness for articles 24 hours old."""
        now = datetime.now(UTC)
        one_day_ago = now - timedelta(hours=24)
        score = _calculate_freshness_score([one_day_ago])

        # exp(-24/12) = exp(-2) ≈ 0.135
        assert abs(score - 0.135) < 0.01

    def test_freshness_very_old(self):
        """Test freshness for very old articles (7 days)."""
        now = datetime.now(UTC)
        week_ago = now - timedelta(days=7)
        score = _calculate_freshness_score([week_ago])

        # exp(-168/12) = exp(-14) ≈ 0.0000008
        assert score < 0.001

    def test_freshness_mixed_ages(self):
        """Test freshness for articles with mixed ages."""
        now = datetime.now(UTC)
        articles = [
            now,  # Brand new
            now - timedelta(hours=6),  # 6 hours old
            now - timedelta(hours=18),  # 18 hours old
        ]
        score = _calculate_freshness_score(articles)

        # Average age: (0 + 6 + 18) / 3 = 8 hours
        # exp(-8/12) ≈ 0.513
        assert abs(score - 0.513) < 0.02

    def test_freshness_empty_list(self):
        """Test freshness with empty article list."""
        score = _calculate_freshness_score([])

        # Should return default 0.5
        assert score == 0.5

    def test_freshness_timezone_aware(self):
        """Test that timezone-aware datetimes work correctly."""
        now = datetime.now(UTC)
        score = _calculate_freshness_score([now])

        assert score > 0.99

    def test_freshness_timezone_naive(self):
        """Test that timezone-naive datetimes are handled."""
        now_naive = datetime.now()  # No timezone
        score = _calculate_freshness_score([now_naive])

        # Should still work (converted to UTC internally)
        assert score > 0.99


class TestSourceQualityScoring:
    """Test source quality score calculation."""

    def test_source_quality_perfect(self):
        """Test perfect source quality (all 100%)."""
        score = _calculate_source_quality_score([100.0, 100.0, 100.0])

        assert score == 1.0

    def test_source_quality_good(self):
        """Test good source quality (average 80%)."""
        score = _calculate_source_quality_score([80.0, 90.0, 70.0])

        # Average: 80, normalized: 0.8
        assert abs(score - 0.8) < 0.01

    def test_source_quality_moderate(self):
        """Test moderate source quality (average 50%)."""
        score = _calculate_source_quality_score([50.0, 60.0, 40.0])

        # Average: 50, normalized: 0.5
        assert score == 0.5

    def test_source_quality_poor(self):
        """Test poor source quality (average 20%)."""
        score = _calculate_source_quality_score([20.0, 10.0, 30.0])

        # Average: 20, normalized: 0.2
        assert score == 0.2

    def test_source_quality_empty(self):
        """Test source quality with empty list."""
        score = _calculate_source_quality_score([])

        # Should return default 0.5
        assert score == 0.5

    def test_source_quality_single_source(self):
        """Test source quality with single source."""
        score = _calculate_source_quality_score([75.0])

        assert score == 0.75


class TestCombinedStoryScoring:
    """Test combined story scoring function."""

    def test_combined_scoring_high_quality_story(self):
        """Test scoring for a high-quality story."""
        now = datetime.now(UTC)

        importance, freshness, quality = _calculate_story_scores(
            article_count=8,  # Many articles
            unique_source_count=5,  # Diverse sources
            entity_count=10,  # Rich entities
            article_published_times=[now, now, now],  # Fresh
            feed_health_scores=[100.0, 95.0, 90.0],  # Healthy feeds
        )

        # All components should be high
        assert importance > 0.8
        assert freshness > 0.9
        assert quality > 0.8

    def test_combined_scoring_low_quality_story(self):
        """Test scoring for a low-quality story."""
        now = datetime.now(UTC)
        week_ago = now - timedelta(days=7)

        importance, freshness, quality = _calculate_story_scores(
            article_count=1,  # Single article
            unique_source_count=1,  # One source
            entity_count=0,  # No entities
            article_published_times=[week_ago],  # Old
            feed_health_scores=[30.0],  # Poor health
        )

        # All components should be low
        assert importance < 0.2
        assert freshness < 0.01
        assert quality < 0.3

    def test_combined_scoring_formula(self):
        """Test that overall quality score uses correct formula."""
        now = datetime.now(UTC)

        importance, freshness, quality = _calculate_story_scores(
            article_count=5,
            unique_source_count=3,
            entity_count=5,
            article_published_times=[now],
            feed_health_scores=[80.0],
        )

        # Quality = 0.4 * importance + 0.3 * freshness + 0.2 * source + 0.1 * engagement
        # Engagement is placeholder 0.5
        expected_quality = 0.4 * importance + 0.3 * freshness + 0.2 * 0.8 + 0.1 * 0.5

        assert abs(quality - expected_quality) < 0.01

    def test_combined_scoring_returns_three_values(self):
        """Test that function returns tuple of 3 scores."""
        now = datetime.now(UTC)

        result = _calculate_story_scores(
            article_count=3,
            unique_source_count=2,
            entity_count=3,
            article_published_times=[now],
            feed_health_scores=[100.0],
        )

        assert isinstance(result, tuple)
        assert len(result) == 3

        importance, freshness, quality = result
        assert 0.0 <= importance <= 1.0
        assert 0.0 <= freshness <= 1.0
        assert 0.0 <= quality <= 1.0


class TestScoringEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_zero_values(self):
        """Test scoring with all zero values."""
        importance = _calculate_importance_score(0, 0, 0)

        # Should be 0.0
        assert importance == 0.0

    def test_very_large_values(self):
        """Test scoring with very large values (should cap)."""
        importance = _calculate_importance_score(1000, 1000, 1000)

        # Should cap at 1.0
        assert importance == 1.0

    def test_negative_time_delta(self):
        """Test freshness with future publication times (edge case)."""
        now = datetime.now(UTC)
        future = now + timedelta(hours=1)

        # Should handle gracefully (may return > 1.0, then capped)
        score = _calculate_freshness_score([future])

        # exp(positive) > 1.0, but capped at 1.0
        assert score >= 0.0
        assert score <= 1.0

    def test_mixed_health_scores(self):
        """Test source quality with mixed health including zeros."""
        score = _calculate_source_quality_score([0.0, 100.0, 50.0])

        # Average: 50, normalized: 0.5
        assert score == 0.5

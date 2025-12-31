#!/usr/bin/env python3
"""
Test script for synthesis cache functionality.

Tests cache operations including:
- Cache key generation
- Cache storage and retrieval
- TTL expiration
- Invalidation
- Token counting
- Statistics
"""
import json
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.stories import Base
from app.synthesis_cache import (
    SYNTHESIS_CACHE_TTL_HOURS,
    SynthesisCache,
    cleanup_expired_cache,
    count_tokens,
    generate_cache_key,
    get_cache_stats,
    get_cached_synthesis,
    invalidate_cache_for_articles,
    store_synthesis_in_cache,
)


def setup_test_db():
    """Create a temporary test database with synthesis_cache table."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)

    # Create synthesis_cache table
    with engine.connect() as conn:
        conn.execute(
            text(
                """
            CREATE TABLE IF NOT EXISTS synthesis_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cache_key TEXT UNIQUE NOT NULL,
                article_ids_json TEXT NOT NULL,
                model TEXT NOT NULL,
                synthesis TEXT NOT NULL,
                key_points_json TEXT,
                why_it_matters TEXT,
                topics_json TEXT,
                entities_json TEXT,
                token_count_input INTEGER,
                token_count_output INTEGER,
                generation_time_ms INTEGER,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                expires_at DATETIME,
                invalidated_at DATETIME
            )
        """
            )
        )
        conn.commit()

    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal()


class TestCacheKeyGeneration:
    """Tests for cache key generation."""

    def test_generate_cache_key_basic(self):
        """Test basic cache key generation."""
        key = generate_cache_key([1, 2, 3], "llama3.1:8b")
        assert isinstance(key, str)
        assert len(key) == 64  # SHA-256 hex digest

    def test_generate_cache_key_order_independent(self):
        """Test that article order doesn't affect cache key."""
        key1 = generate_cache_key([1, 2, 3], "llama3.1:8b")
        key2 = generate_cache_key([3, 1, 2], "llama3.1:8b")
        key3 = generate_cache_key([2, 3, 1], "llama3.1:8b")
        assert key1 == key2 == key3

    def test_generate_cache_key_model_matters(self):
        """Test that different models produce different keys."""
        key1 = generate_cache_key([1, 2, 3], "llama3.1:8b")
        key2 = generate_cache_key([1, 2, 3], "mistral:latest")
        assert key1 != key2

    def test_generate_cache_key_articles_matter(self):
        """Test that different articles produce different keys."""
        key1 = generate_cache_key([1, 2, 3], "llama3.1:8b")
        key2 = generate_cache_key([1, 2, 4], "llama3.1:8b")
        assert key1 != key2


class TestCacheStorage:
    """Tests for cache storage and retrieval."""

    def test_store_and_retrieve(self):
        """Test storing and retrieving synthesis from cache."""
        session = setup_test_db()
        article_ids = [1, 2, 3]
        model = "llama3.1:8b"
        synthesis_result = {
            "synthesis": "Test synthesis content",
            "key_points": ["Point 1", "Point 2", "Point 3"],
            "why_it_matters": "This is important because...",
            "topics": ["AI/ML", "Tech"],
            "entities": ["OpenAI", "GPT-4"],
        }

        # Store
        cache_key = store_synthesis_in_cache(
            session=session,
            article_ids=article_ids,
            model=model,
            synthesis_result=synthesis_result,
            generation_time_ms=5000,
            token_count_input=100,
            token_count_output=50,
        )
        session.commit()

        assert cache_key != ""

        # Retrieve
        cached = get_cached_synthesis(session, article_ids, model)
        assert cached is not None
        assert cached["synthesis"] == "Test synthesis content"
        assert cached["key_points"] == ["Point 1", "Point 2", "Point 3"]
        assert cached["why_it_matters"] == "This is important because..."
        assert cached["_cached"] is True

    def test_cache_miss(self):
        """Test that non-existent cache returns None."""
        session = setup_test_db()
        cached = get_cached_synthesis(session, [999, 998], "llama3.1:8b")
        assert cached is None

    def test_cache_update_existing(self):
        """Test updating an existing cache entry."""
        session = setup_test_db()
        article_ids = [1, 2]
        model = "llama3.1:8b"

        # Store first version
        store_synthesis_in_cache(
            session=session,
            article_ids=article_ids,
            model=model,
            synthesis_result={
                "synthesis": "Version 1",
                "key_points": [],
                "why_it_matters": "",
            },
        )
        session.commit()

        # Store second version (should update)
        store_synthesis_in_cache(
            session=session,
            article_ids=article_ids,
            model=model,
            synthesis_result={
                "synthesis": "Version 2",
                "key_points": [],
                "why_it_matters": "",
            },
        )
        session.commit()

        # Retrieve should get Version 2
        cached = get_cached_synthesis(session, article_ids, model)
        assert cached["synthesis"] == "Version 2"

        # Should only have one entry
        count = session.query(SynthesisCache).count()
        assert count == 1


class TestCacheExpiration:
    """Tests for cache TTL and expiration."""

    def test_expired_cache_returns_none(self):
        """Test that expired cache entries are not returned."""
        session = setup_test_db()
        article_ids = [1, 2]
        model = "llama3.1:8b"

        # Store with past expiration
        cache_key = generate_cache_key(article_ids, model)
        expired_entry = SynthesisCache(
            cache_key=cache_key,
            article_ids_json=json.dumps(sorted(article_ids)),
            model=model,
            synthesis="Expired content",
            created_at=datetime.now(UTC) - timedelta(days=10),
            expires_at=datetime.now(UTC) - timedelta(days=3),  # Expired 3 days ago
        )
        session.add(expired_entry)
        session.commit()

        # Should return None (expired)
        cached = get_cached_synthesis(session, article_ids, model)
        assert cached is None

    def test_cleanup_expired_cache(self):
        """Test cleanup of expired entries."""
        session = setup_test_db()

        # Create expired entry
        expired_entry = SynthesisCache(
            cache_key="expired_key",
            article_ids_json="[1, 2]",
            model="test",
            synthesis="Expired",
            expires_at=datetime.now(UTC) - timedelta(days=1),
        )
        session.add(expired_entry)

        # Create valid entry
        valid_entry = SynthesisCache(
            cache_key="valid_key",
            article_ids_json="[3, 4]",
            model="test",
            synthesis="Valid",
            expires_at=datetime.now(UTC) + timedelta(days=7),
        )
        session.add(valid_entry)
        session.commit()

        # Cleanup
        deleted_count = cleanup_expired_cache(session)
        session.commit()

        assert deleted_count >= 1

        # Valid entry should still exist
        remaining = (
            session.query(SynthesisCache)
            .filter(SynthesisCache.cache_key == "valid_key")
            .first()
        )
        assert remaining is not None


class TestCacheInvalidation:
    """Tests for cache invalidation."""

    def test_invalidate_cache_for_articles(self):
        """Test invalidating cache entries containing specific articles."""
        session = setup_test_db()

        # Create entry with articles [1, 2, 3]
        entry1 = SynthesisCache(
            cache_key="key1",
            article_ids_json="[1, 2, 3]",
            model="test",
            synthesis="Content 1",
            expires_at=datetime.now(UTC) + timedelta(days=7),
        )
        session.add(entry1)

        # Create entry with articles [4, 5, 6]
        entry2 = SynthesisCache(
            cache_key="key2",
            article_ids_json="[4, 5, 6]",
            model="test",
            synthesis="Content 2",
            expires_at=datetime.now(UTC) + timedelta(days=7),
        )
        session.add(entry2)
        session.commit()

        # Invalidate entries containing article 2
        invalidated_count = invalidate_cache_for_articles(session, [2])
        session.commit()

        assert invalidated_count == 1

        # Entry 1 should be invalidated
        entry1_updated = (
            session.query(SynthesisCache)
            .filter(SynthesisCache.cache_key == "key1")
            .first()
        )
        assert entry1_updated.invalidated_at is not None

        # Entry 2 should not be invalidated
        entry2_updated = (
            session.query(SynthesisCache)
            .filter(SynthesisCache.cache_key == "key2")
            .first()
        )
        assert entry2_updated.invalidated_at is None

    def test_invalidated_cache_returns_none(self):
        """Test that invalidated cache entries are not returned."""
        session = setup_test_db()
        article_ids = [1, 2]
        model = "llama3.1:8b"

        # Store entry
        store_synthesis_in_cache(
            session=session,
            article_ids=article_ids,
            model=model,
            synthesis_result={
                "synthesis": "Content",
                "key_points": [],
                "why_it_matters": "",
            },
        )
        session.commit()

        # Verify it's retrievable
        cached = get_cached_synthesis(session, article_ids, model)
        assert cached is not None

        # Invalidate
        invalidate_cache_for_articles(session, [1])
        session.commit()

        # Should now return None
        cached = get_cached_synthesis(session, article_ids, model)
        assert cached is None


class TestTokenCounting:
    """Tests for token counting."""

    def test_count_tokens_empty(self):
        """Test token count for empty string."""
        assert count_tokens("") == 0
        assert count_tokens(None) == 0  # type: ignore

    def test_count_tokens_basic(self):
        """Test token count for basic text."""
        tokens = count_tokens("Hello, world!")
        assert tokens > 0
        assert tokens < 10  # Should be around 3-4 tokens

    def test_count_tokens_longer_text(self):
        """Test token count for longer text."""
        text = "This is a longer piece of text that should have more tokens. " * 10
        tokens = count_tokens(text)
        assert tokens > 50  # Should have many more tokens


class TestCacheStats:
    """Tests for cache statistics."""

    def test_get_cache_stats_empty(self):
        """Test stats for empty cache."""
        session = setup_test_db()
        stats = get_cache_stats(session)

        assert stats["total_entries"] == 0
        assert stats["valid_entries"] == 0
        assert stats["enabled"] is True

    def test_get_cache_stats_with_entries(self):
        """Test stats with cache entries."""
        session = setup_test_db()

        # Add some entries
        for i in range(3):
            entry = SynthesisCache(
                cache_key=f"key_{i}",
                article_ids_json=f"[{i}]",
                model="test",
                synthesis=f"Content {i}",
                generation_time_ms=1000 * (i + 1),
                token_count_input=100 * (i + 1),
                token_count_output=50 * (i + 1),
                expires_at=datetime.now(UTC) + timedelta(days=7),
            )
            session.add(entry)
        session.commit()

        stats = get_cache_stats(session)
        assert stats["total_entries"] == 3
        assert stats["valid_entries"] == 3
        assert stats["avg_generation_time_ms"] > 0
        assert stats["total_tokens_input"] == 600  # 100 + 200 + 300
        assert stats["total_tokens_output"] == 300  # 50 + 100 + 150


class TestCacheDisabled:
    """Tests for cache disabled mode."""

    @patch("app.synthesis_cache.SYNTHESIS_CACHE_ENABLED", False)
    def test_cache_disabled_no_store(self):
        """Test that caching is skipped when disabled."""
        session = setup_test_db()

        # Try to store - should return empty string
        cache_key = store_synthesis_in_cache(
            session=session,
            article_ids=[1, 2],
            model="test",
            synthesis_result={
                "synthesis": "Content",
                "key_points": [],
                "why_it_matters": "",
            },
        )
        assert cache_key == ""

    @patch("app.synthesis_cache.SYNTHESIS_CACHE_ENABLED", False)
    def test_cache_disabled_no_retrieve(self):
        """Test that retrieval returns None when disabled."""
        session = setup_test_db()

        # Even if there was an entry, should return None
        cached = get_cached_synthesis(session, [1, 2], "test")
        assert cached is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

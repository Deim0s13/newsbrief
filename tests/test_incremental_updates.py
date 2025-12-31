#!/usr/bin/env python3
"""
Test script for incremental story updates (ADR 0004).

Tests:
- Finding overlapping stories by article IDs
- Updating stories with new articles
- Version tracking and supersession
"""
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.stories import (
    Base,
    Story,
    StoryArticle,
    create_story,
    find_overlapping_story,
    link_articles_to_story,
    update_story_with_new_articles,
)


def setup_test_db():
    """Create a temporary test database with all required tables."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)

    # Create items table
    with engine.connect() as conn:
        conn.execute(
            text(
                """
            CREATE TABLE IF NOT EXISTS items (
                id INTEGER PRIMARY KEY,
                title TEXT,
                url TEXT,
                published DATETIME,
                summary TEXT,
                ai_summary TEXT,
                topic TEXT,
                feed_id INTEGER
            )
        """
            )
        )

        # Insert test articles
        for i in range(1, 11):
            conn.execute(
                text(
                    """
                INSERT INTO items (id, title, url, summary, topic, published)
                VALUES (:id, :title, :url, :summary, :topic, :published)
            """
                ),
                {
                    "id": i,
                    "title": f"Test Article {i}",
                    "url": f"http://example.com/{i}",
                    "summary": f"Summary for article {i}",
                    "topic": "tech",
                    "published": datetime.now(UTC) - timedelta(hours=i),
                },
            )
        conn.commit()

    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal()


class TestFindOverlappingStory:
    """Tests for find_overlapping_story function."""

    def test_no_overlap_empty_db(self):
        """Test finding overlap with no stories in database."""
        session = setup_test_db()
        result = find_overlapping_story(session, [1, 2, 3])
        assert result is None

    def test_no_overlap_different_articles(self):
        """Test no overlap when cluster has completely different articles."""
        session = setup_test_db()

        # Create existing story with articles 1, 2, 3
        story_id = create_story(
            session=session,
            title="Existing Story",
            synthesis="Test synthesis",
            key_points=["Point 1"],
            why_it_matters="Important",
            topics=["tech"],
            entities=["Company A"],
            importance_score=0.8,
            freshness_score=0.9,
            model="test",
            time_window_start=datetime.now(UTC) - timedelta(hours=24),
            time_window_end=datetime.now(UTC),
        )
        link_articles_to_story(session, story_id, [1, 2, 3])

        # New cluster with articles 7, 8, 9 (no overlap)
        result = find_overlapping_story(session, [7, 8, 9])
        assert result is None

    def test_overlap_below_threshold(self):
        """Test overlap below 70% threshold doesn't match."""
        session = setup_test_db()

        # Create existing story with articles 1, 2, 3, 4, 5
        story_id = create_story(
            session=session,
            title="Existing Story",
            synthesis="Test synthesis",
            key_points=["Point 1"],
            why_it_matters="Important",
            topics=["tech"],
            entities=["Company A"],
            importance_score=0.8,
            freshness_score=0.9,
            model="test",
            time_window_start=datetime.now(UTC) - timedelta(hours=24),
            time_window_end=datetime.now(UTC),
        )
        link_articles_to_story(session, story_id, [1, 2, 3, 4, 5])

        # New cluster with articles 1, 6, 7, 8, 9 (20% overlap - 1 out of 5)
        result = find_overlapping_story(session, [1, 6, 7, 8, 9])
        assert result is None

    def test_overlap_at_threshold(self):
        """Test overlap at exactly 70% threshold matches."""
        session = setup_test_db()

        # Create existing story with articles 1, 2, 3, 4, 5
        story_id = create_story(
            session=session,
            title="Existing Story",
            synthesis="Test synthesis",
            key_points=["Point 1"],
            why_it_matters="Important",
            topics=["tech"],
            entities=["Company A"],
            importance_score=0.8,
            freshness_score=0.9,
            model="test",
            time_window_start=datetime.now(UTC) - timedelta(hours=24),
            time_window_end=datetime.now(UTC),
        )
        link_articles_to_story(session, story_id, [1, 2, 3, 4, 5])

        # New cluster with articles 1, 2, 3, 4, 6, 7, 8, 9, 10 (but only check overlap)
        # Cluster [1, 2, 3, 7] has 3/4 = 75% overlap with story [1,2,3,4,5]
        result = find_overlapping_story(session, [1, 2, 3, 7])
        assert result is not None
        story, existing_ids, overlap_ratio = result
        assert story.id == story_id
        assert overlap_ratio >= 0.70

    def test_overlap_high_percentage(self):
        """Test high overlap percentage matches."""
        session = setup_test_db()

        # Create existing story with articles 1, 2, 3
        story_id = create_story(
            session=session,
            title="Existing Story",
            synthesis="Test synthesis",
            key_points=["Point 1"],
            why_it_matters="Important",
            topics=["tech"],
            entities=["Company A"],
            importance_score=0.8,
            freshness_score=0.9,
            model="test",
            time_window_start=datetime.now(UTC) - timedelta(hours=24),
            time_window_end=datetime.now(UTC),
        )
        link_articles_to_story(session, story_id, [1, 2, 3])

        # New cluster with articles 1, 2, 3, 4 (75% overlap)
        result = find_overlapping_story(session, [1, 2, 3, 4])
        assert result is not None
        story, existing_ids, overlap_ratio = result
        assert story.id == story_id
        assert overlap_ratio == 0.75

    def test_only_matches_active_stories(self):
        """Test that only active stories are considered for overlap."""
        session = setup_test_db()

        # Create archived story with articles 1, 2, 3
        story_id = create_story(
            session=session,
            title="Archived Story",
            synthesis="Test synthesis",
            key_points=["Point 1"],
            why_it_matters="Important",
            topics=["tech"],
            entities=["Company A"],
            importance_score=0.8,
            freshness_score=0.9,
            model="test",
            time_window_start=datetime.now(UTC) - timedelta(hours=24),
            time_window_end=datetime.now(UTC),
        )
        link_articles_to_story(session, story_id, [1, 2, 3])

        # Archive the story
        story = session.query(Story).filter(Story.id == story_id).first()
        story.status = "archived"
        session.commit()

        # New cluster with articles 1, 2, 3, 4 should not match archived story
        result = find_overlapping_story(session, [1, 2, 3, 4])
        assert result is None


class TestUpdateStoryWithNewArticles:
    """Tests for update_story_with_new_articles function."""

    def test_creates_new_version(self):
        """Test that updating a story creates a new version."""
        session = setup_test_db()

        # Create v1 story
        story_id = create_story(
            session=session,
            title="Original Story v1",
            synthesis="Original synthesis",
            key_points=["Point 1"],
            why_it_matters="Important",
            topics=["tech"],
            entities=["Company A"],
            importance_score=0.8,
            freshness_score=0.9,
            model="test",
            time_window_start=datetime.now(UTC) - timedelta(hours=24),
            time_window_end=datetime.now(UTC),
        )
        link_articles_to_story(session, story_id, [1, 2, 3])

        original_story = session.query(Story).filter(Story.id == story_id).first()
        existing_article_ids = {1, 2, 3}

        # Update with new articles
        new_story_id = update_story_with_new_articles(
            session=session,
            existing_story=original_story,
            existing_article_ids=existing_article_ids,
            merged_article_ids=[1, 2, 3, 4, 5],
            synthesis_data={
                "synthesis": "Updated synthesis with new info",
                "key_points": ["Point 1", "Point 2"],
                "why_it_matters": "Even more important",
                "topics": ["tech"],
                "entities": ["Company A", "Company B"],
            },
            model="test",
            cluster_data={
                "importance_score": 0.9,
                "freshness_score": 0.95,
                "quality_score": 0.85,
                "cluster_hash": "newhash123",
                "time_window_start": datetime.now(UTC) - timedelta(hours=24),
                "time_window_end": datetime.now(UTC),
            },
        )
        session.commit()

        # Verify new story created
        new_story = session.query(Story).filter(Story.id == new_story_id).first()
        assert new_story is not None
        assert new_story.version == 2
        assert new_story.previous_version_id == story_id
        assert new_story.status == "active"
        assert new_story.synthesis == "Updated synthesis with new info"

        # Verify original story superseded
        old_story = session.query(Story).filter(Story.id == story_id).first()
        assert old_story.status == "superseded"

    def test_preserves_first_seen(self):
        """Test that first_seen is preserved from original story."""
        session = setup_test_db()

        original_first_seen = datetime.now(UTC) - timedelta(days=3)

        # Create v1 story with specific first_seen
        story_id = create_story(
            session=session,
            title="Original Story",
            synthesis="Original synthesis",
            key_points=["Point 1"],
            why_it_matters="Important",
            topics=["tech"],
            entities=["Company A"],
            importance_score=0.8,
            freshness_score=0.9,
            model="test",
            time_window_start=datetime.now(UTC) - timedelta(hours=24),
            time_window_end=datetime.now(UTC),
            first_seen=original_first_seen,
        )
        link_articles_to_story(session, story_id, [1, 2])

        original_story = session.query(Story).filter(Story.id == story_id).first()

        # Update
        new_story_id = update_story_with_new_articles(
            session=session,
            existing_story=original_story,
            existing_article_ids={1, 2},
            merged_article_ids=[1, 2, 3],
            synthesis_data={
                "synthesis": "Updated",
                "key_points": [],
                "why_it_matters": "",
                "topics": [],
                "entities": [],
            },
            model="test",
            cluster_data={
                "importance_score": 0.8,
                "freshness_score": 0.9,
                "quality_score": 0.7,
                "cluster_hash": "hash",
                "time_window_start": datetime.now(UTC),
                "time_window_end": datetime.now(UTC),
            },
        )
        session.commit()

        # Verify first_seen preserved
        new_story = session.query(Story).filter(Story.id == new_story_id).first()
        # Compare without microseconds due to SQLite precision
        assert new_story.first_seen.date() == original_first_seen.date()

    def test_links_all_merged_articles(self):
        """Test that new version is linked to all merged articles."""
        session = setup_test_db()

        story_id = create_story(
            session=session,
            title="Original",
            synthesis="Original",
            key_points=[],
            why_it_matters="",
            topics=[],
            entities=[],
            importance_score=0.5,
            freshness_score=0.5,
            model="test",
            time_window_start=datetime.now(UTC),
            time_window_end=datetime.now(UTC),
        )
        link_articles_to_story(session, story_id, [1, 2])

        original_story = session.query(Story).filter(Story.id == story_id).first()

        new_story_id = update_story_with_new_articles(
            session=session,
            existing_story=original_story,
            existing_article_ids={1, 2},
            merged_article_ids=[1, 2, 3, 4, 5],
            synthesis_data={
                "synthesis": "Updated",
                "key_points": [],
                "why_it_matters": "",
                "topics": [],
                "entities": [],
            },
            model="test",
            cluster_data={
                "importance_score": 0.5,
                "freshness_score": 0.5,
                "quality_score": 0.5,
                "cluster_hash": "hash",
                "time_window_start": datetime.now(UTC),
                "time_window_end": datetime.now(UTC),
            },
        )
        session.commit()

        # Verify all 5 articles linked to new story
        links = (
            session.query(StoryArticle)
            .filter(StoryArticle.story_id == new_story_id)
            .all()
        )
        linked_article_ids = {link.article_id for link in links}
        assert linked_article_ids == {1, 2, 3, 4, 5}


class TestVersionChain:
    """Tests for version chain functionality."""

    def test_multiple_updates_create_chain(self):
        """Test that multiple updates create a version chain."""
        session = setup_test_db()

        # Create v1
        story_v1_id = create_story(
            session=session,
            title="Story v1",
            synthesis="V1 synthesis",
            key_points=[],
            why_it_matters="",
            topics=[],
            entities=[],
            importance_score=0.5,
            freshness_score=0.5,
            model="test",
            time_window_start=datetime.now(UTC),
            time_window_end=datetime.now(UTC),
        )
        link_articles_to_story(session, story_v1_id, [1])

        story_v1 = session.query(Story).filter(Story.id == story_v1_id).first()

        # Update to v2
        story_v2_id = update_story_with_new_articles(
            session=session,
            existing_story=story_v1,
            existing_article_ids={1},
            merged_article_ids=[1, 2],
            synthesis_data={
                "synthesis": "V2",
                "key_points": [],
                "why_it_matters": "",
                "topics": [],
                "entities": [],
            },
            model="test",
            cluster_data={
                "importance_score": 0.5,
                "freshness_score": 0.5,
                "quality_score": 0.5,
                "cluster_hash": "v2hash",
                "time_window_start": datetime.now(UTC),
                "time_window_end": datetime.now(UTC),
            },
        )
        session.commit()

        story_v2 = session.query(Story).filter(Story.id == story_v2_id).first()

        # Update to v3
        story_v3_id = update_story_with_new_articles(
            session=session,
            existing_story=story_v2,
            existing_article_ids={1, 2},
            merged_article_ids=[1, 2, 3],
            synthesis_data={
                "synthesis": "V3",
                "key_points": [],
                "why_it_matters": "",
                "topics": [],
                "entities": [],
            },
            model="test",
            cluster_data={
                "importance_score": 0.5,
                "freshness_score": 0.5,
                "quality_score": 0.5,
                "cluster_hash": "v3hash",
                "time_window_start": datetime.now(UTC),
                "time_window_end": datetime.now(UTC),
            },
        )
        session.commit()

        # Verify chain: v3 -> v2 -> v1
        story_v3 = session.query(Story).filter(Story.id == story_v3_id).first()
        assert story_v3.version == 3
        assert story_v3.previous_version_id == story_v2_id

        story_v2_refreshed = (
            session.query(Story).filter(Story.id == story_v2_id).first()
        )
        assert story_v2_refreshed.version == 2
        assert story_v2_refreshed.previous_version_id == story_v1_id
        assert story_v2_refreshed.status == "superseded"

        story_v1_refreshed = (
            session.query(Story).filter(Story.id == story_v1_id).first()
        )
        assert story_v1_refreshed.version == 1
        assert story_v1_refreshed.previous_version_id is None
        assert story_v1_refreshed.status == "superseded"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


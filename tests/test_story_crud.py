#!/usr/bin/env python3
"""
Tests for the story read/query functions that remain in app.stories, plus
cleanup_archived_stories() (#346).

create_story(), update_story(), archive_story(), delete_story(), and
link_articles_to_story() were removed in #346 -- confirmed zero production
callers (the live pipeline constructs Story/StoryArticle inline in
generate_stories_simple(), which had grown ~15 fields beyond what
create_story()'s frozen signature ever supported). Test setup that used to
call those functions now uses the tests.pg_testutil factory helpers instead.

Uses PostgreSQL via DATABASE_URL (ADR-0022).
"""
import os
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

if not os.environ.get("DATABASE_URL"):
    pytest.skip("PostgreSQL required (set DATABASE_URL)", allow_module_level=True)

from app.stories import (
    Story,
    StoryArticle,
    cleanup_archived_stories,
    get_stories,
    get_story_by_id,
)
from tests.pg_testutil import (
    create_test_story,
    link_test_articles_to_story,
    pg_session_truncate_story_graph,
    seed_default_feed,
)


def setup_test_db():
    """Reset story-related tables and seed feeds/items used by these tests."""
    session = pg_session_truncate_story_graph()
    seed_default_feed(session)
    session.execute(
        text(
            """
            INSERT INTO items (
                id, feed_id, title, url, url_hash, summary, ranking_score, topic
            )
            VALUES
                (1, 1, 'Article 1', 'http://example.com/i1', 'hash_i1', 'S1', 0.5, 'tech'),
                (2, 1, 'Article 2', 'http://example.com/i2', 'hash_i2', 'S2', 0.5, 'tech'),
                (3, 1, 'Article 3', 'http://example.com/i3', 'hash_i3', 'S3', 0.5, 'tech'),
                (4, 1, 'Article 4', 'http://example.com/i4', 'hash_i4', 'S4', 0.5, 'tech'),
                (5, 1, 'Article 5', 'http://example.com/i5', 'hash_i5', 'S5', 0.5, 'tech'),
                (10, 1, 'Test Article 1', 'http://example.com/1', 'hash1', 'Summary 1', 0.9, 'AI/ML'),
                (20, 1, 'Test Article 2', 'http://example.com/2', 'hash2', 'Summary 2', 0.8, 'Cloud'),
                (30, 1, 'Test Article 3', 'http://example.com/3', 'hash3', 'Summary 3', 0.7, 'Security'),
                (100, 1, 'Article 100', 'http://example.com/100', 'hash100', 'S100', 0.5, 'tech'),
                (200, 1, 'Article 200', 'http://example.com/200', 'hash200', 'S200', 0.5, 'tech')
            """
        )
    )
    session.commit()
    return session


def test_get_story_by_id():
    """Test retrieving a story by ID."""
    session = setup_test_db()
    try:
        story_id = create_test_story(
            session=session,
            title="Test Retrieval Story",
            synthesis="B" * 100,
            key_points=["Point A", "Point B", "Point C"],
            why_it_matters="Testing retrieval",
            topics=["Cloud", "DevOps"],
            entities=["AWS", "Azure"],
            importance_score=0.75,
            freshness_score=0.88,
            model="test",
            time_window_start=datetime.now(UTC),
            time_window_end=datetime.now(UTC),
        )

        link_test_articles_to_story(session, story_id, [10, 20, 30])

        # Retrieve story
        story = get_story_by_id(session, story_id)
        assert story is not None, "Story should be retrieved"
        assert story.id == story_id
        assert story.title == "Test Retrieval Story"
        assert len(story.key_points) == 3
        assert story.key_points == ["Point A", "Point B", "Point C"]
        assert story.article_count == 3
        assert len(story.topics) == 2
        assert "Cloud" in story.topics
    finally:
        session.close()


def test_get_story_not_found():
    """Test retrieving non-existent story returns None."""
    session = setup_test_db()
    try:
        story = get_story_by_id(session, 99999)
        assert story is None, "Non-existent story should return None"
    finally:
        session.close()


def test_get_stories_list():
    """Test querying multiple stories with filters."""
    session = setup_test_db()
    try:
        # Create multiple stories with different scores
        for i in range(5):
            story_id = create_test_story(
                session=session,
                title=f"Test Story Number {i+1}",  # Longer title (> 10 chars)
                synthesis="C" * 100,
                key_points=["A", "B", "C"],
                why_it_matters="Test",
                topics=["Test"],
                entities=["Test"],
                importance_score=0.5 + (i * 0.1),
                freshness_score=0.9,
                model="test",
                time_window_start=datetime.now(UTC),
                time_window_end=datetime.now(UTC),
            )
            # Link at least 1 article to pass validation
            link_test_articles_to_story(session, story_id, [i + 1])

        # Query stories
        stories = get_stories(session, limit=10, status="active", order_by="importance")
        assert len(stories) == 5, f"Expected 5 stories, got {len(stories)}"

        # Verify sorted by importance (highest first)
        assert stories[0].importance_score >= stories[1].importance_score
        assert stories[1].importance_score >= stories[2].importance_score

        # Test limit
        stories_limited = get_stories(session, limit=3)
        assert (
            len(stories_limited) == 3
        ), f"Expected 3 stories, got {len(stories_limited)}"
    finally:
        session.close()


def test_get_stories_generated_at_tiebreak_is_deterministic():
    """
    Reported bug: "Latest Generated" sort order wasn't stable across reloads.

    Batch story generation can give several stories the same (or
    near-identical) generated_at timestamp, and ORDER BY generated_at DESC
    alone has no defined order among ties -- Postgres can return them
    differently from query to query. get_stories() now adds Story.id DESC
    as a secondary key so ties resolve the same way every time.
    """
    session = setup_test_db()
    try:
        same_timestamp = datetime.now(UTC)
        story_ids = []
        for i in range(4):
            story_id = create_test_story(
                session=session,
                title=f"Tied Story {i+1}",
                synthesis="D" * 100,
                key_points=["A", "B", "C"],
                why_it_matters="Test",
                topics=["Test"],
                entities=["Test"],
                importance_score=0.5,
                freshness_score=0.5,
                model="test",
                time_window_start=datetime.now(UTC),
                time_window_end=datetime.now(UTC),
            )
            story = session.query(Story).filter(Story.id == story_id).first()
            story.generated_at = same_timestamp
            session.commit()
            link_test_articles_to_story(session, story_id, [i + 1])
            story_ids.append(story_id)

        first_run = [s.id for s in get_stories(session, order_by="generated_at")]
        second_run = [s.id for s in get_stories(session, order_by="generated_at")]

        assert first_run == second_run, "Order must be stable across identical queries"
        # Secondary key is id DESC: highest id (most recently created) first.
        assert first_run == sorted(story_ids, reverse=True)
    finally:
        session.close()


def test_cleanup_archived():
    """Test cleanup of old archived stories."""
    session = setup_test_db()
    try:
        # Create old archived story
        old_story_id = create_test_story(
            session=session,
            title="Old Archived Story",
            synthesis="G" * 100,
            key_points=["A", "B", "C"],
            why_it_matters="Test",
            topics=["Test"],
            entities=["Test"],
            importance_score=0.5,
            freshness_score=0.7,
            model="test",
            time_window_start=datetime.now(UTC),
            time_window_end=datetime.now(UTC),
        )

        # Archive it and backdate last_updated
        old_story = session.query(Story).filter(Story.id == old_story_id).first()
        old_story.status = "archived"
        old_story.last_updated = datetime.now(UTC) - timedelta(days=40)
        session.commit()

        # Create recent archived story
        recent_story_id = create_test_story(
            session=session,
            title="Recent Archived Story",
            synthesis="H" * 100,
            key_points=["A", "B", "C"],
            why_it_matters="Test",
            topics=["Test"],
            entities=["Test"],
            importance_score=0.5,
            freshness_score=0.7,
            model="test",
            time_window_start=datetime.now(UTC),
            time_window_end=datetime.now(UTC),
        )
        recent_story = session.query(Story).filter(Story.id == recent_story_id).first()
        recent_story.status = "archived"
        session.commit()

        # Cleanup old stories (older than 30 days)
        count = cleanup_archived_stories(session, days=30)
        assert count == 1, f"Should delete 1 old story, deleted {count}"

        # Verify old story is gone, recent one remains
        old = session.query(Story).filter(Story.id == old_story_id).first()
        assert old is None, "Old archived story should be deleted"

        recent = session.query(Story).filter(Story.id == recent_story_id).first()
        assert recent is not None, "Recent archived story should remain"

        # Verify CASCADE also removed the old story's article links
        links = (
            session.query(StoryArticle)
            .filter(StoryArticle.story_id == old_story_id)
            .all()
        )
        assert len(links) == 0, "Article links should be deleted (CASCADE)"
    finally:
        session.close()

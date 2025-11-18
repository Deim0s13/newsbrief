#!/usr/bin/env python3
"""
Test script for story CRUD operations.
Validates that all database operations work correctly with SQLAlchemy ORM.
"""
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.stories import (
    Base,
    Story,
    StoryArticle,
    archive_story,
    cleanup_archived_stories,
    create_story,
    delete_story,
    get_stories,
    get_story_by_id,
    link_articles_to_story,
    update_story,
)


def setup_test_db():
    """Create a temporary test database."""
    from sqlalchemy import text
    
    # Use temporary in-memory SQLite database
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    
    # Create items table for article linking tests
    # (items table is defined in app.db, not in stories Base)
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS items (
                id INTEGER PRIMARY KEY,
                title TEXT,
                url TEXT,
                published DATETIME,
                summary TEXT,
                content_hash TEXT,
                content TEXT,
                ai_summary TEXT,
                ai_model TEXT,
                ai_generated_at DATETIME,
                structured_summary_json TEXT,
                structured_summary_model TEXT,
                structured_summary_content_hash TEXT,
                structured_summary_generated_at DATETIME,
                ranking_score REAL DEFAULT 0.0,
                topic TEXT,
                topic_confidence REAL,
                source_weight REAL DEFAULT 1.0,
                feed_id INTEGER
            )
        """))
        
        # Insert test articles
        conn.execute(text("""
            INSERT INTO items (id, title, url, summary, ranking_score, topic)
            VALUES 
                (10, 'Test Article 1', 'http://example.com/1', 'Summary 1', 0.9, 'AI/ML'),
                (20, 'Test Article 2', 'http://example.com/2', 'Summary 2', 0.8, 'Cloud'),
                (30, 'Test Article 3', 'http://example.com/3', 'Summary 3', 0.7, 'Security')
        """))
        conn.commit()
    
    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal()


def test_create_story():
    """Test creating a story."""
    session = setup_test_db()
    try:
        story_id = create_story(
            session=session,
            title="Test Story: Major AI Breakthrough",
            synthesis="This is a comprehensive test synthesis that exceeds the minimum fifty character requirement for validation.",
            key_points=["First key point", "Second key point", "Third key point"],
            why_it_matters="This is significant because it tests story creation",
            topics=["AI/ML", "Cloud", "Security"],
            entities=["OpenAI", "GPT-5", "Microsoft"],
            importance_score=0.85,
            freshness_score=0.92,
            model="llama3.1:8b",
            time_window_start=datetime.now(UTC) - timedelta(hours=24),
            time_window_end=datetime.now(UTC),
            cluster_method="test",
        )

        assert story_id > 0, "Story ID should be positive"

        # Verify story exists in database
        story = session.query(Story).filter(Story.id == story_id).first()
        assert story is not None, "Story should exist in database"
        assert story.title == "Test Story: Major AI Breakthrough"
        assert story.article_count == 0  # No articles linked yet
        assert story.status == "active"

        return True, "Create story"
    except Exception as e:
        return False, f"Create story: {e}"
    finally:
        session.close()


def test_link_articles():
    """Test linking articles to a story."""
    session = setup_test_db()
    try:
        # Create a story first
        story_id = create_story(
            session=session,
            title="Test Story for Article Linking",
            synthesis="A" * 100,
            key_points=["A", "B", "C"],
            why_it_matters="Test",
            topics=["AI/ML"],
            entities=["Test"],
            importance_score=0.8,
            freshness_score=0.9,
            model="test",
            time_window_start=datetime.now(UTC),
            time_window_end=datetime.now(UTC),
        )

        # Link articles
        link_articles_to_story(
            session=session,
            story_id=story_id,
            article_ids=[1, 2, 3, 4, 5],
            primary_article_id=2,
        )

        # Verify links
        story = session.query(Story).filter(Story.id == story_id).first()
        assert (
            story.article_count == 5
        ), f"Expected 5 articles, got {story.article_count}"

        links = (
            session.query(StoryArticle).filter(StoryArticle.story_id == story_id).all()
        )
        assert len(links) == 5, f"Expected 5 links, got {len(links)}"

        # Verify primary article
        primary = (
            session.query(StoryArticle)
            .filter(StoryArticle.story_id == story_id, StoryArticle.is_primary == True)
            .first()
        )
        assert primary is not None, "Should have a primary article"
        assert (
            primary.article_id == 2
        ), f"Primary should be article 2, got {primary.article_id}"

        return True, "Link articles to story"
    except Exception as e:
        return False, f"Link articles: {e}"
    finally:
        session.close()


def test_get_story_by_id():
    """Test retrieving a story by ID."""
    session = setup_test_db()
    try:
        # Create and link story
        story_id = create_story(
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

        link_articles_to_story(session, story_id, [10, 20, 30])

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

        return True, "Get story by ID"
    except Exception as e:
        return False, f"Get story by ID: {e}"
    finally:
        session.close()


def test_get_story_not_found():
    """Test retrieving non-existent story returns None."""
    session = setup_test_db()
    try:
        story = get_story_by_id(session, 99999)
        assert story is None, "Non-existent story should return None"
        return True, "Get non-existent story"
    except Exception as e:
        return False, f"Get non-existent story: {e}"
    finally:
        session.close()


def test_get_stories_list():
    """Test querying multiple stories with filters."""
    session = setup_test_db()
    try:
        # Create multiple stories with different scores
        for i in range(5):
            story_id = create_story(
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
            link_articles_to_story(session, story_id, [i + 1])

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

        return True, "Get stories (list/filter/sort)"
    except Exception as e:
        return False, f"Get stories: {e}"
    finally:
        session.close()


def test_update_story():
    """Test updating story fields."""
    session = setup_test_db()
    try:
        story_id = create_story(
            session=session,
            title="Original Title",
            synthesis="D" * 100,
            key_points=["A", "B", "C"],
            why_it_matters="Original",
            topics=["AI/ML"],
            entities=["Test"],
            importance_score=0.5,
            freshness_score=0.8,
            model="test",
            time_window_start=datetime.now(UTC),
            time_window_end=datetime.now(UTC),
        )

        # Update story
        success = update_story(
            session,
            story_id,
            title="Updated Title",
            importance_score=0.95,
        )
        assert success, "Update should succeed"

        # Verify updates
        story = session.query(Story).filter(Story.id == story_id).first()
        assert story.title == "Updated Title"
        assert story.importance_score == 0.95

        return True, "Update story"
    except Exception as e:
        return False, f"Update story: {e}"
    finally:
        session.close()


def test_update_nonexistent():
    """Test updating non-existent story returns False."""
    session = setup_test_db()
    try:
        success = update_story(session, 99999, title="Won't work")
        assert not success, "Update non-existent should return False"
        return True, "Update non-existent story"
    except Exception as e:
        return False, f"Update non-existent: {e}"
    finally:
        session.close()


def test_archive_story():
    """Test archiving a story (soft delete)."""
    session = setup_test_db()
    try:
        story_id = create_story(
            session=session,
            title="Story to Archive",
            synthesis="E" * 100,
            key_points=["A", "B", "C"],
            why_it_matters="Test",
            topics=["Test"],
            entities=["Test"],
            importance_score=0.7,
            freshness_score=0.85,
            model="test",
            time_window_start=datetime.now(UTC),
            time_window_end=datetime.now(UTC),
        )

        # Archive story
        success = archive_story(session, story_id)
        assert success, "Archive should succeed"

        # Verify story still exists but is archived
        story = session.query(Story).filter(Story.id == story_id).first()
        assert story is not None, "Story should still exist in database"
        assert (
            story.status == "archived"
        ), f"Status should be 'archived', got '{story.status}'"

        return True, "Archive story (soft delete)"
    except Exception as e:
        return False, f"Archive story: {e}"
    finally:
        session.close()


def test_delete_story():
    """Test hard deleting a story."""
    session = setup_test_db()
    try:
        story_id = create_story(
            session=session,
            title="Story to Delete",
            synthesis="F" * 100,
            key_points=["A", "B", "C"],
            why_it_matters="Test",
            topics=["Test"],
            entities=["Test"],
            importance_score=0.6,
            freshness_score=0.8,
            model="test",
            time_window_start=datetime.now(UTC),
            time_window_end=datetime.now(UTC),
        )

        # Link articles
        link_articles_to_story(session, story_id, [100, 200])

        # Delete story
        success = delete_story(session, story_id)
        assert success, "Delete should succeed"

        # Verify story is gone
        story = session.query(Story).filter(Story.id == story_id).first()
        assert story is None, "Story should be deleted from database"

        # Verify links are also gone (CASCADE)
        links = (
            session.query(StoryArticle).filter(StoryArticle.story_id == story_id).all()
        )
        assert len(links) == 0, "Article links should be deleted (CASCADE)"

        return True, "Delete story (hard delete with CASCADE)"
    except Exception as e:
        return False, f"Delete story: {e}"
    finally:
        session.close()


def test_cleanup_archived():
    """Test cleanup of old archived stories."""
    session = setup_test_db()
    try:
        # Create old archived story
        old_story_id = create_story(
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
        archive_story(session, old_story_id)
        old_story = session.query(Story).filter(Story.id == old_story_id).first()
        old_story.last_updated = datetime.now(UTC) - timedelta(days=40)
        session.commit()

        # Create recent archived story
        recent_story_id = create_story(
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
        archive_story(session, recent_story_id)

        # Cleanup old stories (older than 30 days)
        count = cleanup_archived_stories(session, days=30)
        assert count == 1, f"Should delete 1 old story, deleted {count}"

        # Verify old story is gone, recent one remains
        old = session.query(Story).filter(Story.id == old_story_id).first()
        assert old is None, "Old archived story should be deleted"

        recent = session.query(Story).filter(Story.id == recent_story_id).first()
        assert recent is not None, "Recent archived story should remain"

        return True, "Cleanup archived stories"
    except Exception as e:
        return False, f"Cleanup archived: {e}"
    finally:
        session.close()


def main():
    """Run all tests and report results."""
    print("🧪 Testing Story CRUD Operations\n")
    print("=" * 60)

    tests = [
        test_create_story,
        test_link_articles,
        test_get_story_by_id,
        test_get_story_not_found,
        test_get_stories_list,
        test_update_story,
        test_update_nonexistent,
        test_archive_story,
        test_delete_story,
        test_cleanup_archived,
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

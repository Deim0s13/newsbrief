#!/usr/bin/env python3
"""
Test script for story generation pipeline.
Validates that story generation works end-to-end.
"""

import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.stories import Base, generate_stories_simple, get_stories


def setup_test_db():
    """Create a temporary test database with articles."""
    # Use temporary in-memory SQLite database
    engine = create_engine("sqlite:///:memory:", echo=False)

    # Create all tables (stories, story_articles, and items)
    Base.metadata.create_all(engine)

    # Create additional tables needed for story generation
    with engine.connect() as conn:
        # Items table
        conn.execute(
            text(
                """
            CREATE TABLE IF NOT EXISTS items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT,
                url TEXT,
                published DATETIME,
                summary TEXT,
                ai_summary TEXT,
                topic TEXT,
                content TEXT,
                feed_id INTEGER,
                entities_json TEXT,
                entities_extracted_at DATETIME,
                entities_model TEXT
            )
        """
            )
        )
        
        # Feeds table (required for health score lookups)
        conn.execute(
            text(
                """
            CREATE TABLE IF NOT EXISTS feeds (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                url TEXT,
                health_score REAL DEFAULT 100.0
            )
        """
            )
        )
        
        # Insert a default feed
        conn.execute(
            text("INSERT INTO feeds (id, name, url, health_score) VALUES (1, 'Test Feed', 'http://test.com', 100.0)")
        )
        
        # Synthesis cache table
        conn.execute(
            text(
                """
            CREATE TABLE IF NOT EXISTS synthesis_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cache_key TEXT UNIQUE NOT NULL,
                article_ids_json TEXT NOT NULL,
                model TEXT NOT NULL,
                synthesis TEXT NOT NULL,
                key_points_json TEXT NOT NULL,
                why_it_matters TEXT,
                topics_json TEXT,
                entities_json TEXT,
                token_count_input INTEGER,
                token_count_output INTEGER,
                generation_time_ms INTEGER,
                created_at DATETIME NOT NULL,
                expires_at DATETIME NOT NULL,
                invalidated_at DATETIME
            )
        """
            )
        )
        conn.commit()

    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal()


def insert_test_articles(session):
    """Insert test articles into database."""
    # Current time
    now = datetime.now(UTC)

    # Test articles about AI/ML topic
    ai_articles = [
        (
            "OpenAI Announces GPT-5 with Major Improvements",
            "OpenAI today unveiled GPT-5, featuring significant improvements in reasoning and multimodal capabilities.",
            "AI/ML",
        ),
        (
            "GPT-5 Beats GPT-4 on All Benchmarks",
            "New tests show GPT-5 outperforms its predecessor across all major AI benchmarks.",
            "AI/ML",
        ),
        (
            "OpenAI's Latest Model Shows Improved Reasoning",
            "The company's newest model demonstrates enhanced logical reasoning and problem-solving abilities.",
            "AI/ML",
        ),
        # Different AI story
        (
            "Google Releases New Gemini Model",
            "Google announced Gemini 2.0, their latest multimodal AI model competing with GPT-5.",
            "AI/ML",
        ),
        (
            "Gemini 2.0 Features Native Multimodal Processing",
            "The new model can process text, images, and video natively without separate encoders.",
            "AI/ML",
        ),
    ]

    # Test articles about Cloud/Infrastructure topic
    cloud_articles = [
        (
            "AWS Launches New Database Service",
            "Amazon Web Services introduced a new managed database offering for high-performance workloads.",
            "Cloud",
        ),
        (
            "Microsoft Azure Expands Data Center Network",
            "Azure announces new data centers in three continents to improve global reach.",
            "Cloud",
        ),
    ]

    # Single article about Security
    security_articles = [
        (
            "Critical Vulnerability Found in Popular Library",
            "Researchers discovered a severe security flaw affecting millions of applications.",
            "Security",
        ),
    ]

    all_articles = ai_articles + cloud_articles + security_articles

    article_ids = []
    for title, summary, topic in all_articles:
        result = session.execute(
            text(
                """
                INSERT INTO items (title, summary, ai_summary, topic, published, url, content, feed_id)
                VALUES (:title, :summary, :ai_summary, :topic, :published, :url, :content, :feed_id)
            """
            ),
            {
                "title": title,
                "summary": summary,
                "ai_summary": f"AI Summary: {summary}",  # Simulate AI summary
                "topic": topic,
                "published": now - timedelta(hours=2),  # 2 hours ago
                "url": f"https://example.com/{len(article_ids)}",
                "content": f"Full content: {summary}",
                "feed_id": 1,  # Default test feed
            },
        )
        session.commit()
        article_ids.append(result.lastrowid)

    return article_ids


def test_story_generation():
    """Test the full story generation pipeline."""
    print("🧪 Testing Story Generation Pipeline\n")
    print("=" * 60)

    session = setup_test_db()
    try:
        # Insert test articles
        print("📝 Inserting test articles...")
        article_ids = insert_test_articles(session)
        print(f"✅ Inserted {len(article_ids)} test articles")

        # Generate stories
        print("\n🔄 Generating stories (24h window)...")
        story_ids = generate_stories_simple(
            session=session,
            time_window_hours=24,
            min_articles_per_story=1,
            similarity_threshold=0.3,
            model="llama3.1:8b",  # Will fall back if not available
        )

        print(f"✅ Generated {len(story_ids)} stories")

        # Validate stories
        print("\n🔍 Validating generated stories...")

        assert len(story_ids) > 0, "No stories generated"

        # Retrieve stories
        stories = get_stories(session, limit=10, status="active")

        assert len(stories) == len(story_ids), f"Story count mismatch: created {len(story_ids)}, retrieved {len(stories)}"

        # Validate each story
        for i, story in enumerate(stories, 1):
            print(f"\n  Story #{i}:")
            print(f"  Title: {story.title[:80]}...")
            print(f"  Synthesis: {story.synthesis[:100]}...")
            print(f"  Key Points: {len(story.key_points)} points")
            print(f"  Topics: {story.topics}")
            print(f"  Entities: {story.entities}")
            print(f"  Articles: {story.article_count}")
            print(f"  Importance: {story.importance_score:.2f}")

            # Validate required fields
            assert story.title, "Story must have title"
            assert story.synthesis, "Story must have synthesis"
            assert len(story.key_points) >= 1, "Story must have key points"
            assert story.article_count >= 1, "Story must have articles"
            assert 0.0 <= story.importance_score <= 1.0, "Invalid importance score"
            assert 0.0 <= story.freshness_score <= 1.0, "Invalid freshness score"

        print("\n" + "=" * 60)
        print(f"\n📊 Summary:")
        print(f"  Articles processed: {len(article_ids)}")
        print(f"  Stories generated: {len(story_ids)}")
        print(
            f"  Clustering efficiency: {len(article_ids)/len(story_ids):.1f} articles/story"
        )

        # Expected clusters based on our test data:
        # - GPT-5 articles (3 articles) -> 1 story
        # - Gemini articles (2 articles) -> 1 story
        # - AWS article (1 article) -> 1 story
        # - Azure article (1 article) -> 1 story (or merged with AWS)
        # - Security article (1 article) -> 1 story
        # Total: 4-5 stories expected

        expected_stories = range(4, 6)  # 4-5 stories
        if len(story_ids) in expected_stories:
            print(f"  ✅ Story count in expected range: {expected_stories}")
        else:
            print(
                f"  ⚠️  Story count ({len(story_ids)}) outside expected range: {expected_stories}"
            )

        print("\n✅ All validation tests passed!")
    finally:
        session.close()


def main():
    """Run all tests and report results."""
    success, message = test_story_generation()

    if success:
        print("\n" + "=" * 60)
        print("✅ All tests passed!")
        return 0
    else:
        print("\n" + "=" * 60)
        print(f"❌ Tests failed: {message}")
        return 1


if __name__ == "__main__":
    exit(main())

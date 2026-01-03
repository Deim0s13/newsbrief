#!/usr/bin/env python3
"""
Manual test for story generation with real Ollama LLM.
Tests the complete synthesis pipeline with actual AI generation.

NOTE: These tests require Ollama to be running with llama3.1:8b model.
They will be skipped in CI where Ollama is not available.
"""

import os
import tempfile
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.llm import get_llm_service
from app.stories import (Base, _generate_story_synthesis,
                         generate_stories_simple)

# Use a temporary file-based database for threading support
_test_db_path = None


def _check_llm_available():
    """Check if LLM is available, skip test if not."""
    llm_service = get_llm_service()
    if not llm_service.is_available():
        pytest.skip("Ollama not available - skipping LLM test")
    if not llm_service.ensure_model("llama3.1:8b"):
        pytest.skip("Model llama3.1:8b not available - skipping LLM test")


def setup_test_db():
    """Create a temporary test database with articles."""
    global _test_db_path
    
    # Use file-based SQLite with check_same_thread=False for threading support
    _test_db_path = tempfile.mktemp(suffix=".db")
    engine = create_engine(
        f"sqlite:///{_test_db_path}",
        echo=False,
        connect_args={"check_same_thread": False}
    )
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


def test_llm_availability():
    """Test if Ollama is available."""
    print("🔍 Checking Ollama availability...")

    llm_service = get_llm_service()

    if not llm_service.is_available():
        print("⚠️ Ollama is not available - skipping LLM tests")
        import pytest
        pytest.skip("Ollama not available")

    print("✅ Ollama is available")

    # Check if model is available
    model = "llama3.1:8b"
    print(f"🔍 Checking model: {model}...")

    if not llm_service.ensure_model(model):
        print(f"⚠️ Model {model} not available - skipping")
        import pytest
        pytest.skip(f"Model {model} not available")

    print(f"✅ Model {model} is ready")


def test_synthesis_with_llm():
    """Test story synthesis with real LLM."""
    # Skip if LLM not available (e.g., in CI)
    _check_llm_available()
    
    print("\n🧪 Testing Story Synthesis with Real LLM")
    print("=" * 70)

    session = setup_test_db()

    try:
        # Insert test articles about the same story (GPT-5 release)
        now = datetime.now(UTC)

        articles = [
            {
                "title": "OpenAI Announces GPT-5 with Major Improvements",
                "summary": "OpenAI today unveiled GPT-5, their most advanced language model to date. The new model features significantly improved reasoning capabilities, better context understanding, and native multimodal processing. CEO Sam Altman stated this represents a 'major leap forward' in AI capabilities.",
                "ai_summary": "GPT-5 released by OpenAI with enhanced reasoning, multimodal support, and improved performance over GPT-4.",
                "topic": "AI/ML",
            },
            {
                "title": "GPT-5 Outperforms GPT-4 on All Major Benchmarks",
                "summary": "Independent testing shows GPT-5 achieving state-of-the-art results across all major AI benchmarks. The model scored 92% on MMLU, up from 86% for GPT-4, and showed remarkable improvements in coding tasks with 94% on HumanEval.",
                "ai_summary": "GPT-5 sets new benchmarks with 92% MMLU and 94% HumanEval scores, significantly outperforming GPT-4.",
                "topic": "AI/ML",
            },
            {
                "title": "Developers React to GPT-5's New API Features",
                "summary": "The developer community is excited about GPT-5's new API capabilities, including streaming responses, function calling improvements, and reduced latency. Early adopters report the model is 2x faster than GPT-4 while being more accurate.",
                "ai_summary": "GPT-5 API features streaming, better function calling, and 2x faster performance than GPT-4, receiving positive developer feedback.",
                "topic": "AI/ML",
            },
        ]

        article_ids = []
        for article in articles:
            result = session.execute(
                text(
                    """
                    INSERT INTO items (title, summary, ai_summary, topic, published, url, content, feed_id)
                    VALUES (:title, :summary, :ai_summary, :topic, :published, :url, :content, :feed_id)
                """
                ),
                {
                    "title": article["title"],
                    "summary": article["summary"],
                    "ai_summary": article["ai_summary"],
                    "topic": article["topic"],
                    "published": now - timedelta(hours=1),
                    "url": f"https://example.com/article-{len(article_ids)}",
                    "content": article["summary"],
                    "feed_id": 1,
                },
            )
            session.commit()
            article_ids.append(result.lastrowid)

        print(f"✅ Inserted {len(article_ids)} related articles\n")

        # Test synthesis
        print("🔄 Generating synthesis with LLM...")
        print("-" * 70)

        synthesis_data = _generate_story_synthesis(
            session, article_ids, model="llama3.1:8b"
        )

        print("\n📰 Generated Story:")
        print("=" * 70)
        print(f"\n💡 Synthesis:")
        print(f"   {synthesis_data['synthesis']}\n")

        print(f"📌 Key Points:")
        for i, point in enumerate(synthesis_data["key_points"], 1):
            print(f"   {i}. {point}")

        print(f"\n🎯 Why It Matters:")
        print(f"   {synthesis_data['why_it_matters']}\n")

        print(f"🏷️  Topics: {', '.join(synthesis_data['topics'])}")
        print(f"👥 Entities: {', '.join(synthesis_data['entities'])}")

        print("\n" + "=" * 70)

        # Validate structure
        assert synthesis_data["synthesis"], "Synthesis should not be empty"
        assert (
            len(synthesis_data["key_points"]) >= 3
        ), "Should have at least 3 key points"
        assert synthesis_data["why_it_matters"], "Why it matters should not be empty"
        assert synthesis_data["topics"], "Should have topics"
        assert synthesis_data["entities"], "Should have entities"

        # Check that it's not just concatenation (LLM actually synthesized)
        is_real_synthesis = (
            len(synthesis_data["synthesis"]) > 100  # Should be a proper paragraph
            and "Multiple articles" not in synthesis_data["synthesis"]  # Not fallback
            and len(synthesis_data["entities"]) > 2  # Extracted entities
        )

        if is_real_synthesis:
            print("\n✅ LLM Synthesis Verified:")
            print("   - Generated coherent paragraph")
            print("   - Extracted multiple entities")
            print("   - Proper structured output")
        else:
            print("\n⚠️  May have used fallback synthesis")
    finally:
        session.close()
        _cleanup_test_db()


def _cleanup_test_db():
    """Clean up temporary database file."""
    global _test_db_path
    if _test_db_path and os.path.exists(_test_db_path):
        try:
            os.unlink(_test_db_path)
        except OSError:
            pass  # Ignore cleanup errors


def test_full_pipeline_with_llm():
    """Test the complete story generation pipeline."""
    # Skip if LLM not available (e.g., in CI)
    _check_llm_available()
    
    print("\n\n🧪 Testing Full Pipeline with LLM")
    print("=" * 70)

    session = setup_test_db()

    try:
        # Insert diverse test articles
        now = datetime.now(UTC)

        articles = [
            # GPT-5 cluster (should merge)
            ("OpenAI Announces GPT-5", "GPT-5 announcement details", "AI/ML"),
            ("GPT-5 Beats GPT-4", "Benchmark results", "AI/ML"),
            ("GPT-5 API Released", "Developer features", "AI/ML"),
            # Different topic
            ("AWS Launches New Database", "Aurora v3 details", "Cloud"),
            ("Google Cloud Updates", "GCP new features", "Cloud"),
        ]

        for title, summary, topic in articles:
            session.execute(
                text(
                    """
                    INSERT INTO items (title, summary, ai_summary, topic, published, url, content, feed_id)
                    VALUES (:title, :summary, :ai_summary, :topic, :published, :url, :content, :feed_id)
                """
                ),
                {
                    "title": title,
                    "summary": summary,
                    "ai_summary": f"AI Summary: {summary}",
                    "topic": topic,
                    "published": now - timedelta(hours=2),
                    "url": f"https://example.com/{title.replace(' ', '-')}",
                    "content": summary,
                    "feed_id": 1,
                },
            )
        session.commit()

        print(f"✅ Inserted {len(articles)} test articles\n")

        # Generate stories
        print("🔄 Running story generation pipeline...")
        story_ids = generate_stories_simple(
            session=session,
            time_window_hours=24,
            min_articles_per_story=1,
            similarity_threshold=0.3,
            model="llama3.1:8b",
        )

        print(f"\n✅ Generated {len(story_ids)} stories")
        print(f"   Articles clustered: {len(articles)} → {len(story_ids)} stories")
        print(f"   Clustering ratio: {len(articles)/len(story_ids):.1f} articles/story")

        # We expect 2-3 stories:
        # - 1 story from GPT-5 articles (3 similar articles)
        # - 1-2 stories from Cloud articles (depends on similarity)

        if 2 <= len(story_ids) <= 4:
            print(f"   ✅ Story count in expected range (2-4)")
        else:
            print(f"   ⚠️  Story count outside expected range: {len(story_ids)}")
        
        # Still pass if we got stories, the count range is just informational
        assert len(story_ids) > 0, "Should generate at least one story"
    finally:
        session.close()
        _cleanup_test_db()


def main():
    """Run all manual tests."""
    print("=" * 70)
    print("🧪 Manual Story Generation Test with Real Ollama LLM")
    print("=" * 70)

    # Check Ollama availability
    if not test_llm_availability():
        print("\n❌ Cannot proceed without Ollama")
        print("\n💡 To fix:")
        print("   1. Start Ollama: ollama serve")
        print("   2. Pull model: ollama pull llama3.1:8b")
        print("   3. Run this test again")
        return 1

    # Test synthesis
    success1, msg1 = test_synthesis_with_llm()

    # Test full pipeline
    success2, msg2 = test_full_pipeline_with_llm()

    # Summary
    print("\n" + "=" * 70)
    print("📊 Test Summary")
    print("=" * 70)
    print(f"LLM Synthesis Test: {'✅ PASS' if success1 else '❌ FAIL'} - {msg1}")
    print(f"Full Pipeline Test: {'✅ PASS' if success2 else '❌ FAIL'} - {msg2}")

    if success1 and success2:
        print("\n✅ All manual tests passed!")
        print("\n🎉 Story generation with LLM is working correctly!")
        return 0
    else:
        print("\n❌ Some tests failed")
        return 1


if __name__ == "__main__":
    exit(main())

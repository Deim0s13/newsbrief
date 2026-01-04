"""Unit tests for entity extraction functionality."""

import json
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import text

from app.entities import (
    ExtractedEntities,
    extract_and_cache_entities,
    extract_entities,
    get_cached_entities,
    get_entity_overlap,
    store_entity_cache,
)


class TestExtractedEntities:
    """Test ExtractedEntities dataclass."""

    def test_to_json_string(self):
        """Test JSON serialization."""
        entities = ExtractedEntities(
            companies=["Google", "OpenAI"],
            products=["Gemini 2.0", "GPT-4"],
            people=["Sundar Pichai"],
            technologies=["AI", "Machine Learning"],
            locations=["San Francisco"],
        )

        json_str = entities.to_json_string()
        data = json.loads(json_str)

        assert data["companies"] == ["Google", "OpenAI"]
        assert data["products"] == ["Gemini 2.0", "GPT-4"]
        assert data["people"] == ["Sundar Pichai"]
        assert data["technologies"] == ["AI", "Machine Learning"]
        assert data["locations"] == ["San Francisco"]

    def test_from_json_string(self):
        """Test JSON deserialization."""
        json_str = json.dumps(
            {
                "companies": ["Google"],
                "products": ["Gemini"],
                "people": [],
                "technologies": ["AI"],
                "locations": [],
            }
        )

        entities = ExtractedEntities.from_json_string(json_str)

        assert entities.companies == ["Google"]
        assert entities.products == ["Gemini"]
        assert entities.people == []
        assert entities.technologies == ["AI"]
        assert entities.locations == []

    def test_is_empty_true(self):
        """Test is_empty returns True for empty entities."""
        entities = ExtractedEntities(
            companies=[],
            products=[],
            people=[],
            technologies=[],
            locations=[],
        )

        assert entities.is_empty() is True

    def test_is_empty_false(self):
        """Test is_empty returns False when entities exist."""
        entities = ExtractedEntities(
            companies=["Google"],
            products=[],
            people=[],
            technologies=[],
            locations=[],
        )

        assert entities.is_empty() is False

    def test_all_entities(self):
        """Test all_entities returns flat set."""
        entities = ExtractedEntities(
            companies=["Google", "OpenAI"],
            products=["Gemini"],
            people=[],
            technologies=["AI"],
            locations=["San Francisco"],
        )

        all_ents = entities.all_entities()

        assert len(all_ents) == 5
        assert "Google" in all_ents
        assert "OpenAI" in all_ents
        assert "Gemini" in all_ents
        assert "AI" in all_ents
        assert "San Francisco" in all_ents


class TestEntityOverlap:
    """Test entity overlap calculation."""

    def test_full_overlap(self):
        """Test 100% overlap."""
        entities1 = ExtractedEntities(
            companies=["Google"],
            products=["Gemini"],
            people=[],
            technologies=[],
            locations=[],
        )
        entities2 = ExtractedEntities(
            companies=["Google"],
            products=["Gemini"],
            people=[],
            technologies=[],
            locations=[],
        )

        overlap = get_entity_overlap(entities1, entities2)

        assert overlap == 1.0

    def test_partial_overlap(self):
        """Test partial overlap."""
        entities1 = ExtractedEntities(
            companies=["Google", "Microsoft"],
            products=[],
            people=[],
            technologies=[],
            locations=[],
        )
        entities2 = ExtractedEntities(
            companies=["Google", "Apple"],
            products=[],
            people=[],
            technologies=[],
            locations=[],
        )

        overlap = get_entity_overlap(entities1, entities2)

        # Intersection: {Google}, Union: {Google, Microsoft, Apple}
        # Overlap = 1/3 = 0.333...
        assert 0.3 < overlap < 0.4

    def test_no_overlap(self):
        """Test zero overlap."""
        entities1 = ExtractedEntities(
            companies=["Google"],
            products=[],
            people=[],
            technologies=[],
            locations=[],
        )
        entities2 = ExtractedEntities(
            companies=["Apple"],
            products=[],
            people=[],
            technologies=[],
            locations=[],
        )

        overlap = get_entity_overlap(entities1, entities2)

        assert overlap == 0.0

    def test_empty_entities(self):
        """Test overlap with empty entities."""
        entities1 = ExtractedEntities(
            companies=[],
            products=[],
            people=[],
            technologies=[],
            locations=[],
        )
        entities2 = ExtractedEntities(
            companies=[],
            products=[],
            people=[],
            technologies=[],
            locations=[],
        )

        overlap = get_entity_overlap(entities1, entities2)

        assert overlap == 0.0


class TestEntityExtraction:
    """Test entity extraction with LLM."""

    def test_extract_entities_no_title_or_summary(self):
        """Test extraction with no input."""
        entities = extract_entities("", "")

        assert entities.is_empty()

    @patch("app.entities.get_llm_service")
    def test_extract_entities_llm_unavailable(self, mock_get_llm):
        """Test extraction when LLM is unavailable."""
        mock_service = MagicMock()
        mock_service.is_available.return_value = False
        mock_get_llm.return_value = mock_service

        entities = extract_entities("Test Title", "Test summary")

        assert entities.is_empty()

    @patch("app.entities.get_llm_service")
    def test_extract_entities_success(self, mock_get_llm):
        """Test successful entity extraction."""
        # Mock LLM service
        mock_service = MagicMock()
        mock_service.is_available.return_value = True
        mock_client = MagicMock()
        mock_client.generate.return_value = {
            "response": json.dumps(
                {
                    "companies": ["Google", "OpenAI"],
                    "products": ["Gemini 2.0"],
                    "people": [],
                    "technologies": ["AI"],
                    "locations": ["San Francisco"],
                }
            )
        }
        mock_service.client = mock_client
        mock_get_llm.return_value = mock_service

        entities = extract_entities(
            "Google Announces Gemini 2.0",
            "Google released Gemini 2.0 in San Francisco, competing with OpenAI.",
        )

        assert "Google" in entities.companies
        assert "OpenAI" in entities.companies
        assert "Gemini 2.0" in entities.products
        assert "AI" in entities.technologies
        assert "San Francisco" in entities.locations

    @patch("app.entities.get_llm_service")
    def test_extract_entities_json_error(self, mock_get_llm):
        """Test extraction with invalid JSON response."""
        # Mock LLM service
        mock_service = MagicMock()
        mock_service.is_available.return_value = True
        mock_client = MagicMock()
        mock_client.generate.return_value = {"response": "not valid json"}
        mock_service.client = mock_client
        mock_get_llm.return_value = mock_service

        entities = extract_entities("Test Title", "Test summary")

        # Should return empty entities on error
        assert entities.is_empty()

    @patch("app.entities.get_llm_service")
    def test_extract_entities_limits_to_five_per_category(self, mock_get_llm):
        """Test that entities are limited to 5 per category."""
        # Mock LLM service
        mock_service = MagicMock()
        mock_service.is_available.return_value = True
        mock_client = MagicMock()
        mock_client.generate.return_value = {
            "response": json.dumps(
                {
                    "companies": [
                        "Company1",
                        "Company2",
                        "Company3",
                        "Company4",
                        "Company5",
                        "Company6",
                        "Company7",
                    ],
                    "products": [],
                    "people": [],
                    "technologies": [],
                    "locations": [],
                }
            )
        }
        mock_service.client = mock_client
        mock_get_llm.return_value = mock_service

        entities = extract_entities("Test Title", "Test summary")

        # Should limit to 5
        assert len(entities.companies) == 5


class TestEntityCaching:
    """Test entity caching functionality."""

    def test_store_and_retrieve_cache(self, setup_test_db):
        """Test storing and retrieving cached entities."""
        session = setup_test_db

        # Insert a test article
        result = session.execute(
            text(
                """
            INSERT INTO items (feed_id, title, url, url_hash, published)
            VALUES (1, 'Test Article', 'http://test.com/1', 'hash1', datetime('now'))
            """
            )
        )
        session.commit()
        article_id = result.lastrowid

        # Create and store entities
        entities = ExtractedEntities(
            companies=["Google"],
            products=["Gemini"],
            people=[],
            technologies=["AI"],
            locations=[],
        )

        success = store_entity_cache(article_id, entities, session, model="llama3.1:8b")
        assert success is True

        # Retrieve cached entities
        cached = get_cached_entities(article_id, session, model="llama3.1:8b")
        assert cached is not None
        assert cached.companies == ["Google"]
        assert cached.products == ["Gemini"]
        assert cached.technologies == ["AI"]

    def test_cache_miss_different_model(self, setup_test_db):
        """Test cache miss when model differs."""
        session = setup_test_db

        # Insert a test article
        result = session.execute(
            text(
                """
            INSERT INTO items (feed_id, title, url, url_hash, published)
            VALUES (1, 'Test Article', 'http://test.com/2', 'hash2', datetime('now'))
            """
            )
        )
        session.commit()
        article_id = result.lastrowid

        # Store entities with one model
        entities = ExtractedEntities(
            companies=["Google"],
            products=[],
            people=[],
            technologies=[],
            locations=[],
        )
        store_entity_cache(article_id, entities, session, model="llama3.1:8b")

        # Try to retrieve with different model
        cached = get_cached_entities(article_id, session, model="different-model")
        assert cached is None

    def test_cache_miss_no_entities(self, setup_test_db):
        """Test cache miss when no entities stored."""
        session = setup_test_db

        # Insert a test article without entities
        result = session.execute(
            text(
                """
            INSERT INTO items (feed_id, title, url, url_hash, published)
            VALUES (1, 'Test Article', 'http://test.com/3', 'hash3', datetime('now'))
            """
            )
        )
        session.commit()
        article_id = result.lastrowid

        # Try to retrieve entities (should be None)
        cached = get_cached_entities(article_id, session)
        assert cached is None


@pytest.fixture
def setup_test_db():
    """Set up test database with items table."""
    from app.db import SessionLocal, init_db

    # Initialize database
    init_db()

    # Create session
    session = SessionLocal()

    # Create a test feed if needed
    try:
        session.execute(
            text(
                """
            INSERT OR IGNORE INTO feeds (id, url, name)
            VALUES (1, 'http://test.com/feed', 'Test Feed')
            """
            )
        )
        session.commit()
    except Exception:
        session.rollback()

    yield session

    # Cleanup
    try:
        session.execute(text("DELETE FROM items WHERE url LIKE 'http://test.com/%'"))
        session.commit()
    except Exception:
        session.rollback()
    finally:
        session.close()

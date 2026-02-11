"""Unit tests for entity extraction functionality."""

import json
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import text

from app.entities import (
    ROLE_MENTIONED,
    ROLE_PRIMARY,
    EntityWithMetadata,
    ExtractedEntities,
    extract_and_cache_entities,
    extract_entities,
    get_cached_entities,
    get_entity_overlap,
    store_entity_cache,
)


class TestExtractedEntities:
    """Test ExtractedEntities dataclass."""

    def test_to_json_string_legacy_input(self):
        """Test JSON serialization with simple string input (backward compat)."""
        entities = ExtractedEntities(
            companies=["Google", "OpenAI"],
            products=["Gemini 2.0", "GPT-4"],
            people=["Sundar Pichai"],
            technologies=["AI", "Machine Learning"],
            locations=["San Francisco"],
        )

        json_str = entities.to_json_string()
        data = json.loads(json_str)

        # V2 format includes version marker
        assert data.get("version") == 2
        # Companies should be converted to full entity objects
        assert len(data["companies"]) == 2
        assert data["companies"][0]["name"] == "Google"
        assert data["companies"][1]["name"] == "OpenAI"

    def test_to_json_string_enhanced(self):
        """Test JSON serialization with EntityWithMetadata input."""
        entities = ExtractedEntities(
            companies=[
                EntityWithMetadata("Google", 0.95, ROLE_PRIMARY, "Search giant"),
                EntityWithMetadata("OpenAI", 0.9, ROLE_MENTIONED, "AI company"),
            ],
            products=[],
            people=[],
            technologies=[],
            locations=[],
        )

        json_str = entities.to_json_string()
        data = json.loads(json_str)

        assert data["version"] == 2
        assert data["companies"][0]["name"] == "Google"
        assert data["companies"][0]["confidence"] == 0.95
        assert data["companies"][0]["role"] == ROLE_PRIMARY
        assert data["companies"][0]["disambiguation"] == "Search giant"

    def test_from_json_string_legacy(self):
        """Test JSON deserialization of legacy (v1) format."""
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

        # Should convert strings to EntityWithMetadata
        assert len(entities.companies) == 1
        assert entities.companies[0].name == "Google"
        assert entities.companies[0].confidence == 0.8  # Default
        assert entities.companies[0].role == ROLE_MENTIONED  # Default

    def test_from_json_string_v2(self):
        """Test JSON deserialization of enhanced (v2) format."""
        json_str = json.dumps(
            {
                "version": 2,
                "companies": [
                    {
                        "name": "Google",
                        "confidence": 0.95,
                        "role": "primary_subject",
                        "disambiguation": "Tech company",
                    },
                ],
                "products": [],
                "people": [],
                "technologies": [],
                "locations": [],
            }
        )

        entities = ExtractedEntities.from_json_string(json_str)

        assert entities.companies[0].name == "Google"
        assert entities.companies[0].confidence == 0.95
        assert entities.companies[0].role == "primary_subject"
        assert entities.companies[0].disambiguation == "Tech company"

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
        """Test all_entities returns flat set of names."""
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

    def test_all_entities_with_metadata(self):
        """Test all_entities_with_metadata returns full objects."""
        entities = ExtractedEntities(
            companies=[EntityWithMetadata("Google", 0.95, ROLE_PRIMARY, None)],
            products=[EntityWithMetadata("Gemini", 0.9, ROLE_MENTIONED, None)],
            people=[],
            technologies=[],
            locations=[],
        )

        all_ents = entities.all_entities_with_metadata()

        assert len(all_ents) == 2
        assert all_ents[0].name == "Google"
        assert all_ents[0].confidence == 0.95

    def test_get_primary_entities(self):
        """Test filtering for primary entities."""
        entities = ExtractedEntities(
            companies=[
                EntityWithMetadata("Google", 0.95, ROLE_PRIMARY, None),
                EntityWithMetadata("Microsoft", 0.7, ROLE_MENTIONED, None),
            ],
            products=[],
            people=[],
            technologies=[],
            locations=[],
        )

        primary = entities.get_primary_entities()

        assert len(primary) == 1
        assert primary[0].name == "Google"

    def test_average_confidence(self):
        """Test average confidence calculation."""
        entities = ExtractedEntities(
            companies=[
                EntityWithMetadata("Google", 0.9, ROLE_PRIMARY, None),
                EntityWithMetadata("Microsoft", 0.8, ROLE_MENTIONED, None),
            ],
            products=[],
            people=[],
            technologies=[],
            locations=[],
        )

        avg = entities.average_confidence()

        assert abs(avg - 0.85) < 0.001  # Floating point tolerance


class TestEntityOverlap:
    """Test entity overlap calculation."""

    def test_full_overlap_simple(self):
        """Test 100% overlap with simple Jaccard."""
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

        overlap = get_entity_overlap(
            entities1, entities2, use_confidence_weighting=False
        )

        assert overlap == 1.0

    def test_full_overlap_weighted(self):
        """Test full overlap with confidence weighting."""
        entities1 = ExtractedEntities(
            companies=[EntityWithMetadata("Google", 0.95, ROLE_PRIMARY, None)],
            products=[EntityWithMetadata("Gemini", 0.9, ROLE_MENTIONED, None)],
            people=[],
            technologies=[],
            locations=[],
        )
        entities2 = ExtractedEntities(
            companies=[EntityWithMetadata("Google", 0.95, ROLE_PRIMARY, None)],
            products=[EntityWithMetadata("Gemini", 0.9, ROLE_MENTIONED, None)],
            people=[],
            technologies=[],
            locations=[],
        )

        overlap = get_entity_overlap(
            entities1, entities2, use_confidence_weighting=True
        )

        # Should be high due to full match with good confidence
        assert overlap > 0.9

    def test_partial_overlap_simple(self):
        """Test partial overlap with simple Jaccard."""
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

        overlap = get_entity_overlap(
            entities1, entities2, use_confidence_weighting=False
        )

        # Intersection: {Google}, Union: {Google, Microsoft, Apple}
        # Overlap = 1/3 = 0.333...
        assert 0.3 < overlap < 0.4

    def test_partial_overlap_weighted_primary_boost(self):
        """Test that primary_subject entities get boosted in overlap."""
        entities1 = ExtractedEntities(
            companies=[
                EntityWithMetadata("Google", 0.95, ROLE_PRIMARY, None),
                EntityWithMetadata("Microsoft", 0.7, ROLE_MENTIONED, None),
            ],
            products=[],
            people=[],
            technologies=[],
            locations=[],
        )
        entities2 = ExtractedEntities(
            companies=[
                EntityWithMetadata("Google", 0.9, ROLE_PRIMARY, None),
                EntityWithMetadata("Apple", 0.8, ROLE_MENTIONED, None),
            ],
            products=[],
            people=[],
            technologies=[],
            locations=[],
        )

        weighted = get_entity_overlap(
            entities1, entities2, use_confidence_weighting=True
        )
        simple = get_entity_overlap(
            entities1, entities2, use_confidence_weighting=False
        )

        # Weighted should be higher because the match is a primary subject
        assert weighted > simple

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
    def test_extract_entities_success_legacy_format(self, mock_get_llm):
        """Test successful entity extraction with legacy format response."""
        # Mock LLM service
        mock_service = MagicMock()
        mock_service.is_available.return_value = True
        mock_client = MagicMock()
        # Legacy format (simple string arrays)
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
            enhanced=False,  # Force legacy mode
        )

        # Check names via all_entities()
        all_ents = entities.all_entities()
        assert "Google" in all_ents
        assert "OpenAI" in all_ents
        assert "Gemini 2.0" in all_ents
        assert "AI" in all_ents
        assert "San Francisco" in all_ents

    @patch("app.entities.get_llm_service")
    def test_extract_entities_success_enhanced_format(self, mock_get_llm):
        """Test successful entity extraction with enhanced format response."""
        # Mock LLM service
        mock_service = MagicMock()
        mock_service.is_available.return_value = True
        mock_client = MagicMock()
        # Enhanced format (objects with metadata)
        mock_client.generate.return_value = {
            "response": json.dumps(
                {
                    "companies": [
                        {
                            "name": "Google",
                            "confidence": 0.95,
                            "role": "primary_subject",
                            "disambiguation": "Tech giant",
                        },
                        {
                            "name": "OpenAI",
                            "confidence": 0.85,
                            "role": "mentioned",
                            "disambiguation": "AI company",
                        },
                    ],
                    "products": [
                        {
                            "name": "Gemini 2.0",
                            "confidence": 0.9,
                            "role": "primary_subject",
                            "disambiguation": None,
                        },
                    ],
                    "people": [],
                    "technologies": [
                        {
                            "name": "AI",
                            "confidence": 0.8,
                            "role": "mentioned",
                            "disambiguation": None,
                        },
                    ],
                    "locations": [
                        {
                            "name": "San Francisco",
                            "confidence": 0.7,
                            "role": "mentioned",
                            "disambiguation": None,
                        },
                    ],
                }
            )
        }
        mock_service.client = mock_client
        mock_get_llm.return_value = mock_service

        entities = extract_entities(
            "Google Announces Gemini 2.0",
            "Google released Gemini 2.0 in San Francisco, competing with OpenAI.",
            enhanced=True,
        )

        # Check metadata preserved
        assert entities.companies[0].name == "Google"
        assert entities.companies[0].confidence == 0.95
        assert entities.companies[0].role == "primary_subject"

        # Check primary entities filter
        primary = entities.get_primary_entities()
        assert len(primary) == 2  # Google and Gemini 2.0

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

        entities = extract_entities("Test Title", "Test summary", enhanced=False)

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
            VALUES (1, 'Test Article', 'http://test.com/1', 'hash1', NOW())
            RETURNING id
            """
            )
        )
        session.commit()
        article_id = result.scalar()

        # Create and store entities (with metadata)
        entities = ExtractedEntities(
            companies=[
                EntityWithMetadata("Google", 0.95, ROLE_PRIMARY, "Tech company")
            ],
            products=[EntityWithMetadata("Gemini", 0.9, ROLE_MENTIONED, None)],
            people=[],
            technologies=[EntityWithMetadata("AI", 0.8, ROLE_MENTIONED, None)],
            locations=[],
        )

        success = store_entity_cache(article_id, entities, session, model="llama3.1:8b")
        assert success is True

        # Retrieve cached entities
        cached = get_cached_entities(article_id, session, model="llama3.1:8b")
        assert cached is not None
        # Check entity names
        assert cached.companies[0].name == "Google"
        assert cached.products[0].name == "Gemini"
        assert cached.technologies[0].name == "AI"
        # Check metadata preserved
        assert cached.companies[0].confidence == 0.95
        assert cached.companies[0].role == ROLE_PRIMARY
        assert cached.companies[0].disambiguation == "Tech company"

    def test_cache_miss_different_model(self, setup_test_db):
        """Test cache miss when model differs."""
        session = setup_test_db

        # Insert a test article
        result = session.execute(
            text(
                """
            INSERT INTO items (feed_id, title, url, url_hash, published)
            VALUES (1, 'Test Article', 'http://test.com/2', 'hash2', NOW())
            RETURNING id
            """
            )
        )
        session.commit()
        article_id = result.scalar()

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
            VALUES (1, 'Test Article', 'http://test.com/3', 'hash3', NOW())
            RETURNING id
            """
            )
        )
        session.commit()
        article_id = result.scalar()

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
            INSERT INTO feeds (id, url, name)
            VALUES (1, 'http://test.com/feed', 'Test Feed')
            ON CONFLICT (id) DO NOTHING
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

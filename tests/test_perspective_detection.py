"""Tests for perspective/viewpoint detection (#203, ADR-0023, v0.9.1).

Covers the PerspectiveOutput validation schema (app.llm_output), the
ArticlePerspective dataclass + its JSON round-trip (app.entities), the
extract_entities() integration point where perspective is parsed from the
same LLM call as entities, and the items.perspective_json cache round-trip.
"""

import json
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import text

from app.entities import ArticlePerspective, ExtractedEntities, extract_entities
from app.llm_output import EnhancedEntityOutput, PerspectiveOutput


class TestPerspectiveOutputValidation:
    """PerspectiveOutput (app.llm_output) validation behavior."""

    def test_defaults_to_not_applicable(self):
        output = PerspectiveOutput()
        assert output.applicable is False
        assert output.political_leaning is None
        assert output.stakeholder is None
        assert output.regional is None
        assert output.tone is None
        assert output.confidence == 0.6

    def test_valid_applicable_perspective(self):
        output = PerspectiveOutput.model_validate(
            {
                "applicable": True,
                "political_leaning": "Center-Left",
                "stakeholder": "consumer",
                "regional": "national",
                "tone": "analytical",
                "confidence": 0.85,
            }
        )
        assert output.applicable is True
        # Case-insensitive normalization
        assert output.political_leaning == "center-left"
        assert output.stakeholder == "consumer"
        assert output.regional == "national"
        assert output.tone == "analytical"
        assert output.confidence == 0.85

    def test_hallucinated_enum_value_degrades_to_none(self):
        """An out-of-enum value from the LLM must not raise -- it's dropped."""
        output = PerspectiveOutput.model_validate(
            {"applicable": True, "political_leaning": "moderate-ish"}
        )
        assert output.political_leaning is None
        # Other fields unaffected.
        assert output.applicable is True

    def test_not_applicable_clears_contradictory_fields(self):
        """If the LLM says not-applicable but still fills in a category,
        trust 'not applicable' and drop the (contradictory) category."""
        output = PerspectiveOutput.model_validate(
            {"applicable": False, "political_leaning": "left", "tone": "critical"}
        )
        assert output.applicable is False
        assert output.political_leaning is None
        assert output.tone is None

    def test_confidence_clamped_to_valid_range(self):
        output = PerspectiveOutput.model_validate({"confidence": 5.0})
        assert output.confidence == 1.0
        output2 = PerspectiveOutput.model_validate({"confidence": -1.0})
        assert output2.confidence == 0.0

    def test_confidence_falls_back_on_bad_input(self):
        output = PerspectiveOutput.model_validate({"confidence": "not-a-number"})
        assert output.confidence == 0.6

    def test_applicable_string_coercion(self):
        assert (
            PerspectiveOutput.model_validate({"applicable": "true"}).applicable is True
        )
        assert (
            PerspectiveOutput.model_validate({"applicable": "false"}).applicable
            is False
        )


class TestEnhancedEntityOutputPerspectiveField:
    """EnhancedEntityOutput.perspective -- the combined-response schema."""

    def test_missing_perspective_key_defaults_safely(self):
        """If the LLM response has no 'perspective' key at all (e.g. an older
        prompt/response), entity parsing must not fail."""
        output = EnhancedEntityOutput.model_validate({"companies": ["Cisco"]})
        assert output.perspective.applicable is False

    def test_perspective_key_parsed_alongside_entities(self):
        output = EnhancedEntityOutput.model_validate(
            {
                "companies": [{"name": "Acme Corp", "confidence": 0.9}],
                "perspective": {
                    "applicable": True,
                    "stakeholder": "business",
                    "tone": "critical",
                    "confidence": 0.7,
                },
            }
        )
        assert output.companies[0].name == "Acme Corp"
        assert output.perspective.applicable is True
        assert output.perspective.stakeholder == "business"

    def test_malformed_perspective_does_not_break_entity_parsing(self):
        """A perspective value that fails validation (e.g. a plain string
        instead of an object) must not prevent the rest of the model from
        validating via the existing extract_partial() fallback path."""
        from app.llm_output import extract_partial

        data = {
            "companies": [{"name": "Acme Corp", "confidence": 0.9}],
            "perspective": "not an object",
        }
        model, extracted, failed = extract_partial(data, EnhancedEntityOutput)
        assert model is not None
        assert model.companies[0].name == "Acme Corp"
        assert model.perspective.applicable is False
        assert "perspective" in failed


class TestArticlePerspectiveDataclass:
    """ArticlePerspective (app.entities) JSON round-trip."""

    def test_to_dict_and_from_dict_round_trip(self):
        perspective = ArticlePerspective(
            applicable=True,
            political_leaning="right",
            stakeholder=None,
            regional="international",
            tone="supportive",
            confidence=0.75,
        )
        restored = ArticlePerspective.from_dict(perspective.to_dict())
        assert restored == perspective

    def test_to_json_string_and_from_json_string_round_trip(self):
        perspective = ArticlePerspective(applicable=False)
        restored = ArticlePerspective.from_json_string(perspective.to_json_string())
        assert restored == perspective

    def test_from_output_maps_all_fields(self):
        output = PerspectiveOutput.model_validate(
            {
                "applicable": True,
                "political_leaning": "center",
                "stakeholder": "regulatory",
                "regional": "local",
                "tone": "neutral",
                "confidence": 0.55,
            }
        )
        perspective = ArticlePerspective.from_output(output)
        assert perspective.applicable is True
        assert perspective.political_leaning == "center"
        assert perspective.stakeholder == "regulatory"
        assert perspective.regional == "local"
        assert perspective.tone == "neutral"
        assert perspective.confidence == 0.55

    def test_from_dict_defaults_missing_confidence(self):
        restored = ArticlePerspective.from_dict({"applicable": True})
        assert restored.confidence == 0.6


class TestExtractEntitiesPerspectiveIntegration:
    """extract_entities() populates .perspective from the same LLM call."""

    @patch("app.entities.get_llm_service")
    def test_perspective_applicable_parsed_from_response(self, mock_get_llm):
        mock_service = MagicMock()
        mock_service.is_available.return_value = True
        mock_client = MagicMock()
        mock_client.generate.return_value = {
            "response": json.dumps(
                {
                    "companies": [],
                    "products": [],
                    "people": [],
                    "technologies": [],
                    "locations": [],
                    "perspective": {
                        "applicable": True,
                        "stakeholder": "business",
                        "regional": "local",
                        "tone": "critical",
                        "confidence": 0.7,
                    },
                }
            )
        }
        mock_service.backend = mock_client
        mock_get_llm.return_value = mock_service

        entities = extract_entities(
            "Small businesses warn of layoffs",
            "Small business owners are warning that the new minimum wage "
            "will force layoffs, calling the policy economically reckless.",
            enhanced=True,
        )

        assert entities.perspective is not None
        assert entities.perspective.applicable is True
        assert entities.perspective.stakeholder == "business"
        assert entities.perspective.tone == "critical"

    @patch("app.entities.get_llm_service")
    def test_perspective_not_applicable_for_neutral_content(self, mock_get_llm):
        mock_service = MagicMock()
        mock_service.is_available.return_value = True
        mock_client = MagicMock()
        mock_client.generate.return_value = {
            "response": json.dumps(
                {
                    "companies": [{"name": "IPFS", "confidence": 0.8}],
                    "products": [],
                    "people": [],
                    "technologies": [],
                    "locations": [],
                    "perspective": {"applicable": False},
                }
            )
        }
        mock_service.backend = mock_client
        mock_get_llm.return_value = mock_service

        entities = extract_entities(
            "Understanding IPFS",
            "A technical overview of IPFS internals.",
            enhanced=True,
        )

        assert entities.perspective is not None
        assert entities.perspective.applicable is False
        assert entities.perspective.political_leaning is None

    @patch("app.entities.get_llm_service")
    def test_missing_perspective_key_still_extracts_entities(self, mock_get_llm):
        """A response with no 'perspective' key at all (e.g. before this
        prompt change, or a model that ignores the instruction) must not
        break entity extraction."""
        mock_service = MagicMock()
        mock_service.is_available.return_value = True
        mock_client = MagicMock()
        mock_client.generate.return_value = {
            "response": json.dumps(
                {
                    "companies": [{"name": "Google", "confidence": 0.9}],
                    "products": [],
                    "people": [],
                    "technologies": [],
                    "locations": [],
                }
            )
        }
        mock_service.backend = mock_client
        mock_get_llm.return_value = mock_service

        entities = extract_entities("Google news", "Some article.", enhanced=True)

        assert entities.companies[0].name == "Google"
        assert entities.perspective is not None
        assert entities.perspective.applicable is False


class TestPerspectiveCacheRoundTrip:
    """items.perspective_json cache round-trip via store_entity_cache /
    get_cached_entities."""

    def test_perspective_persisted_and_retrieved(self, setup_test_db):
        from app.entities import get_cached_entities, store_entity_cache

        session = setup_test_db
        article_id = _insert_test_article(session, "http://test.com/perspective-1")

        entities = ExtractedEntities(
            companies=["Acme Corp"],
            products=[],
            people=[],
            technologies=[],
            locations=[],
            perspective=ArticlePerspective(
                applicable=True,
                stakeholder="business",
                tone="critical",
                confidence=0.7,
            ),
        )
        assert store_entity_cache(article_id, entities, session, model="llama3.1:8b")

        cached = get_cached_entities(article_id, session, model="llama3.1:8b")
        assert cached is not None
        assert cached.perspective is not None
        assert cached.perspective.applicable is True
        assert cached.perspective.stakeholder == "business"
        assert cached.perspective.tone == "critical"

    def test_no_perspective_stored_when_none(self, setup_test_db):
        """Backward compatibility: an ExtractedEntities with perspective=None
        (e.g. legacy-format extraction) must round-trip to perspective=None,
        not an error."""
        from app.entities import get_cached_entities, store_entity_cache

        session = setup_test_db
        article_id = _insert_test_article(session, "http://test.com/perspective-2")

        entities = ExtractedEntities(
            companies=["Acme Corp"],
            products=[],
            people=[],
            technologies=[],
            locations=[],
        )
        assert store_entity_cache(article_id, entities, session, model="llama3.1:8b")

        cached = get_cached_entities(article_id, session, model="llama3.1:8b")
        assert cached is not None
        assert cached.perspective is None

    def test_null_perspective_json_on_pre_existing_row(self, setup_test_db):
        """A row written before this migration (perspective_json IS NULL)
        must still cache-hit on entities with perspective=None."""
        session = setup_test_db
        article_id = _insert_test_article(session, "http://test.com/perspective-3")

        from app.entities import get_cached_entities

        session.execute(
            text(
                """
                UPDATE items
                SET entities_json = :entities_json,
                    entities_model = :model,
                    entities_extracted_at = NOW()
                WHERE id = :article_id
                """
            ),
            {
                "entities_json": ExtractedEntities(
                    companies=["Old Co"]
                ).to_json_string(),
                "model": "llama3.1:8b",
                "article_id": article_id,
            },
        )
        session.commit()

        cached = get_cached_entities(article_id, session, model="llama3.1:8b")
        assert cached is not None
        assert cached.companies[0].name == "Old Co"
        assert cached.perspective is None


def _insert_test_article(session, url: str) -> int:
    result = session.execute(
        text(
            """
            INSERT INTO items (feed_id, title, url, url_hash, published)
            VALUES (1, 'Test Article', :url, :url_hash, NOW())
            RETURNING id
            """
        ),
        {"url": url, "url_hash": url},
    )
    session.commit()
    return result.scalar()


@pytest.fixture
def setup_test_db():
    """Set up test database with items table (mirrors tests/test_entities.py)."""
    from app.db import SessionLocal, init_db

    init_db()
    session = SessionLocal()

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
    session.close()

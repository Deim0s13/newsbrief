"""Entity extraction from articles using LLM.

This module provides entity extraction functionality to identify key entities
(companies, products, people, technologies, locations) from article content.
These entities are used for improved story clustering and similarity scoring.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, Set

from sqlalchemy import text
from sqlalchemy.orm import Session

from .llm import get_llm_service

logger = logging.getLogger(__name__)


@dataclass
class ExtractedEntities:
    """Structured entity data extracted from article content."""

    companies: List[str]  # e.g., ["Google", "OpenAI", "Microsoft"]
    products: List[str]  # e.g., ["Gemini 2.0", "GPT-4", "ChatGPT"]
    people: List[str]  # e.g., ["Sundar Pichai", "Sam Altman"]
    technologies: List[str]  # e.g., ["AI", "Machine Learning", "Neural Networks"]
    locations: List[str]  # e.g., ["San Francisco", "Silicon Valley"]

    def to_json_string(self) -> str:
        """Serialize to JSON string for database storage."""
        return json.dumps(
            {
                "companies": self.companies,
                "products": self.products,
                "people": self.people,
                "technologies": self.technologies,
                "locations": self.locations,
            }
        )

    @classmethod
    def from_json_string(cls, json_str: str) -> ExtractedEntities:
        """Deserialize from JSON string."""
        data = json.loads(json_str)
        return cls(
            companies=data.get("companies", []),
            products=data.get("products", []),
            people=data.get("people", []),
            technologies=data.get("technologies", []),
            locations=data.get("locations", []),
        )

    def is_empty(self) -> bool:
        """Check if no entities were extracted."""
        return (
            len(self.companies) == 0
            and len(self.products) == 0
            and len(self.people) == 0
            and len(self.technologies) == 0
            and len(self.locations) == 0
        )

    def all_entities(self) -> Set[str]:
        """Get all entities as a flat set."""
        return set(
            self.companies
            + self.products
            + self.people
            + self.technologies
            + self.locations
        )


def _create_entity_extraction_prompt(title: str, summary: str) -> str:
    """Create LLM prompt for entity extraction."""
    # Combine title and summary, clean up
    content = f"{title}\n\n{summary}".strip()

    prompt = f"""You are an entity extraction AI. Extract key entities from this article.

ARTICLE:
{content}

INSTRUCTIONS:
Extract the following entity types that are CENTRAL to the article (not just mentioned in passing):
- Companies/Organizations: Business entities, tech companies, organizations
- Products/Services: Specific product names, services, platforms
- People: Named individuals (full names preferred)
- Technologies: Specific technologies, frameworks, programming languages
- Locations: Cities, countries, regions (if relevant to the story)

OUTPUT FORMAT (JSON only):
{{
  "companies": ["Company1", "Company2"],
  "products": ["Product1", "Product2"],
  "people": ["Person1", "Person2"],
  "technologies": ["Tech1", "Tech2"],
  "locations": ["Location1", "Location2"]
}}

IMPORTANT:
- Only include entities that are CLEARLY CENTRAL to the article
- Use proper capitalization (e.g., "OpenAI" not "openai")
- Include empty arrays [] for categories with no relevant entities
- Output ONLY valid JSON, no additional text
- Limit to 5 entities per category maximum

JSON Response:"""
    return prompt


def extract_entities(
    title: str,
    summary: str,
    model: str = "llama3.1:8b",
) -> ExtractedEntities:
    """
    Extract named entities from article using LLM.

    Args:
        title: Article title
        summary: Article summary/content
        model: LLM model to use for extraction

    Returns:
        ExtractedEntities object with categorized entities
    """
    # Validate inputs
    if not title and not summary:
        logger.warning("No title or summary provided for entity extraction")
        return ExtractedEntities(
            companies=[],
            products=[],
            people=[],
            technologies=[],
            locations=[],
        )

    # Get LLM service
    llm_service = get_llm_service()

    # Check if service is available
    if not llm_service.is_available():
        logger.warning("LLM service unavailable, returning empty entities")
        return ExtractedEntities(
            companies=[],
            products=[],
            people=[],
            technologies=[],
            locations=[],
        )

    try:
        # Create prompt
        prompt = _create_entity_extraction_prompt(title, summary or "")

        # Call LLM
        response = llm_service.client.generate(
            model=model,
            prompt=prompt,
            options={
                "temperature": 0.1,  # Low temperature for factual extraction
                "top_k": 40,
                "top_p": 0.8,
                "repeat_penalty": 1.1,
            },
        )

        raw_response = response.get("response", "").strip()

        if not raw_response:
            logger.warning("Empty response from LLM for entity extraction")
            return ExtractedEntities(
                companies=[],
                products=[],
                people=[],
                technologies=[],
                locations=[],
            )

        # Clean markdown formatting if present
        if raw_response.startswith("```json"):
            raw_response = (
                raw_response.replace("```json", "").replace("```", "").strip()
            )
        elif raw_response.startswith("```"):
            raw_response = raw_response.replace("```", "").strip()

        # Parse JSON
        data = json.loads(raw_response)

        # Extract and validate entity lists
        entities = ExtractedEntities(
            companies=data.get("companies", [])[:5],  # Limit to 5 per category
            products=data.get("products", [])[:5],
            people=data.get("people", [])[:5],
            technologies=data.get("technologies", [])[:5],
            locations=data.get("locations", [])[:5],
        )

        logger.info(
            f"Extracted {len(entities.all_entities())} entities from article: {title[:50]}..."
        )
        return entities

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON response for entity extraction: {e}")
        return ExtractedEntities(
            companies=[],
            products=[],
            people=[],
            technologies=[],
            locations=[],
        )
    except Exception as e:
        logger.error(f"Entity extraction failed: {e}")
        return ExtractedEntities(
            companies=[],
            products=[],
            people=[],
            technologies=[],
            locations=[],
        )


def get_cached_entities(
    article_id: int,
    session: Session,
    model: str = "llama3.1:8b",
) -> Optional[ExtractedEntities]:
    """
    Get cached entities for an article.

    Args:
        article_id: Article ID
        session: Database session
        model: Model used for extraction (for cache validation)

    Returns:
        ExtractedEntities if cached, None otherwise
    """
    try:
        row = session.execute(
            text(
                """
            SELECT entities_json, entities_extracted_at, entities_model
            FROM items
            WHERE id = :article_id
            AND entities_json IS NOT NULL
            """
            ),
            {"article_id": article_id},
        ).first()

        if row and row[0]:
            # Check if model matches (invalidate cache if model changed)
            cached_model = row[2]
            if cached_model != model:
                logger.debug(
                    f"Entity cache miss for article {article_id}: model mismatch"
                )
                return None

            # Parse and return cached entities
            entities = ExtractedEntities.from_json_string(row[0])
            logger.debug(f"Entity cache hit for article {article_id}")
            return entities

    except Exception as e:
        logger.warning(f"Failed to retrieve cached entities: {e}")

    return None


def store_entity_cache(
    article_id: int,
    entities: ExtractedEntities,
    session: Session,
    model: str = "llama3.1:8b",
) -> bool:
    """
    Store extracted entities in database cache.

    Args:
        article_id: Article ID
        entities: Extracted entities
        session: Database session
        model: Model used for extraction

    Returns:
        True if successful, False otherwise
    """
    try:
        session.execute(
            text(
                """
            UPDATE items
            SET entities_json = :entities_json,
                entities_extracted_at = :extracted_at,
                entities_model = :model
            WHERE id = :article_id
            """
            ),
            {
                "entities_json": entities.to_json_string(),
                "extracted_at": datetime.now().isoformat(),
                "model": model,
                "article_id": article_id,
            },
        )
        session.commit()
        logger.debug(f"Stored entity cache for article {article_id}")
        return True

    except Exception as e:
        logger.error(f"Failed to store entity cache: {e}")
        session.rollback()
        return False


def get_entity_overlap(
    entities1: ExtractedEntities,
    entities2: ExtractedEntities,
) -> float:
    """
    Calculate overlap score between two entity sets.

    Uses Jaccard similarity: |intersection| / |union|

    Args:
        entities1: First entity set
        entities2: Second entity set

    Returns:
        Overlap score (0.0 to 1.0)
    """
    # Get all entities as flat sets
    set1 = entities1.all_entities()
    set2 = entities2.all_entities()

    # Handle empty sets
    if len(set1) == 0 and len(set2) == 0:
        return 0.0

    # Calculate Jaccard similarity
    intersection = len(set1 & set2)
    union = len(set1 | set2)

    return intersection / union if union > 0 else 0.0


def extract_and_cache_entities(
    article_id: int,
    title: str,
    summary: str,
    session: Session,
    model: str = "llama3.1:8b",
    use_cache: bool = True,
) -> ExtractedEntities:
    """
    Extract entities with caching support (convenience function).

    Args:
        article_id: Article ID
        title: Article title
        summary: Article summary
        session: Database session
        model: LLM model to use
        use_cache: Whether to use cached entities

    Returns:
        ExtractedEntities object
    """
    # Check cache first
    if use_cache:
        cached = get_cached_entities(article_id, session, model)
        if cached:
            return cached

    # Extract entities
    entities = extract_entities(title, summary, model)

    # Store in cache
    store_entity_cache(article_id, entities, session, model)

    return entities

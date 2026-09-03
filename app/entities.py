"""Entity extraction from articles using LLM.

This module provides entity extraction functionality to identify key entities
(companies, products, people, technologies, locations) from article content.
These entities are used for improved story clustering and similarity scoring.

Enhanced in v0.8.1 (Issue #103) with:
- Confidence scores per entity
- Entity roles (primary_subject, mentioned, quoted)
- Disambiguation hints
- Few-shot examples for better accuracy

Extended in v0.9.1 (Issue #203, ADR-0023) with perspective/viewpoint
classification, piggybacked on the same LLM call (one JSON response) rather
than a separate round-trip -- see ArticlePerspective and extract_entities().
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Union

from sqlalchemy import text
from sqlalchemy.orm import Session

from .entity_normalization import normalize_and_store_entities
from .llm import get_llm_service
from .llm_output import (
    EnhancedEntityOutput,
    EntityOutput,
    PerspectiveOutput,
    parse_and_validate,
)
from .processing_states import ArticleProcessingState, apply_article_processing_state

logger = logging.getLogger(__name__)


# Entity role constants
ROLE_PRIMARY = "primary_subject"  # Central to the story
ROLE_MENTIONED = "mentioned"  # Referenced but not focus
ROLE_QUOTED = "quoted"  # Source of quotes/statements


@dataclass
class EntityWithMetadata:
    """
    Entity with rich metadata for improved accuracy and context.

    Added in v0.8.1 (Issue #103).
    """

    name: str
    confidence: float = 0.8  # 0.0-1.0, how certain the extraction is
    role: str = ROLE_MENTIONED  # primary_subject, mentioned, quoted
    disambiguation: Optional[str] = None  # e.g., "Apple Inc., tech company"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "name": self.name,
            "confidence": self.confidence,
            "role": self.role,
            "disambiguation": self.disambiguation,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EntityWithMetadata":
        """Create from dictionary."""
        return cls(
            name=data.get("name", ""),
            confidence=data.get("confidence", 0.8),
            role=data.get("role", ROLE_MENTIONED),
            disambiguation=data.get("disambiguation"),
        )

    @classmethod
    def from_string(cls, name: str) -> "EntityWithMetadata":
        """Create from simple string (backward compatibility)."""
        return cls(name=name, confidence=0.8, role=ROLE_MENTIONED)


@dataclass
class ArticlePerspective:
    """
    Perspective/viewpoint classification for an article (#203, ADR-0023,
    v0.9.1). Extracted in the same LLM call as entities (see
    extract_entities()) and cached in its own ``items.perspective_json``
    column, keyed by the same ``entities_model``/``entities_extracted_at``
    cache-validity tracking as entities (they're always produced together).

    Deliberately coarse (4 bounded categories) and optional --
    ``applicable=False`` is the expected/common case for purely factual or
    technical content (e.g. most dev-tool articles), not an error.
    """

    applicable: bool = False
    political_leaning: Optional[str] = None
    stakeholder: Optional[str] = None
    regional: Optional[str] = None
    tone: Optional[str] = None
    confidence: float = 0.6

    def to_dict(self) -> Dict[str, Any]:
        return {
            "applicable": self.applicable,
            "political_leaning": self.political_leaning,
            "stakeholder": self.stakeholder,
            "regional": self.regional,
            "tone": self.tone,
            "confidence": self.confidence,
        }

    def to_json_string(self) -> str:
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ArticlePerspective":
        return cls(
            applicable=bool(data.get("applicable", False)),
            political_leaning=data.get("political_leaning"),
            stakeholder=data.get("stakeholder"),
            regional=data.get("regional"),
            tone=data.get("tone"),
            confidence=float(data.get("confidence", 0.6) or 0.6),
        )

    @classmethod
    def from_json_string(cls, json_str: str) -> "ArticlePerspective":
        return cls.from_dict(json.loads(json_str))

    @classmethod
    def from_output(cls, output: "PerspectiveOutput") -> "ArticlePerspective":
        """Build from the validated LLM response schema."""
        return cls(
            applicable=output.applicable,
            political_leaning=output.political_leaning,
            stakeholder=output.stakeholder,
            regional=output.regional,
            tone=output.tone,
            confidence=output.confidence,
        )


@dataclass
class ExtractedEntities:
    """
    Structured entity data extracted from article content.

    Supports both legacy (list of strings) and enhanced (list of EntityWithMetadata)
    formats for backward compatibility.

    ``perspective`` (v0.9.1, #203) is populated from the same LLM call but
    persisted to a separate ``items.perspective_json`` column rather than
    folded into ``entities_json`` -- it's a different concern from entity
    extraction and this keeps entity_normalization.py/entity_backfill.py
    (which read entities_json) unaffected. It is intentionally NOT part of
    to_json_string()/from_json_string() below.
    """

    companies: List[Union[str, EntityWithMetadata]] = field(default_factory=list)
    products: List[Union[str, EntityWithMetadata]] = field(default_factory=list)
    people: List[Union[str, EntityWithMetadata]] = field(default_factory=list)
    technologies: List[Union[str, EntityWithMetadata]] = field(default_factory=list)
    locations: List[Union[str, EntityWithMetadata]] = field(default_factory=list)
    perspective: Optional[ArticlePerspective] = None

    def _normalize_entity(
        self, entity: Union[str, EntityWithMetadata, Dict]
    ) -> EntityWithMetadata:
        """Normalize entity to EntityWithMetadata."""
        if isinstance(entity, EntityWithMetadata):
            return entity
        if isinstance(entity, dict):
            return EntityWithMetadata.from_dict(entity)
        return EntityWithMetadata.from_string(str(entity))

    def _get_name(self, entity: Union[str, EntityWithMetadata, Dict]) -> str:
        """Extract name from entity (any format)."""
        if isinstance(entity, EntityWithMetadata):
            return entity.name
        if isinstance(entity, dict):
            return entity.get("name", "")
        return str(entity)

    def to_json_string(self) -> str:
        """Serialize to JSON string for database storage (enhanced format)."""
        return json.dumps(
            {
                "version": 2,  # Mark as enhanced format
                "companies": [
                    self._normalize_entity(e).to_dict() for e in self.companies
                ],
                "products": [
                    self._normalize_entity(e).to_dict() for e in self.products
                ],
                "people": [self._normalize_entity(e).to_dict() for e in self.people],
                "technologies": [
                    self._normalize_entity(e).to_dict() for e in self.technologies
                ],
                "locations": [
                    self._normalize_entity(e).to_dict() for e in self.locations
                ],
            }
        )

    @classmethod
    def from_json_string(cls, json_str: str) -> "ExtractedEntities":
        """Deserialize from JSON string (handles both legacy and enhanced)."""
        data = json.loads(json_str)

        # Check for enhanced format (v2)
        if data.get("version") == 2:
            return cls(
                companies=[
                    EntityWithMetadata.from_dict(e) for e in data.get("companies", [])
                ],
                products=[
                    EntityWithMetadata.from_dict(e) for e in data.get("products", [])
                ],
                people=[
                    EntityWithMetadata.from_dict(e) for e in data.get("people", [])
                ],
                technologies=[
                    EntityWithMetadata.from_dict(e)
                    for e in data.get("technologies", [])
                ],
                locations=[
                    EntityWithMetadata.from_dict(e) for e in data.get("locations", [])
                ],
            )

        # Legacy format (v1) - convert strings to EntityWithMetadata
        return cls(
            companies=[
                EntityWithMetadata.from_string(e) for e in data.get("companies", [])
            ],
            products=[
                EntityWithMetadata.from_string(e) for e in data.get("products", [])
            ],
            people=[EntityWithMetadata.from_string(e) for e in data.get("people", [])],
            technologies=[
                EntityWithMetadata.from_string(e) for e in data.get("technologies", [])
            ],
            locations=[
                EntityWithMetadata.from_string(e) for e in data.get("locations", [])
            ],
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
        """Get all entity names as a flat set."""
        all_items = (
            self.companies
            + self.products
            + self.people
            + self.technologies
            + self.locations
        )
        return {self._get_name(e) for e in all_items}

    def all_entities_with_metadata(self) -> List[EntityWithMetadata]:
        """Get all entities with their metadata."""
        all_items = (
            self.companies
            + self.products
            + self.people
            + self.technologies
            + self.locations
        )
        return [self._normalize_entity(e) for e in all_items]

    def get_primary_entities(self) -> List[EntityWithMetadata]:
        """Get only entities with primary_subject role."""
        return [e for e in self.all_entities_with_metadata() if e.role == ROLE_PRIMARY]

    def get_high_confidence_entities(
        self, threshold: float = 0.7
    ) -> List[EntityWithMetadata]:
        """Get entities above confidence threshold."""
        return [
            e for e in self.all_entities_with_metadata() if e.confidence >= threshold
        ]

    def average_confidence(self) -> float:
        """Calculate average confidence across all entities."""
        all_entities = self.all_entities_with_metadata()
        if not all_entities:
            return 0.0
        return sum(e.confidence for e in all_entities) / len(all_entities)


def _create_entity_extraction_prompt(
    title: str, summary: str, enhanced: bool = True
) -> str:
    """
    Create LLM prompt for entity extraction.

    Args:
        title: Article title
        summary: Article summary/content
        enhanced: If True, use enhanced format with metadata (v0.8.1)

    Returns:
        Prompt string for LLM
    """
    # Combine title and summary, clean up
    content = f"{title}\n\n{summary}".strip()

    if not enhanced:
        # Legacy simple format
        return f"""You are an entity extraction AI. Extract key entities from this article.

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

    # Enhanced format with metadata (v0.8.1)
    prompt = f"""You are an expert entity extraction system. Extract entities from this article with detailed metadata.

ARTICLE:
{content}

=== ENTITY CATEGORIES ===

1. COMPANIES: Organizations, corporations, agencies, institutions
   - Include: Tech companies, startups, government agencies, NGOs
   - Exclude: Generic terms like "the company" or "the startup"

2. PRODUCTS: Named products, services, platforms, applications
   - Include: Software products, hardware devices, services, APIs
   - Exclude: Generic categories like "smartphone" or "database"

3. PEOPLE: Named individuals mentioned or quoted
   - Include: Full names when available (e.g., "Sundar Pichai" not just "Pichai")
   - Include: Titles/roles when relevant for disambiguation

4. TECHNOLOGIES: Specific technologies, frameworks, languages, standards
   - Include: Programming languages, frameworks, protocols, AI models
   - Exclude: Vague terms like "machine learning" unless specifically discussed

5. LOCATIONS: Relevant geographic locations
   - Include: Cities, countries, regions central to the story
   - Exclude: Generic locations not meaningful to the article

=== PERSPECTIVE (only if genuinely applicable) ===

Most articles (tech/product news, dev tools, factual reporting) have NO
identifiable political or stakeholder viewpoint -- for these, set
"applicable": false and leave the category fields null. Only set
"applicable": true when the article clearly takes or reports a viewpoint
on a contested topic (politics, policy, business controversy, etc.).

When applicable, classify:
- political_leaning: "left" | "center-left" | "center" | "center-right" | "right"
- stakeholder: "business" | "consumer" | "regulatory" | "labor" | "environmental"
- regional: "local" | "national" | "international" (scope of the viewpoint)
- tone: "supportive" | "critical" | "neutral" | "analytical" (toward the subject)
- confidence: 0.0-1.0

Do not guess a category you're unsure of -- leave it null rather than forcing a label.

=== ENTITY METADATA ===

For each entity, provide:
- name: The canonical name (proper capitalization)
- confidence: 0.0-1.0 (how certain is this extraction?)
  - 0.9+: Explicitly named and central to article
  - 0.7-0.9: Clearly mentioned, moderate relevance
  - 0.5-0.7: Inferred or tangentially mentioned
- role: The entity's role in the article
  - "primary_subject": Central to the story
  - "mentioned": Referenced but not focus
  - "quoted": Source of a quote or statement
- disambiguation: Brief context to avoid confusion (optional)
  - e.g., "Apple Inc., technology company" vs "apple, fruit"
  - e.g., "Sam Altman, OpenAI CEO"

=== FEW-SHOT EXAMPLES ===

Example 1 - Tech announcement:
Article: "OpenAI announced GPT-5 today. CEO Sam Altman said the model represents a breakthrough in reasoning capabilities. Microsoft, a major investor, will integrate it into Azure."

Output:
{{
  "companies": [
    {{"name": "OpenAI", "confidence": 0.95, "role": "primary_subject", "disambiguation": "AI research company"}},
    {{"name": "Microsoft", "confidence": 0.85, "role": "mentioned", "disambiguation": "OpenAI investor"}}
  ],
  "products": [
    {{"name": "GPT-5", "confidence": 0.95, "role": "primary_subject", "disambiguation": "OpenAI language model"}},
    {{"name": "Azure", "confidence": 0.7, "role": "mentioned", "disambiguation": "Microsoft cloud platform"}}
  ],
  "people": [
    {{"name": "Sam Altman", "confidence": 0.9, "role": "quoted", "disambiguation": "OpenAI CEO"}}
  ],
  "technologies": [
    {{"name": "large language models", "confidence": 0.8, "role": "mentioned", "disambiguation": null}}
  ],
  "locations": [],
  "perspective": {{"applicable": false, "political_leaning": null, "stakeholder": null, "regional": null, "tone": null, "confidence": 0.6}}
}}

Example 2 - Acquisition story:
Article: "Cisco announced plans to acquire cybersecurity firm Splunk for $28B. The deal, expected to close in Q1, will strengthen Cisco's security portfolio. Analyst Jane Doe from Gartner called it 'transformative for the industry.'"

Output:
{{
  "companies": [
    {{"name": "Cisco", "confidence": 0.95, "role": "primary_subject", "disambiguation": "Acquiring company, networking giant"}},
    {{"name": "Splunk", "confidence": 0.95, "role": "primary_subject", "disambiguation": "Target company, cybersecurity/data platform"}},
    {{"name": "Gartner", "confidence": 0.7, "role": "mentioned", "disambiguation": "Research firm"}}
  ],
  "products": [],
  "people": [
    {{"name": "Jane Doe", "confidence": 0.85, "role": "quoted", "disambiguation": "Gartner analyst"}}
  ],
  "technologies": [
    {{"name": "cybersecurity", "confidence": 0.8, "role": "mentioned", "disambiguation": null}}
  ],
  "locations": [],
  "perspective": {{"applicable": false, "political_leaning": null, "stakeholder": null, "regional": null, "tone": null, "confidence": 0.6}}
}}

Example 3 - Single-lens policy story (perspective IS applicable):
Article: "Small business owners are warning that the city's new minimum wage increase will force layoffs and price hikes, calling the policy 'well-intentioned but economically reckless' for local retailers already struggling with rising costs."

Output:
{{
  "companies": [],
  "products": [],
  "people": [],
  "technologies": [],
  "locations": [],
  "perspective": {{"applicable": true, "political_leaning": null, "stakeholder": "business", "regional": "local", "tone": "critical", "confidence": 0.7}}
}}

Note: classify the perspective THIS article is written from/reports (its
dominant lens), not every viewpoint mentioned -- a balanced article citing
multiple sides is usually "applicable": false or "tone": "neutral"/"analytical"
rather than an artificial single stakeholder pick.

=== YOUR TASK ===

Now extract entities from the article above. Output ONLY valid JSON matching this structure:
{{
  "companies": [{{"name": "...", "confidence": 0.0-1.0, "role": "...", "disambiguation": "..."}}],
  "products": [...],
  "people": [...],
  "technologies": [...],
  "locations": [...],
  "perspective": {{"applicable": true|false, "political_leaning": "...", "stakeholder": "...", "regional": "...", "tone": "...", "confidence": 0.0-1.0}}
}}

Rules:
- Maximum 5 entities per category
- Include empty arrays [] for categories with no entities
- Use proper capitalization
- Be precise: prefer fewer high-confidence entities over many low-confidence ones
- Default to "applicable": false for perspective unless the article clearly has one
- Output ONLY the JSON, no additional text

JSON:"""
    return prompt


def extract_entities(
    title: str,
    summary: str,
    model: str = "llama3.1:8b",
    enhanced: bool = True,
) -> ExtractedEntities:
    """
    Extract named entities from article using LLM.

    Args:
        title: Article title
        summary: Article summary/content
        model: LLM model to use for extraction
        enhanced: Use enhanced format with metadata (v0.8.1, Issue #103)

    Returns:
        ExtractedEntities object with categorized entities and metadata
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

    # Ensure the model is actually pulled before generating (mirrors the
    # synthesis path in stories.py). Without this, a not-yet-pulled model
    # returns a 404 that looks identical to "no entities found" downstream,
    # silently poisoning the entity cache (see #328-adjacent clustering bug).
    if not llm_service.ensure_model(model):
        logger.warning(
            f"Model {model} not available for entity extraction, returning empty entities"
        )
        return ExtractedEntities(
            companies=[],
            products=[],
            people=[],
            technologies=[],
            locations=[],
        )

    try:
        # Create prompt (enhanced by default)
        prompt = _create_entity_extraction_prompt(
            title, summary or "", enhanced=enhanced
        )

        # Call LLM
        response = llm_service.backend.generate(
            model=model,
            prompt=prompt,
            options={
                "temperature": 0.1,  # Low temperature for factual extraction
                "top_k": 40,
                "top_p": 0.8,
                "repeat_penalty": 1.1,
            },
        )

        raw_response = (response.get("response") or "").strip()

        if not raw_response:
            logger.warning("Empty response from LLM for entity extraction")
            return ExtractedEntities(
                companies=[],
                products=[],
                people=[],
                technologies=[],
                locations=[],
            )

        # Try enhanced parsing first if using enhanced mode
        entities: Optional[ExtractedEntities] = None

        if enhanced:
            # Try parsing as enhanced format
            parsed_enhanced, enhanced_metrics = parse_and_validate(
                raw_response,
                EnhancedEntityOutput,
                required_fields=[],
                allow_partial=True,
                circuit_breaker_name="entity_extraction_enhanced",
            )

            if parsed_enhanced is not None:
                # Convert EnhancedEntityOutput to ExtractedEntities with metadata
                entities = ExtractedEntities(
                    companies=[
                        EntityWithMetadata(
                            name=e.name,
                            confidence=e.confidence,
                            role=e.role,
                            disambiguation=e.disambiguation,
                        )
                        for e in parsed_enhanced.companies
                    ],
                    products=[
                        EntityWithMetadata(
                            name=e.name,
                            confidence=e.confidence,
                            role=e.role,
                            disambiguation=e.disambiguation,
                        )
                        for e in parsed_enhanced.products
                    ],
                    people=[
                        EntityWithMetadata(
                            name=e.name,
                            confidence=e.confidence,
                            role=e.role,
                            disambiguation=e.disambiguation,
                        )
                        for e in parsed_enhanced.people
                    ],
                    technologies=[
                        EntityWithMetadata(
                            name=e.name,
                            confidence=e.confidence,
                            role=e.role,
                            disambiguation=e.disambiguation,
                        )
                        for e in parsed_enhanced.technologies
                    ],
                    locations=[
                        EntityWithMetadata(
                            name=e.name,
                            confidence=e.confidence,
                            role=e.role,
                            disambiguation=e.disambiguation,
                        )
                        for e in parsed_enhanced.locations
                    ],
                    perspective=ArticlePerspective.from_output(
                        parsed_enhanced.perspective
                    ),
                )
                logger.info(
                    f"Enhanced entity extraction: {len(entities.all_entities())} entities "
                    f"(avg confidence: {entities.average_confidence():.2f}); "
                    f"perspective applicable={entities.perspective.applicable if entities.perspective else False}"
                )

        # Fall back to legacy parsing if enhanced failed or not enabled
        if entities is None:
            parsed_output, parse_metrics = parse_and_validate(
                raw_response,
                EntityOutput,
                required_fields=[],
                allow_partial=True,
                circuit_breaker_name="entity_extraction",
            )

            if parsed_output is None:
                logger.warning(
                    f"Failed to parse entity extraction response: {parse_metrics.error_category}"
                )
                return ExtractedEntities(
                    companies=[],
                    products=[],
                    people=[],
                    technologies=[],
                    locations=[],
                )

            # Convert legacy format to EntityWithMetadata
            entities = ExtractedEntities(
                companies=[
                    EntityWithMetadata.from_string(c) for c in parsed_output.companies
                ],
                products=[
                    EntityWithMetadata.from_string(p) for p in parsed_output.products
                ],
                people=[
                    EntityWithMetadata.from_string(p) for p in parsed_output.people
                ],
                technologies=[
                    EntityWithMetadata.from_string(t)
                    for t in parsed_output.technologies
                ],
                locations=[
                    EntityWithMetadata.from_string(l) for l in parsed_output.locations
                ],
            )
            logger.info(
                f"Extracted {len(entities.all_entities())} entities from article: "
                f"{title[:50]}... (legacy format)"
            )

        return entities

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
            SELECT entities_json, entities_extracted_at, entities_model, perspective_json
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
            perspective_json = row[3]
            if perspective_json:
                try:
                    entities.perspective = ArticlePerspective.from_json_string(
                        perspective_json
                    )
                except Exception:
                    logger.debug(
                        f"Failed to parse cached perspective for article {article_id}"
                    )
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
                entities_model = :model,
                perspective_json = :perspective_json
            WHERE id = :article_id
            """
            ),
            {
                "entities_json": entities.to_json_string(),
                "extracted_at": datetime.now().isoformat(),
                "model": model,
                "perspective_json": (
                    entities.perspective.to_json_string()
                    if entities.perspective
                    else None
                ),
                "article_id": article_id,
            },
        )
        apply_article_processing_state(
            session,
            article_id,
            ArticleProcessingState.ENRICHED,
            context="store_entity_cache",
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
    use_confidence_weighting: bool = True,
) -> float:
    """
    Calculate overlap score between two entity sets.

    Enhanced in v0.8.1 (Issue #103) with confidence weighting:
    - High-confidence matches count more than low-confidence ones
    - Primary subjects get extra weight

    Args:
        entities1: First entity set
        entities2: Second entity set
        use_confidence_weighting: If True, weight matches by confidence (v0.8.1)

    Returns:
        Overlap score (0.0 to 1.0)
    """
    # Get all entities as flat sets (names only for intersection)
    set1 = entities1.all_entities()
    set2 = entities2.all_entities()

    # Handle empty sets
    if len(set1) == 0 and len(set2) == 0:
        return 0.0

    # Simple Jaccard if weighting disabled
    if not use_confidence_weighting:
        intersection = len(set1 & set2)
        union = len(set1 | set2)
        return intersection / union if union > 0 else 0.0

    # Confidence-weighted calculation
    # Build lookup maps: name -> EntityWithMetadata
    def _build_entity_map(entities: ExtractedEntities) -> Dict[str, EntityWithMetadata]:
        entity_map: Dict[str, EntityWithMetadata] = {}
        for e in entities.all_entities_with_metadata():
            name_lower = e.name.lower()
            # Keep the higher confidence version if duplicate
            if (
                name_lower not in entity_map
                or e.confidence > entity_map[name_lower].confidence
            ):
                entity_map[name_lower] = e
        return entity_map

    map1 = _build_entity_map(entities1)
    map2 = _build_entity_map(entities2)

    # Find matching entities
    common_names = set(map1.keys()) & set(map2.keys())

    if not common_names:
        return 0.0

    # Calculate weighted score
    # For each match: score = avg_confidence * role_multiplier
    total_weighted_score = 0.0
    max_possible_score = 0.0

    for name in common_names:
        e1 = map1[name]
        e2 = map2[name]

        # Average confidence of the match
        avg_conf = (e1.confidence + e2.confidence) / 2

        # Role multiplier: primary subjects count more
        role_mult = 1.0
        if e1.role == ROLE_PRIMARY or e2.role == ROLE_PRIMARY:
            role_mult = 1.5
        elif e1.role == ROLE_QUOTED or e2.role == ROLE_QUOTED:
            role_mult = 1.2

        total_weighted_score += avg_conf * role_mult
        max_possible_score += 1.0 * role_mult  # Max if confidence were 1.0

    # Calculate total possible (union with weighting)
    all_names = set(map1.keys()) | set(map2.keys())
    total_possible = len(all_names)

    if total_possible == 0:
        return 0.0

    # Blend: weighted match quality + coverage
    match_quality = (
        total_weighted_score / max_possible_score if max_possible_score > 0 else 0.0
    )
    coverage = len(common_names) / total_possible

    # Combined score: 70% match quality, 30% coverage
    return 0.7 * match_quality + 0.3 * coverage


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
            _normalize_entities_safe(session, article_id, cached)
            return cached

    # Extract entities
    entities = extract_entities(title, summary, model)

    # Store in cache
    store_entity_cache(article_id, entities, session, model)

    _normalize_entities_safe(session, article_id, entities)

    return entities


def _normalize_entities_safe(
    session: Session, article_id: int, entities: ExtractedEntities
) -> None:
    """
    Best-effort normalization into the relational entity graph (#199,
    ADR-0023). Fire-and-forget, matching the "embeddings optional" pattern
    elsewhere in the pipeline: a normalization failure must never break
    extraction/clustering, which is why entities_json/get_cached_entities
    above remain the source of truth for clustering similarity.
    """
    try:
        normalize_and_store_entities(session, article_id, entities)
        session.commit()
    except Exception as e:
        logger.warning(
            "Entity normalization failed for article %s (non-fatal): %s",
            article_id,
            e,
        )
        session.rollback()

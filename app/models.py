from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, Union

from pydantic import BaseModel, Field, HttpUrl, validator


class FeedIn(BaseModel):
    url: HttpUrl
    name: Optional[str] = Field(None, description="Custom name for the feed")
    description: Optional[str] = Field(None, description="Description of the feed")
    category: Optional[str] = Field(None, description="Feed category/tag")
    priority: int = Field(
        1, description="Feed priority (1-5, higher = more important)", ge=1, le=5
    )
    disabled: bool = Field(False, description="Whether the feed is disabled")


class FeedOut(BaseModel):
    id: int
    url: str
    name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    priority: int = 1
    disabled: bool = False
    robots_allowed: bool = True
    etag: Optional[str] = None
    last_modified: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    # Statistics
    total_articles: int = Field(0, description="Total articles from this feed")
    last_fetch_at: Optional[datetime] = Field(
        None, description="Last fetch attempt timestamp"
    )
    last_error: Optional[str] = Field(None, description="Last error message if any")
    fetch_count: int = Field(0, description="Total number of fetch attempts")
    success_count: int = Field(0, description="Total number of successful fetches")
    # Enhanced health monitoring
    last_success_at: Optional[datetime] = Field(
        None, description="Last successful fetch timestamp"
    )
    consecutive_failures: int = Field(0, description="Number of consecutive failures")
    avg_response_time_ms: Optional[float] = Field(
        None, description="Average response time in milliseconds"
    )
    last_response_time_ms: Optional[float] = Field(
        None, description="Last response time in milliseconds"
    )
    health_score: float = Field(100.0, description="Overall health score (0-100)")
    last_modified_check: Optional[datetime] = Field(
        None, description="Last time we checked Last-Modified"
    )
    etag_check: Optional[datetime] = Field(
        None, description="Last time we checked ETag"
    )


class FeedUpdate(BaseModel):
    name: Optional[str] = Field(None, description="Custom name for the feed")
    description: Optional[str] = Field(None, description="Description of the feed")
    category: Optional[str] = Field(None, description="Feed category/tag")
    priority: Optional[int] = Field(None, description="Feed priority (1-5)", ge=1, le=5)
    disabled: Optional[bool] = Field(None, description="Whether the feed is disabled")


class FeedStats(BaseModel):
    """Detailed statistics for a specific feed."""

    feed_id: int
    total_articles: int
    articles_last_24h: int
    articles_last_7d: int
    articles_last_30d: int
    avg_articles_per_day: float
    last_fetch_at: Optional[datetime]
    last_error: Optional[str]
    success_rate: float  # percentage
    avg_response_time_ms: float


@dataclass
class TextChunk:
    """Represents a chunk of text for processing."""

    content: str
    start_pos: int
    end_pos: int
    token_count: int
    chunk_index: int


@dataclass
class ChunkSummary:
    """Summary of a single text chunk."""

    chunk_index: int
    bullets: List[str]
    key_topics: List[str]
    summary_text: str
    token_count: int


class StructuredSummary(BaseModel):
    """Structured AI-generated summary with bullets, significance, and tags."""

    bullets: List[str] = Field(..., description="Key points as bullet list (3-5 items)")
    why_it_matters: str = Field(..., description="Why this story is significant")
    tags: List[str] = Field(..., description="Relevant topic tags (3-6 items)")
    content_hash: str = Field(..., description="Hash of source content for caching")
    model: str = Field(..., description="LLM model used for generation")
    generated_at: datetime = Field(..., description="When this summary was generated")

    # Chunking metadata (new in v0.3.2)
    is_chunked: bool = Field(
        False, description="Whether this summary was created from chunked content"
    )
    chunk_count: Optional[int] = Field(
        None, description="Number of chunks processed (if chunked)"
    )
    total_tokens: Optional[int] = Field(
        None, description="Total token count of original content"
    )
    processing_method: str = Field(
        "direct", description="Processing method: 'direct' or 'map-reduce'"
    )

    @validator("bullets")
    def validate_bullets(cls, v):
        if not isinstance(v, list) or len(v) < 1 or len(v) > 8:
            raise ValueError("bullets must be a list with 1-8 items")
        return [str(bullet).strip() for bullet in v if bullet.strip()]

    @validator("tags")
    def validate_tags(cls, v):
        if not isinstance(v, list) or len(v) < 1 or len(v) > 10:
            raise ValueError("tags must be a list with 1-10 items")
        return [str(tag).strip().lower() for tag in v if tag.strip()]

    @validator("why_it_matters")
    def validate_why_it_matters(cls, v):
        if not v or len(v.strip()) < 10:
            raise ValueError("why_it_matters must be at least 10 characters")
        return v.strip()

    def to_json_string(self) -> str:
        """Convert to JSON string for database storage."""
        return json.dumps(
            self.dict(exclude={"content_hash", "model", "generated_at"}),
            ensure_ascii=False,
        )

    @classmethod
    def from_json_string(
        cls, json_str: str, content_hash: str, model: str, generated_at: datetime
    ) -> "StructuredSummary":
        """Create from JSON string with metadata."""
        data = json.loads(json_str)
        return cls(
            bullets=data["bullets"],
            why_it_matters=data["why_it_matters"],
            tags=data["tags"],
            content_hash=content_hash,
            model=model,
            generated_at=generated_at,
            # Handle chunking metadata (backward compatible)
            is_chunked=data.get("is_chunked", False),
            chunk_count=data.get("chunk_count"),
            total_tokens=data.get("total_tokens"),
            processing_method=data.get("processing_method", "direct"),
        )


class ItemOut(BaseModel):
    id: int
    title: Optional[str] = None
    url: str
    published: Optional[datetime] = None
    summary: Optional[str] = None
    feed_id: Optional[int] = Field(
        None, description="ID of the feed this article belongs to"
    )
    # Legacy plain text AI summary (for backward compatibility)
    ai_summary: Optional[str] = None
    ai_model: Optional[str] = None
    ai_generated_at: Optional[datetime] = None
    # New structured AI summary
    structured_summary: Optional[StructuredSummary] = None
    # Fallback summary (v0.3.3) - extracted sentences when AI unavailable
    fallback_summary: Optional[str] = Field(
        None, description="First 2 sentences when AI summary unavailable"
    )
    is_fallback_summary: bool = Field(
        False, description="Whether the primary summary is a fallback"
    )
    # Ranking and topic fields (v0.4.0)
    ranking_score: float = Field(
        0.0, description="Calculated relevance score for ranking"
    )
    topic: Optional[str] = Field(None, description="Classified article topic")
    topic_confidence: float = Field(
        0.0, description="Confidence level of topic classification (0.0-1.0)"
    )
    source_weight: float = Field(
        1.0, description="Importance weight of the source feed"
    )


class SummaryRequest(BaseModel):
    """Request to generate summary for specific item(s)."""

    item_ids: List[int] = Field(..., description="List of item IDs to summarize")
    model: Optional[str] = Field(None, description="Optional LLM model override")
    force_regenerate: bool = Field(
        False, description="Force regenerate even if summary exists"
    )
    use_structured: bool = Field(
        True, description="Generate structured JSON summaries (default: True)"
    )


class SummaryResponse(BaseModel):
    """Response from summary generation."""

    success: bool
    summaries_generated: int
    errors: int
    results: List["SummaryResultOut"]


class SummaryResultOut(BaseModel):
    """Individual summary result."""

    item_id: int
    success: bool
    # Legacy fields (for backward compatibility)
    summary: Optional[str] = None
    model: Optional[str] = None
    error: Optional[str] = None
    tokens_used: Optional[int] = None
    generation_time: Optional[float] = None
    # New structured summary
    structured_summary: Optional[StructuredSummary] = None
    content_hash: Optional[str] = None
    cache_hit: bool = Field(False, description="Whether this result came from cache")


class LLMStatusOut(BaseModel):
    """LLM service status information."""

    available: bool
    base_url: str
    current_model: str
    models_available: List[str] = []
    error: Optional[str] = None


# Utility functions for content hashing
def extract_first_sentences(content: str, sentence_count: int = 2) -> str:
    """
    Extract the first N sentences from content as a fallback summary.

    Args:
        content: The article content to extract sentences from
        sentence_count: Number of sentences to extract (default: 2)

    Returns:
        String containing the first N sentences, or the full content if shorter
    """
    if not content or not content.strip():
        return ""

    # Clean the content - remove excessive whitespace
    cleaned_content = re.sub(r"\s+", " ", content.strip())

    # Split into sentences using a simpler, more reliable pattern
    # This handles periods, exclamation marks, question marks
    # Use a simple approach that works reliably
    sentence_pattern = r"[.!?]+\s+"
    sentences = re.split(sentence_pattern, cleaned_content)

    # Filter out empty sentences and take the first N
    sentences = [s.strip() for s in sentences if s.strip()]

    if not sentences:
        # If no sentences found, return first 200 characters as fallback
        return (
            cleaned_content[:200] + "..."
            if len(cleaned_content) > 200
            else cleaned_content
        )

    # Take first N sentences
    selected_sentences = sentences[:sentence_count]
    result = " ".join(selected_sentences)

    # Ensure the result ends with proper punctuation
    if result and result[-1] not in ".!?":
        result += "..."

    return result


def create_content_hash(title: str, content: str) -> str:
    """Create a hash of article title + content for caching purposes."""
    combined = f"{title}|{content}".encode("utf-8")
    return hashlib.sha256(combined).hexdigest()[:16]  # First 16 chars for readability


def create_cache_key(content_hash: str, model: str) -> str:
    """Create cache key combining content hash and model name."""
    return f"{content_hash}:{model}"


def parse_cache_key(cache_key: str) -> tuple[str, str]:
    """Parse cache key back to content_hash and model."""
    try:
        content_hash, model = cache_key.split(":", 1)
        return content_hash, model
    except ValueError:
        raise ValueError(f"Invalid cache key format: {cache_key}")


# Quality breakdown model (v0.8.1 - Issue #233)
class QualityBreakdownOut(BaseModel):
    """Quality score breakdown with component scores."""

    completeness: float = Field(
        0.0,
        description="Presence of required fields (key points, synthesis, why_it_matters)",
    )
    coverage: float = Field(
        0.0, description="Synthesis depth relative to source article count"
    )
    entity_consistency: float = Field(
        0.0, description="Percentage of entities mentioned in synthesis text"
    )
    parse_success: float = Field(
        0.0, description="Parsing quality (direct parse vs repairs/fallbacks)"
    )
    title_quality: float = Field(
        0.0, description="Title source (LLM vs fallback) and length quality"
    )
    overall: float = Field(0.0, description="Weighted composite quality score")

    class Config:
        """Pydantic config."""

        from_attributes = True


# Clustering factors model (v0.8.1 - Issue #232)
class ClusteringFactorsOut(BaseModel):
    """Weights used in clustering similarity calculation."""

    entity_weight: float = Field(0.5, description="Weight for entity overlap")
    keyword_weight: float = Field(0.3, description="Weight for keyword overlap")
    topic_weight: float = Field(0.2, description="Weight for topic bonus")


# Clustering metadata model (v0.8.1 - Issue #232)
class ClusteringMetadataOut(BaseModel):
    """Metadata explaining why articles were grouped together."""

    shared_entities: List[str] = Field(
        default_factory=list, description="Entities appearing in multiple articles"
    )
    shared_keywords: List[str] = Field(
        default_factory=list, description="Keywords appearing in multiple articles"
    )
    avg_similarity: float = Field(
        0.0, description="Average pairwise similarity between articles"
    )
    topic_consensus: Optional[str] = Field(
        None, description="Most common topic in the cluster"
    )
    topic_confidence_avg: float = Field(
        0.0, description="Average topic classification confidence"
    )
    article_count: int = Field(0, description="Number of articles in cluster")
    clustering_factors: Optional[ClusteringFactorsOut] = Field(
        None, description="Weights used in similarity calculation"
    )

    class Config:
        """Pydantic config."""

        from_attributes = True


# Story models for aggregated news
class StoryOut(BaseModel):
    """A synthesized news story aggregating multiple articles."""

    id: int
    title: str
    synthesis: str
    key_points: List[str] = Field(default_factory=list)
    why_it_matters: Optional[str] = None
    topics: List[str] = Field(default_factory=list)
    entities: List[str] = Field(default_factory=list)
    article_count: int
    importance_score: float = 0.0
    freshness_score: float = 0.0
    generated_at: datetime
    first_seen: Optional[datetime] = None
    last_updated: Optional[datetime] = None
    supporting_articles: List[ItemOut] = Field(default_factory=list)
    primary_article_id: Optional[int] = None
    model: Optional[str] = None  # LLM model used for synthesis
    status: str = "active"  # Story status: active or archived
    # Quality metrics (v0.8.1 - Issue #105)
    quality_score: Optional[float] = None
    title_source: Optional[str] = None  # "llm" or "fallback"
    parse_strategy: Optional[str] = None  # "direct", "markdown_block", etc.
    # Quality breakdown (v0.8.1 - Issue #233)
    quality_breakdown: Optional["QualityBreakdownOut"] = None
    # Clustering metadata (v0.8.1 - Issue #232)
    clustering_metadata: Optional["ClusteringMetadataOut"] = None

    @validator("title")
    def validate_title(cls, v):
        if not v or len(v.strip()) < 10:
            raise ValueError("title must be at least 10 characters")
        if len(v) > 200:
            raise ValueError("title must not exceed 200 characters")
        return v.strip()

    @validator("synthesis")
    def validate_synthesis(cls, v):
        if not v or len(v.strip()) < 50:
            raise ValueError("synthesis must be at least 50 characters")
        if len(v) > 5000:
            raise ValueError("synthesis must not exceed 5000 characters")
        return v.strip()

    @validator("key_points")
    def validate_key_points(cls, v):
        # Pad if too few key points (LLM sometimes returns < 3)
        import logging

        logger = logging.getLogger(__name__)

        original_len = len(v)
        if len(v) < 3:
            logger.info(f"[VALIDATOR] Padding key_points from {len(v)} to 3")
            v = list(v)  # Make a copy
            while len(v) < 3:
                if len(v) == 1:
                    v.append("Additional details in supporting articles")
                elif len(v) == 2:
                    v.append("See full article details below")

        if len(v) > 8:
            logger.warning(f"[VALIDATOR] Truncating key_points from {len(v)} to 8")
            v = v[:8]  # Truncate instead of raising error

        result = [point.strip() for point in v if point.strip()]
        if original_len != len(result):
            logger.info(
                f"[VALIDATOR] Final key_points count: {len(result)} (was {original_len})"
            )
        return result

    @validator("importance_score", "freshness_score")
    def validate_score(cls, v):
        if not 0.0 <= v <= 1.0:
            raise ValueError("score must be between 0.0 and 1.0")
        return v

    @validator("article_count")
    def validate_article_count(cls, v):
        if v < 1:
            raise ValueError("story must have at least 1 article")
        return v


class StoryDetailOut(BaseModel):
    """Detailed story view with full article list."""

    story: StoryOut
    articles: List[ItemOut]


class StoriesListOut(BaseModel):
    """List of stories for the landing page."""

    stories: List[StoryOut]
    total: int
    limit: int
    offset: int


class StoryGenerationRequest(BaseModel):
    """Request to generate/refresh stories."""

    time_window_hours: int = Field(
        24, description="Look back window in hours", ge=1, le=168
    )
    min_articles_per_story: int = Field(
        1, description="Minimum articles to form a story", ge=1
    )
    similarity_threshold: float = Field(
        0.25,
        description="Similarity threshold (0.0-1.0) - lowered for v0.6.1 entity-based clustering",
        ge=0.0,
        le=1.0,
    )
    model: str = Field("llama3.1:8b", description="LLM model to use for synthesis")


class StoryGenerationResponse(BaseModel):
    """Response from story generation (v0.6.1 enhanced)."""

    success: bool
    stories_generated: int
    story_ids: List[int]
    time_window_hours: int
    model: str
    # v0.6.1: Enhanced feedback for 0-stories UX
    articles_found: int = 0
    clusters_created: int = 0
    duplicates_skipped: int = 0
    message: Optional[str] = None


# Story JSON field serialization helpers
def serialize_story_json_field(items: List[str]) -> str:
    """
    Serialize list of strings to JSON for database storage.

    Used for: key_points_json, topics_json, entities_json

    Args:
        items: List of strings (topics, entities, key_points)

    Returns:
        JSON string for database storage

    Example:
        >>> serialize_story_json_field(["AI/ML", "Cloud"])
        '["AI/ML", "Cloud"]'
    """
    return json.dumps(items, ensure_ascii=False)


def deserialize_story_json_field(json_str: Optional[str]) -> List[str]:
    """
    Deserialize JSON string from database to list of strings.

    Used for: key_points_json, topics_json, entities_json

    Args:
        json_str: JSON string from database (or None)

    Returns:
        List of strings (empty list if json_str is None or invalid)

    Example:
        >>> deserialize_story_json_field('["AI/ML", "Cloud"]')
        ['AI/ML', 'Cloud']
        >>> deserialize_story_json_field(None)
        []
    """
    if not json_str:
        return []
    try:
        result = json.loads(json_str)
        return result if isinstance(result, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


# Update forward references
SummaryResponse.model_rebuild()

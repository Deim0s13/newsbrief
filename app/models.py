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
    priority: int = Field(1, description="Feed priority (1-5, higher = more important)", ge=1, le=5)
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
    created_at: datetime
    updated_at: datetime
    # Statistics
    total_articles: int = Field(0, description="Total articles from this feed")
    last_fetch_at: Optional[datetime] = Field(None, description="Last fetch attempt timestamp")
    last_error: Optional[str] = Field(None, description="Last error message if any")
    fetch_count: int = Field(0, description="Total number of fetch attempts")
    success_count: int = Field(0, description="Total number of successful fetches")
    # Enhanced health monitoring
    last_success_at: Optional[datetime] = Field(None, description="Last successful fetch timestamp")
    consecutive_failures: int = Field(0, description="Number of consecutive failures")
    avg_response_time_ms: float = Field(0.0, description="Average response time in milliseconds")
    last_response_time_ms: float = Field(0.0, description="Last response time in milliseconds")
    health_score: float = Field(100.0, description="Overall health score (0-100)")
    last_modified_check: Optional[datetime] = Field(None, description="Last time we checked Last-Modified")
    etag_check: Optional[datetime] = Field(None, description="Last time we checked ETag")


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


# Update forward references
SummaryResponse.model_rebuild()

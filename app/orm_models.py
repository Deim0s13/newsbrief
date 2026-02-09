"""
SQLAlchemy ORM models for NewsBrief database.

This module defines all database tables as SQLAlchemy ORM models,
providing portable schema definitions that work with both SQLite and PostgreSQL.

Tables:
- Feed: RSS/Atom feed sources
- Item: Individual articles from feeds
- Story: Synthesized stories aggregating multiple articles
- StoryArticle: Junction table linking stories to articles
- SynthesisCache: LLM synthesis cache for performance
- LLMMetrics: Quality metrics tracking for LLM operations (v0.8.1)

See ADR 0007 for the database migration strategy.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    """Base class for all ORM models."""

    pass


class Feed(Base):
    """RSS/Atom feed source."""

    __tablename__ = "feeds"

    id = Column(Integer, primary_key=True)
    url = Column(Text, unique=True, nullable=False)
    name = Column(Text)
    etag = Column(Text)
    last_modified = Column(Text)
    robots_allowed = Column(Integer, default=1)
    disabled = Column(Integer, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
    updated_at = Column(DateTime, default=lambda: datetime.now(UTC))
    last_fetch_at = Column(DateTime)
    last_success_at = Column(DateTime)
    fetch_count = Column(Integer, default=0)
    success_count = Column(Integer, default=0)
    consecutive_failures = Column(Integer, default=0)
    last_response_time_ms = Column(Integer)
    avg_response_time_ms = Column(Integer)
    last_error = Column(Text)
    health_score = Column(Float, default=100.0)
    # Optional metadata
    description = Column(Text)
    category = Column(Text)
    priority = Column(Integer, default=1)
    last_modified_check = Column(DateTime)
    etag_check = Column(DateTime)

    # Relationships
    items = relationship("Item", back_populates="feed", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_feeds_health_score", "health_score", postgresql_using="btree"),
    )


class Item(Base):
    """Individual article from a feed."""

    __tablename__ = "items"

    id = Column(Integer, primary_key=True)
    feed_id = Column(Integer, ForeignKey("feeds.id"), nullable=False)
    title = Column(Text)
    url = Column(Text, nullable=False)
    url_hash = Column(Text, unique=True, nullable=False)
    published = Column(DateTime)
    author = Column(Text)
    summary = Column(Text)
    content = Column(Text)
    content_hash = Column(Text)
    # AI summary fields
    ai_summary = Column(Text)
    ai_model = Column(Text)
    ai_generated_at = Column(DateTime)
    structured_summary_json = Column(Text)
    structured_summary_model = Column(Text)
    structured_summary_content_hash = Column(Text)
    structured_summary_generated_at = Column(DateTime)
    # Ranking and topic fields (v0.4.0)
    ranking_score = Column(Float, default=0.0)
    topic = Column(Text)
    topic_confidence = Column(Float, default=0.0)
    source_weight = Column(Float, default=1.0)
    # Entity extraction (v0.6.1)
    entities_json = Column(Text)
    entities_extracted_at = Column(DateTime)
    entities_model = Column(Text)
    # Content extraction metadata (v0.8.0 - ADR-0024)
    extraction_method = Column(String(20), default="legacy")
    extraction_quality = Column(Float)
    extraction_error = Column(Text)
    extracted_at = Column(DateTime)
    extraction_time_ms = Column(Integer)
    # Timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))

    # Relationships
    feed = relationship("Feed", back_populates="items")
    story_links = relationship(
        "StoryArticle", back_populates="article", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_items_published", "published"),
        Index("idx_items_content_hash", "content_hash"),
        Index("idx_items_ranking_score", "ranking_score"),
        Index("idx_items_topic", "topic"),
        Index("idx_items_ranking_composite", "topic", "ranking_score", "published"),
        Index(
            "idx_structured_summary_cache",
            "structured_summary_content_hash",
            "structured_summary_model",
        ),
        # Extraction metadata indexes (v0.8.0)
        Index("idx_items_extraction_method", "extraction_method"),
        Index(
            "idx_items_extraction_quality", "extraction_method", "extraction_quality"
        ),
    )


class Story(Base):
    """Synthesized news story aggregating multiple articles."""

    __tablename__ = "stories"

    id = Column(Integer, primary_key=True)
    title = Column(String(200), nullable=False)
    synthesis = Column(Text, nullable=False)
    key_points_json = Column(Text)
    why_it_matters = Column(Text)
    topics_json = Column(Text)
    entities_json = Column(Text)
    article_count = Column(Integer, default=0)
    importance_score = Column(Float, default=0.0)
    freshness_score = Column(Float, default=0.0)
    quality_score = Column(Float, default=0.5)
    # Quality metrics breakdown (v0.8.1 - Issue #105)
    quality_breakdown_json = Column(Text)  # JSON breakdown of score components
    title_source = Column(String(20))  # 'llm' or 'fallback'
    parse_strategy = Column(String(30))  # JSON parsing strategy used
    cluster_method = Column(String(50))
    story_hash = Column(String(64), unique=True)
    generated_at = Column(DateTime, default=lambda: datetime.now(UTC))
    first_seen = Column(DateTime)
    last_updated = Column(DateTime)
    time_window_start = Column(DateTime)
    time_window_end = Column(DateTime)
    model = Column(String(50))
    status = Column(String(20), default="active")
    # Versioning (v0.6.3 - ADR 0004)
    version = Column(Integer, default=1)
    previous_version_id = Column(Integer, ForeignKey("stories.id"))

    # Relationships
    story_articles = relationship(
        "StoryArticle", back_populates="story", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_stories_generated_at", "generated_at"),
        Index("idx_stories_importance", "importance_score"),
        Index("idx_stories_status", "status"),
        Index("idx_stories_previous_version", "previous_version_id"),
    )


class StoryArticle(Base):
    """Junction table linking stories to articles."""

    __tablename__ = "story_articles"

    id = Column(Integer, primary_key=True)
    story_id = Column(
        Integer, ForeignKey("stories.id", ondelete="CASCADE"), nullable=False
    )
    article_id = Column(
        Integer, ForeignKey("items.id", ondelete="CASCADE"), nullable=False
    )
    relevance_score = Column(Float, default=1.0)
    is_primary = Column(Boolean, default=False)
    added_at = Column(DateTime, default=lambda: datetime.now(UTC))

    # Relationships
    story = relationship("Story", back_populates="story_articles")
    article = relationship("Item", back_populates="story_links")

    __table_args__ = (
        UniqueConstraint("story_id", "article_id", name="uq_story_article"),
        Index("idx_story_articles_story", "story_id"),
        Index("idx_story_articles_article", "article_id"),
    )


class ImportHistory(Base):
    """
    History of OPML feed imports.

    Tracks import attempts with statistics and links to any failed feeds.
    Retained for 30 days for user reference.
    """

    __tablename__ = "import_history"

    id = Column(Integer, primary_key=True)
    imported_at = Column(DateTime, default=lambda: datetime.now(UTC), nullable=False)
    filename = Column(Text)
    feeds_added = Column(Integer, default=0)
    feeds_updated = Column(Integer, default=0)
    feeds_skipped = Column(Integer, default=0)
    feeds_failed = Column(Integer, default=0)
    validation_enabled = Column(Boolean, default=True)

    # Status tracking for async imports (v0.5.4)
    status = Column(String(20), default="completed")  # processing, completed, failed
    total_feeds = Column(Integer, default=0)
    processed_feeds = Column(Integer, default=0)
    completed_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)

    # Relationships
    failed_feeds = relationship(
        "FailedImport", back_populates="import_history", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_import_history_date", "imported_at"),
        Index("idx_import_history_status", "status"),
    )


class FailedImport(Base):
    """
    Failed feed imports from OPML.

    Stores details about feeds that failed validation during import,
    allowing users to review and retry.
    """

    __tablename__ = "failed_imports"

    id = Column(Integer, primary_key=True)
    import_id = Column(
        Integer, ForeignKey("import_history.id", ondelete="CASCADE"), nullable=False
    )
    feed_url = Column(Text, nullable=False)
    feed_name = Column(Text)
    error_message = Column(Text)
    status = Column(String(20), default="pending")  # pending, resolved, dismissed
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
    resolved_at = Column(DateTime)

    # Relationships
    import_history = relationship("ImportHistory", back_populates="failed_feeds")

    __table_args__ = (
        Index("idx_failed_imports_import_id", "import_id"),
        Index("idx_failed_imports_status", "status"),
    )


class SynthesisCache(Base):
    """
    Cache for LLM synthesis results.

    Stores synthesis output keyed by a deterministic hash of
    sorted article IDs + model name for cache hits.

    See ADR 0003 for caching strategy.
    """

    __tablename__ = "synthesis_cache"

    id = Column(Integer, primary_key=True)
    cache_key = Column(String(64), unique=True, nullable=False)
    article_ids_json = Column(Text, nullable=False)
    model = Column(String(50), nullable=False)
    # Synthesis results
    synthesis = Column(Text, nullable=False)
    key_points_json = Column(Text)
    why_it_matters = Column(Text)
    topics_json = Column(Text)
    entities_json = Column(Text)
    # Metrics
    token_count_input = Column(Integer)
    token_count_output = Column(Integer)
    generation_time_ms = Column(Integer)
    # Timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
    expires_at = Column(DateTime)
    invalidated_at = Column(DateTime)

    __table_args__ = (
        Index("idx_synthesis_cache_key", "cache_key"),
        Index("idx_synthesis_cache_expires", "expires_at"),
    )


class LLMMetrics(Base):
    """
    Quality metrics tracking for LLM operations.

    Stores per-operation metrics for synthesis, entity extraction,
    and topic classification to enable quality monitoring and trend analysis.

    Added in v0.8.1 - Issue #105: Add output quality metrics and tracking.
    """

    __tablename__ = "llm_metrics"

    id = Column(Integer, primary_key=True)
    operation_type = Column(
        String(50), nullable=False
    )  # synthesis, entity_extraction, topic_classification
    model = Column(String(50))

    # Timing
    created_at = Column(DateTime, default=lambda: datetime.now(UTC), nullable=False)
    generation_time_ms = Column(Integer)

    # Parse metrics
    parse_success = Column(Boolean, default=True)
    parse_strategy = Column(String(30))  # direct, markdown_block, brace_match, etc.
    repairs_applied = Column(Text)  # JSON array of repair types
    retry_count = Column(Integer, default=0)

    # Quality scores
    quality_score = Column(Float)  # Overall quality score 0.0-1.0
    quality_breakdown = Column(Text)  # JSON breakdown of components

    # Token usage
    token_count_input = Column(Integer)
    token_count_output = Column(Integer)

    # Context
    story_id = Column(
        Integer, ForeignKey("stories.id", ondelete="SET NULL"), nullable=True
    )
    article_id = Column(
        Integer, ForeignKey("items.id", ondelete="SET NULL"), nullable=True
    )
    article_count = Column(Integer)

    # Error tracking
    error_category = Column(String(50))
    error_message = Column(Text)

    __table_args__ = (
        Index("idx_llm_metrics_created_at", "created_at"),
        Index("idx_llm_metrics_operation", "operation_type"),
        Index("idx_llm_metrics_quality", "quality_score"),
        Index("idx_llm_metrics_success", "parse_success"),
    )

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

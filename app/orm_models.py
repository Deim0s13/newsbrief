"""
SQLAlchemy ORM models for NewsBrief database.

This module defines all database tables as SQLAlchemy ORM models,
providing schema definitions for PostgreSQL (ADR-0022), including pgvector-backed
embedding columns.

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

from pgvector.sqlalchemy import Vector
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
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, relationship

# Keep in sync with alembic/versions/017_embedding_vector_768.py (#251).
_EMBEDDING_DIMENSIONS = 768


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
    # Pipeline processing state (ADR-0030 / #273); separate from feed/item lifecycle
    processing_state = Column(
        String(32),
        nullable=False,
        default="fetched",
        server_default="fetched",
    )
    # Per-entity pipeline failure detail (#293, ADR-0030); distinct from extraction_error
    processing_error = Column(Text, nullable=True)
    processing_failed_at = Column(DateTime(timezone=True), nullable=True)
    failure_stage = Column(String(64), nullable=True)
    last_failed_run_group_id = Column(String(36), nullable=True)
    # Semantic embeddings (pgvector; #250, ADR-0026)
    embedding = Column(Vector(_EMBEDDING_DIMENSIONS), nullable=True)
    embedding_model = Column(String(100), nullable=True)
    embedding_version = Column(String(50), nullable=True)
    embedded_at = Column(DateTime(timezone=True), nullable=True)
    # Last embedding failure message, if any (#278); cleared on next success.
    embedding_error = Column(Text, nullable=True)
    # Post-hoc semantic duplicate flagging (#257, ADR-0026); distinct from the
    # exact-match url_hash/content_hash dedup applied at ingest (app/feeds.py).
    duplicate_of_id = Column(Integer, ForeignKey("items.id"), nullable=True)
    duplicate_similarity = Column(Float, nullable=True)
    duplicate_detection_method = Column(String(20), nullable=True)
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
        Index("idx_items_duplicate_of_id", "duplicate_of_id"),
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
    # Confidence score: source reliability × breadth × recency × synthesis quality (#220)
    confidence_score = Column(Float, nullable=True)
    # Synthesis routing path: 'standard' or 'deep' (#282)
    synthesis_path = Column(String(20), nullable=True)
    # Numeric cluster complexity score (0.0-1.0), advisory-only (#280,
    # ADR-0026); does not affect synthesis_path routing above.
    complexity_score = Column(Float, nullable=True)
    # Quality metrics breakdown (v0.8.1 - Issue #105)
    quality_breakdown_json = Column(Text)  # JSON breakdown of score components
    title_source = Column(String(20))  # 'llm' or 'fallback'
    parse_strategy = Column(String(30))  # JSON parsing strategy used
    # Clustering metadata (v0.8.1 - Issue #232)
    clustering_metadata_json = Column(
        Text
    )  # JSON: shared entities, keywords, similarity
    cluster_method = Column(String(50))
    story_hash = Column(String(64), unique=True)
    generated_at = Column(DateTime, default=lambda: datetime.now(UTC))
    first_seen = Column(DateTime)
    last_updated = Column(DateTime)
    time_window_start = Column(DateTime)
    time_window_end = Column(DateTime)
    model = Column(Text)
    status = Column(String(20), default="active")
    # Pipeline processing state (ADR-0030 / #273); separate from status (active/archived)
    processing_state = Column(
        String(32),
        nullable=False,
        default="candidate",
        server_default="candidate",
    )
    processing_error = Column(Text, nullable=True)
    processing_failed_at = Column(DateTime(timezone=True), nullable=True)
    failure_stage = Column(String(64), nullable=True)
    last_failed_run_group_id = Column(String(36), nullable=True)
    # Semantic embeddings (pgvector; #250, ADR-0026)
    embedding = Column(Vector(_EMBEDDING_DIMENSIONS), nullable=True)
    embedding_model = Column(String(100), nullable=True)
    embedding_version = Column(String(50), nullable=True)
    embedded_at = Column(DateTime(timezone=True), nullable=True)
    # Source credibility (v0.8.2 - Issue #198)
    source_credibility_score = Column(Float)  # Weighted average 0.0-1.0
    low_credibility_warning = Column(Boolean, default=False)  # All sources < 0.5
    sources_excluded = Column(Integer, default=0)  # Ineligible sources filtered
    # Confidence gate warning: score below warn threshold but above hold threshold (#287)
    confidence_warning = Column(Boolean, default=False)
    # Versioning (v0.6.3 - ADR 0004)
    version = Column(Integer, default=1)
    previous_version_id = Column(Integer, ForeignKey("stories.id"))
    # Historical story linking (#258, ADR-0026): semantically related stories from
    # the past N days, computed via pgvector cosine similarity after embedding.
    historical_links_json = Column(Text, nullable=True)
    continues_story_id = Column(Integer, ForeignKey("stories.id"), nullable=True)
    continues_similarity = Column(Float, nullable=True)
    # Light RAG: historical anchors injected into the synthesis prompt for
    # continuity, if any (#259, ADR-0026); distinct from historical_links_json
    # above, which is computed post-synthesis.
    synthesis_anchors_json = Column(Text, nullable=True)
    # Structured, UI-facing context anchors (#279, #281, ADR-0026): merges the
    # pre-synthesis retrieval hook (#279) with historical_links_json (#258)
    # into a single list of {story_id, title, similarity, published_at,
    # kind: "current"|"background", rationale} entries.
    context_anchors_json = Column(Text, nullable=True)

    # Relationships
    story_articles = relationship(
        "StoryArticle", back_populates="story", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_stories_generated_at", "generated_at"),
        Index("idx_stories_importance", "importance_score"),
        Index("idx_stories_status", "status"),
        Index("idx_stories_previous_version", "previous_version_id"),
        Index("idx_stories_credibility", "source_credibility_score"),
        Index("idx_stories_low_cred_warning", "low_credibility_warning"),
        Index("idx_stories_continues_story_id", "continues_story_id"),
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
    model = Column(Text, nullable=False)
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
    model = Column(Text)

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


class SourceCredibility(Base):
    """
    Source credibility ratings from external providers.

    Stores factual accuracy and bias metadata for news sources.
    Credibility score is based ONLY on factual_reporting, not political bias.

    Added in v0.8.2 - Issue #196: Create source_credibility database schema
    See ADR-0028: Source Credibility Architecture
    """

    __tablename__ = "source_credibility"

    id = Column(Integer, primary_key=True)

    # Core identification
    domain = Column(String(255), unique=True, nullable=False)
    name = Column(String(255))
    homepage_url = Column(Text)

    # Source classification (NOT a score penalty - ADR-0028)
    source_type = Column(String(20), nullable=False, default="news")
    # Values: news, satire, conspiracy, fake_news, pro_science, state_media, advocacy

    # Factual reporting - the ONLY input to credibility_score
    factual_reporting = Column(String(20))
    # Values: very_high, high, mostly_factual, mixed, low, very_low

    # Political bias - metadata only, NOT used in scoring (ADR-0028)
    bias = Column(String(20))
    # Values: left, left_center, center, right_center, right

    # Computed credibility score (0.0-1.0, based on factual_reporting only)
    credibility_score = Column(Float)

    # Synthesis eligibility (satire/fake excluded by default)
    is_eligible_for_synthesis = Column(Boolean, default=True, nullable=False)

    # Provenance & versioning (ADR-0028)
    provider = Column(String(50), nullable=False, default="mbfc_community")
    provider_url = Column(Text)
    dataset_version = Column(String(100))
    raw_payload = Column(Text)  # JSON

    # Timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(UTC), nullable=False)
    last_updated = Column(DateTime, default=lambda: datetime.now(UTC), nullable=False)

    __table_args__ = (
        Index("idx_source_credibility_domain", "domain"),
        Index("idx_source_credibility_type", "source_type"),
        Index("idx_source_credibility_score", "credibility_score"),
        Index("idx_source_credibility_provider", "provider"),
        Index("idx_source_credibility_eligible", "is_eligible_for_synthesis"),
    )


class PipelineStageRun(Base):
    """
    One row per pipeline stage execution (ADR-0029 / #274).

    ``run_group_id`` ties stages from a single operator or scheduled invocation.
    """

    __tablename__ = "pipeline_stage_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_group_id = Column(String(36), nullable=False)
    stage = Column(String(64), nullable=False)
    trigger = Column(String(32), nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=False)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    success = Column(Boolean, nullable=True)
    error_message = Column(Text, nullable=True)
    stats_json = Column(Text, nullable=True)
    target_type = Column(String(32), nullable=True)
    target_id = Column(Integer, nullable=True)
    attempts = Column(Integer, nullable=False, default=1)
    discarded_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("idx_pipeline_stage_runs_run_group", "run_group_id"),
        Index("idx_pipeline_stage_runs_stage_started", "stage", "started_at"),
        Index(
            "idx_pipeline_stage_runs_dead_letter",
            "finished_at",
            "success",
            "discarded_at",
        ),
    )


class OperatorAction(Base):
    """
    Audit row for admin pipeline / operator mutations (#277).

    Optional ``operator_label`` comes from ``X-Operator-Label`` (or ``X-Operator-Id``).
    """

    __tablename__ = "operator_actions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    action_type = Column(String(64), nullable=False)
    details_json = Column(Text, nullable=True)
    operator_label = Column(String(256), nullable=True)
    client_ip = Column(String(64), nullable=True)

    __table_args__ = (Index("idx_operator_actions_created", "created_at"),)


class RetrievalTrace(Base):
    """
    Audit row for semantic retrieval queries (#256, ADR-0026).

    Logged for every completed similarity search (similar articles, related
    stories, semantic search) to support debugging, evaluation, and quality
    monitoring of the retrieval subsystem.
    """

    __tablename__ = "retrieval_traces"

    id = Column(Integer, primary_key=True, autoincrement=True)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    query_type = Column(String(50), nullable=False)
    source_id = Column(Integer, nullable=True)
    source_type = Column(String(20), nullable=True)
    retrieved_ids_json = Column(Text, nullable=False, default="[]")
    similarity_scores_json = Column(Text, nullable=False, default="[]")
    filters_applied_json = Column(Text, nullable=True)
    duration_ms = Column(Integer, nullable=True)

    __table_args__ = (
        Index("idx_retrieval_traces_type", "query_type"),
        Index("idx_retrieval_traces_created", "created_at"),
    )


class Entity(Base):
    """
    Canonical, deduplicated entity (#199, ADR-0023, v0.9.0).

    Populated by ``app/entity_normalization.py`` from the existing per-article
    LLM extraction (``app/entities.py``) -- either at cluster time (go-forward)
    or via the one-time ``python -m app.cli entity-backfill`` script. Not a
    replacement for ``items.entities_json`` / ``stories.entities_json``, which
    remain the fast path for clustering similarity.

    ``entity_type`` is one of the extraction categories: company, product,
    person, technology, location.
    """

    __tablename__ = "entities"

    id = Column(Integer, primary_key=True, autoincrement=True)
    canonical_name = Column(String(255), nullable=False)
    entity_type = Column(String(50), nullable=False)
    aliases = Column(JSONB, nullable=False, default=list, server_default="[]")
    description = Column(Text, nullable=True)
    # Mapped to the DB column "metadata" under a non-reserved Python attribute
    # name -- "metadata" is reserved on declarative models (Base.metadata).
    entity_metadata = Column(
        "metadata", JSONB, nullable=False, default=dict, server_default="{}"
    )
    first_seen = Column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    last_seen = Column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    mention_count = Column(Integer, nullable=False, default=0)
    # Nullable and unpopulated for now -- the extraction prompt doesn't
    # produce per-entity sentiment yet (separate scope, not silently dropped).
    avg_sentiment = Column(Float, nullable=True)
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    mentions = relationship(
        "EntityMention", back_populates="entity", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_entities_type", "entity_type"),
        Index("idx_entities_mention_count", "mention_count"),
    )


class EntityMention(Base):
    """
    One occurrence of an ``Entity`` in an article, optionally linked to the
    story it was clustered into (#199, ADR-0023, v0.9.0).

    ``story_id`` is set once the article is clustered into a story
    (``app/stories.py`` links it in right after the ``StoryArticle`` rows are
    created); it stays ``NULL`` for mentions from articles not yet in a story.

    ``prominence_score`` blends the extraction's per-entity confidence with a
    role multiplier (primary_subject > quoted > mentioned) into a single
    weighting signal for entity-based story connections (#202); there is no
    separate ``role`` column in this schema.
    """

    __tablename__ = "entity_mentions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    entity_id = Column(
        Integer, ForeignKey("entities.id", ondelete="CASCADE"), nullable=False
    )
    article_id = Column(
        Integer, ForeignKey("items.id", ondelete="CASCADE"), nullable=False
    )
    story_id = Column(
        Integer, ForeignKey("stories.id", ondelete="SET NULL"), nullable=True
    )
    mention_context = Column(Text, nullable=True)
    sentiment_score = Column(Float, nullable=True)
    prominence_score = Column(Float, nullable=True)
    mentioned_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    entity = relationship("Entity", back_populates="mentions")

    __table_args__ = (
        UniqueConstraint(
            "entity_id", "article_id", name="uq_entity_mentions_entity_article"
        ),
        Index("idx_entity_mentions_entity_id", "entity_id"),
        Index("idx_entity_mentions_article_id", "article_id"),
        Index("idx_entity_mentions_story_id", "story_id"),
    )


class ReclassifyJob(Base):
    """Track async topic reclassification jobs (v0.8.1 - Issue #248)."""

    __tablename__ = "reclassify_jobs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    status = Column(String(20), nullable=False, default="pending")
    total_articles = Column(Integer, nullable=False, default=0)
    processed_articles = Column(Integer, nullable=False, default=0)
    changed_articles = Column(Integer, nullable=False, default=0)
    error_count = Column(Integer, nullable=False, default=0)
    batch_size = Column(Integer, nullable=False, default=100)
    use_llm = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    error_message = Column(Text)

    __table_args__ = (
        Index("idx_reclassify_jobs_status", "status"),
        Index("idx_reclassify_jobs_created", "created_at"),
    )

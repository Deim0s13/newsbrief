"""
Story CRUD operations using SQLAlchemy ORM.

Provides database operations for story-based aggregation:
- Create stories
- Link articles to stories
- Query stories with filters
- Update/archive/delete stories
- Generate stories from articles
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime, timedelta
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    desc,
    text,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session, relationship

from .entities import (
    ExtractedEntities,
    extract_and_cache_entities,
    get_entity_overlap,
)
from .llm import get_llm_service
from .models import (
    ItemOut,
    StoryOut,
    deserialize_story_json_field,
    serialize_story_json_field,
)

logger = logging.getLogger(__name__)

# Configuration
STORY_ARCHIVE_DAYS = int(
    os.getenv("STORY_ARCHIVE_DAYS", "7")
)  # Auto-archive after 7 days
STORY_DELETE_DAYS = int(
    os.getenv("STORY_DELETE_DAYS", "30")
)  # Hard delete after 30 days

# ORM Base
Base = declarative_base()  # type: ignore


# ORM Models


class Story(Base):  # type: ignore[misc,valid-type]
    """ORM model for stories table."""

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
    cluster_method = Column(String)
    story_hash = Column(String, unique=True)
    generated_at = Column(DateTime, default=lambda: datetime.now(UTC))
    first_seen = Column(DateTime)
    last_updated = Column(DateTime)
    time_window_start = Column(DateTime)
    time_window_end = Column(DateTime)
    model = Column(String)
    status = Column(String, default="active")

    # Relationship to articles via junction table
    story_articles = relationship(
        "StoryArticle", back_populates="story", cascade="all, delete-orphan"
    )


class StoryArticle(Base):  # type: ignore[misc,valid-type]
    """ORM model for story_articles junction table."""

    __tablename__ = "story_articles"

    id = Column(Integer, primary_key=True)
    story_id = Column(
        Integer, ForeignKey("stories.id", ondelete="CASCADE"), nullable=False
    )
    article_id = Column(
        Integer, nullable=False
    )  # FK to items table (not ORM yet, so no ForeignKey constraint)
    relevance_score = Column(Float, default=1.0)
    is_primary = Column(Boolean, default=False)
    added_at = Column(DateTime, default=lambda: datetime.now(UTC))

    # Relationships
    story = relationship("Story", back_populates="story_articles")
    # Note: items table is not ORM yet, so we don't define relationship to it


# CRUD Operations


def create_story(
    session: Session,
    title: str,
    synthesis: str,
    key_points: List[str],
    why_it_matters: str,
    topics: List[str],
    entities: List[str],
    importance_score: float,
    freshness_score: float,
    model: str,
    time_window_start: datetime,
    time_window_end: datetime,
    cluster_method: str = "naive",
    story_hash: Optional[str] = None,
    first_seen: Optional[datetime] = None,
) -> int:
    """
    Create a new story.

    Args:
        session: SQLAlchemy session
        title: Story title
        synthesis: AI-generated synthesis paragraph
        key_points: List of key bullet points
        why_it_matters: Significance analysis
        topics: List of topic tags
        entities: List of entities (companies, products, people)
        importance_score: Story importance (0.0-1.0)
        freshness_score: Time-based relevance (0.0-1.0)
        model: LLM model used for synthesis
        time_window_start: Start of article time window
        time_window_end: End of article time window
        cluster_method: Clustering algorithm used
        story_hash: Unique hash for deduplication
        first_seen: When story was first generated

    Returns:
        Story ID
    """
    story = Story(
        title=title,
        synthesis=synthesis,
        key_points_json=serialize_story_json_field(key_points),
        why_it_matters=why_it_matters,
        topics_json=serialize_story_json_field(topics),
        entities_json=serialize_story_json_field(entities),
        article_count=0,  # Will be updated when articles are linked
        importance_score=importance_score,
        freshness_score=freshness_score,
        cluster_method=cluster_method,
        story_hash=story_hash,
        generated_at=datetime.now(UTC),
        first_seen=first_seen or datetime.now(UTC),
        last_updated=datetime.now(UTC),
        time_window_start=time_window_start,
        time_window_end=time_window_end,
        model=model,
        status="active",
    )

    session.add(story)
    session.commit()
    session.refresh(story)

    logger.info(f"Created story #{story.id}: {title[:50]}...")
    return story.id  # type: ignore[return-value]


def link_articles_to_story(
    session: Session,
    story_id: int,
    article_ids: List[int],
    primary_article_id: Optional[int] = None,
) -> None:
    """
    Link articles to a story via junction table.

    Args:
        session: SQLAlchemy session
        story_id: Story ID
        article_ids: List of article IDs to link
        primary_article_id: Optional primary article ID (most relevant)
    """
    # Create links
    for article_id in article_ids:
        story_article = StoryArticle(
            story_id=story_id,
            article_id=article_id,
            relevance_score=1.0,  # Can be adjusted later with clustering scores
            is_primary=(article_id == primary_article_id),
            added_at=datetime.now(UTC),
        )
        session.add(story_article)

    # Update article count on story
    story = session.query(Story).filter(Story.id == story_id).first()
    if story:
        story.article_count = len(article_ids)  # type: ignore[assignment]
        story.last_updated = datetime.now(UTC)  # type: ignore[assignment]

    session.commit()
    logger.info(f"Linked {len(article_ids)} articles to story #{story_id}")


def get_story_by_id(session: Session, story_id: int) -> Optional[StoryOut]:
    """
    Get story by ID with supporting articles.

    Args:
        session: SQLAlchemy session
        story_id: Story ID

    Returns:
        StoryOut model or None if not found
    """
    story = session.query(Story).filter(Story.id == story_id).first()
    if not story:
        return None

    # Get article IDs from junction table
    article_ids = [sa.article_id for sa in story.story_articles]
    primary_article_id = next(
        (sa.article_id for sa in story.story_articles if sa.is_primary), None
    )

    # Query articles from items table
    articles: List[ItemOut] = []
    if article_ids:
        from sqlalchemy import text

        from app.models import StructuredSummary, extract_first_sentences

        # Build IN clause with proper placeholders (SQLite requirement)
        placeholders = ", ".join([f":id_{i}" for i in range(len(article_ids))])
        params = {f"id_{i}": aid for i, aid in enumerate(article_ids)}

        rows = session.execute(
            text(
                f"""
                SELECT id, title, url, published, summary, content_hash, content,
                       ai_summary, ai_model, ai_generated_at,
                       structured_summary_json, structured_summary_model, 
                       structured_summary_content_hash, structured_summary_generated_at,
                       ranking_score, topic, topic_confidence, source_weight, feed_id
                FROM items 
                WHERE id IN ({placeholders})
                ORDER BY ranking_score DESC
                """
            ),
            params,
        ).all()

        for r in rows:
            # Parse structured summary if available
            structured_summary = None
            if r[10] and r[11]:  # structured_summary_json and model
                try:
                    structured_summary = StructuredSummary.from_json_string(
                        r[10],
                        r[12]
                        or r[5]
                        or "",  # structured content_hash, fallback to main content_hash
                        r[11],
                        datetime.fromisoformat(r[13]) if r[13] else datetime.now(UTC),
                    )
                except Exception:
                    pass  # Skip if parsing fails

            # Generate fallback summary if no AI summary available
            fallback_summary = None
            is_fallback = False
            has_ai_summary = structured_summary is not None or r[7] is not None
            if not has_ai_summary and r[6]:  # content field
                try:
                    fallback_summary = extract_first_sentences(r[6], sentence_count=2)
                    is_fallback = True
                except Exception:
                    pass

            articles.append(
                ItemOut(
                    id=r[0],
                    title=r[1],
                    url=r[2],
                    published=datetime.fromisoformat(r[3]) if r[3] else None,
                    summary=r[4],
                    ai_summary=r[7],
                    ai_model=r[8],
                    ai_generated_at=datetime.fromisoformat(r[9]) if r[9] else None,
                    structured_summary=structured_summary,
                    fallback_summary=fallback_summary,
                    is_fallback_summary=is_fallback,
                    ranking_score=r[14] or 0.0,
                    topic=r[15],
                    topic_confidence=r[16] or 0.0,
                    source_weight=r[17] or 1.0,
                    feed_id=r[18],
                )
            )

    return _story_db_to_model(story, articles, primary_article_id)


def get_stories(
    session: Session,
    limit: int = 10,
    offset: int = 0,
    status: Optional[str] = "active",
    order_by: str = "importance",
) -> List[StoryOut]:
    """
    Query stories with filters and sorting.

    Args:
        session: SQLAlchemy session
        limit: Maximum number of stories to return
        offset: Number of stories to skip (for pagination)
        status: Filter by status ('active', 'archived', or None for all)
        order_by: Sort order ('importance', 'freshness', or 'generated_at')

    Returns:
        List of StoryOut models
    """
    query = session.query(Story)

    # Apply status filter if provided
    if status:
        query = query.filter(Story.status == status)

    # Apply sorting
    if order_by == "importance":
        query = query.order_by(desc(Story.importance_score))
    elif order_by == "freshness":
        query = query.order_by(desc(Story.freshness_score))
    else:  # generated_at
        query = query.order_by(desc(Story.generated_at))

    query = query.offset(offset).limit(limit)
    stories = query.all()

    # Convert to StoryOut models
    # For list view, we don't need full article details
    return [_story_db_to_model(story, [], None) for story in stories]


def update_story(session: Session, story_id: int, **updates) -> bool:
    """
    Update story fields.

    Args:
        session: SQLAlchemy session
        story_id: Story ID
        **updates: Fields to update (title, synthesis, importance_score, etc.)

    Returns:
        True if story was updated, False if not found
    """
    story = session.query(Story).filter(Story.id == story_id).first()
    if not story:
        return False

    # Update allowed fields
    allowed_fields = {
        "title",
        "synthesis",
        "key_points_json",
        "why_it_matters",
        "topics_json",
        "entities_json",
        "importance_score",
        "freshness_score",
        "status",
    }

    for key, value in updates.items():
        if key in allowed_fields:
            setattr(story, key, value)

    story.last_updated = datetime.now(UTC)  # type: ignore[assignment]
    session.commit()

    logger.info(f"Updated story #{story_id}")
    return True


def archive_story(session: Session, story_id: int) -> bool:
    """
    Archive story (soft delete).

    Sets status to 'archived' without deleting the record.

    Args:
        session: SQLAlchemy session
        story_id: Story ID

    Returns:
        True if story was archived, False if not found
    """
    story = session.query(Story).filter(Story.id == story_id).first()
    if not story:
        return False

    story.status = "archived"  # type: ignore[assignment]
    story.last_updated = datetime.now(UTC)  # type: ignore[assignment]
    session.commit()

    logger.info(f"Archived story #{story_id}")
    return True


def delete_story(session: Session, story_id: int) -> bool:
    """
    Hard delete story (CASCADE deletes story_articles).

    Permanently removes story and its article links from database.

    Args:
        session: SQLAlchemy session
        story_id: Story ID

    Returns:
        True if story was deleted, False if not found
    """
    story = session.query(Story).filter(Story.id == story_id).first()
    if not story:
        return False

    session.delete(story)
    session.commit()

    logger.info(f"Deleted story #{story_id}")
    return True


def cleanup_archived_stories(
    session: Session,
    days: int = STORY_DELETE_DAYS,
) -> int:
    """
    Hard delete archived stories older than N days.

    Args:
        session: SQLAlchemy session
        days: Delete stories archived more than this many days ago

    Returns:
        Number of stories deleted
    """
    cutoff_date = datetime.now(UTC) - timedelta(days=days)

    stories = (
        session.query(Story)
        .filter(Story.status == "archived", Story.last_updated < cutoff_date)
        .all()
    )

    count = len(stories)
    for story in stories:
        session.delete(story)

    session.commit()

    logger.info(f"Cleaned up {count} archived stories older than {days} days")
    return count


# Helper Functions


def _story_db_to_model(  # type: ignore[misc]
    story: Story,
    articles: List[ItemOut],
    primary_article_id: Optional[int] = None,
) -> StoryOut:
    """
    Convert ORM Story to Pydantic StoryOut model.

    Args:
        story: ORM Story object
        articles: List of supporting articles
        primary_article_id: ID of primary article

    Returns:
        StoryOut model
    """
    # SQLAlchemy Column types vs runtime values - mypy doesn't understand ORM magic
    # fmt: off
    return StoryOut(
        id=story.id,  # type: ignore[arg-type]
        title=story.title,  # type: ignore[arg-type]
        synthesis=story.synthesis,  # type: ignore[arg-type]
        key_points=deserialize_story_json_field(story.key_points_json),  # type: ignore[arg-type]
        why_it_matters=story.why_it_matters,  # type: ignore[arg-type]
        topics=deserialize_story_json_field(story.topics_json),  # type: ignore[arg-type]
        entities=deserialize_story_json_field(story.entities_json),  # type: ignore[arg-type]
        article_count=story.article_count,  # type: ignore[arg-type]
        importance_score=story.importance_score,  # type: ignore[arg-type]
        freshness_score=story.freshness_score,  # type: ignore[arg-type]
        generated_at=story.generated_at,  # type: ignore[arg-type]
        first_seen=story.first_seen,  # type: ignore[arg-type]
        last_updated=story.last_updated,  # type: ignore[arg-type]
        supporting_articles=articles,
        primary_article_id=primary_article_id,
    )
    # fmt: on


# Story Generation Functions


def _extract_keywords(title: str) -> Set[str]:
    """
    Extract meaningful keywords from article title.

    Simple extraction: lowercase, remove common words, split on non-alpha.

    Args:
        title: Article title

    Returns:
        Set of keywords
    """
    # Common stop words to ignore
    stop_words = {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "for",
        "from",
        "has",
        "he",
        "in",
        "is",
        "it",
        "its",
        "of",
        "on",
        "that",
        "the",
        "to",
        "was",
        "will",
        "with",
    }

    # Lowercase and extract words (alphanumeric + some punctuation)
    words = re.findall(r"\b[a-z0-9]+\b", title.lower())

    # Filter out stop words and short words (< 3 chars)
    keywords = {w for w in words if len(w) >= 3 and w not in stop_words}

    return keywords


def _calculate_keyword_overlap(keywords1: Set[str], keywords2: Set[str]) -> float:
    """
    Calculate Jaccard similarity between two keyword sets.

    Args:
        keywords1: First set of keywords
        keywords2: Second set of keywords

    Returns:
        Similarity score (0.0 to 1.0)
    """
    if not keywords1 or not keywords2:
        return 0.0

    intersection = len(keywords1 & keywords2)
    union = len(keywords1 | keywords2)

    return intersection / union if union > 0 else 0.0


def _calculate_combined_similarity(
    keywords1: Set[str],
    keywords2: Set[str],
    entities1: Optional[ExtractedEntities],
    entities2: Optional[ExtractedEntities],
    keyword_weight: float = 0.4,
    entity_weight: float = 0.6,
) -> float:
    """
    Calculate combined similarity using keywords and entities.

    Args:
        keywords1: First article keywords
        keywords2: Second article keywords
        entities1: First article entities (optional)
        entities2: Second article entities (optional)
        keyword_weight: Weight for keyword similarity (default: 0.4)
        entity_weight: Weight for entity similarity (default: 0.6)

    Returns:
        Combined similarity score (0.0 to 1.0)
    """
    # Calculate keyword similarity
    keyword_sim = _calculate_keyword_overlap(keywords1, keywords2)

    # Calculate entity similarity if both entities exist
    if entities1 and entities2:
        entity_sim = get_entity_overlap(entities1, entities2)
    else:
        # If no entities, fall back to pure keyword similarity
        entity_sim = 0.0
        # Adjust weights to compensate for missing entity data
        keyword_weight = 1.0
        entity_weight = 0.0

    # Weighted combination
    combined_sim = (keyword_weight * keyword_sim) + (entity_weight * entity_sim)

    return combined_sim


def _generate_story_synthesis(
    session: Session,
    article_ids: List[int],
    model: str = "llama3.1:8b",
    articles_cache: Optional[Dict[int, Any]] = None,
) -> Dict[str, Any]:
    """
    Generate story synthesis from multiple articles using LLM.

    Args:
        session: Database session
        article_ids: List of article IDs to synthesize
        model: LLM model to use
        articles_cache: Optional cached article data to avoid DB queries

    Returns:
        Dict with synthesis, key_points, why_it_matters, topics, entities
    """
    # Use cached article data if available, otherwise fetch
    if articles_cache:
        articles = [articles_cache[aid] for aid in article_ids if aid in articles_cache]
    else:
        # Fetch article details
        # Build IN clause with proper placeholders
        placeholders = ", ".join([f":id_{i}" for i in range(len(article_ids))])
        params = {f"id_{i}": aid for i, aid in enumerate(article_ids)}

        articles = session.execute(
            text(
                f"""
            SELECT id, title, summary, ai_summary, topic
            FROM items 
            WHERE id IN ({placeholders})
            ORDER BY published DESC
        """
            ),
            params,
        ).fetchall()

    if not articles:
        raise ValueError("No articles found for synthesis")

    # Build context for LLM
    article_summaries = []
    for article in articles:
        if articles_cache:
            # Cached data is already a dict/tuple
            article_id, title, summary, ai_summary, topic = (
                article["id"],
                article["title"],
                article["summary"],
                article["ai_summary"],
                article["topic"],
            )
        else:
            article_id, title, summary, ai_summary, topic = article
        content = ai_summary or summary or title
        article_summaries.append(f"- {title}\n  {content[:200]}")

    context = "\n\n".join(article_summaries)

    # Create prompt for multi-document synthesis
    prompt = f"""You are a news aggregator. Synthesize these related articles into a single coherent story.

Articles:
{context}

Generate a JSON response with:
1. "synthesis": 2-3 sentence summary of the overall story (50-150 words)
2. "key_points": List of 3-5 bullet points covering main facts
3. "why_it_matters": 1-2 sentences explaining significance
4. "topics": List of 1-3 relevant topic tags (e.g., "AI/ML", "Cloud", "Security")
5. "entities": List of 3-7 key entities mentioned (companies, products, people)

Respond ONLY with valid JSON, no other text.

Example format:
{{
  "synthesis": "OpenAI announced GPT-5 with significant improvements...",
  "key_points": [
    "Released March 2024",
    "10x faster than GPT-4",
    "New multimodal capabilities"
  ],
  "why_it_matters": "This represents a major leap in AI capabilities...",
  "topics": ["AI/ML", "Enterprise"],
  "entities": ["OpenAI", "GPT-5", "Sam Altman"]
}}

JSON:"""

    try:
        llm_service = get_llm_service()

        if not llm_service.is_available():
            logger.warning("LLM service not available, using fallback synthesis")
            return _fallback_synthesis(articles)

        if not llm_service.ensure_model(model):
            logger.warning(f"Model {model} not available, using fallback synthesis")
            return _fallback_synthesis(articles)

        # Generate synthesis
        response = llm_service.client.generate(
            model=model,
            prompt=prompt,
            options={
                "temperature": 0.3,
                "top_k": 40,
                "top_p": 0.9,
                "num_predict": 500,
            },
        )

        # Extract JSON from response
        response_text = response.get("response", "")

        # Try to find JSON in response (might have extra text)
        json_match = re.search(r"\{.*\}", response_text, re.DOTALL)
        if json_match:
            result = json.loads(json_match.group())

            # Validate required fields
            if all(k in result for k in ["synthesis", "key_points", "why_it_matters"]):
                key_points = result.get("key_points", [])

                # Ensure at least 3 key points (pad if LLM returns too few)
                if len(key_points) < 3:
                    logger.warning(
                        f"LLM returned only {len(key_points)} key points, padding to 3"
                    )

                    # Pad with generic points from synthesis or article data
                    if len(key_points) == 0:
                        key_points = [
                            "Multiple related articles aggregated",
                            f"Based on {len(articles)} sources",
                            "See supporting articles for details",
                        ]
                    elif len(key_points) == 1:
                        key_points.append(f"Based on {len(articles)} sources")
                        key_points.append("See supporting articles for details")
                    elif len(key_points) == 2:
                        key_points.append(f"Based on {len(articles)} sources")

                return {
                    "synthesis": result["synthesis"],
                    "key_points": key_points,
                    "why_it_matters": result.get("why_it_matters", ""),
                    "topics": result.get("topics", []),
                    "entities": result.get("entities", []),
                }

        logger.warning("LLM response invalid, using fallback")
        return _fallback_synthesis(articles)

    except Exception as e:
        logger.error(f"Failed to generate synthesis with LLM: {e}")
        return _fallback_synthesis(articles)


def _fallback_synthesis(articles: Sequence[Any]) -> Dict[str, Any]:
    """
    Generate fallback synthesis when LLM is unavailable.

    Args:
        articles: List of article tuples (id, title, summary, ai_summary, topic)

    Returns:
        Dict with synthesis fields
    """
    titles = [article[1] for article in articles]
    topics = list({article[4] for article in articles if article[4]})

    if len(articles) == 1:
        synthesis = f"{titles[0]}"
        key_points = [
            "Single article - see details below",
            f"Source: {titles[0][:80]}...",
            f"Topic: {topics[0] if topics else 'General'}",
        ]
    else:
        synthesis = (
            f"Multiple articles about {topics[0] if topics else 'this topic'}: "
            + ", ".join(titles[:3])
        )
        if len(titles) > 3:
            synthesis += f" and {len(titles) - 3} more"

        # Ensure at least 3 key points
        key_points = [f"• {title}" for title in titles[:5]]

        # Pad with generic points if needed
        while len(key_points) < 3:
            if len(key_points) == 1:
                key_points.append(f"• {len(articles)} related articles")
            elif len(key_points) == 2:
                key_points.append(
                    f"• Topics: {', '.join(topics) if topics else 'Various'}"
                )

    return {
        "synthesis": synthesis,
        "key_points": key_points,
        "why_it_matters": "See articles for details",
        "topics": topics[:3] if topics else ["Uncategorized"],
        "entities": [],
    }


def generate_stories_simple(
    session: Session,
    time_window_hours: int = 24,
    min_articles_per_story: int = 1,
    similarity_threshold: float = 0.3,
    model: str = "llama3.1:8b",
    max_workers: int = 3,  # Parallel LLM calls
) -> List[int]:
    """
    Generate stories from recent articles using hybrid clustering (OPTIMIZED + ENTITIES v0.6.1).

    Clustering approach:
    1. Group by topic (coarse filter)
    2. Extract entities (companies, products, people, technologies, locations)
    3. Within each topic, cluster by combined keyword + entity similarity
    4. Generate synthesis for each cluster (IN PARALLEL)
    5. Store stories in database (BATCHED COMMITS)

    Similarity Calculation (v0.6.1):
    - 40% keyword overlap (title-based)
    - 60% entity overlap (LLM-extracted entities)
    - Graceful fallback to pure keyword similarity if entity extraction fails

    Optimizations:
    - Parallel LLM synthesis calls using ThreadPoolExecutor
    - Cached article data to avoid redundant queries
    - Cached entity extractions to avoid redundant LLM calls
    - Batched database commits
    - Performance instrumentation

    Args:
        session: SQLAlchemy session
        time_window_hours: Look back this many hours for articles
        min_articles_per_story: Minimum articles per story (1 = allow single-article stories)
        similarity_threshold: Minimum combined similarity to cluster articles (0.0-1.0)
        model: LLM model for synthesis and entity extraction
        max_workers: Maximum parallel LLM synthesis calls (default: 3)

    Returns:
        List of created story IDs
    """
    overall_start = time.time()
    logger.info(
        f"Starting OPTIMIZED story generation: time_window={time_window_hours}h, "
        f"min_articles={min_articles_per_story}, threshold={similarity_threshold}, "
        f"max_workers={max_workers}"
    )

    # Get articles from time window (fetch ALL data once to cache it)
    cutoff_time = datetime.now(UTC) - timedelta(hours=time_window_hours)

    data_fetch_start = time.time()
    articles = session.execute(
        text(
            """
        SELECT id, title, topic, published, summary, ai_summary
        FROM items 
        WHERE published >= :cutoff_time
        AND (ai_summary IS NOT NULL OR summary IS NOT NULL)
        ORDER BY published DESC
    """
        ),
        {"cutoff_time": cutoff_time},
    ).fetchall()
    data_fetch_time = time.time() - data_fetch_start

    if not articles:
        logger.info("No articles found in time window")
        return []

    logger.info(
        f"Found {len(articles)} articles in time window ({data_fetch_time:.2f}s)"
    )

    # Build article cache (optimization: avoid repeated queries)
    articles_cache = {
        int(art[0]): {
            "id": int(art[0]),
            "title": str(art[1]),
            "topic": art[2],
            "published": art[3],
            "summary": art[4],
            "ai_summary": art[5],
        }
        for art in articles
    }

    # Step 1: Group by topic (coarse filter)
    topic_groups: Dict[str, List[Any]] = defaultdict(list)
    for article in articles:
        topic = article[2] or "uncategorized"
        topic_groups[topic].append(article)

    logger.info(f"Grouped into {len(topic_groups)} topics")

    # Step 2: Within each topic, cluster by keyword overlap
    clusters: List[List[int]] = []

    for topic, topic_articles in topic_groups.items():
        logger.debug(f"Processing topic '{topic}' with {len(topic_articles)} articles")

        # Extract keywords for each article
        article_keywords = {}
        for article in topic_articles:
            article_id = int(article[0])  # type: ignore[index]
            title = str(article[1])  # type: ignore[index]
            article_keywords[article_id] = _extract_keywords(title)

        # Extract entities for each article (v0.6.1 - enhanced clustering)
        article_entities = {}
        entity_extraction_start = time.time()
        for article in topic_articles:
            article_id = int(article[0])  # type: ignore[index]
            title = str(article[1])  # type: ignore[index]
            summary = article[4] or article[5] or ""  # type: ignore[index]
            
            try:
                entities = extract_and_cache_entities(
                    article_id=article_id,
                    title=title,
                    summary=str(summary),
                    session=session,
                    model=model,
                    use_cache=True,
                )
                article_entities[article_id] = entities
            except Exception as e:
                logger.warning(f"Failed to extract entities for article {article_id}: {e}")
                article_entities[article_id] = None
        
        entity_extraction_time = time.time() - entity_extraction_start
        logger.debug(
            f"Entity extraction for {len(topic_articles)} articles took {entity_extraction_time:.2f}s"
        )

        # Greedy clustering: iterate through articles, add to existing cluster or create new one
        topic_clusters: List[List[int]] = []

        for article in topic_articles:
            article_id = int(article[0])  # type: ignore[index]
            keywords = article_keywords[article_id]
            entities = article_entities.get(article_id)

            # Find best matching cluster
            best_cluster = None
            best_similarity = 0.0

            for cluster in topic_clusters:
                # Calculate average combined similarity to cluster (keywords + entities)
                similarities = [
                    _calculate_combined_similarity(
                        keywords,
                        article_keywords[aid],
                        entities,
                        article_entities.get(aid),
                    )
                    for aid in cluster
                ]
                avg_similarity = (
                    sum(similarities) / len(similarities) if similarities else 0.0
                )

                if avg_similarity > best_similarity:
                    best_similarity = avg_similarity
                    best_cluster = cluster

            # Add to best cluster if similar enough, otherwise create new cluster
            if best_cluster and best_similarity >= similarity_threshold:
                best_cluster.append(article_id)
            else:
                topic_clusters.append([article_id])

        clusters.extend(topic_clusters)
        logger.debug(
            f"Topic '{topic}' clustered into {len(topic_clusters)} story clusters"
        )

    logger.info(f"Total clusters: {len(clusters)}")

    # Filter clusters by minimum articles
    clusters = [c for c in clusters if len(c) >= min_articles_per_story]
    logger.info(
        f"After filtering (min={min_articles_per_story}): {len(clusters)} clusters"
    )

    if not clusters:
        logger.info("No clusters meet minimum article threshold")
        return []

    # Step 3: Generate story synthesis for ALL clusters IN PARALLEL
    logger.info(f"Starting parallel LLM synthesis with {max_workers} workers...")
    synthesis_start = time.time()

    # Prepare cluster data with cached article info
    cluster_data_list = []
    for cluster_article_ids in clusters:
        # Calculate metadata from cached data
        cluster_articles = [articles_cache[aid] for aid in cluster_article_ids]
        published_times = [art["published"] for art in cluster_articles]

        # Get time range
        time_window_start = min(published_times) if published_times else cutoff_time
        time_window_end = max(published_times) if published_times else datetime.now(UTC)

        # Convert string to datetime if needed (SQLite returns strings)
        if isinstance(time_window_start, str):
            time_window_start = datetime.fromisoformat(
                time_window_start.replace("Z", "+00:00")
            )
        if isinstance(time_window_end, str):
            time_window_end = datetime.fromisoformat(
                time_window_end.replace("Z", "+00:00")
            )

        cluster_data_list.append(
            {
                "article_ids": cluster_article_ids,
                "time_window_start": time_window_start,
                "time_window_end": time_window_end,
                "importance_score": min(1.0, 0.3 + (len(cluster_article_ids) * 0.1)),
                "freshness_score": 1.0,
                "cluster_hash": hashlib.md5(
                    json.dumps(sorted(cluster_article_ids)).encode()
                ).hexdigest(),
            }
        )

    # Parallel LLM synthesis with ThreadPoolExecutor
    synthesis_results = []

    def generate_synthesis_for_cluster(cluster_data):
        """Helper function for parallel execution."""
        try:
            synthesis_data = _generate_story_synthesis(
                session,
                cluster_data["article_ids"],
                model,
                articles_cache=articles_cache,
            )
            return {
                "success": True,
                "cluster_data": cluster_data,
                "synthesis_data": synthesis_data,
            }
        except Exception as e:
            logger.error(f"Synthesis failed for cluster: {e}")
            return {
                "success": False,
                "cluster_data": cluster_data,
                "error": str(e),
            }

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all synthesis tasks
        futures = {
            executor.submit(generate_synthesis_for_cluster, cluster_data): i
            for i, cluster_data in enumerate(cluster_data_list)
        }

        # Collect results as they complete
        for future in as_completed(futures):
            cluster_idx = futures[future]
            try:
                result = future.result()
                synthesis_results.append(result)
                if result["success"]:
                    logger.debug(
                        f"Completed synthesis {len(synthesis_results)}/{len(clusters)} "
                        f"(cluster {cluster_idx + 1})"
                    )
            except Exception as e:
                logger.error(f"Failed to get synthesis result: {e}")

    synthesis_time = time.time() - synthesis_start
    successful_syntheses = sum(1 for r in synthesis_results if r["success"])
    logger.info(
        f"Parallel LLM synthesis complete: {successful_syntheses}/{len(clusters)} succeeded "
        f"({synthesis_time:.2f}s, avg {synthesis_time/len(clusters):.2f}s per story)"
    )

    # Step 4: Create stories in database (batched commits)
    logger.info("Creating stories in database...")
    db_start = time.time()
    story_ids = []

    # Check for existing story hashes to avoid duplicates
    cluster_hashes = [
        result["cluster_data"]["cluster_hash"]
        for result in synthesis_results
        if result["success"]
    ]

    if cluster_hashes:
        placeholders = ", ".join([f":hash_{i}" for i in range(len(cluster_hashes))])
        hash_params = {f"hash_{i}": h for i, h in enumerate(cluster_hashes)}

        existing_hashes = session.execute(
            text(
                f"SELECT story_hash FROM stories WHERE story_hash IN ({placeholders})"
            ),
            hash_params,
        ).fetchall()
        existing_hash_set = {row[0] for row in existing_hashes}
        logger.info(
            f"Found {len(existing_hash_set)} existing stories (will skip duplicates)"
        )
    else:
        existing_hash_set = set()

    # Collect all stories to create without committing
    stories_to_create = []
    skipped_duplicates = 0

    for result in synthesis_results:
        if not result["success"]:
            continue

        cluster_data = result["cluster_data"]
        synthesis_data = result["synthesis_data"]

        # Skip if story already exists
        if cluster_data["cluster_hash"] in existing_hash_set:
            skipped_duplicates += 1
            logger.debug(
                f"Skipping duplicate story with hash {cluster_data['cluster_hash']}"
            )
            continue

        try:
            # Create story WITHOUT commit (will batch commit at end)
            story = Story(
                title=synthesis_data["synthesis"][:200],
                synthesis=synthesis_data["synthesis"],
                key_points_json=serialize_story_json_field(
                    synthesis_data["key_points"]
                ),
                why_it_matters=synthesis_data["why_it_matters"],
                topics_json=serialize_story_json_field(synthesis_data["topics"]),
                entities_json=serialize_story_json_field(synthesis_data["entities"]),
                article_count=len(cluster_data["article_ids"]),
                importance_score=cluster_data["importance_score"],
                freshness_score=cluster_data["freshness_score"],
                cluster_method="hybrid_topic_keywords_optimized",
                story_hash=cluster_data["cluster_hash"],
                generated_at=datetime.now(UTC),
                first_seen=datetime.now(UTC),
                last_updated=datetime.now(UTC),
                time_window_start=cluster_data["time_window_start"],
                time_window_end=cluster_data["time_window_end"],
                model=model,
                status="active",
            )
            session.add(story)
            stories_to_create.append((story, cluster_data["article_ids"]))

        except Exception as e:
            logger.error(f"Failed to prepare story: {e}", exc_info=True)
            continue

    if skipped_duplicates > 0:
        logger.info(f"Skipped {skipped_duplicates} duplicate stories")

    # Single flush to assign IDs
    session.flush()

    # Now link articles (story IDs are available)
    for story, article_ids in stories_to_create:
        try:
            for article_id in article_ids:
                story_article = StoryArticle(
                    story_id=story.id,
                    article_id=article_id,
                    relevance_score=1.0,
                    is_primary=(article_id == article_ids[0]),
                    added_at=datetime.now(UTC),
                )
                session.add(story_article)

            story_ids.append(story.id)  # type: ignore[arg-type]

        except Exception as e:
            logger.error(f"Failed to link articles for story: {e}", exc_info=True)
            continue

    # Single commit for ALL stories
    try:
        session.commit()
        db_time = time.time() - db_start
        logger.info(
            f"Database operations complete: {len(story_ids)} stories committed ({db_time:.2f}s)"
        )
    except Exception as e:
        session.rollback()
        logger.error(f"Failed to commit stories: {e}", exc_info=True)
        return []

    overall_time = time.time() - overall_start

    if len(story_ids) == 0 and skipped_duplicates > 0:
        logger.info(
            f"✅ Story generation COMPLETE: 0 new stories (all {skipped_duplicates} were duplicates) "
            f"in {overall_time:.2f}s"
        )
    else:
        logger.info(
            f"✅ Story generation COMPLETE: {len(story_ids)} stories created in {overall_time:.2f}s "
            f"(fetch: {data_fetch_time:.2f}s, synthesis: {synthesis_time:.2f}s, db: {db_time:.2f}s)"
        )

    return story_ids

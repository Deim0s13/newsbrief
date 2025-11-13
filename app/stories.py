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
from collections import defaultdict
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

    # Query articles separately (items table not ORM yet)
    # For now, we'll return story without articles - articles will be fetched by API layer
    articles: List[ItemOut] = []  # TODO: Query items table when needed

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


def _generate_story_synthesis(
    session: Session, article_ids: List[int], model: str = "llama3.1:8b"
) -> Dict[str, Any]:
    """
    Generate story synthesis from multiple articles using LLM.

    Args:
        session: Database session
        article_ids: List of article IDs to synthesize
        model: LLM model to use

    Returns:
        Dict with synthesis, key_points, why_it_matters, topics, entities
    """
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
                return {
                    "synthesis": result["synthesis"],
                    "key_points": result.get("key_points", []),
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
        key_points = ["Single article - see details below"]
    else:
        synthesis = (
            f"Multiple articles about {topics[0] if topics else 'this topic'}: "
            + ", ".join(titles[:3])
        )
        if len(titles) > 3:
            synthesis += f" and {len(titles) - 3} more"
        key_points = [f"• {title}" for title in titles[:5]]

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
) -> List[int]:
    """
    Generate stories from recent articles using hybrid clustering.

    Clustering approach:
    1. Group by topic (coarse filter)
    2. Within each topic, cluster by title keyword overlap
    3. Generate synthesis for each cluster
    4. Store stories in database

    Args:
        session: SQLAlchemy session
        time_window_hours: Look back this many hours for articles
        min_articles_per_story: Minimum articles per story (1 = allow single-article stories)
        similarity_threshold: Minimum keyword overlap to cluster articles (0.0-1.0)
        model: LLM model for synthesis

    Returns:
        List of created story IDs
    """
    logger.info(
        f"Starting story generation: time_window={time_window_hours}h, "
        f"min_articles={min_articles_per_story}, threshold={similarity_threshold}"
    )

    # Get articles from time window
    cutoff_time = datetime.now(UTC) - timedelta(hours=time_window_hours)

    articles = session.execute(
        text(
            """
        SELECT id, title, topic, published
        FROM items 
        WHERE published >= :cutoff_time
        AND (ai_summary IS NOT NULL OR summary IS NOT NULL)
        ORDER BY published DESC
    """
        ),
        {"cutoff_time": cutoff_time},
    ).fetchall()

    if not articles:
        logger.info("No articles found in time window")
        return []

    logger.info(f"Found {len(articles)} articles in time window")

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

        # Greedy clustering: iterate through articles, add to existing cluster or create new one
        topic_clusters: List[List[int]] = []

        for article in topic_articles:
            article_id = int(article[0])  # type: ignore[index]
            keywords = article_keywords[article_id]

            # Find best matching cluster
            best_cluster = None
            best_similarity = 0.0

            for cluster in topic_clusters:
                # Calculate average similarity to cluster
                similarities = [
                    _calculate_keyword_overlap(keywords, article_keywords[aid])
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

    # Step 3: Generate story for each cluster
    story_ids = []

    for i, cluster_article_ids in enumerate(clusters):
        try:
            logger.debug(
                f"Generating story {i+1}/{len(clusters)} from {len(cluster_article_ids)} articles"
            )

            # Generate synthesis
            synthesis_data = _generate_story_synthesis(
                session, cluster_article_ids, model
            )

            # Calculate importance and freshness scores
            # For now, use simple heuristics
            importance_score = min(
                1.0, 0.3 + (len(cluster_article_ids) * 0.1)
            )  # More articles = more important
            freshness_score = 1.0  # All articles are recent (from time window)

            # Get time window for this cluster
            placeholders = ", ".join(
                [f":id_{i}" for i in range(len(cluster_article_ids))]
            )
            params = {f"id_{i}": aid for i, aid in enumerate(cluster_article_ids)}

            cluster_times = session.execute(
                text(
                    f"""
                SELECT MIN(published), MAX(published)
                FROM items 
                WHERE id IN ({placeholders})
            """
                ),
                params,
            ).first()

            # Convert to datetime if needed (SQLite returns strings)
            time_window_start = cluster_times[0]  # type: ignore[index]
            time_window_end = cluster_times[1]  # type: ignore[index]

            if isinstance(time_window_start, str):
                time_window_start = datetime.fromisoformat(
                    time_window_start.replace("Z", "+00:00")
                )
            if isinstance(time_window_end, str):
                time_window_end = datetime.fromisoformat(
                    time_window_end.replace("Z", "+00:00")
                )

            # Generate story hash for deduplication
            cluster_hash = hashlib.md5(
                json.dumps(sorted(cluster_article_ids)).encode()
            ).hexdigest()

            # Create story
            story_id = create_story(
                session=session,
                title=synthesis_data["synthesis"][:200],  # type: ignore[index] # Use first part as title
                synthesis=synthesis_data["synthesis"],  # type: ignore[index]
                key_points=synthesis_data["key_points"],
                why_it_matters=synthesis_data["why_it_matters"],
                topics=synthesis_data["topics"],
                entities=synthesis_data["entities"],
                importance_score=importance_score,
                freshness_score=freshness_score,
                model=model,
                time_window_start=time_window_start,
                time_window_end=time_window_end,
                cluster_method="hybrid_topic_keywords",
                story_hash=cluster_hash,
            )

            # Link articles to story
            link_articles_to_story(
                session=session,
                story_id=story_id,
                article_ids=cluster_article_ids,
                primary_article_id=cluster_article_ids[
                    0
                ],  # Most recent article is primary
            )

            story_ids.append(story_id)
            logger.info(
                f"Created story #{story_id} from {len(cluster_article_ids)} articles"
            )

        except Exception as e:
            logger.error(f"Failed to create story for cluster: {e}", exc_info=True)
            continue

    logger.info(f"Story generation complete: {len(story_ids)} stories created")
    return story_ids

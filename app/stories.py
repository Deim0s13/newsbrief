"""
Story CRUD operations using SQLAlchemy ORM.

Provides database operations for story-based aggregation:
- Create stories
- Link articles to stories
- Query stories with filters
- Update/archive/delete stories
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime, timedelta
from typing import List, Optional

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
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session, relationship

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
Base = declarative_base()


# ORM Models


class Story(Base):
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


class StoryArticle(Base):
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
    return story.id


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
        story.article_count = len(article_ids)
        story.last_updated = datetime.now(UTC)

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
    status: str = "active",
    order_by: str = "importance",
) -> List[StoryOut]:
    """
    Query stories with filters and sorting.

    Args:
        session: SQLAlchemy session
        limit: Maximum number of stories to return
        status: Filter by status ('active' or 'archived')
        order_by: Sort order ('importance', 'date', or 'freshness')

    Returns:
        List of StoryOut models
    """
    query = session.query(Story).filter(Story.status == status)

    # Apply sorting
    if order_by == "importance":
        query = query.order_by(desc(Story.importance_score))
    elif order_by == "freshness":
        query = query.order_by(desc(Story.freshness_score))
    else:  # date
        query = query.order_by(desc(Story.generated_at))

    query = query.limit(limit)
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

    story.last_updated = datetime.utcnow()
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

    story.status = "archived"
    story.last_updated = datetime.utcnow()
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


def _story_db_to_model(
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
    return StoryOut(
        id=story.id,
        title=story.title,
        synthesis=story.synthesis,
        key_points=deserialize_story_json_field(story.key_points_json),
        why_it_matters=story.why_it_matters,
        topics=deserialize_story_json_field(story.topics_json),
        entities=deserialize_story_json_field(story.entities_json),
        article_count=story.article_count,
        importance_score=story.importance_score,
        freshness_score=story.freshness_score,
        generated_at=story.generated_at,
        first_seen=story.first_seen,
        last_updated=story.last_updated,
        supporting_articles=articles,
        primary_article_id=primary_article_id,
    )

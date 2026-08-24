"""PostgreSQL-only helpers for integration tests (ADR-0022)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session


def create_test_story(
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
    Create a bare-minimum ``Story`` row for test setup.

    This is a test-only fixture helper, not a production code path -- it
    replaces the ``create_story()`` CRUD function that was removed from
    ``app.stories`` in #346 (confirmed zero production callers; the live
    pipeline constructs ``Story`` inline in ``generate_stories_simple()``
    with ~15 additional fields this helper doesn't need to replicate for
    test purposes).
    """
    from app.models import serialize_story_json_field
    from app.orm_models import Story
    from app.processing_states import StoryProcessingState

    story = Story(
        title=title,
        synthesis=synthesis,
        key_points_json=serialize_story_json_field(key_points),
        why_it_matters=why_it_matters,
        topics_json=serialize_story_json_field(topics),
        entities_json=serialize_story_json_field(entities),
        article_count=0,
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
        processing_state=StoryProcessingState.PUBLISHED.value,
        version=1,
    )
    session.add(story)
    session.commit()
    session.refresh(story)
    return story.id  # type: ignore[return-value]


def link_test_articles_to_story(
    session: Session,
    story_id: int,
    article_ids: List[int],
    primary_article_id: Optional[int] = None,
) -> None:
    """Link articles to a story for test setup (see create_test_story)."""
    from app.orm_models import Story, StoryArticle

    for article_id in article_ids:
        session.add(
            StoryArticle(
                story_id=story_id,
                article_id=article_id,
                relevance_score=1.0,
                is_primary=(article_id == primary_article_id),
                added_at=datetime.now(UTC),
            )
        )

    story = session.query(Story).filter(Story.id == story_id).first()
    if story:
        story.article_count = len(article_ids)  # type: ignore[assignment]
        story.last_updated = datetime.now(UTC)  # type: ignore[assignment]

    session.commit()


def pg_session_truncate_story_graph() -> Session:
    """Fresh session; story-related tables truncated with identity reset."""
    from app.db import SessionLocal, init_db

    init_db()
    session = SessionLocal()
    session.execute(
        text("TRUNCATE story_articles, stories, items, feeds RESTART IDENTITY CASCADE")
    )
    session.commit()
    return session


def pg_session_truncate_synthesis_cache() -> Session:
    from app.db import SessionLocal, init_db

    init_db()
    session = SessionLocal()
    session.execute(text("TRUNCATE synthesis_cache RESTART IDENTITY CASCADE"))
    session.commit()
    return session


def pg_session_truncate_retrieval_traces() -> Session:
    """Fresh session; story graph + retrieval_traces truncated with identity reset."""
    from app.db import SessionLocal, init_db

    init_db()
    session = SessionLocal()
    session.execute(
        text(
            "TRUNCATE retrieval_traces, story_articles, stories, items, feeds "
            "RESTART IDENTITY CASCADE"
        )
    )
    session.commit()
    return session

"""PostgreSQL-only helpers for integration tests (ADR-0022)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Iterable, List, Optional

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


def _vec(seed: float, dims: int = 768) -> List[float]:
    """Deterministic vector; small seed deltas => near-1.0 cosine similarity.

    Was copy-pasted byte-for-byte across 6 test files (#359) -- shared here
    so the RAG-integration test cluster (semantic dedup, retrieval, light
    RAG, retrieval tracing, context retrieval, historical linking) has one
    definition instead of six.
    """
    return [seed + 0.0001 * i for i in range(dims)]


def seed_default_feed(
    session: Session,
    feed_id: int = 1,
    url: str = "http://example.com/feed",
    name: str = "Test Feed",
    disabled: int = 0,
    health_score: float = 100.0,
) -> None:
    """Insert a single minimal feed row for test setup.

    Extracted from the near-identical inline SQL repeated in
    ``_seed_feed()`` (see below) and several ``setup_test_db()`` fixtures
    (#359). Parameterized rather than hardcoded so callers that need a
    different id/url (e.g. a distinct feed per test) aren't forced into
    the same literal values.
    """
    session.execute(
        text(
            "INSERT INTO feeds (id, url, name, disabled, health_score) "
            "VALUES (:id, :url, :name, :disabled, :health_score)"
        ),
        {
            "id": feed_id,
            "url": url,
            "name": name,
            "disabled": disabled,
            "health_score": health_score,
        },
    )


def _seed_feed(session: Session) -> None:
    """Insert the RAG-cluster's conventional default feed (id=1).

    Was copy-pasted byte-for-byte across 5 test files (#359) -- now a thin
    wrapper over ``seed_default_feed()`` so RAG-cluster call sites don't
    need to change their existing ``_seed_feed(session)`` call shape.
    """
    seed_default_feed(session)


def resync_sequences(
    session: Session,
    tables: Iterable[str] = (
        "feeds",
        "items",
        "stories",
        "story_articles",
        "retrieval_traces",
        "synthesis_cache",
    ),
) -> None:
    """Advance each table's serial ``id`` sequence past its current max value.

    Guards against ``IntegrityError: duplicate key value violates unique
    constraint "<table>_pkey"`` (#358): many integration tests insert rows
    with explicit hardcoded primary keys (``id=1``, ``id=999``, ...) after a
    ``TRUNCATE ... RESTART IDENTITY``. Explicit-value inserts don't advance a
    PostgreSQL serial sequence, so it stays parked at 1 while low-numbered
    rows now exist -- any later insert via ``DEFAULT``/an omitted id column
    (a normal ORM insert) then collides with those ids.

    Called automatically after every test (see conftest.py's
    ``dispose_db_connections_after_test``), not just from the truncate
    helpers below -- calling it right after a ``TRUNCATE`` is a no-op (the
    table is empty at that point); the actual danger window is *between*
    tests, once one test's explicit-id seed data exists and a later test
    inserts via a normal ORM/implicit-id path.
    """
    for table in tables:
        session.execute(
            text(
                f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
                f"COALESCE((SELECT MAX(id) FROM {table}), 1))"
            )
        )
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

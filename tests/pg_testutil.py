"""PostgreSQL-only helpers for integration tests (ADR-0022)."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session


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

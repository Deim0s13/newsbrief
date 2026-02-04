# Database utilities - PostgreSQL only (ADR 0022)
from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

logger = logging.getLogger(__name__)

# Database configuration - PostgreSQL required
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL environment variable is required. "
        "Example: postgresql://user:pass@localhost:5432/newsbrief"
    )

# Normalize URL for psycopg3 driver (handles both postgresql:// and postgresql+psycopg://)
db_url = DATABASE_URL
if db_url.startswith("postgresql://"):
    db_url = db_url.replace("postgresql://", "postgresql+psycopg://", 1)
elif db_url.startswith("postgres://"):
    # Handle Heroku-style URLs
    db_url = db_url.replace("postgres://", "postgresql+psycopg://", 1)

# pool_pre_ping: Test connections before use (handles dropped connections)
engine = create_engine(db_url, future=True, pool_pre_ping=True)
logger.info("🐘 Using PostgreSQL database")

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


@contextmanager
def session_scope() -> Iterator:
    sess = SessionLocal()
    try:
        yield sess
        sess.commit()
    except Exception:
        sess.rollback()
        raise
    finally:
        sess.close()


def init_db() -> None:
    """
    Initialize database connection.

    Verifies PostgreSQL connection is working.
    Schema management is handled by Alembic migrations.
    """
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            logger.info("✅ PostgreSQL connection verified")
    except Exception as e:
        logger.error(f"❌ PostgreSQL connection failed: {e}")
        logger.error("   Ensure DATABASE_URL is correct and Postgres is running")
        raise

# Database utilities - supports SQLite (dev) and PostgreSQL (prod)
from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

logger = logging.getLogger(__name__)

# Database configuration
DATABASE_URL = os.getenv("DATABASE_URL")

if DATABASE_URL:
    # PostgreSQL mode (production)
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
else:
    # SQLite mode (development)
    DATA_DIR = Path("data")
    DATA_DIR.mkdir(exist_ok=True, parents=True)
    DB_PATH = DATA_DIR / "newsbrief.sqlite3"
    engine = create_engine(
        f"sqlite:///{DB_PATH}", future=True, connect_args={"check_same_thread": False}
    )
    logger.info("📦 Using SQLite database")

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def is_postgres() -> bool:
    """Check if using PostgreSQL backend."""
    return DATABASE_URL is not None and "postgres" in DATABASE_URL.lower()


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
    Initialize database with all required tables and indexes.

    For SQLite (development):
    - Creates all tables from scratch if needed
    - Adds missing tables/columns (migration)
    - Uses CREATE TABLE IF NOT EXISTS for idempotent migrations

    For PostgreSQL (production):
    - Skips table creation (expects Alembic migrations to have been run)
    - Verifies database connection is working
    """
    if is_postgres():
        # PostgreSQL: Verify connection, but don't create tables
        # Schema management is handled by Alembic migrations (Issue #31)
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
                logger.info("✅ PostgreSQL connection verified")
        except Exception as e:
            logger.error(f"❌ PostgreSQL connection failed: {e}")
            logger.error("   Ensure DATABASE_URL is correct and Postgres is running")
            raise
        return

    # SQLite: Create tables using SQLAlchemy ORM models
    from .orm_models import Base as ORMBase

    # Check if this is a fresh database or existing
    with engine.connect() as conn:
        result = conn.exec_driver_sql(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='stories'"
        )
        is_fresh = len(result.fetchall()) == 0

    if is_fresh:
        logger.info("🔄 Creating database schema from ORM models...")
    else:
        logger.info("✅ Database exists, verifying schema...")

    # Create all tables from ORM models (uses CREATE TABLE IF NOT EXISTS)
    ORMBase.metadata.create_all(engine)

    if is_fresh:
        logger.info("✅ Database schema created successfully")

    # Migration: Add columns for existing databases (backward compatibility)
    with engine.begin() as conn:

        # Migration: Add columns if they don't exist (for existing databases)
        migration_columns = [
            # Items table migrations
            "ALTER TABLE items ADD COLUMN ai_summary TEXT;",
            "ALTER TABLE items ADD COLUMN ai_model TEXT;",
            "ALTER TABLE items ADD COLUMN ai_generated_at DATETIME;",
            "ALTER TABLE items ADD COLUMN content_hash TEXT;",
            "ALTER TABLE items ADD COLUMN structured_summary_json TEXT;",
            "ALTER TABLE items ADD COLUMN structured_summary_model TEXT;",
            "ALTER TABLE items ADD COLUMN structured_summary_content_hash TEXT;",
            "ALTER TABLE items ADD COLUMN structured_summary_generated_at DATETIME;",
            # New ranking and topic columns (v0.4.0)
            "ALTER TABLE items ADD COLUMN ranking_score REAL DEFAULT 0.0;",
            "ALTER TABLE items ADD COLUMN topic TEXT;",
            "ALTER TABLE items ADD COLUMN topic_confidence REAL DEFAULT 0.0;",
            "ALTER TABLE items ADD COLUMN source_weight REAL DEFAULT 1.0;",
            # Entity extraction columns (v0.6.1)
            "ALTER TABLE items ADD COLUMN entities_json TEXT;",
            "ALTER TABLE items ADD COLUMN entities_extracted_at DATETIME;",
            "ALTER TABLE items ADD COLUMN entities_model TEXT;",
            # Story quality scoring columns (v0.6.1)
            "ALTER TABLE stories ADD COLUMN importance_score REAL DEFAULT 0.5;",
            "ALTER TABLE stories ADD COLUMN freshness_score REAL DEFAULT 0.5;",
            "ALTER TABLE stories ADD COLUMN quality_score REAL DEFAULT 0.5;",
            # Story versioning columns (v0.6.3 - ADR 0004)
            "ALTER TABLE stories ADD COLUMN version INTEGER DEFAULT 1;",
            "ALTER TABLE stories ADD COLUMN previous_version_id INTEGER;",
            # Feeds table migrations (v0.5.3)
            "ALTER TABLE feeds ADD COLUMN name TEXT;",
            "ALTER TABLE feeds ADD COLUMN description TEXT;",
            "ALTER TABLE feeds ADD COLUMN category TEXT;",
            "ALTER TABLE feeds ADD COLUMN priority INTEGER DEFAULT 1;",
            "ALTER TABLE feeds ADD COLUMN last_fetch_at DATETIME;",
            "ALTER TABLE feeds ADD COLUMN last_error TEXT;",
            "ALTER TABLE feeds ADD COLUMN fetch_count INTEGER DEFAULT 0;",
            "ALTER TABLE feeds ADD COLUMN success_count INTEGER DEFAULT 0;",
            # Enhanced health monitoring (v0.5.3 polish)
            "ALTER TABLE feeds ADD COLUMN last_success_at DATETIME;",
            "ALTER TABLE feeds ADD COLUMN consecutive_failures INTEGER DEFAULT 0;",
            "ALTER TABLE feeds ADD COLUMN avg_response_time_ms INTEGER;",
            "ALTER TABLE feeds ADD COLUMN last_response_time_ms INTEGER;",
            "ALTER TABLE feeds ADD COLUMN health_score REAL DEFAULT 100.0;",
            "ALTER TABLE feeds ADD COLUMN last_modified_check DATETIME;",
            "ALTER TABLE feeds ADD COLUMN etag_check DATETIME;",
        ]

        for migration_sql in migration_columns:
            try:
                conn.exec_driver_sql(migration_sql)
            except:
                pass  # Column already exists
        # Create indexes for performance
        conn.exec_driver_sql(
            """
        CREATE INDEX IF NOT EXISTS idx_items_published ON items(published DESC);
        """
        )
        conn.exec_driver_sql(
            """
        CREATE INDEX IF NOT EXISTS idx_items_content_hash ON items(content_hash);
        """
        )
        conn.exec_driver_sql(
            """
        CREATE INDEX IF NOT EXISTS idx_structured_summary_cache
        ON items(structured_summary_content_hash, structured_summary_model);
        """
        )
        # New ranking and topic indexes (v0.4.0)
        conn.exec_driver_sql(
            """
        CREATE INDEX IF NOT EXISTS idx_items_ranking_score ON items(ranking_score DESC);
        """
        )
        conn.exec_driver_sql(
            """
        CREATE INDEX IF NOT EXISTS idx_items_topic ON items(topic);
        """
        )
        conn.exec_driver_sql(
            """
        CREATE INDEX IF NOT EXISTS idx_items_ranking_composite
        ON items(topic, ranking_score DESC, published DESC);
        """
        )
        conn.exec_driver_sql(
            """
        CREATE INDEX IF NOT EXISTS idx_feeds_health_score ON feeds(health_score DESC);
        """
        )
        # Story indexes (v0.5.0)
        conn.exec_driver_sql(
            """
        CREATE INDEX IF NOT EXISTS idx_stories_generated_at ON stories(generated_at DESC);
        """
        )
        conn.exec_driver_sql(
            """
        CREATE INDEX IF NOT EXISTS idx_stories_importance ON stories(importance_score DESC);
        """
        )
        conn.exec_driver_sql(
            """
        CREATE INDEX IF NOT EXISTS idx_stories_status ON stories(status);
        """
        )
        conn.exec_driver_sql(
            """
        CREATE INDEX IF NOT EXISTS idx_story_articles_story ON story_articles(story_id);
        """
        )
        conn.exec_driver_sql(
            """
        CREATE INDEX IF NOT EXISTS idx_story_articles_article ON story_articles(article_id);
        """
        )
        # Story versioning index (v0.6.3)
        conn.exec_driver_sql(
            """
        CREATE INDEX IF NOT EXISTS idx_stories_previous_version ON stories(previous_version_id);
        """
        )
        # Synthesis cache indexes (v0.6.3)
        conn.exec_driver_sql(
            """
        CREATE INDEX IF NOT EXISTS idx_synthesis_cache_key ON synthesis_cache(cache_key);
        """
        )
        conn.exec_driver_sql(
            """
        CREATE INDEX IF NOT EXISTS idx_synthesis_cache_expires ON synthesis_cache(expires_at);
        """
        )

        if is_fresh:
            logger.info("🎉 Database schema created successfully!")
        else:
            logger.info("✅ Database schema verification complete")

# sqlite db utils
from __future__ import annotations

import logging
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

logger = logging.getLogger(__name__)

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True, parents=True)
DB_PATH = DATA_DIR / "newsbrief.sqlite3"

engine = create_engine(
    f"sqlite:///{DB_PATH}", future=True, connect_args={"check_same_thread": False}
)
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
    Initialize database with all required tables and indexes.

    Handles both:
    - New databases: Creates all tables from scratch
    - Existing databases: Adds missing tables/columns (migration)

    Uses CREATE TABLE IF NOT EXISTS for idempotent migrations.
    """
    with engine.begin() as conn:
        # Check if this is a migration (stories table doesn't exist yet)
        result = conn.exec_driver_sql(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='stories'"
        )
        is_migration = len(result.fetchall()) == 0

        if is_migration:
            logger.info("🔄 Migrating database to v0.5.0 (story architecture)...")
        else:
            logger.info("✅ Database already has story tables, verifying schema...")
        conn.exec_driver_sql(
            """
        CREATE TABLE IF NOT EXISTS feeds (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          url TEXT UNIQUE NOT NULL,
          name TEXT,
          etag TEXT,
          last_modified TEXT,
          robots_allowed INTEGER DEFAULT 1,
          disabled INTEGER DEFAULT 0,
          created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
          updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
          last_fetch_at DATETIME,
          last_success_at DATETIME,
          fetch_count INTEGER DEFAULT 0,
          success_count INTEGER DEFAULT 0,
          consecutive_failures INTEGER DEFAULT 0,
          last_response_time_ms INTEGER,
          avg_response_time_ms INTEGER,
          last_error TEXT,
          health_score REAL DEFAULT 100.0
        );
        """
        )
        conn.exec_driver_sql(
            """
        CREATE TABLE IF NOT EXISTS items (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          feed_id INTEGER NOT NULL,
          title TEXT,
          url TEXT NOT NULL,
          url_hash TEXT NOT NULL UNIQUE,
          published DATETIME,
          author TEXT,
          summary TEXT,
          content TEXT,
          content_hash TEXT,
          ai_summary TEXT,
          ai_model TEXT,
          ai_generated_at DATETIME,
          structured_summary_json TEXT,
          structured_summary_model TEXT,
          structured_summary_content_hash TEXT,
          structured_summary_generated_at DATETIME,
          ranking_score REAL DEFAULT 0.0,
          topic TEXT,
          topic_confidence REAL DEFAULT 0.0,
          source_weight REAL DEFAULT 1.0,
          created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
          FOREIGN KEY(feed_id) REFERENCES feeds(id)
        );
        """
        )

        # Stories table - aggregated/synthesized news stories
        conn.exec_driver_sql(
            """
        CREATE TABLE IF NOT EXISTS stories (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          title TEXT NOT NULL,
          synthesis TEXT NOT NULL,
          key_points_json TEXT,
          why_it_matters TEXT,
          topics_json TEXT,
          entities_json TEXT,
          article_count INTEGER DEFAULT 0,
          importance_score REAL DEFAULT 0.0,
          freshness_score REAL DEFAULT 0.0,
          cluster_method TEXT,
          story_hash TEXT UNIQUE,
          generated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
          first_seen DATETIME,
          last_updated DATETIME,
          time_window_start DATETIME,
          time_window_end DATETIME,
          model TEXT,
          status TEXT DEFAULT 'active'
        );
        """
        )

        # Story-Article junction table
        conn.exec_driver_sql(
            """
        CREATE TABLE IF NOT EXISTS story_articles (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          story_id INTEGER NOT NULL,
          article_id INTEGER NOT NULL,
          relevance_score REAL DEFAULT 1.0,
          is_primary BOOLEAN DEFAULT 0,
          added_at DATETIME DEFAULT CURRENT_TIMESTAMP,
          FOREIGN KEY(story_id) REFERENCES stories(id) ON DELETE CASCADE,
          FOREIGN KEY(article_id) REFERENCES items(id) ON DELETE CASCADE,
          UNIQUE(story_id, article_id)
        );
        """
        )

        # Synthesis cache table (v0.6.3 - ADR 0003)
        conn.exec_driver_sql(
            """
        CREATE TABLE IF NOT EXISTS synthesis_cache (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          cache_key TEXT UNIQUE NOT NULL,
          article_ids_json TEXT NOT NULL,
          model TEXT NOT NULL,
          synthesis TEXT NOT NULL,
          key_points_json TEXT,
          why_it_matters TEXT,
          topics_json TEXT,
          entities_json TEXT,
          token_count_input INTEGER,
          token_count_output INTEGER,
          generation_time_ms INTEGER,
          created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
          expires_at DATETIME,
          invalidated_at DATETIME
        );
        """
        )

        if is_migration:
            logger.info("✅ Story tables created successfully")

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

        if is_migration:
            logger.info("🎉 Database migration to v0.5.0 complete!")
        else:
            logger.info("✅ Database schema verification complete")

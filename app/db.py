# sqlite db utils
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

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
    with engine.begin() as conn:
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
            "ALTER TABLE items ADD COLUMN ranking_score REAL DEFAULT 0.0;",
            "ALTER TABLE items ADD COLUMN topic TEXT;",
            "ALTER TABLE items ADD COLUMN topic_confidence REAL DEFAULT 0.0;",
            "ALTER TABLE items ADD COLUMN source_weight REAL DEFAULT 1.0;",
            # Feeds table migrations
            "ALTER TABLE feeds ADD COLUMN name TEXT;",
            "ALTER TABLE feeds ADD COLUMN last_fetch_at DATETIME;",
            "ALTER TABLE feeds ADD COLUMN last_success_at DATETIME;",
            "ALTER TABLE feeds ADD COLUMN fetch_count INTEGER DEFAULT 0;",
            "ALTER TABLE feeds ADD COLUMN success_count INTEGER DEFAULT 0;",
            "ALTER TABLE feeds ADD COLUMN consecutive_failures INTEGER DEFAULT 0;",
            "ALTER TABLE feeds ADD COLUMN last_response_time_ms INTEGER;",
            "ALTER TABLE feeds ADD COLUMN avg_response_time_ms INTEGER;",
            "ALTER TABLE feeds ADD COLUMN last_error TEXT;",
            "ALTER TABLE feeds ADD COLUMN health_score REAL DEFAULT 100.0;",
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
        CREATE INDEX IF NOT EXISTS idx_feeds_health_score ON feeds(health_score DESC);
        """
        )

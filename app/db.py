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
          etag TEXT,
          last_modified TEXT,
          robots_allowed INTEGER DEFAULT 1,
          disabled INTEGER DEFAULT 0,
          created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
          updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
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
          created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
          FOREIGN KEY(feed_id) REFERENCES feeds(id)
        );
        """
        )

        # Migration: Add AI summary columns if they don't exist
        migration_columns = [
            "ALTER TABLE items ADD COLUMN ai_summary TEXT;",
            "ALTER TABLE items ADD COLUMN ai_model TEXT;",
            "ALTER TABLE items ADD COLUMN ai_generated_at DATETIME;",
            # New structured summary columns
            "ALTER TABLE items ADD COLUMN content_hash TEXT;",
            "ALTER TABLE items ADD COLUMN structured_summary_json TEXT;",
            "ALTER TABLE items ADD COLUMN structured_summary_model TEXT;",
            "ALTER TABLE items ADD COLUMN structured_summary_content_hash TEXT;",
            "ALTER TABLE items ADD COLUMN structured_summary_generated_at DATETIME;",
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

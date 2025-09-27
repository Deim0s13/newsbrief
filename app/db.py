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
    f"sqlite:///{DB_PATH}",
    future=True,
    connect_args={"check_same_thread": False}
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
        conn.exec_driver_sql("""
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
        """)
        conn.exec_driver_sql("""
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
          created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
          FOREIGN KEY(feed_id) REFERENCES feeds(id)
        );
        """)
        conn.exec_driver_sql("""
        CREATE INDEX IF NOT EXISTS idx_items_published ON items(published DESC);
        """)
#!/usr/bin/env python3
"""
Seed dev database with real RSS feeds.

Wipes existing feeds (and cascaded items/stories) then imports
data/feeds.opml and does an immediate feed refresh.

Usage:
    python scripts/seed_dev_feeds.py
    make seed-dev
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql://newsbrief:newsbrief_dev@localhost:5433/newsbrief",
)

from app.db import session_scope
from app.feeds import fetch_and_store, import_opml_content
from sqlalchemy import text


def clear_feeds(session) -> int:
    count = session.execute(text("SELECT COUNT(*) FROM feeds")).scalar()
    if count:
        session.execute(text("DELETE FROM story_articles"))
        session.execute(text("DELETE FROM stories"))
        session.execute(text("DELETE FROM items"))
        session.execute(text("DELETE FROM feeds"))
        session.execute(text("ALTER SEQUENCE feeds_id_seq RESTART WITH 1"))
    return count


def load_opml() -> str:
    opml_path = os.path.join(os.path.dirname(__file__), "..", "data", "feeds.opml")
    with open(opml_path, "r", encoding="utf-8") as f:
        return f.read()


def run():
    print("Clearing existing feeds...")
    with session_scope() as session:
        removed = clear_feeds(session)
        session.commit()
    print(f"  Removed {removed} feed(s) (items/stories cascaded)")

    print("Importing data/feeds.opml...")
    opml_content = load_opml()
    result = import_opml_content(opml_content, validate=False)
    added = result.get("feeds_added", 0)
    skipped = result.get("feeds_skipped", 0)
    failed = result.get("feeds_failed", 0)
    print(f"  Added: {added}  Skipped: {skipped}  Failed: {failed}")

    if added == 0:
        print("WARNING: No feeds added — check data/feeds.opml")
        return

    print("Fetching articles from all feeds (this may take a minute)...")
    stats = fetch_and_store()
    print(f"  Items fetched: {stats.total_items}")
    print(f"  Feeds processed: {stats.total_feeds_processed}")
    if stats.feeds_error:
        print(f"  Feeds with errors: {stats.feeds_error}")

    print("Done — dev DB seeded with real articles")


if __name__ == "__main__":
    run()

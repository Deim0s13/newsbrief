"""
Backfill the relational entity graph from already-cached LLM extractions
(#199, ADR-0023, v0.9.0).

For every ``items`` row with a cached ``entities_json`` (v0.6.1 per-article
LLM extraction) that hasn't been normalized yet, parses the cache and
upserts into ``entities`` / ``entity_mentions`` (see
``app/entity_normalization.py``). No LLM calls are made -- this is a pure
one-time normalization pass over data that's already been extracted; items
without a cached extraction are skipped (they'll be normalized go-forward
the next time they're processed during clustering).

CLI entry: ``python -m app.cli entity-backfill``.
"""

from __future__ import annotations

import argparse
import logging
import sys
from typing import Callable, Optional, Sequence, Tuple

from sqlalchemy import text
from sqlalchemy.orm import Session

from .embed_backfill import resolve_database_url_for_cli
from .entities import ExtractedEntities
from .entity_normalization import normalize_and_store_entities
from .orm_models import Item

logger = logging.getLogger(__name__)


def _parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="NewsBrief maintenance CLI")
    sub = p.add_subparsers(dest="command", required=True)

    b = sub.add_parser(
        "entity-backfill",
        help=(
            "Normalize cached entity extractions (items.entities_json) into "
            "the entities/entity_mentions tables"
        ),
    )
    b.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the pending count and exit without writing",
    )
    b.add_argument(
        "--batch-size",
        type=int,
        default=200,
        metavar="N",
        help="Rows to fetch per DB batch (default: 200)",
    )
    b.add_argument(
        "--limit",
        type=int,
        default=None,
        metavar="N",
        help="Max items to process (for testing)",
    )
    b.add_argument(
        "--database-url",
        type=str,
        default=None,
        metavar="URL",
        help="PostgreSQL URL (otherwise use DATABASE_URL env or --dev)",
    )
    b.add_argument(
        "--dev",
        action="store_true",
        help="Use local dev DB if DATABASE_URL is unset (same default as embed-backfill)",
    )
    return p.parse_args(argv)


def _pending_count(session: Session) -> int:
    row = session.execute(
        text(
            """
            SELECT COUNT(*) FROM items i
            WHERE i.entities_json IS NOT NULL
            AND NOT EXISTS (
                SELECT 1 FROM entity_mentions em WHERE em.article_id = i.id
            )
            """
        )
    ).first()
    return int(row[0]) if row else 0


def _link_mentions_to_existing_stories(session: Session) -> int:
    """
    Backfill story_id onto any entity_mentions left NULL, for articles that
    are already linked to a story via story_articles. Run once at the end
    of the backfill (rather than per-item) since it's a single bulk UPDATE.
    """
    result = session.execute(
        text(
            """
            UPDATE entity_mentions em
            SET story_id = sa.story_id
            FROM story_articles sa
            WHERE em.article_id = sa.article_id AND em.story_id IS NULL
            """
        )
    )
    return result.rowcount or 0  # type: ignore[attr-defined]


def _run_backfill(
    session_factory: Callable[[], Session],
    *,
    batch_size: int,
    limit: Optional[int],
    total_pending: int,
) -> Tuple[int, int, int]:
    """Returns (items_processed, new_mentions, errors)."""
    processed = new_mentions = errors = 0
    batch_size = max(1, batch_size)
    last_id = 0

    while True:
        if limit is not None and processed >= limit:
            break
        session = session_factory()
        try:
            rows = (
                session.query(Item)
                .filter(
                    Item.entities_json.isnot(None),
                    Item.id > last_id,
                    text(
                        "NOT EXISTS (SELECT 1 FROM entity_mentions em "
                        "WHERE em.article_id = items.id)"
                    ),
                )
                .order_by(Item.id)
                .limit(batch_size)
                .all()
            )
            if not rows:
                break
            last_id = max(int(r.id) for r in rows)

            if limit is not None:
                cap = limit - processed
                if cap <= 0:
                    break
                rows = rows[:cap]

            for row in rows:
                try:
                    entities = ExtractedEntities.from_json_string(
                        str(row.entities_json)
                    )
                    added = normalize_and_store_entities(session, int(row.id), entities)
                    new_mentions += added
                    processed += 1
                    logger.info(
                        "entity-backfill %s/%s (item id=%s, +%s mentions)",
                        processed,
                        total_pending if total_pending else "?",
                        row.id,
                        added,
                    )
                except Exception as e:
                    errors += 1
                    logger.error("Entity backfill failed for item %s: %s", row.id, e)
                    session.rollback()
            session.commit()
        finally:
            session.close()

    return processed, new_mentions, errors


def main_entity_backfill(args: argparse.Namespace) -> int:
    from .db import SessionLocal

    session = SessionLocal()
    try:
        pending = _pending_count(session)
    finally:
        session.close()

    logger.info("entity-backfill pending: %s items", pending)

    if args.dry_run:
        print(f"items pending normalization: {pending}")
        return 0

    def factory() -> Session:
        return SessionLocal()

    processed, new_mentions, errors = _run_backfill(
        factory,
        batch_size=args.batch_size,
        limit=args.limit,
        total_pending=pending,
    )

    session = SessionLocal()
    try:
        linked = _link_mentions_to_existing_stories(session)
        session.commit()
    finally:
        session.close()

    logger.info(
        "entity-backfill finished: items_processed=%s new_mentions=%s "
        "story_links_backfilled=%s errors=%s",
        processed,
        new_mentions,
        linked,
        errors,
    )
    return 1 if errors else 0


def main_cli(argv: Optional[Sequence[str]] = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s %(message)s",
    )
    args = _parse_args(argv)
    if args.command == "entity-backfill":
        early = resolve_database_url_for_cli(args)
        if early is not None:
            return early
        return main_entity_backfill(args)
    return 2


if __name__ == "__main__":
    sys.exit(main_cli())

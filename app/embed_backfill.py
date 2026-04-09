"""
Backfill embeddings for items and stories missing vectors (#254).

CLI entry: ``python -m app.cli embed-backfill``.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from datetime import UTC, datetime
from typing import Callable, List, Optional, Sequence, Tuple

from sqlalchemy.orm import Session

from .embedding_service import EmbeddingService, create_embedding_service_from_settings
from .item_embeddings import (
    build_item_embed_text,
    is_embedding_generation_enabled,
    persist_item_embedding,
)
from .models import StructuredSummary
from .orm_models import Item, Story
from .story_embeddings import build_story_embed_text, persist_story_embedding

logger = logging.getLogger(__name__)

# Same URL as Makefile ``make dev`` / ``make migrate-dev`` (Podman Postgres on 5433).
DEFAULT_DEV_DATABASE_URL = (
    "postgresql://newsbrief:newsbrief_dev@127.0.0.1:5433/newsbrief"
)


def resolve_database_url_for_cli(args: argparse.Namespace) -> Optional[int]:
    """
    Ensure ``os.environ['DATABASE_URL']`` is set before ``app.db`` is imported.

    Returns an exit code (e.g. 2) when the URL cannot be resolved; ``None`` if ok.
    """
    if getattr(args, "database_url", None):
        url = str(args.database_url).strip()
        if not url:
            logger.error("--database-url must be non-empty")
            return 2
        os.environ["DATABASE_URL"] = url
        return None
    if os.environ.get("DATABASE_URL", "").strip():
        return None
    if getattr(args, "dev", False):
        os.environ["DATABASE_URL"] = DEFAULT_DEV_DATABASE_URL
        logger.warning(
            "DATABASE_URL not set; using --dev default %s (see: make db-up)",
            DEFAULT_DEV_DATABASE_URL,
        )
        return None
    sys.stderr.write(
        "embed-backfill: DATABASE_URL is not set.\n"
        "  export DATABASE_URL='postgresql://newsbrief:newsbrief_dev@127.0.0.1:5433/newsbrief'\n"
        "  or run with:  --dev          (same URL as Makefile `make dev`)\n"
        "  or run with:  --database-url postgresql://...\n"
    )
    return 2


def item_embed_text_from_orm(item: Item) -> Optional[str]:
    """Same preference order as live article embedding (#252)."""
    title = item.title  # type: ignore[assignment]
    ss = None
    if item.structured_summary_json and item.structured_summary_model:  # type: ignore[truthy-bool]
        try:
            ss = StructuredSummary.from_json_string(
                str(item.structured_summary_json),
                str(item.structured_summary_content_hash or ""),
                str(item.structured_summary_model or ""),
                item.structured_summary_generated_at or datetime.now(UTC),
            )
        except Exception as e:
            logger.debug("Structured summary parse failed for item %s: %s", item.id, e)
            ss = None
    if ss is not None:
        return build_item_embed_text(title, structured_summary=ss)
    return build_item_embed_text(
        title,
        ai_summary=item.ai_summary,  # type: ignore[arg-type]
        feed_summary=item.summary,  # type: ignore[arg-type]
    )


def _parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="NewsBrief maintenance CLI")
    sub = p.add_subparsers(dest="command", required=True)

    b = sub.add_parser(
        "embed-backfill",
        help="Generate embeddings for items/stories with embedding IS NULL",
    )
    b.add_argument(
        "--articles-only",
        action="store_true",
        help="Only backfill article (items) embeddings",
    )
    b.add_argument(
        "--stories-only",
        action="store_true",
        help="Only backfill story embeddings",
    )
    b.add_argument(
        "--dry-run",
        action="store_true",
        help="Print counts and exit without calling Ollama or writing",
    )
    b.add_argument(
        "--batch-size",
        type=int,
        default=50,
        metavar="N",
        help="Rows to fetch per DB batch (default: 50)",
    )
    b.add_argument(
        "--sleep-seconds",
        type=float,
        default=0.0,
        metavar="S",
        help="Pause between successful batches (default: 0)",
    )
    b.add_argument(
        "--limit",
        type=int,
        default=None,
        metavar="N",
        help="Max successfully embedded rows per entity type (for testing)",
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
        help=f"Use local dev DB if DATABASE_URL is unset ({DEFAULT_DEV_DATABASE_URL})",
    )
    return p.parse_args(argv)


async def _embed_batch_or_fallback(
    svc: EmbeddingService,
    texts: List[str],
) -> List[List[float]]:
    try:
        return await svc.embed_texts(texts, batch_size=len(texts))
    except Exception as e:
        logger.warning("Batch embed failed (%s); falling back to single requests", e)
        out: List[List[float]] = []
        for t in texts:
            out.append(await svc.embed_text(t))
        return out


async def _run_article_backfill(
    session_factory: Callable[[], Session],
    svc: EmbeddingService,
    *,
    batch_size: int,
    sleep_s: float,
    limit: Optional[int],
    total_pending: int,
) -> Tuple[int, int, int]:
    """Returns (embedded_ok, skipped_no_text, batch_errors)."""
    done = skipped = errors = 0
    batch_size = max(1, batch_size)
    last_id = 0

    while True:
        if limit is not None and done >= limit:
            break
        session = session_factory()
        try:
            q = (
                session.query(Item)
                .filter(Item.embedding.is_(None), Item.id > last_id)
                .order_by(Item.id)
                .limit(batch_size)
            )
            rows = q.all()
            if not rows:
                break
            last_id = max(int(r.id) for r in rows)

            batch_items: List[Item] = []
            texts: List[str] = []
            for row in rows:
                et = item_embed_text_from_orm(row)
                if not et:
                    skipped += 1
                    logger.warning(
                        "Skipping item %s: no embeddable summary text", row.id
                    )
                    continue
                batch_items.append(row)
                texts.append(et)

            if limit is not None:
                cap = limit - done
                if cap <= 0:
                    break
                batch_items = batch_items[:cap]
                texts = texts[:cap]

            if not batch_items:
                session.commit()
                continue

            try:
                vectors = await _embed_batch_or_fallback(svc, texts)
            except Exception as e:
                errors += len(batch_items)
                logger.error("Embedding failed for item batch: %s", e, exc_info=True)
                session.rollback()
                continue

            info = svc.get_model_info()
            for row, vec in zip(batch_items, vectors):
                persist_item_embedding(
                    session,
                    int(row.id),
                    vec,
                    embedding_model=str(info.get("model", "")),
                    embedding_version=str(info.get("version", "")),
                )
                done += 1
                logger.info(
                    "embed-backfill articles %s/%s (item id=%s)",
                    done,
                    total_pending if total_pending else "?",
                    row.id,
                )
            session.commit()
        finally:
            session.close()

        if sleep_s > 0:
            await asyncio.sleep(sleep_s)

    return done, skipped, errors


async def _run_story_backfill(
    session_factory: Callable[[], Session],
    svc: EmbeddingService,
    *,
    batch_size: int,
    sleep_s: float,
    limit: Optional[int],
    total_pending: int,
) -> Tuple[int, int, int]:
    done = skipped = errors = 0
    batch_size = max(1, batch_size)
    last_id = 0

    while True:
        if limit is not None and done >= limit:
            break
        session = session_factory()
        try:
            q = (
                session.query(Story)
                .filter(Story.embedding.is_(None), Story.id > last_id)
                .order_by(Story.id)
                .limit(batch_size)
            )
            rows = q.all()
            if not rows:
                break
            last_id = max(int(r.id) for r in rows)

            batch_stories: List[Story] = []
            texts: List[str] = []
            for row in rows:
                et = build_story_embed_text(row.title, row.synthesis)  # type: ignore[arg-type]
                if not et:
                    skipped += 1
                    logger.warning("Skipping story %s: no embeddable text", row.id)
                    continue
                batch_stories.append(row)
                texts.append(et)

            if limit is not None:
                cap = limit - done
                if cap <= 0:
                    break
                batch_stories = batch_stories[:cap]
                texts = texts[:cap]

            if not batch_stories:
                session.commit()
                continue

            try:
                vectors = await _embed_batch_or_fallback(svc, texts)
            except Exception as e:
                errors += len(batch_stories)
                logger.error("Embedding failed for story batch: %s", e, exc_info=True)
                session.rollback()
                continue

            info = svc.get_model_info()
            for row, vec in zip(batch_stories, vectors):
                persist_story_embedding(
                    row,
                    vec,
                    embedding_model=str(info.get("model", "")),
                    embedding_version=str(info.get("version", "")),
                )
                done += 1
                logger.info(
                    "embed-backfill stories %s/%s (story id=%s)",
                    done,
                    total_pending if total_pending else "?",
                    row.id,
                )
            session.commit()
        finally:
            session.close()

        if sleep_s > 0:
            await asyncio.sleep(sleep_s)

    return done, skipped, errors


async def async_main_embed_backfill(args: argparse.Namespace) -> int:
    if args.articles_only and args.stories_only:
        logger.error("Use only one of --articles-only and --stories-only")
        return 2

    do_articles = not args.stories_only
    do_stories = not args.articles_only

    if not is_embedding_generation_enabled():
        logger.error(
            "Embedding generation is disabled "
            "(NEWSBRIEF_EMBEDDING_ENABLED or model_config embedding.enabled). "
            "Enable it to run backfill."
        )
        return 1

    from .db import SessionLocal

    session = SessionLocal()
    try:
        ap = (
            session.query(Item).filter(Item.embedding.is_(None)).count()
            if do_articles
            else 0
        )
        sp = (
            session.query(Story).filter(Story.embedding.is_(None)).count()
            if do_stories
            else 0
        )
    finally:
        session.close()

    logger.info("embed-backfill pending: articles=%s stories=%s", ap, sp)

    if args.dry_run:
        if do_articles:
            print(f"articles: {ap} rows with embedding IS NULL")
        if do_stories:
            print(f"stories: {sp} rows with embedding IS NULL")
        return 0

    svc = create_embedding_service_from_settings()

    def factory() -> Session:
        return SessionLocal()

    exit_code = 0
    if do_articles and ap:
        d, sk, er = await _run_article_backfill(
            factory,
            svc,
            batch_size=args.batch_size,
            sleep_s=args.sleep_seconds,
            limit=args.limit,
            total_pending=ap,
        )
        logger.info(
            "Articles finished: embedded=%s skipped_no_text=%s batch_errors=%s",
            d,
            sk,
            er,
        )
        if er:
            exit_code = 1

    if do_stories and sp:
        d, sk, er = await _run_story_backfill(
            factory,
            svc,
            batch_size=args.batch_size,
            sleep_s=args.sleep_seconds,
            limit=args.limit,
            total_pending=sp,
        )
        logger.info(
            "Stories finished: embedded=%s skipped_no_text=%s batch_errors=%s",
            d,
            sk,
            er,
        )
        if er:
            exit_code = 1

    return exit_code


def main_cli(argv: Optional[Sequence[str]] = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s %(message)s",
    )
    args = _parse_args(argv)
    if args.command == "embed-backfill":
        early = resolve_database_url_for_cli(args)
        if early is not None:
            return early
        return asyncio.run(async_main_embed_backfill(args))
    return 2


if __name__ == "__main__":
    sys.exit(main_cli())

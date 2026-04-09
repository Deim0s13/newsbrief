"""Tests for app.embed_backfill (#254)."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.embed_backfill import (
    DEFAULT_DEV_DATABASE_URL,
    _embed_batch_or_fallback,
    _parse_args,
    async_main_embed_backfill,
    item_embed_text_from_orm,
    resolve_database_url_for_cli,
)


def test_item_embed_text_ai_summary() -> None:
    item = SimpleNamespace(
        id=1,
        title="Headline",
        structured_summary_json=None,
        structured_summary_model=None,
        structured_summary_content_hash=None,
        structured_summary_generated_at=None,
        ai_summary="AI body here.",
        summary=None,
    )
    t = item_embed_text_from_orm(item)  # type: ignore[arg-type]
    assert t == "Headline\n\nAI body here."


def test_item_embed_text_structured() -> None:
    payload = {
        "bullets": ["a", "b"],
        "why_it_matters": "This matters enough for validation rules here.",
        "tags": ["x"],
        "is_chunked": False,
        "chunk_count": 1,
        "total_tokens": 1,
        "processing_method": "direct",
    }
    item = SimpleNamespace(
        id=2,
        title="T2",
        structured_summary_json=json.dumps(payload),
        structured_summary_model="m",
        structured_summary_content_hash="h",
        structured_summary_generated_at=datetime.now(UTC),
        ai_summary=None,
        summary=None,
    )
    t = item_embed_text_from_orm(item)  # type: ignore[arg-type]
    assert t.startswith("T2\n\n")
    assert "- a" in t
    assert "validation rules" in t


def test_parse_args_embed_backfill() -> None:
    args = _parse_args(["embed-backfill", "--dry-run", "--batch-size", "10"])
    assert args.command == "embed-backfill"
    assert args.dry_run is True
    assert args.batch_size == 10


def test_resolve_database_url_prefers_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    args = _parse_args(
        [
            "embed-backfill",
            "--database-url",
            "postgresql://a:b@host:5432/db",
            "--dry-run",
        ]
    )
    assert resolve_database_url_for_cli(args) is None
    assert os.environ["DATABASE_URL"] == "postgresql://a:b@host:5432/db"


def test_resolve_database_url_dev_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    args = _parse_args(["embed-backfill", "--dev", "--dry-run"])
    assert resolve_database_url_for_cli(args) is None
    assert os.environ["DATABASE_URL"] == DEFAULT_DEV_DATABASE_URL


def test_resolve_database_url_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    args = _parse_args(["embed-backfill", "--dry-run"])
    assert resolve_database_url_for_cli(args) == 2


@pytest.mark.asyncio
async def test_embed_batch_or_fallback_on_batch_failure() -> None:
    svc = MagicMock()
    svc.embed_texts = AsyncMock(side_effect=RuntimeError("rate limit"))
    svc.embed_text = AsyncMock(return_value=[0.1, 0.2])

    out = await _embed_batch_or_fallback(svc, ["hello", "world"])
    assert len(out) == 2
    assert svc.embed_text.call_count == 2


@pytest.mark.asyncio
async def test_async_main_disabled_embedding(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@127.0.0.1:5432/test")
    monkeypatch.setenv("NEWSBRIEF_EMBEDDING_ENABLED", "0")
    ns = SimpleNamespace(
        command="embed-backfill",
        articles_only=False,
        stories_only=False,
        dry_run=False,
        batch_size=50,
        sleep_seconds=0.0,
        limit=None,
    )
    code = await async_main_embed_backfill(ns)
    assert code == 1


@pytest.mark.asyncio
async def test_async_main_both_only_flags() -> None:
    ns = SimpleNamespace(
        command="embed-backfill",
        articles_only=True,
        stories_only=True,
        dry_run=True,
        batch_size=50,
        sleep_seconds=0.0,
        limit=None,
    )
    code = await async_main_embed_backfill(ns)
    assert code == 2

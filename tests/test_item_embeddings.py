"""Tests for app.item_embeddings (#252)."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.item_embeddings import (
    build_item_embed_text,
    is_embedding_generation_enabled,
    maybe_embed_item_after_summary,
)
from app.models import StructuredSummary


def test_is_embedding_generation_enabled_env_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NEWSBRIEF_EMBEDDING_ENABLED", "false")
    assert is_embedding_generation_enabled() is False


def test_is_embedding_generation_enabled_env_on(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NEWSBRIEF_EMBEDDING_ENABLED", "true")
    assert is_embedding_generation_enabled() is True


def test_build_item_embed_text_structured() -> None:
    ss = StructuredSummary(
        bullets=["a", "b"],
        why_it_matters="significance here ok",
        tags=["t1"],
        content_hash="h",
        model="m",
        generated_at=datetime.now(timezone.utc),
    )
    t = build_item_embed_text("Title", structured_summary=ss)
    assert t.startswith("Title\n\n")
    assert "- a" in t
    assert "significance here ok" in t


def test_build_item_embed_text_plain() -> None:
    assert build_item_embed_text("Hi", ai_summary="plain body") == "Hi\n\nplain body"


def test_build_item_embed_text_none() -> None:
    assert build_item_embed_text("x", feed_summary=None, ai_summary=None) is None


def test_maybe_embed_skips_cache_hit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.item_embeddings.asyncio.run", MagicMock())
    session = MagicMock()
    r = SimpleNamespace(
        summary="s",
        model="m",
        success=True,
        cache_hit=True,
        structured_summary=None,
        content_hash=None,
    )
    maybe_embed_item_after_summary(
        session, 1, "T", r, use_structured=False, feed_summary=None
    )
    session.get.assert_not_called()


def test_maybe_embed_persists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    vec = [0.001 * (i % 7) for i in range(768)]

    class FakeSvc:
        async def embed_text(self, text: str) -> list[float]:
            return vec

        def get_model_info(self) -> dict:
            return {"model": "nomic", "version": "1.0"}

    monkeypatch.setattr(
        "app.item_embeddings.create_embedding_service_from_settings",
        lambda: FakeSvc(),
    )
    monkeypatch.setenv("NEWSBRIEF_EMBEDDING_ENABLED", "true")

    item = MagicMock()
    session = MagicMock()
    session.get = MagicMock(return_value=item)

    ss = StructuredSummary(
        bullets=["pt"],
        why_it_matters="significance ok",
        tags=["t"],
        content_hash="h",
        model="lm",
        generated_at=datetime.now(timezone.utc),
    )
    r = SimpleNamespace(
        summary="{}",
        model="lm",
        success=True,
        structured_summary=ss,
        cache_hit=False,
        content_hash="h",
    )
    maybe_embed_item_after_summary(
        session, 42, "Headline", r, use_structured=True, feed_summary=None
    )
    session.get.assert_called_once()
    assert item.embedding == vec
    assert item.embedding_model == "nomic"
    assert item.embedding_version == "1.0"
    assert item.embedded_at is not None

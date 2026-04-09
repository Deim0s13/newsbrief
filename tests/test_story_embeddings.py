"""Tests for app.story_embeddings (#253)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.orm_models import Story
from app.story_embeddings import (
    build_story_embed_text,
    maybe_embed_story_after_synthesis,
    persist_story_embedding,
)


def test_build_story_embed_text_both() -> None:
    t = build_story_embed_text("My title", "Body synthesis here.")
    assert t == "My title\n\nBody synthesis here."


def test_build_story_embed_text_title_only() -> None:
    assert build_story_embed_text("Only title", "") == "Only title"
    assert build_story_embed_text("Only title", None) == "Only title"


def test_build_story_embed_text_synthesis_only() -> None:
    assert build_story_embed_text("", "Just synthesis") == "Just synthesis"


def test_build_story_embed_text_none() -> None:
    assert build_story_embed_text("", "") is None
    assert build_story_embed_text(None, None) is None


def test_maybe_embed_skips_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEWSBRIEF_EMBEDDING_ENABLED", "false")
    monkeypatch.setattr("app.story_embeddings.asyncio.run", MagicMock())
    session = MagicMock()
    story = Story(title="T", synthesis="S")
    story.id = 1
    maybe_embed_story_after_synthesis(session, story)  # type: ignore[arg-type]


def test_maybe_embed_skips_no_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEWSBRIEF_EMBEDDING_ENABLED", "true")
    monkeypatch.setattr("app.story_embeddings.asyncio.run", MagicMock())
    session = MagicMock()
    story = Story(title="T", synthesis="S")
    story.id = None
    maybe_embed_story_after_synthesis(session, story)  # type: ignore[arg-type]


def test_maybe_embed_persists(monkeypatch: pytest.MonkeyPatch) -> None:
    vec = [0.001 * (i % 7) for i in range(768)]

    class FakeSvc:
        async def embed_text(self, text: str) -> list[float]:
            assert "Hello" in text
            assert "World" in text
            return vec

        def get_model_info(self) -> dict:
            return {"model": "nomic-embed-text", "version": "1.0"}

    monkeypatch.setattr(
        "app.story_embeddings.create_embedding_service_from_settings",
        lambda: FakeSvc(),
    )
    monkeypatch.setenv("NEWSBRIEF_EMBEDDING_ENABLED", "true")

    session = MagicMock()
    story = Story(title="Hello", synthesis="World")
    story.id = 99
    maybe_embed_story_after_synthesis(session, story)  # type: ignore[arg-type]
    assert story.embedding == vec
    assert story.embedding_model == "nomic-embed-text"
    assert story.embedding_version == "1.0"
    assert story.embedded_at is not None


def test_persist_story_embedding() -> None:
    vec = [0.01] * 768
    story = Story(title="a", synthesis="b")
    persist_story_embedding(
        story,
        vec,
        embedding_model="m",
        embedding_version="v",
    )
    assert story.embedding == vec
    assert story.embedding_model == "m"
    assert story.embedding_version == "v"
    assert story.embedded_at is not None

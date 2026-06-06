"""Tests for app.embedding_service (#251)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.embedding_service import (
    EmbeddingService,
    create_embedding_service_from_settings,
)


def _vec768() -> list[float]:
    return [0.01 * (i % 10) for i in range(768)]


def _async_client_cm(mock_post: AsyncMock) -> MagicMock:
    inst = MagicMock()
    inst.post = mock_post
    acm = MagicMock()
    acm.__aenter__ = AsyncMock(return_value=inst)
    acm.__aexit__ = AsyncMock(return_value=None)
    return acm


@pytest.mark.asyncio
async def test_embed_text_success() -> None:
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json = MagicMock(return_value={"embedding": _vec768()})
    mock_post = AsyncMock(return_value=mock_response)
    with patch(
        "app.embedding_service.httpx.AsyncClient",
        return_value=_async_client_cm(mock_post),
    ):
        svc = EmbeddingService(
            base_url="http://ollama:11434",
            model="nomic-embed-text",
            dimensions=768,
            model_version="1.0",
            max_retries=1,
        )
        out = await svc.embed_text("hello world")
        assert len(out) == 768
        mock_post.assert_awaited_once()
        assert mock_post.await_args[0][0] == "http://ollama:11434/api/embeddings"
        assert mock_post.await_args[1]["json"] == {
            "model": "nomic-embed-text",
            "prompt": "hello world",
        }


@pytest.mark.asyncio
async def test_embed_text_empty_raises() -> None:
    svc = EmbeddingService(dimensions=768, max_retries=1)
    with pytest.raises(ValueError, match="non-empty"):
        await svc.embed_text("   ")


@pytest.mark.asyncio
async def test_embed_text_wrong_length_raises() -> None:
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json = MagicMock(return_value={"embedding": [0.1, 0.2]})
    mock_post = AsyncMock(return_value=mock_response)
    with patch(
        "app.embedding_service.httpx.AsyncClient",
        return_value=_async_client_cm(mock_post),
    ):
        svc = EmbeddingService(dimensions=768, max_retries=1)
        with pytest.raises(ValueError, match="embedding length"):
            await svc.embed_text("x")


@pytest.mark.asyncio
async def test_embed_texts_batches() -> None:
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json = MagicMock(return_value={"embedding": _vec768()})
    mock_post = AsyncMock(return_value=mock_response)
    with patch(
        "app.embedding_service.httpx.AsyncClient",
        return_value=_async_client_cm(mock_post),
    ):
        svc = EmbeddingService(dimensions=768, max_retries=1, max_concurrent_requests=8)
        out = await svc.embed_texts(["a", "b"], batch_size=1)
        assert len(out) == 2
        assert len(out[0]) == 768
        assert mock_post.await_count == 2


@pytest.mark.asyncio
async def test_embed_retries_then_success() -> None:
    ok = MagicMock()
    ok.raise_for_status = MagicMock()
    ok.json = MagicMock(return_value={"embedding": _vec768()})
    fail_resp = MagicMock()
    fail_resp.raise_for_status = MagicMock(side_effect=httpx.HTTPError("boom"))

    mock_post = AsyncMock(side_effect=[fail_resp, ok])
    with patch(
        "app.embedding_service.httpx.AsyncClient",
        return_value=_async_client_cm(mock_post),
    ):
        with patch("app.embedding_service.asyncio.sleep", new_callable=AsyncMock):
            svc = EmbeddingService(dimensions=768, max_retries=3)
            out = await svc.embed_text("x")
            assert len(out) == 768
            assert mock_post.await_count == 2


def test_get_model_info() -> None:
    svc = EmbeddingService(model="m1", dimensions=768, model_version="mv")
    assert svc.get_model_info() == {
        "model": "m1",
        "dimensions": 768,
        "version": "mv",
    }


def test_create_embedding_service_from_settings_dimension_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app import settings as settings_mod

    class Fake:
        def get_embedding_profile_config(self) -> dict:
            return {
                "profile_id": "fast",
                "model": "x",
                "dimensions": 1024,
                "model_version": "1",
            }

    monkeypatch.setattr(settings_mod, "get_settings_service", lambda: Fake())
    with pytest.raises(ValueError, match="must match"):
        create_embedding_service_from_settings()


def test_create_embedding_service_from_settings_ok(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app import settings as settings_mod

    class Fake:
        def get_embedding_profile_config(self) -> dict:
            return {
                "profile_id": "fast",
                "model": "nomic-embed-text",
                "dimensions": 768,
                "model_version": "2",
            }

    monkeypatch.setattr(settings_mod, "get_settings_service", lambda: Fake())
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://embed-host:11434")
    svc = create_embedding_service_from_settings()
    assert svc.base_url == "http://embed-host:11434"
    assert svc.model == "nomic-embed-text"
    assert svc.dimensions == 768
    assert svc.model_version == "2"

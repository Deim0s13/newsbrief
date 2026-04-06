"""
Async embedding generation via Ollama `/api/embeddings` (#251).

Configured through ``data/model_config.json`` (embedding section) and optional
``NEWSBRIEF_EMBEDDING_MODEL`` / ``NEWSBRIEF_EMBEDDING_DIMENSIONS``. Vector
width must match ``app.orm_models._EMBEDDING_DIMENSIONS`` (pgvector column).
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import TYPE_CHECKING, Any, List, Optional

import httpx

from .orm_models import _EMBEDDING_DIMENSIONS

if TYPE_CHECKING:
    from .settings import SettingsService

logger = logging.getLogger(__name__)

DEFAULT_OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
DEFAULT_TIMEOUT = 120.0
DEFAULT_RETRIES = 3
DEFAULT_MAX_CONCURRENT = 4


class EmbeddingService:
    """Generate dense embeddings using a local Ollama server."""

    def __init__(
        self,
        base_url: str = DEFAULT_OLLAMA_BASE_URL,
        model: str = "nomic-embed-text",
        dimensions: int = _EMBEDDING_DIMENSIONS,
        model_version: str = "1.0",
        *,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_RETRIES,
        max_concurrent_requests: int = DEFAULT_MAX_CONCURRENT,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.dimensions = dimensions
        self.model_version = model_version
        self.timeout = timeout
        self.max_retries = max(1, max_retries)
        self.max_concurrent_requests = max(1, max_concurrent_requests)

    def get_model_info(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "dimensions": self.dimensions,
            "version": self.model_version,
        }

    async def embed_text(self, text: str) -> List[float]:
        stripped = (text or "").strip()
        if not stripped:
            raise ValueError("text must be non-empty")
        vec = await self._embed_one(stripped)
        self._validate_vector(vec)
        return vec

    async def embed_texts(
        self,
        texts: List[str],
        *,
        batch_size: int = 32,
    ) -> List[List[float]]:
        if not texts:
            return []
        normalized: List[str] = []
        for i, raw in enumerate(texts):
            s = (raw or "").strip()
            if not s:
                raise ValueError(f"texts[{i}] must be non-empty after strip")
            normalized.append(s)

        sem = asyncio.Semaphore(self.max_concurrent_requests)
        batch_size = max(1, batch_size)

        async def one(prompt: str) -> List[float]:
            async with sem:
                vec = await self._embed_one(prompt)
                self._validate_vector(vec)
                return vec

        out: List[List[float]] = []
        for i in range(0, len(normalized), batch_size):
            chunk = normalized[i : i + batch_size]
            part = await asyncio.gather(*(one(t) for t in chunk))
            out.extend(part)
        return out

    def _validate_vector(self, vec: List[float]) -> None:
        if len(vec) != self.dimensions:
            raise ValueError(
                f"embedding length {len(vec)} != expected {self.dimensions} "
                f"for model {self.model!r}"
            )

    async def _embed_one(self, text: str) -> List[float]:
        url = f"{self.base_url}/api/embeddings"
        payload = {"model": self.model, "prompt": text}
        last_err: Optional[BaseException] = None

        for attempt in range(self.max_retries):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.post(url, json=payload)
                    response.raise_for_status()
                    data = response.json()
                emb = data.get("embedding")
                if not isinstance(emb, list):
                    raise ValueError("Ollama response missing embedding array")
                return [float(x) for x in emb]
            except (httpx.HTTPError, ValueError, TypeError) as e:
                last_err = e
                wait_s = 2**attempt
                logger.warning(
                    "Ollama embedding attempt %s/%s failed: %s",
                    attempt + 1,
                    self.max_retries,
                    e,
                )
                if attempt + 1 < self.max_retries:
                    await asyncio.sleep(wait_s)

        assert last_err is not None
        raise last_err


def create_embedding_service_from_settings(
    settings_service: Optional["SettingsService"] = None,
) -> EmbeddingService:
    """Build ``EmbeddingService`` from ``model_config.json`` embedding section."""
    from .settings import get_settings_service

    svc = settings_service or get_settings_service()
    ec = svc.get_embedding_profile_config()
    dims = int(ec["dimensions"])
    if dims != _EMBEDDING_DIMENSIONS:
        raise ValueError(
            f"model_config embedding dimensions ({dims}) must match "
            f"ORM / DB width ({_EMBEDDING_DIMENSIONS}); fix config or migration"
        )
    return EmbeddingService(
        base_url=os.getenv("OLLAMA_BASE_URL", DEFAULT_OLLAMA_BASE_URL),
        model=str(ec["model"]),
        dimensions=dims,
        model_version=str(ec["model_version"]),
    )

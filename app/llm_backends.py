"""
Pluggable LLM backend abstraction (#335, ADR-0025/ADR-0033).

`app/llm.py` and several call sites (`stories.py`, `entities.py`, `topics.py`,
`routers/health.py`, `routers/items.py`) were tightly coupled to `ollama.Client`.
This module introduces a small backend interface so the underlying inference
server can be selected per platform via `device_profiles[<platform>].backend`
in `data/model_config.json` (Ollama everywhere by default; MLX-based serving
on macOS, see #336) without changing call-site code.

This issue (#335) is a pure refactor: `LLMService` now routes its own calls
through `OllamaBackend` instead of talking to `ollama.Client` directly, but
observable behavior is unchanged. `LLMService.client` still returns the raw
`ollama.Client` instance for the external call sites listed above -- they are
migrated to call through the abstraction directly in #337.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@runtime_checkable
class LLMBackend(Protocol):
    """Common interface for a local LLM inference backend."""

    def generate(
        self,
        model: str,
        prompt: str,
        options: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Generate text for `prompt`. Returns a dict with at least a "response" key."""
        ...

    def list_models(self) -> List[str]:
        """Return the names/tags of models currently available on this backend."""
        ...

    def ensure_model(self, model: str) -> bool:
        """Ensure `model` is available (pulling/loading it if the backend supports
        that). Returns True if the model is ready to use."""
        ...

    def is_available(self) -> bool:
        """Return True if the backend service is reachable."""
        ...


class OllamaBackend:
    """
    LLMBackend implementation wrapping the `ollama` Python client.

    Default backend on all platforms today; Windows stays on this
    permanently, macOS may switch to `OMLXBackend` once #336 lands.
    """

    def __init__(self, base_url: str):
        self.base_url = base_url
        self._client = None

    @property
    def raw_client(self):
        """
        The underlying `ollama.Client`, exposed for legacy call sites that
        still reach through `LLMService.client` directly (removed in #337).
        """
        if self._client is None:
            try:
                import ollama

                self._client = ollama.Client(host=self.base_url)
            except ImportError:
                logger.error("Ollama package not installed. Run: pip install ollama")
                raise
            except Exception as e:
                logger.error(f"Failed to initialize Ollama client: {e}")
                raise
        return self._client

    def generate(
        self,
        model: str,
        prompt: str,
        options: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        return self.raw_client.generate(
            model=model, prompt=prompt, options=options or {}, **kwargs
        )

    def list_models(self) -> List[str]:
        try:
            models = self.raw_client.list()
        except Exception as e:
            logger.error(f"Failed to list Ollama models: {e}")
            return []

        if isinstance(models, dict) and "models" in models:
            return [m.get("name", m.get("model", "")) for m in models["models"] if m]
        return []

    def ensure_model(self, model: str) -> bool:
        try:
            if model not in self.list_models():
                logger.info(f"Pulling model {model}...")
                self.raw_client.pull(model)
                logger.info(f"Successfully pulled model {model}")
            return True
        except Exception as e:
            logger.error(f"Failed to ensure model {model}: {e}")
            return False

    def is_available(self) -> bool:
        try:
            import httpx

            response = httpx.get(f"{self.base_url}/api/tags", timeout=3.0)
            return response.status_code == 200
        except Exception as e:
            logger.warning(f"Ollama service not available: {e}")
            return False


# Registry of implemented backend types. "mlx" is added in #336.
_BACKEND_TYPES = {
    "ollama": OllamaBackend,
}


def get_backend(base_url: str, backend_type: Optional[str] = None) -> LLMBackend:
    """
    Resolve an `LLMBackend` instance.

    Args:
        base_url: Base URL for the backend service (e.g. `OLLAMA_BASE_URL`).
        backend_type: Explicit backend type (currently only `"ollama"`). If
            omitted, resolved from the current platform's `device_profiles`
            config (`SettingsService.get_backend_type()`, ADR-0033/#335).
    """
    if backend_type is None:
        try:
            from .settings import get_settings_service

            backend_type = get_settings_service().get_backend_type()
        except Exception as e:
            logger.warning(
                f"Failed to resolve backend type from settings: {e}, "
                "defaulting to 'ollama'"
            )
            backend_type = "ollama"

    backend_type = (backend_type or "ollama").lower()

    backend_cls = _BACKEND_TYPES.get(backend_type)
    if backend_cls is None:
        raise ValueError(
            f"Unsupported LLM backend '{backend_type}'. Implemented backends: "
            f"{sorted(_BACKEND_TYPES)}. MLX support lands in #336."
        )

    return backend_cls(base_url)

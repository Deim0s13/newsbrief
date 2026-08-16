"""
Pluggable LLM backend abstraction (#335/#336, ADR-0025/ADR-0033).

`app/llm.py` and several call sites (`stories.py`, `entities.py`, `topics.py`,
`routers/health.py`, `routers/items.py`) were tightly coupled to `ollama.Client`.
This module introduces a small backend interface so the underlying inference
server can be selected per platform via `device_profiles[<platform>].backend`
in `data/model_config.json`: `OllamaBackend` (default, all platforms) or
`OMLXBackend` (macOS, shared oMLX instance -- ADR-0033 addendum for the
throughput rationale) -- without changing call-site code.

#335 was a pure refactor: `LLMService` routes its own calls through the
resolved backend instead of talking to `ollama.Client` directly, but
observable behavior is unchanged while `device_profiles.<platform>.backend`
stays `"ollama"` everywhere. #337 migrated the external call sites listed
above to call through `LLMService.backend` directly; `LLMService.client`
remains only as a legacy passthrough to the raw `ollama.Client`.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Callable, Dict, List, Optional, Protocol, runtime_checkable

logger = logging.getLogger(__name__)

# oMLX connection config (#336). Same shared instance also used by the
# separate ai-lab project -- see #334 for the reachability/contention notes.
OMLX_BASE_URL = os.getenv("OMLX_BASE_URL", "http://localhost:8000")
OMLX_API_KEY = os.getenv("OMLX_API_KEY", "")


@runtime_checkable
class LLMBackend(Protocol):
    """Common interface for a local LLM inference backend."""

    base_url: str

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

    Default backend on all platforms; Windows stays on this permanently.
    macOS can switch to `OMLXBackend` via `device_profiles.darwin.backend`.
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
        # Ollama defaults `think` to enabled for supported reasoning models
        # (Qwen 3, DeepSeek R1/v3.1, GPT-OSS) whenever the caller doesn't
        # specify it (docs.ollama.com/capabilities/thinking, #332) -- costing
        # latency/tokens on every structured-JSON call site (stories.py,
        # entities.py, topics.py, llm.py) that never asked for chain-of-
        # thought. Default it off here so those call sites get the fast,
        # direct-answer path without each needing to know about `think`;
        # stories.py's deliberate deep-synthesis chain-of-thought mode (#286)
        # still opts back in by passing think=True explicitly, which wins
        # over this default. No-op for non-thinking models and for oMLX
        # (OMLXBackend drops unsupported kwargs).
        kwargs.setdefault("think", False)
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


# Ollama `options` keys that have a direct equivalent in oMLX's OpenAI-compatible
# `/v1/completions` API. `top_k` and `repeat_penalty` have no equivalent there
# and are dropped (logged at debug) rather than raising -- call sites build
# these dicts assuming Ollama and are migrated to the abstraction in #337, not
# rewritten to be backend-aware.
_OMLX_OPTION_MAP = {
    "temperature": "temperature",
    "top_p": "top_p",
    "num_predict": "max_tokens",
    "max_tokens": "max_tokens",
}
_OMLX_DEFAULT_MAX_TOKENS = 900


def _translate_options_for_omlx(options: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Map an Ollama-style `options` dict onto oMLX's OpenAI-compatible params."""
    translated: Dict[str, Any] = {}
    dropped = []
    for key, value in (options or {}).items():
        mapped_key = _OMLX_OPTION_MAP.get(key)
        if mapped_key:
            translated[mapped_key] = value
        else:
            dropped.append(key)
    if dropped:
        logger.debug(f"oMLX backend: dropping unsupported options {dropped}")
    translated.setdefault("max_tokens", _OMLX_DEFAULT_MAX_TOKENS)
    return translated


class OMLXBackend:
    """
    LLMBackend implementation targeting a shared oMLX instance's
    OpenAI-compatible API (ADR-0025/ADR-0033 amendment, #336).

    macOS-only today. Models must already be present in oMLX's local model
    directory (`~/.omlx/models`) -- unlike Ollama, this backend does not pull
    models on demand; `ensure_model()` only checks availability.
    """

    def __init__(
        self,
        base_url: str = OMLX_BASE_URL,
        api_key: str = OMLX_API_KEY,
    ):
        self.base_url = base_url
        self.api_key = api_key

    def _headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}

    def generate(
        self,
        model: str,
        prompt: str,
        options: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        import httpx

        if kwargs:
            # e.g. `think=True` (#286, stories.py chain-of-thought mode) has no
            # equivalent in oMLX's completions API and is silently dropped.
            logger.debug(f"oMLX backend: ignoring unsupported kwargs {sorted(kwargs)}")

        payload = {"model": model, "prompt": prompt}
        payload.update(_translate_options_for_omlx(options))

        response = httpx.post(
            f"{self.base_url}/v1/completions",
            headers=self._headers(),
            json=payload,
            timeout=300.0,
        )
        response.raise_for_status()
        data = response.json()
        text = data["choices"][0]["text"]
        # Shaped like ollama.Client().generate()'s return value so callers
        # that read response["response"] work unchanged once migrated (#337).
        return {"response": text, "raw": data}

    def list_models(self) -> List[str]:
        import httpx

        try:
            response = httpx.get(
                f"{self.base_url}/v1/models", headers=self._headers(), timeout=5.0
            )
            response.raise_for_status()
            data = response.json()
        except Exception as e:
            logger.error(f"Failed to list oMLX models: {e}")
            return []

        return [m.get("id", "") for m in data.get("data", []) if m]

    def ensure_model(self, model: str) -> bool:
        available = self.list_models()
        if model in available:
            return True
        logger.error(
            f"Model '{model}' not found on oMLX instance ({self.base_url}). "
            "oMLX does not auto-download models -- it must already be present "
            "in ~/.omlx/models. Available: "
            f"{available}"
        )
        return False

    def is_available(self) -> bool:
        import httpx

        try:
            response = httpx.get(
                f"{self.base_url}/v1/models", headers=self._headers(), timeout=3.0
            )
            return response.status_code == 200
        except Exception as e:
            logger.warning(f"oMLX service not available: {e}")
            return False


# Registry of implemented backend types, keyed by `device_profiles.<platform>.backend`.
_BACKEND_TYPES: Dict[str, Callable[[str], LLMBackend]] = {
    "ollama": lambda base_url: OllamaBackend(base_url),
    "mlx": lambda base_url: OMLXBackend(),
}


def get_backend(base_url: str, backend_type: Optional[str] = None) -> LLMBackend:
    """
    Resolve an `LLMBackend` instance.

    Args:
        base_url: Base URL for the Ollama backend (e.g. `OLLAMA_BASE_URL`).
            Ignored for the `"mlx"` backend, which reads its own connection
            config from `OMLX_BASE_URL`/`OMLX_API_KEY`.
        backend_type: Explicit backend type (`"ollama"` or `"mlx"`). If
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

    backend_factory = _BACKEND_TYPES.get(backend_type)
    if backend_factory is None:
        raise ValueError(
            f"Unsupported LLM backend '{backend_type}'. Implemented backends: "
            f"{sorted(_BACKEND_TYPES)}."
        )

    return backend_factory(base_url)

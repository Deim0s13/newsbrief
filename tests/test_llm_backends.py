"""
Tests for #335/#336: pluggable LLM backend abstraction (Ollama + MLX,
ADR-0025/ADR-0033).

Pure unit tests - the `ollama` client and `httpx` are mocked; no live services
are contacted.
"""

from unittest.mock import MagicMock, patch

import pytest

from app.llm_backends import OllamaBackend, OMLXBackend, get_backend
from app.stories import _run_llm_call

# ---------------------------------------------------------------------------
# OllamaBackend
# ---------------------------------------------------------------------------


class TestOllamaBackendGenerate:
    def test_generate_delegates_to_raw_client(self):
        backend = OllamaBackend(base_url="http://localhost:11434")
        mock_client = MagicMock()
        mock_client.generate.return_value = {"response": "hello"}
        backend._client = mock_client

        result = backend.generate(
            model="qwen2.5:14b", prompt="hi", options={"temperature": 0.2}
        )

        assert result == {"response": "hello"}
        mock_client.generate.assert_called_once_with(
            model="qwen2.5:14b",
            prompt="hi",
            options={"temperature": 0.2},
            think=False,
        )

    def test_generate_defaults_options_to_empty_dict(self):
        backend = OllamaBackend(base_url="http://localhost:11434")
        mock_client = MagicMock()
        mock_client.generate.return_value = {"response": "hello"}
        backend._client = mock_client

        backend.generate(model="qwen2.5:14b", prompt="hi")

        mock_client.generate.assert_called_once_with(
            model="qwen2.5:14b", prompt="hi", options={}, think=False
        )

    def test_generate_passes_through_extra_kwargs(self):
        """e.g. `think=True` used by stories.py for reasoning-model prompts (#286)."""
        backend = OllamaBackend(base_url="http://localhost:11434")
        mock_client = MagicMock()
        mock_client.generate.return_value = {"response": "hello"}
        backend._client = mock_client

        backend.generate(model="deepseek-r1:14b", prompt="hi", think=True)

        mock_client.generate.assert_called_once_with(
            model="deepseek-r1:14b", prompt="hi", options={}, think=True
        )


class TestOllamaBackendThinkDefault:
    """
    Regression tests for #332: Ollama defaults `think` to enabled for
    supported reasoning models (Qwen 3, DeepSeek R1/v3.1, GPT-OSS) whenever
    the caller doesn't specify it, costing latency/tokens on every
    structured-JSON call site that never asked for chain-of-thought.
    `OllamaBackend.generate()` now defaults `think=False` unless the caller
    explicitly overrides it.
    """

    def test_think_defaults_to_false_when_not_specified(self):
        backend = OllamaBackend(base_url="http://localhost:11434")
        mock_client = MagicMock()
        mock_client.generate.return_value = {"response": "hello"}
        backend._client = mock_client

        backend.generate(model="qwen3:14b", prompt="hi")

        assert mock_client.generate.call_args.kwargs["think"] is False

    def test_explicit_think_true_overrides_default(self):
        backend = OllamaBackend(base_url="http://localhost:11434")
        mock_client = MagicMock()
        mock_client.generate.return_value = {"response": "hello"}
        backend._client = mock_client

        backend.generate(model="deepseek-r1:14b", prompt="hi", think=True)

        assert mock_client.generate.call_args.kwargs["think"] is True

    def test_explicit_think_false_is_respected(self):
        backend = OllamaBackend(base_url="http://localhost:11434")
        mock_client = MagicMock()
        mock_client.generate.return_value = {"response": "hello"}
        backend._client = mock_client

        backend.generate(model="qwen3:14b", prompt="hi", think=False)

        assert mock_client.generate.call_args.kwargs["think"] is False


class TestOllamaBackendListModels:
    def test_list_models_parses_standard_response(self):
        backend = OllamaBackend(base_url="http://localhost:11434")
        mock_client = MagicMock()
        mock_client.list.return_value = {
            "models": [{"name": "qwen2.5:14b"}, {"name": "mistral:7b"}]
        }
        backend._client = mock_client

        assert backend.list_models() == ["qwen2.5:14b", "mistral:7b"]

    def test_list_models_falls_back_to_model_key(self):
        backend = OllamaBackend(base_url="http://localhost:11434")
        mock_client = MagicMock()
        mock_client.list.return_value = {"models": [{"model": "qwen2.5:14b"}]}
        backend._client = mock_client

        assert backend.list_models() == ["qwen2.5:14b"]

    def test_list_models_returns_empty_on_unexpected_shape(self):
        backend = OllamaBackend(base_url="http://localhost:11434")
        mock_client = MagicMock()
        mock_client.list.return_value = ["not", "a", "dict"]
        backend._client = mock_client

        assert backend.list_models() == []

    def test_list_models_returns_empty_on_error(self):
        backend = OllamaBackend(base_url="http://localhost:11434")
        mock_client = MagicMock()
        mock_client.list.side_effect = RuntimeError("connection refused")
        backend._client = mock_client

        assert backend.list_models() == []


class TestOllamaBackendEnsureModel:
    def test_ensure_model_skips_pull_when_already_present(self):
        backend = OllamaBackend(base_url="http://localhost:11434")
        mock_client = MagicMock()
        mock_client.list.return_value = {"models": [{"name": "qwen2.5:14b"}]}
        backend._client = mock_client

        assert backend.ensure_model("qwen2.5:14b") is True
        mock_client.pull.assert_not_called()

    def test_ensure_model_pulls_when_missing(self):
        backend = OllamaBackend(base_url="http://localhost:11434")
        mock_client = MagicMock()
        mock_client.list.return_value = {"models": []}
        backend._client = mock_client

        assert backend.ensure_model("qwen2.5:14b") is True
        mock_client.pull.assert_called_once_with("qwen2.5:14b")

    def test_ensure_model_returns_false_on_pull_failure(self):
        backend = OllamaBackend(base_url="http://localhost:11434")
        mock_client = MagicMock()
        mock_client.list.return_value = {"models": []}
        mock_client.pull.side_effect = RuntimeError("404 model not found")
        backend._client = mock_client

        assert backend.ensure_model("qwen2.5:14b") is False


class TestOllamaBackendIsAvailable:
    @patch("httpx.get")
    def test_is_available_true_on_200(self, mock_get):
        mock_get.return_value = MagicMock(status_code=200)
        backend = OllamaBackend(base_url="http://localhost:11434")
        assert backend.is_available() is True

    @patch("httpx.get")
    def test_is_available_false_on_error(self, mock_get):
        mock_get.side_effect = RuntimeError("connection refused")
        backend = OllamaBackend(base_url="http://localhost:11434")
        assert backend.is_available() is False


class TestOllamaBackendRawClient:
    def test_raw_client_lazily_constructs_ollama_client(self):
        backend = OllamaBackend(base_url="http://localhost:11434")
        with patch("ollama.Client") as mock_ollama_client_cls:
            mock_instance = MagicMock()
            mock_ollama_client_cls.return_value = mock_instance

            client = backend.raw_client

            assert client is mock_instance
            mock_ollama_client_cls.assert_called_once_with(
                host="http://localhost:11434"
            )

    def test_raw_client_is_cached(self):
        backend = OllamaBackend(base_url="http://localhost:11434")
        with patch("ollama.Client") as mock_ollama_client_cls:
            mock_ollama_client_cls.return_value = MagicMock()

            first = backend.raw_client
            second = backend.raw_client

            assert first is second
            mock_ollama_client_cls.assert_called_once()


# ---------------------------------------------------------------------------
# OMLXBackend (#336)
# ---------------------------------------------------------------------------


class TestOMLXBackendGenerate:
    @patch("httpx.post")
    def test_generate_posts_to_completions_endpoint(self, mock_post):
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"choices": [{"text": "hello from mlx"}]},
        )
        backend = OMLXBackend(base_url="http://localhost:8000", api_key="test-key")

        result = backend.generate(model="some-mlx-model", prompt="hi")

        assert result["response"] == "hello from mlx"
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args.kwargs
        assert call_kwargs["json"]["model"] == "some-mlx-model"
        assert call_kwargs["json"]["prompt"] == "hi"
        assert call_kwargs["headers"] == {"Authorization": "Bearer test-key"}

    @patch("httpx.post")
    def test_generate_translates_ollama_style_options(self, mock_post):
        mock_post.return_value = MagicMock(
            status_code=200, json=lambda: {"choices": [{"text": "ok"}]}
        )
        backend = OMLXBackend(base_url="http://localhost:8000", api_key="k")

        backend.generate(
            model="m",
            prompt="p",
            options={
                "temperature": 0.2,
                "top_k": 40,
                "top_p": 0.8,
                "repeat_penalty": 1.1,
                "num_predict": 500,
            },
        )

        payload = mock_post.call_args.kwargs["json"]
        assert payload["temperature"] == 0.2
        assert payload["top_p"] == 0.8
        assert payload["max_tokens"] == 500
        # No OpenAI-completions equivalent - dropped, not passed through
        assert "top_k" not in payload
        assert "repeat_penalty" not in payload
        assert "num_predict" not in payload

    @patch("httpx.post")
    def test_generate_defaults_max_tokens_when_absent(self, mock_post):
        mock_post.return_value = MagicMock(
            status_code=200, json=lambda: {"choices": [{"text": "ok"}]}
        )
        backend = OMLXBackend(base_url="http://localhost:8000", api_key="k")

        backend.generate(model="m", prompt="p")

        assert mock_post.call_args.kwargs["json"]["max_tokens"] == 900

    @patch("httpx.post")
    def test_generate_without_api_key_sends_no_auth_header(self, mock_post):
        mock_post.return_value = MagicMock(
            status_code=200, json=lambda: {"choices": [{"text": "ok"}]}
        )
        backend = OMLXBackend(base_url="http://localhost:8000", api_key="")

        backend.generate(model="m", prompt="p")

        assert mock_post.call_args.kwargs["headers"] == {}

    @patch("httpx.post")
    def test_generate_raises_on_http_error(self, mock_post):
        import httpx

        mock_response = MagicMock(status_code=401)
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "unauthorized", request=MagicMock(), response=mock_response
        )
        mock_post.return_value = mock_response
        backend = OMLXBackend(base_url="http://localhost:8000", api_key="bad-key")

        with pytest.raises(httpx.HTTPStatusError):
            backend.generate(model="m", prompt="p")


class TestOMLXBackendListModels:
    @patch("httpx.get")
    def test_list_models_parses_openai_style_response(self, mock_get):
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {
                "object": "list",
                "data": [
                    {"id": "mlx-community--Llama-3.2-3B-Instruct-4bit"},
                    {"id": "unsloth--Qwen3.6-35B-A3B-UD-MLX-4bit"},
                ],
            },
        )
        backend = OMLXBackend(base_url="http://localhost:8000", api_key="k")

        models = backend.list_models()

        assert models == [
            "mlx-community--Llama-3.2-3B-Instruct-4bit",
            "unsloth--Qwen3.6-35B-A3B-UD-MLX-4bit",
        ]

    @patch("httpx.get")
    def test_list_models_returns_empty_on_error(self, mock_get):
        mock_get.side_effect = RuntimeError("connection refused")
        backend = OMLXBackend(base_url="http://localhost:8000", api_key="k")

        assert backend.list_models() == []


class TestOMLXBackendEnsureModel:
    @patch("httpx.get")
    def test_ensure_model_true_when_present(self, mock_get):
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {"data": [{"id": "some-model"}]},
        )
        backend = OMLXBackend(base_url="http://localhost:8000", api_key="k")

        assert backend.ensure_model("some-model") is True

    @patch("httpx.get")
    def test_ensure_model_false_when_absent_no_download_attempted(self, mock_get):
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {"data": [{"id": "other-model"}]},
        )
        backend = OMLXBackend(base_url="http://localhost:8000", api_key="k")

        assert backend.ensure_model("missing-model") is False


class TestOMLXBackendIsAvailable:
    @patch("httpx.get")
    def test_is_available_true_on_200(self, mock_get):
        mock_get.return_value = MagicMock(status_code=200)
        backend = OMLXBackend(base_url="http://localhost:8000", api_key="k")
        assert backend.is_available() is True

    @patch("httpx.get")
    def test_is_available_false_on_401(self, mock_get):
        mock_get.return_value = MagicMock(status_code=401)
        backend = OMLXBackend(base_url="http://localhost:8000", api_key="wrong")
        assert backend.is_available() is False

    @patch("httpx.get")
    def test_is_available_false_on_connection_error(self, mock_get):
        mock_get.side_effect = RuntimeError("connection refused")
        backend = OMLXBackend(base_url="http://localhost:8000", api_key="k")
        assert backend.is_available() is False


# ---------------------------------------------------------------------------
# get_backend() factory
# ---------------------------------------------------------------------------


class TestGetBackendFactory:
    def test_explicit_backend_type_bypasses_settings_lookup(self):
        backend = get_backend("http://localhost:11434", backend_type="ollama")
        assert isinstance(backend, OllamaBackend)
        assert backend.base_url == "http://localhost:11434"

    def test_explicit_mlx_backend_type_returns_omlx_backend(self):
        backend = get_backend("http://localhost:11434", backend_type="mlx")
        assert isinstance(backend, OMLXBackend)

    def test_mlx_backend_ignores_ollama_base_url_arg(self):
        """OMLXBackend manages its own connection config (OMLX_BASE_URL/OMLX_API_KEY)."""
        backend = get_backend("http://localhost:11434", backend_type="mlx")
        assert backend.base_url != "http://localhost:11434"

    def test_resolves_backend_type_from_settings_when_omitted(self):
        with patch("app.settings.get_settings_service") as mock_get_settings:
            mock_settings = MagicMock()
            mock_settings.get_backend_type.return_value = "ollama"
            mock_get_settings.return_value = mock_settings

            backend = get_backend("http://localhost:11434")

            assert isinstance(backend, OllamaBackend)
            mock_settings.get_backend_type.assert_called_once()

    def test_resolves_mlx_backend_type_from_settings_when_omitted(self):
        with patch("app.settings.get_settings_service") as mock_get_settings:
            mock_settings = MagicMock()
            mock_settings.get_backend_type.return_value = "mlx"
            mock_get_settings.return_value = mock_settings

            backend = get_backend("http://localhost:11434")

            assert isinstance(backend, OMLXBackend)

    def test_defaults_to_ollama_when_settings_lookup_fails(self):
        with patch("app.settings.get_settings_service") as mock_get_settings:
            mock_get_settings.side_effect = RuntimeError("config unavailable")

            backend = get_backend("http://localhost:11434")

            assert isinstance(backend, OllamaBackend)

    def test_backend_type_is_case_insensitive(self):
        backend = get_backend("http://localhost:11434", backend_type="OLLAMA")
        assert isinstance(backend, OllamaBackend)

    def test_unsupported_backend_type_raises_clear_error(self):
        with pytest.raises(ValueError, match="Unsupported LLM backend 'vllm'"):
            get_backend("http://localhost:11434", backend_type="vllm")


# ---------------------------------------------------------------------------
# LLMService <-> backend integration (#335 - verifies the refactor preserved
# observable behavior; internals now route through LLMBackend, not
# ollama.Client directly).
# ---------------------------------------------------------------------------


class TestLLMServiceBackendIntegration:
    def test_client_property_returns_backend_raw_client(self):
        from app.llm import LLMService

        fake_backend = MagicMock()
        fake_backend.raw_client = "sentinel-raw-client"
        service = LLMService(base_url="http://localhost:11434", backend=fake_backend)

        assert service.client == "sentinel-raw-client"

    def test_is_available_delegates_to_backend(self):
        from app.llm import LLMService

        fake_backend = MagicMock()
        fake_backend.is_available.return_value = True
        service = LLMService(base_url="http://localhost:11434", backend=fake_backend)

        assert service.is_available() is True
        fake_backend.is_available.assert_called_once()

    def test_ensure_model_delegates_to_backend_with_resolved_model(self):
        from app.llm import LLMService

        fake_backend = MagicMock()
        fake_backend.ensure_model.return_value = True
        service = LLMService(
            base_url="http://localhost:11434", model="qwen2.5:14b", backend=fake_backend
        )

        assert service.ensure_model() is True
        fake_backend.ensure_model.assert_called_once_with("qwen2.5:14b")

    def test_ensure_model_explicit_arg_overrides_service_model(self):
        from app.llm import LLMService

        fake_backend = MagicMock()
        fake_backend.ensure_model.return_value = True
        service = LLMService(
            base_url="http://localhost:11434", model="qwen2.5:14b", backend=fake_backend
        )

        service.ensure_model("mistral:7b")
        fake_backend.ensure_model.assert_called_once_with("mistral:7b")

    def test_backend_property_lazily_resolves_when_not_injected(self):
        from app.llm import LLMService

        with patch("app.llm.get_backend") as mock_get_backend:
            mock_backend = MagicMock()
            mock_get_backend.return_value = mock_backend

            service = LLMService(base_url="http://localhost:11434")
            resolved = service.backend

            assert resolved is mock_backend
            mock_get_backend.assert_called_once_with("http://localhost:11434")

    def test_backend_property_is_cached(self):
        from app.llm import LLMService

        with patch("app.llm.get_backend") as mock_get_backend:
            mock_get_backend.return_value = MagicMock()

            service = LLMService(base_url="http://localhost:11434")
            first = service.backend
            second = service.backend

            assert first is second
            mock_get_backend.assert_called_once()


# ---------------------------------------------------------------------------
# stories.py call-site wiring (#337 - migrated off `llm_service.client`)
# ---------------------------------------------------------------------------


class TestStoriesRunLLMCallWiring:
    def test_run_llm_call_uses_backend_not_client(self):
        mock_service = MagicMock()
        mock_service.backend.generate.return_value = {"response": "synthesized text"}

        result = _run_llm_call(mock_service, model="qwen2.5:14b", prompt="hi")

        assert result == "synthesized text"
        mock_service.backend.generate.assert_called_once()
        mock_service.client.generate.assert_not_called()

    def test_run_llm_call_passes_think_kwarg_through(self):
        """think=True (#286, chain-of-thought mode) must reach the backend."""
        mock_service = MagicMock()
        mock_service.backend.generate.return_value = {"response": "ok"}

        _run_llm_call(mock_service, model="deepseek-r1:14b", prompt="hi", think=True)

        call_kwargs = mock_service.backend.generate.call_args.kwargs
        assert call_kwargs["think"] is True

    def test_run_llm_call_omits_think_by_default(self):
        mock_service = MagicMock()
        mock_service.backend.generate.return_value = {"response": "ok"}

        _run_llm_call(mock_service, model="qwen2.5:14b", prompt="hi")

        call_kwargs = mock_service.backend.generate.call_args.kwargs
        assert "think" not in call_kwargs

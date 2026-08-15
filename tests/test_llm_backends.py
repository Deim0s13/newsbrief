"""
Tests for #335: pluggable LLM backend abstraction (Ollama + MLX, ADR-0025/ADR-0033).

Pure unit tests - the `ollama` client and `httpx` are mocked; no live services
are contacted.
"""

from unittest.mock import MagicMock, patch

import pytest

from app.llm_backends import OllamaBackend, get_backend

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
            model="qwen2.5:14b", prompt="hi", options={"temperature": 0.2}
        )

    def test_generate_defaults_options_to_empty_dict(self):
        backend = OllamaBackend(base_url="http://localhost:11434")
        mock_client = MagicMock()
        mock_client.generate.return_value = {"response": "hello"}
        backend._client = mock_client

        backend.generate(model="qwen2.5:14b", prompt="hi")

        mock_client.generate.assert_called_once_with(
            model="qwen2.5:14b", prompt="hi", options={}
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
# get_backend() factory
# ---------------------------------------------------------------------------


class TestGetBackendFactory:
    def test_explicit_backend_type_bypasses_settings_lookup(self):
        backend = get_backend("http://localhost:11434", backend_type="ollama")
        assert isinstance(backend, OllamaBackend)
        assert backend.base_url == "http://localhost:11434"

    def test_resolves_backend_type_from_settings_when_omitted(self):
        with patch("app.settings.get_settings_service") as mock_get_settings:
            mock_settings = MagicMock()
            mock_settings.get_backend_type.return_value = "ollama"
            mock_get_settings.return_value = mock_settings

            backend = get_backend("http://localhost:11434")

            assert isinstance(backend, OllamaBackend)
            mock_settings.get_backend_type.assert_called_once()

    def test_defaults_to_ollama_when_settings_lookup_fails(self):
        with patch("app.settings.get_settings_service") as mock_get_settings:
            mock_get_settings.side_effect = RuntimeError("config unavailable")

            backend = get_backend("http://localhost:11434")

            assert isinstance(backend, OllamaBackend)

    def test_backend_type_is_case_insensitive(self):
        backend = get_backend("http://localhost:11434", backend_type="OLLAMA")
        assert isinstance(backend, OllamaBackend)

    def test_unsupported_backend_type_raises_clear_error(self):
        with pytest.raises(ValueError, match="Unsupported LLM backend 'mlx'"):
            get_backend("http://localhost:11434", backend_type="mlx")

    def test_unsupported_backend_type_error_mentions_336(self):
        with pytest.raises(ValueError, match="#336"):
            get_backend("http://localhost:11434", backend_type="mlx")


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

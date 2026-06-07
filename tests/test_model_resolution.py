"""
Tests for #294: active model profile is respected across all generation paths.

Validates that story generation (API endpoint, scheduler, pipeline runner)
uses the active profile from settings rather than a hardcoded 'llama3.1:8b'.
"""

import os

# app.db raises RuntimeError at import time without DATABASE_URL.
# Set a dummy value so module-level checks pass; no real connection is made
# because all DB calls are patched in these tests.
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test")

from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_settings_service(active_model: str = "qwen2.5:14b"):
    svc = MagicMock()
    svc.get_active_model.return_value = active_model
    return svc


# ---------------------------------------------------------------------------
# StoryGenerationRequest default
# ---------------------------------------------------------------------------


class TestStoryGenerationRequestModel:
    def test_model_defaults_to_none(self):
        """Request body with no model field should default to None, not llama3.1:8b."""
        from app.models import StoryGenerationRequest

        req = StoryGenerationRequest()
        assert (
            req.model is None
        ), "model should be None so the endpoint falls back to active profile"

    def test_explicit_model_is_preserved(self):
        """If a caller explicitly sets a model it should be honoured."""
        from app.models import StoryGenerationRequest

        req = StoryGenerationRequest(model="mistral:7b")
        assert req.model == "mistral:7b"


# ---------------------------------------------------------------------------
# /stories/generate endpoint — model resolution
# ---------------------------------------------------------------------------


class TestGenerateEndpointModelResolution:
    @patch("app.routers.stories.get_settings_service")
    @patch("app.routers.stories.generate_stories_simple")
    def test_active_profile_used_when_model_omitted(self, mock_gen, mock_svc):
        """Endpoint with no model in body should use get_active_model()."""
        from fastapi import BackgroundTasks
        from starlette.requests import Request
        from starlette.testclient import TestClient

        from app.routers.stories import router

        mock_svc.return_value = _make_settings_service("qwen2.5:14b")

        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(router)

        with TestClient(app) as client:
            resp = client.post("/stories/generate", json={})

        assert resp.status_code == 202
        assert resp.json()["model"] == "qwen2.5:14b"

    @patch("app.routers.stories.get_settings_service")
    @patch("app.routers.stories.generate_stories_simple")
    def test_explicit_model_overrides_active_profile(self, mock_gen, mock_svc):
        """Explicit model in request body takes precedence over active profile."""
        mock_svc.return_value = _make_settings_service("qwen2.5:14b")

        from fastapi import FastAPI
        from starlette.testclient import TestClient

        from app.routers.stories import router

        app = FastAPI()
        app.include_router(router)

        with TestClient(app) as client:
            resp = client.post("/stories/generate", json={"model": "mistral:7b"})

        assert resp.status_code == 202
        assert resp.json()["model"] == "mistral:7b"

    @patch("app.routers.stories.get_settings_service")
    @patch("app.routers.stories.generate_stories_simple")
    def test_model_is_not_llama_default(self, mock_gen, mock_svc):
        """Regression: endpoint must not default to llama3.1:8b."""
        mock_svc.return_value = _make_settings_service("qwen2.5:14b")

        from fastapi import FastAPI
        from starlette.testclient import TestClient

        from app.routers.stories import router

        app = FastAPI()
        app.include_router(router)

        with TestClient(app) as client:
            resp = client.post("/stories/generate", json={})

        assert resp.json()["model"] != "llama3.1:8b"


# ---------------------------------------------------------------------------
# Scheduler — reads active model at call time
# ---------------------------------------------------------------------------


class TestSchedulerModelResolution:
    def test_scheduler_uses_active_model(self):
        """Scheduled generation should read active model at job run time."""
        from app.pipeline_runner import StageResult
        from app.scheduler import scheduled_story_generation

        mock_stage = MagicMock()
        mock_stage.return_value = StageResult(
            "story_generation",
            True,
            {"stories_created": 1, "stories_archived": 0},
            None,
        )
        mock_svc = _make_settings_service("qwen2.5:32b")

        # Scheduler defers these imports inside the function, so patch at their source modules
        with patch(
            "app.pipeline_runner.execute_story_generation_stage", mock_stage
        ), patch("app.settings.get_settings_service", return_value=mock_svc):
            scheduled_story_generation()

        # The model passed to the stage must come from settings, not a constant
        assert (
            mock_stage.called
        ), "execute_story_generation_stage should have been called"
        call_kwargs = mock_stage.call_args
        model_used = call_kwargs.kwargs.get("model")
        assert (
            model_used != "llama3.1:8b"
        ), "Scheduler must not pass hardcoded llama3.1:8b to execute_story_generation_stage"
        assert (
            model_used == "qwen2.5:32b"
        ), f"Expected qwen2.5:32b from mocked active profile, got {model_used!r}"


# ---------------------------------------------------------------------------
# Generation status endpoint
# ---------------------------------------------------------------------------


class TestGenerationStatusEndpoint:
    def test_status_endpoint_exists_and_returns_json(self):
        """GET /stories/generation-status should return in_progress field."""
        from fastapi import FastAPI
        from starlette.testclient import TestClient

        from app.routers.stories import router

        app = FastAPI()
        app.include_router(router)

        # Patch session_scope so no real DB is needed
        with patch("app.routers.stories.session_scope") as mock_scope:
            mock_session = MagicMock()
            mock_session.execute.return_value.fetchone.return_value = None
            mock_scope.return_value.__enter__ = MagicMock(return_value=mock_session)
            mock_scope.return_value.__exit__ = MagicMock(return_value=False)

            with TestClient(app) as client:
                resp = client.get("/stories/generation-status")

        assert resp.status_code == 200
        data = resp.json()
        assert "in_progress" in data

    def test_status_in_progress_false_when_no_runs(self):
        """No pipeline_stage_runs row → in_progress is False."""
        from fastapi import FastAPI
        from starlette.testclient import TestClient

        from app.routers.stories import router

        app = FastAPI()
        app.include_router(router)

        with patch("app.routers.stories.session_scope") as mock_scope:
            mock_session = MagicMock()
            mock_session.execute.return_value.fetchone.return_value = None
            mock_scope.return_value.__enter__ = MagicMock(return_value=mock_session)
            mock_scope.return_value.__exit__ = MagicMock(return_value=False)

            with TestClient(app) as client:
                resp = client.get("/stories/generation-status")

        assert resp.json()["in_progress"] is False

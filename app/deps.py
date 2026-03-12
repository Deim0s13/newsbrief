"""Shared dependencies for routers. Decouples route handlers from app.main."""

import os
from pathlib import Path

from fastapi import Request
from fastapi.templating import Jinja2Templates
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from .db import session_scope
from .llm import OLLAMA_BASE_URL, get_llm_service, is_llm_available

RATE_LIMIT_DEFAULT = os.environ.get("RATE_LIMIT_DEFAULT", "100/minute")
RATE_LIMIT_LLM = os.environ.get("RATE_LIMIT_LLM", "10/minute")

# Templates: created here so routers can import without depending on main.
# main.py sets env globals (environment, app_version) on this object after app creation.
_templates_dir = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=str(_templates_dir))


def get_version() -> str:
    """Read version from pyproject.toml (single source of truth)."""
    try:
        import tomllib as _toml
    except ImportError:
        import tomli as _toml  # Python < 3.11 fallback

    pyproject_path = Path(__file__).resolve().parent.parent / "pyproject.toml"
    try:
        with open(pyproject_path, "rb") as f:
            data = _toml.load(f)
            return data.get("project", {}).get("version", "dev")
    except Exception:
        return "dev"


def get_client_ip(request: Request) -> str:
    """Get client IP, preferring X-Forwarded-For when behind proxy."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


limiter = Limiter(key_func=get_client_ip, default_limits=[RATE_LIMIT_DEFAULT])


def register_limiter_on_app(app) -> None:
    """Attach limiter to app and add rate-limit exception handler. Call from main."""
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

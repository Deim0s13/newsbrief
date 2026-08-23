"""
Shared pytest fixtures for the NewsBrief test suite.
"""

from __future__ import annotations

import os
from urllib.parse import urlsplit

import pytest

# The dedicated Postgres port for local/CI dev DBs (see CLAUDE.md, Makefile `db-up`).
_DEV_DB_PORT = 5433


def pytest_configure(config: pytest.Config) -> None:
    """Hard guard: refuse to run against any database that isn't the dev DB.

    Several tests run destructive `TRUNCATE`/`DELETE FROM feeds/items/stories`
    as setup (see tests/pg_testutil.py). A `DATABASE_URL` accidentally pointed at
    production (port 5432) once wiped all of prod's real feeds/items/stories,
    leaving only test fixtures behind. This check aborts the whole test session
    before any test runs if DATABASE_URL isn't the port-5433 dev DB.

    Exempt when running under GitHub Actions: ci-dev.yml/ci-prod.yml spin up
    their own disposable `postgres:5432` service container (db `newsbrief_test`,
    torn down with the runner) -- never real production, which only GitHub's
    hosted runners can't reach anyway.
    """
    if os.environ.get("GITHUB_ACTIONS") == "true":
        return

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        return  # DB-dependent tests self-skip via `pytest.skip(..., allow_module_level=True)`

    port = urlsplit(database_url).port
    if port != _DEV_DB_PORT:
        raise pytest.UsageError(
            f"Refusing to run: DATABASE_URL targets port {port}, not the dedicated "
            f"dev DB port {_DEV_DB_PORT}. This test suite runs destructive TRUNCATE/DELETE "
            "against feeds/items/stories as part of normal setup — pointing it at any other "
            "database (e.g. production) will wipe real data. Run `make db-up` and use "
            f"postgresql://newsbrief:newsbrief_dev@localhost:{_DEV_DB_PORT}/newsbrief."
        )


@pytest.fixture(autouse=True)
def dispose_db_connections_after_test():
    """
    Close all SQLAlchemy sessions and pool connections after each test.

    Without this, sessions left open by tests hold idle PostgreSQL transactions.
    Subsequent tests calling TRUNCATE block on those locks for the full
    per-test timeout (120s) before the GC eventually closes the session.

    engine.dispose() alone is not enough — it only closes idle pool connections.
    Sessions still hold checked-out connections until explicitly closed.
    close_all_sessions() returns those connections to the pool first.
    """
    yield
    try:
        from sqlalchemy.orm import close_all_sessions

        from app.db import engine

        close_all_sessions()
        engine.dispose()
    except Exception:
        pass

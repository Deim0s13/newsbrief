"""
Shared pytest fixtures for the NewsBrief test suite.
"""

from __future__ import annotations

import pytest


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

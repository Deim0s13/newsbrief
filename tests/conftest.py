"""
Shared pytest fixtures for the NewsBrief test suite.
"""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def dispose_db_connections_after_test():
    """
    Close all pooled DB connections after each test.

    Without this, SQLAlchemy sessions left open by tests hold idle transactions.
    PostgreSQL then blocks TRUNCATE statements in subsequent tests waiting for
    those transactions to end, causing ~120s hangs per affected test.
    """
    yield
    try:
        from app.db import engine

        engine.dispose()
    except Exception:
        pass

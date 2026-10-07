"""Tests for OPML import's zero-feeds-found handling (user-reported bug).

The user imported an OPML file that was really just a list of newsletter
names (<outline type="rss" text="..."/> with no xmlUrl attribute at all).
Parsing succeeded but found zero importable outlines, and the import
silently "completed" reporting 0 of 0 with no explanation. These tests
cover the fix: a clear, surfaced error instead of silent success.
"""

from __future__ import annotations

import os

import pytest

if not os.environ.get("DATABASE_URL"):
    pytest.skip("PostgreSQL required (set DATABASE_URL)", allow_module_level=True)

from sqlalchemy import text

from app.feeds import create_import_record, get_import_status, import_opml_content
from tests.pg_testutil import pg_session_truncate_story_graph

# Reproduces the user's real file: a nested OPML with <outline> entries that
# have no xmlUrl attribute at all -- just names.
NO_URLS_OPML = """<?xml version="1.0" encoding="UTF-8"?>
<opml version="2.0">
  <head><title>Newsletters</title></head>
  <body>
    <outline text="Daily AI Briefings">
      <outline type="rss" text="TLDR AI" />
      <outline type="rss" text="The Rundown AI" />
    </outline>
  </body>
</opml>
"""

VALID_OPML = """<?xml version="1.0" encoding="UTF-8"?>
<opml version="2.0">
  <head><title>Feeds</title></head>
  <body>
    <outline text="Example" type="rss" xmlUrl="http://example.com/feed"
              htmlUrl="http://example.com" />
  </body>
</opml>
"""


def _truncate_import_tables(session) -> None:
    session.execute(
        text("TRUNCATE failed_imports, import_history RESTART IDENTITY CASCADE")
    )
    session.commit()


class TestZeroOutlinesFound:
    def test_sync_import_reports_clear_error_not_silent_zero(self):
        session = pg_session_truncate_story_graph()
        try:
            _truncate_import_tables(session)
            result = import_opml_content(NO_URLS_OPML, validate=False)

            assert result["feeds_added"] == 0
            assert result["errors"], "expected a clear error message, got none"
            assert "xmlUrl" in result["errors"][0]
        finally:
            session.close()

    def test_async_import_marks_record_failed_with_message(self):
        session = pg_session_truncate_story_graph()
        try:
            _truncate_import_tables(session)
            import_id = create_import_record(
                filename="newsletters.opml", total_feeds=0, validation_enabled=False
            )

            result = import_opml_content(
                NO_URLS_OPML,
                validate=False,
                filename="newsletters.opml",
                import_id=import_id,
            )
            assert result["feeds_added"] == 0

            status = get_import_status(import_id)
            assert status is not None
            assert status["status"] == "failed"
            assert status["error_message"]
            assert "xmlUrl" in status["error_message"]
        finally:
            session.close()

    def test_valid_opml_still_imports_normally(self):
        """Regression guard: a real OPML with xmlUrl still imports fine."""
        session = pg_session_truncate_story_graph()
        try:
            _truncate_import_tables(session)
            session.execute(
                text("DELETE FROM feeds WHERE url = 'http://example.com/feed'")
            )
            session.commit()

            result = import_opml_content(VALID_OPML, validate=False)

            assert not result["errors"]
            assert result["feeds_added"] == 1
        finally:
            session.close()

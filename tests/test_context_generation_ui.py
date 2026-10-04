"""UI smoke tests for the story detail page's Context Engine panels
(v0.10.0, #216, ADR-0023) -- "Why It Matters" significance angles and the
new "Additional Context" panel (background/glossary/precedent).
"""

from __future__ import annotations

import os

import pytest

if not os.environ.get("DATABASE_URL"):
    pytest.skip("PostgreSQL required (set DATABASE_URL)", allow_module_level=True)

from datetime import UTC, datetime, timedelta

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from starlette.testclient import TestClient

from app.context_generation import store_story_context
from app.deps import templates
from app.llm_output import (
    BackgroundItem,
    GlossaryTerm,
    PrecedentItem,
    SignificanceAngle,
)
from app.routers.pages import router
from tests.pg_testutil import (
    create_test_story,
    link_test_articles_to_story,
    pg_session_truncate_story_graph,
    seed_default_feed,
)

LONG_TITLE = "Federal Reserve Cuts Interest Rates Amid Slowing Job Growth"
LONG_SYNTHESIS = (
    "This is a synthesis body long enough to satisfy the StoryOut model's "
    "minimum-length validator for testing purposes, describing a rate cut."
)


@pytest.fixture(autouse=True, scope="module")
def _template_globals():
    """base.html reads these globals, normally set by app.main at import
    time; set them directly here so we can mount a lightweight app with
    just the pages router (no scheduler/OPML startup hooks)."""
    templates.env.globals["environment"] = "development"
    templates.env.globals["app_version"] = lambda: "test"
    templates.env.globals["git_revision"] = ""


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(router)
    app.mount("/static", StaticFiles(directory="app/static"), name="static")
    with TestClient(app) as c:
        yield c


@pytest.fixture
def story_with_full_context():
    session = pg_session_truncate_story_graph()
    seed_default_feed(session)
    now = datetime.now(UTC)

    story_id = create_test_story(
        session,
        title=LONG_TITLE,
        synthesis=LONG_SYNTHESIS,
        key_points=["p1", "p2"],
        why_it_matters="This affects interest rates broadly.",
        topics=["economy"],
        entities=["Federal Reserve"],
        importance_score=0.5,
        freshness_score=0.5,
        model="test-model",
        time_window_start=now - timedelta(hours=1),
        time_window_end=now,
        first_seen=now,
    )
    session.execute(
        text(
            "INSERT INTO items (id, feed_id, title, url, url_hash, published) "
            "VALUES (1, 1, 'Article A', 'http://x/1', 'h1', NOW())"
        )
    )
    session.commit()
    link_test_articles_to_story(session, story_id, [1], primary_article_id=1)

    store_story_context(
        session,
        story_id,
        "significance",
        [
            SignificanceAngle(
                dimension="economic", text="Markets react.", confidence=0.8
            )
        ],
    )
    store_story_context(
        session,
        story_id,
        "background",
        [BackgroundItem(text="How this situation developed.", confidence=0.7)],
    )
    store_story_context(
        session,
        story_id,
        "glossary",
        [
            GlossaryTerm(
                term="quantitative easing",
                definition="Central bank bond buying to boost money supply.",
                confidence=0.6,
            )
        ],
    )
    store_story_context(
        session,
        story_id,
        "precedent",
        [
            PrecedentItem(
                text="Similar to the July cut.", related_story_id=None, confidence=0.5
            )
        ],
    )

    yield story_id

    session.close()


@pytest.fixture
def story_without_context():
    session = pg_session_truncate_story_graph()
    seed_default_feed(session)
    now = datetime.now(UTC)

    story_id = create_test_story(
        session,
        title=LONG_TITLE,
        synthesis=LONG_SYNTHESIS,
        key_points=["p1", "p2"],
        why_it_matters="This affects interest rates broadly.",
        topics=["economy"],
        entities=[],
        importance_score=0.5,
        freshness_score=0.5,
        model="test-model",
        time_window_start=now - timedelta(hours=1),
        time_window_end=now,
        first_seen=now,
    )
    session.execute(
        text(
            "INSERT INTO items (id, feed_id, title, url, url_hash, published) "
            "VALUES (1, 1, 'Article A', 'http://x/1', 'h1', NOW())"
        )
    )
    session.commit()
    link_test_articles_to_story(session, story_id, [1], primary_article_id=1)

    yield story_id

    session.close()


class TestWhyItMattersSignificancePanel:
    def test_significance_angle_rendered(self, client, story_with_full_context):
        resp = client.get(f"/story/{story_with_full_context}")
        assert resp.status_code == 200
        html = resp.text
        assert "Why It Matters" in html
        assert "Markets react." in html
        assert "economic" in html

    def test_legacy_why_it_matters_still_rendered(
        self, client, story_with_full_context
    ):
        resp = client.get(f"/story/{story_with_full_context}")
        assert "This affects interest rates broadly." in resp.text

    def test_no_significance_no_extra_markup_crash(self, client, story_without_context):
        """A story with the legacy why_it_matters but no story_context rows
        should render fine (additive feature, no crash on empty list)."""
        resp = client.get(f"/story/{story_without_context}")
        assert resp.status_code == 200
        assert "This affects interest rates broadly." in resp.text


class TestAdditionalContextPanel:
    def test_panel_rendered_with_all_types(self, client, story_with_full_context):
        resp = client.get(f"/story/{story_with_full_context}")
        assert resp.status_code == 200
        html = resp.text
        assert "Additional Context" in html
        assert "Background" in html
        assert "How this situation developed." in html
        assert "Glossary" in html
        assert "quantitative easing" in html
        assert "Central bank bond buying to boost money supply." in html
        assert "Historical Precedent" in html
        assert "Similar to the July cut." in html

    def test_panel_hidden_when_no_context(self, client, story_without_context):
        resp = client.get(f"/story/{story_without_context}")
        assert resp.status_code == 200
        # "Additional Context" also appears in an HTML comment even when the
        # panel itself is hidden -- check for the panel's actual id instead.
        assert 'id="context-panel"' not in resp.text

    def test_panel_starts_collapsed(self, client, story_with_full_context):
        resp = client.get(f"/story/{story_with_full_context}")
        html = resp.text
        # The details div should carry the 'hidden' class initially.
        assert 'id="context-details" class="hidden' in html

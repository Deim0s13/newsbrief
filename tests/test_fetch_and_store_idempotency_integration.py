"""
Integration tests for fetch_and_store idempotency (ADR-0031, phase 2).

Requires PostgreSQL (DATABASE_URL). Mocks HTTP so tests are deterministic and offline.

Imports are deferred so pytest can collect this module when DATABASE_URL is unset (tests skip at runtime).
"""

from __future__ import annotations

import os
from collections import deque
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="PostgreSQL required (set DATABASE_URL)",
)


class _MockResp:
    __slots__ = ("status_code", "content", "headers", "reason_phrase", "text")

    def __init__(self, status_code: int, content: bytes, content_type: str) -> None:
        self.status_code = status_code
        self.content = content
        self.headers = {"content-type": content_type}
        self.reason_phrase = "OK"
        self.text = content.decode("utf-8", errors="replace")


def _rss_one_item(
    *,
    article_url: str,
    title: str = "Test item",
    summary: str = "Summary line.",
    pub_date: str = "Mon, 01 Jan 2024 12:00:00 GMT",
) -> bytes:
    xml = f"""<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0"><channel><title>Ch</title>
<item><title>{title}</title><link>{article_url}</link>
<pubDate>{pub_date}</pubDate><description>{summary}</description></item>
</channel></rss>"""
    return xml.encode("utf-8")


def _atom_one_entry(
    *,
    article_url: str,
    published: str = "2024-01-01T12:00:00+00:00",
    updated: str = "2024-06-15T12:00:00+00:00",
    summary: str = "Summary line.",
) -> bytes:
    xml = f"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"><title>T</title>
<entry><title>Item</title>
<link href="{article_url}"/><id>urn:nb:test:1</id>
<published>{published}</published>
<updated>{updated}</updated>
<summary type="html">{summary}</summary>
</entry></feed>"""
    return xml.encode("utf-8")


def _html_article(body_paragraph: str) -> bytes:
    html = f"""<!DOCTYPE html><html><head><title>t</title></head>
<body><article><p>{body_paragraph}</p></article></body></html>"""
    return html.encode("utf-8")


def _stub_extract_content(html: str, url: str, rss_summary: str = ""):  # noqa: ARG001
    """Deterministic extract for tests (avoids trafilatura variance)."""
    import re

    from app.extraction import ExtractionMetadata, ExtractionResult

    m = re.search(r"<p>([^<]+)</p>", html or "")
    text = m.group(1) if m else (rss_summary or "fallback")
    return ExtractionResult(
        content=text,
        title=None,
        method="test_stub",
        quality_score=0.9,
        metadata=ExtractionMetadata(),
        error=None,
        stage_results=[],
        extraction_time_ms=0,
    )


def _install_httpx_mock(
    feed_url: str, response_queue: deque[tuple[str, bytes, str]]
) -> MagicMock:
    """Queue order: each refresh cycle consumes GET feed, then GET article."""

    def get(url: str, **kwargs: object) -> _MockResp:
        u = str(url)
        if not response_queue:
            pytest.fail(f"Unexpected HTTP get: {u} (queue empty)")
        exp_url, body, ctype = response_queue.popleft()
        assert u == exp_url, f"Expected URL {exp_url!r}, got {u!r}"
        return _MockResp(200, body, ctype)

    mock_instance = MagicMock()
    mock_instance.get.side_effect = get
    mock_cm = MagicMock()
    mock_cm.__enter__.return_value = mock_instance
    mock_cm.__exit__.return_value = False
    return mock_cm


@pytest.fixture
def idempotency_feed():
    """Create an isolated feed row and delete it (and its items) after the test."""
    from sqlalchemy.exc import OperationalError

    from app.db import SessionLocal, init_db
    from app.feeds import url_hash

    try:
        init_db()
    except OperationalError:
        pytest.skip("PostgreSQL not reachable with current DATABASE_URL")
    import uuid

    slug = uuid.uuid4().hex[:12]
    feed_url = f"https://test.invalid/idem-{slug}/rss.xml"
    article_url = f"https://test.invalid/idem-{slug}/article"

    with SessionLocal() as s:
        s.execute(
            text("DELETE FROM items WHERE url_hash = :h"),
            {"h": url_hash(article_url)},
        )
        s.execute(text("DELETE FROM feeds WHERE url = :u"), {"u": feed_url})
        res = s.execute(
            text(
                """
            INSERT INTO feeds (url, name, robots_allowed, disabled)
            VALUES (:u, 'idempotency-integration', 1, 0)
            RETURNING id
            """
            ),
            {"u": feed_url},
        )
        fid = res.scalar()
        s.commit()

    yield fid, feed_url, article_url

    with SessionLocal() as s:
        s.execute(text("DELETE FROM items WHERE feed_id = :fid"), {"fid": fid})
        s.execute(text("DELETE FROM feeds WHERE id = :fid"), {"fid": fid})
        s.commit()


def _item_count_and_content(article_url: str) -> tuple[int, str | None]:
    from app.db import SessionLocal
    from app.feeds import url_hash

    h = url_hash(article_url)
    with SessionLocal() as s:
        n = s.execute(
            text("SELECT COUNT(*) FROM items WHERE url_hash = :h"),
            {"h": h},
        ).scalar()
        content = s.execute(
            text("SELECT content FROM items WHERE url_hash = :h"),
            {"h": h},
        ).scalar()
    return int(n or 0), content


@patch("app.feeds.extract_content", new=_stub_extract_content)
@patch("app.feeds.update_feed_health_scores", return_value={})
@patch("app.feeds.is_article_url_allowed", return_value=True)
@patch("app.feeds.httpx.Client")
def test_double_refresh_rss_no_second_row(
    mock_client_cls,
    _allow,
    _health,
    idempotency_feed,
):
    from app.feeds import fetch_and_store

    fid, feed_url, article_url = idempotency_feed
    rss = _rss_one_item(article_url=article_url)
    html = _html_article("BODY_MARK_RSS_STABLE")

    q: deque[tuple[str, bytes, str]] = deque(
        [
            (feed_url, rss, "application/rss+xml; charset=utf-8"),
            (article_url, html, "text/html; charset=utf-8"),
            (feed_url, rss, "application/rss+xml; charset=utf-8"),
            (article_url, html, "text/html; charset=utf-8"),
        ]
    )
    mock_client_cls.return_value = _install_httpx_mock(feed_url, q)

    with patch(
        "app.feeds.list_feeds",
        return_value=[(fid, feed_url, None, None, 1, 0, None)],
    ):
        s1 = fetch_and_store()
        s2 = fetch_and_store()

    assert q == deque(), "All mocked HTTP responses should be consumed"

    n, content = _item_count_and_content(article_url)
    assert n == 1
    assert content and "BODY_MARK_RSS_STABLE" in content

    assert s1.items_inserted >= 1
    assert s1.total_items >= 1
    assert s2.items_inserted == 0
    assert s2.items_updated == 0
    assert s2.total_items == 0


@patch("app.feeds.extract_content", new=_stub_extract_content)
@patch("app.feeds.update_feed_health_scores", return_value={})
@patch("app.feeds.is_article_url_allowed", return_value=True)
@patch("app.feeds.httpx.Client")
def test_atom_revision_updates_row_when_body_changes(
    mock_client_cls,
    _allow,
    _health,
    idempotency_feed,
):
    from app.feeds import fetch_and_store

    fid, feed_url, article_url = idempotency_feed
    atom = _atom_one_entry(article_url=article_url)
    html1 = _html_article("FIRST_REVISION_BODY")
    html2 = _html_article("SECOND_REVISION_BODY")

    q: deque[tuple[str, bytes, str]] = deque(
        [
            (feed_url, atom, "application/atom+xml; charset=utf-8"),
            (article_url, html1, "text/html; charset=utf-8"),
            (feed_url, atom, "application/atom+xml; charset=utf-8"),
            (article_url, html2, "text/html; charset=utf-8"),
            (feed_url, atom, "application/atom+xml; charset=utf-8"),
            (article_url, html2, "text/html; charset=utf-8"),
        ]
    )
    mock_client_cls.return_value = _install_httpx_mock(feed_url, q)

    with patch(
        "app.feeds.list_feeds",
        return_value=[(fid, feed_url, None, None, 1, 0, None)],
    ):
        s1 = fetch_and_store()
        s2 = fetch_and_store()
        s3 = fetch_and_store()

    assert q == deque()

    n, content = _item_count_and_content(article_url)
    assert n == 1
    assert content and "SECOND_REVISION_BODY" in content
    assert "FIRST_REVISION_BODY" not in (content or "")

    assert s1.items_inserted == 1
    assert s2.items_updated == 1
    assert s3.items_updated == 0
    assert s3.total_items == 0


@patch("app.feeds.extract_content", new=_stub_extract_content)
@patch("app.feeds.update_feed_health_scores", return_value={})
@patch("app.feeds.is_article_url_allowed", return_value=True)
@patch("app.feeds.httpx.Client")
def test_atom_revision_no_db_write_when_hash_unchanged(
    mock_client_cls,
    _allow,
    _health,
    idempotency_feed,
):
    from app.feeds import fetch_and_store

    fid, feed_url, article_url = idempotency_feed
    atom = _atom_one_entry(article_url=article_url)
    html = _html_article("SAME_BODY_HASH")

    q: deque[tuple[str, bytes, str]] = deque(
        [
            (feed_url, atom, "application/atom+xml; charset=utf-8"),
            (article_url, html, "text/html; charset=utf-8"),
            (feed_url, atom, "application/atom+xml; charset=utf-8"),
            (article_url, html, "text/html; charset=utf-8"),
        ]
    )
    mock_client_cls.return_value = _install_httpx_mock(feed_url, q)

    with patch(
        "app.feeds.list_feeds",
        return_value=[(fid, feed_url, None, None, 1, 0, None)],
    ):
        s1 = fetch_and_store()
        s2 = fetch_and_store()

    assert q == deque()
    n, _ = _item_count_and_content(article_url)
    assert n == 1
    assert s1.items_inserted == 1
    assert s2.items_updated == 0
    assert s2.total_items == 0

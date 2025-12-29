from __future__ import annotations

import hashlib
import os
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Optional, Tuple

import bleach
import certifi
import feedparser
import httpx
from sqlalchemy import text

from .db import session_scope
from .models import create_content_hash
from .ranking import calculate_ranking_score, classify_article_topic
from .readability import extract_readable
from .topics import classify_topic as classify_topic_unified

# Allowed HTML tags for sanitized content (safe formatting only)
ALLOWED_HTML_TAGS = ["p", "br", "b", "i", "em", "strong", "ul", "ol", "li", "a"]
ALLOWED_HTML_ATTRIBUTES = {"a": ["href", "title"]}


def sanitize_html(html_content: str) -> str:
    """
    Sanitize HTML content, removing dangerous tags while preserving safe formatting.

    Args:
        html_content: Raw HTML string from RSS feed

    Returns:
        Sanitized HTML with only safe tags allowed
    """
    if not html_content:
        return ""
    return bleach.clean(
        html_content,
        tags=ALLOWED_HTML_TAGS,
        attributes=ALLOWED_HTML_ATTRIBUTES,
        strip=True,  # Remove disallowed tags entirely (not just escape)
    )


def migrate_sanitize_existing_summaries() -> int:
    """
    Migrate existing article summaries to sanitized HTML.

    This function runs automatically on app startup to ensure all existing
    summaries are sanitized. It's idempotent - running multiple times is safe.

    Returns:
        Number of articles updated
    """
    import logging

    logger = logging.getLogger(__name__)
    updated_count = 0

    with session_scope() as session:
        # Get all articles with non-empty summaries
        rows = session.execute(
            text(
                "SELECT id, summary FROM items WHERE summary IS NOT NULL AND summary != ''"
            )
        ).fetchall()

        for row in rows:
            article_id, original_summary = row
            sanitized = sanitize_html(original_summary)

            # Only update if sanitization changed the content
            if sanitized != original_summary:
                session.execute(
                    text("UPDATE items SET summary = :summary WHERE id = :id"),
                    {"summary": sanitized, "id": article_id},
                )
                updated_count += 1

        session.commit()

    if updated_count > 0:
        logger.info(f"Sanitized {updated_count} existing article summaries")
    else:
        logger.debug("No article summaries needed sanitization")

    return updated_count


@dataclass
class RefreshStats:
    """Detailed statistics from a refresh operation."""

    total_items: int
    total_feeds_processed: int
    feeds_skipped_disabled: int
    feeds_skipped_robots: int
    feeds_cached_304: int
    feeds_error: int
    items_per_feed: dict[int, int]
    refresh_time_seconds: float
    hit_global_limit: bool
    hit_time_limit: bool
    robots_txt_blocked_articles: int


# Configurable limits (can be overridden by environment variables)
MAX_ITEMS_PER_REFRESH = int(os.getenv("NEWSBRIEF_MAX_ITEMS_PER_REFRESH", "150"))
MAX_ITEMS_PER_FEED = int(os.getenv("NEWSBRIEF_MAX_ITEMS_PER_FEED", "50"))
MAX_REFRESH_TIME_SECONDS = int(
    os.getenv("NEWSBRIEF_MAX_REFRESH_TIME", "300")
)  # 5 minutes
HTTP_TIMEOUT = 20.0  # seconds

# In-memory cache for robots.txt files (cleared each refresh cycle)
_robots_txt_cache: dict[str, str | None] = {}


def url_hash(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


def _get_robots_txt(domain: str) -> str | None:
    """
    Get robots.txt content for domain, using cache.
    Returns None if not available or error.
    """
    if domain in _robots_txt_cache:
        return _robots_txt_cache[domain]

    try:
        robots_url = f"https://{domain}/robots.txt"
        with httpx.Client(timeout=HTTP_TIMEOUT) as c:
            r = c.get(robots_url)
            if r.status_code == 200:
                _robots_txt_cache[domain] = r.text
                return r.text
    except Exception:
        pass

    # Cache empty result to avoid repeated failures
    _robots_txt_cache[domain] = None
    return None


def is_robot_allowed(feed_url: str) -> bool:
    """
    Check if feed URL is allowed by robots.txt.
    Uses simple robots.txt parsing for common patterns.
    """
    try:
        from urllib.parse import urlparse

        parts = urlparse(feed_url)
        domain = parts.netloc

        robots_txt = _get_robots_txt(domain)
        if robots_txt is None:
            return True  # No robots.txt = allowed

        return _check_robots_txt_path(robots_txt, parts.path or "/", user_agent="*")
    except Exception:
        return True  # Error = allow (fail-safe)


def _check_robots_txt_path(robots_txt: str, path: str, user_agent: str = "*") -> bool:
    """
    Parse robots.txt and check if specific path is allowed.

    Args:
        robots_txt: Raw robots.txt content
        path: URL path to check (e.g., '/rss.xml')
        user_agent: User agent to match (default: '*')

    Returns:
        True if allowed, False if disallowed
    """
    if not robots_txt.strip():
        return True

    # Simple line-by-line parser
    current_user_agent = None
    disallow_patterns: list[str] = []
    allow_patterns: list[str] = []

    for line in robots_txt.split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        if line.lower().startswith("user-agent:"):
            current_user_agent = line.split(":", 1)[1].strip()
            if current_user_agent in ("*", user_agent.lower()):
                disallow_patterns = []  # Reset for this user agent
                allow_patterns = []
        elif current_user_agent in ("*", user_agent.lower()):
            if line.lower().startswith("disallow:"):
                pattern = line.split(":", 1)[1].strip()
                if pattern:
                    disallow_patterns.append(pattern)
            elif line.lower().startswith("allow:"):
                pattern = line.split(":", 1)[1].strip()
                if pattern:
                    allow_patterns.append(pattern)

    # Check allow patterns first (they override disallow)
    for pattern in allow_patterns:
        if _path_matches_pattern(path, pattern):
            return True

    # Check disallow patterns
    for pattern in disallow_patterns:
        if _path_matches_pattern(path, pattern):
            return False

    return True  # Default: allow


def _path_matches_pattern(path: str, pattern: str) -> bool:
    """Check if path matches robots.txt pattern (simple prefix matching)."""
    if pattern == "/":
        return True  # Disallow everything
    return path.startswith(pattern)


def is_article_url_allowed(article_url: str) -> bool:
    """
    Check if individual article URL is allowed by robots.txt.
    Used before fetching article content for readability extraction.
    """
    try:
        from urllib.parse import urlparse

        parts = urlparse(article_url)
        domain = parts.netloc

        robots_txt = _get_robots_txt(domain)
        if robots_txt is None:
            return True  # No robots.txt = allowed

        return _check_robots_txt_path(
            robots_txt, parts.path or "/", user_agent="newsbrief"
        )
    except Exception:
        return True  # Error = allow (fail-safe)


def ensure_feed(feed_url: str) -> int:
    with session_scope() as s:
        row = s.execute(
            text("SELECT id FROM feeds WHERE url=:u"), {"u": feed_url}
        ).first()
        if row:
            return int(row[0])

        # Try to get feed name from RSS feed
        feed_name = None
        feed_status = "active"  # Track feed status

        try:
            import feedparser

            feed_data = feedparser.parse(feed_url)

            # Check if feed is valid and has content
            if feed_data.feed and not feed_data.bozo:
                # Try multiple attributes for feed name
                if hasattr(feed_data.feed, "title") and feed_data.feed.title:
                    feed_name = feed_data.feed.title
                elif hasattr(feed_data.feed, "subtitle") and feed_data.feed.subtitle:
                    feed_name = feed_data.feed.subtitle
                elif (
                    hasattr(feed_data.feed, "description")
                    and feed_data.feed.description
                ):
                    # Use first part of description as name
                    desc = feed_data.feed.description
                    feed_name = desc[:50] + "..." if len(desc) > 50 else desc
                elif feed_data.entries and len(feed_data.entries) > 0:
                    # Try to infer name from first entry's source
                    first_entry = feed_data.entries[0]
                    if hasattr(first_entry, "source") and first_entry.source:
                        feed_name = first_entry.source
                    elif hasattr(first_entry, "author") and first_entry.author:
                        feed_name = first_entry.author
            else:
                # Feed is malformed or invalid
                feed_status = "invalid"
        except Exception as e:
            # Check if it's a network error (404, etc.)
            if "404" in str(e) or "Not Found" in str(e):
                feed_status = "not_found"
            else:
                feed_status = "error"

        # If we still don't have a name, use domain name as fallback
        if not feed_name or feed_name.strip() == "":
            try:
                from urllib.parse import urlparse

                domain = urlparse(feed_url).netloc
                # Create a more descriptive name from domain
                if domain:
                    if feed_status == "not_found":
                        feed_name = f"[DISCONTINUED] Feed from {domain}"
                    elif feed_status == "invalid":
                        feed_name = f"[INVALID] Feed from {domain}"
                    else:
                        feed_name = f"Feed from {domain}"
                else:
                    feed_name = "Unnamed Feed"
            except Exception:
                feed_name = "Unnamed Feed"

        allowed = 1 if is_robot_allowed(feed_url) else 0
        s.execute(
            text(
                """
        INSERT INTO feeds(url, name, robots_allowed) VALUES(:u, :name, :allowed)
        """
            ),
            {"u": feed_url, "name": feed_name, "allowed": allowed},
        )
        fid = s.execute(
            text("SELECT id FROM feeds WHERE url=:u"), {"u": feed_url}
        ).scalar()
        return int(fid)


def list_feeds() -> Iterable[Tuple[int, str, Optional[str], Optional[str], int, int]]:
    with session_scope() as s:
        rows = s.execute(
            text(
                "SELECT id, url, etag, last_modified, robots_allowed, disabled FROM feeds"
            )
        ).all()
        for r in rows:
            yield int(r[0]), r[1], r[2], r[3], int(r[4]), int(r[5])


def add_feed(url: str) -> int:
    return ensure_feed(url)


def calculate_health_score(
    fetch_count: int,
    success_count: int,
    consecutive_failures: int,
    avg_response_time_ms: float,
) -> float:
    """Calculate a health score (0-100) based on various metrics."""
    if fetch_count == 0:
        return 100.0

    # Base success rate (0-70 points)
    success_rate = success_count / fetch_count
    success_points = success_rate * 70

    # Consecutive failures penalty (0-20 point deduction)
    failure_penalty = min(consecutive_failures * 5, 20)

    # Response time scoring (0-10 points)
    # Fast: <500ms = 10pts, Medium: 500-2000ms = 5pts, Slow: >2000ms = 0pts
    if avg_response_time_ms < 500:
        response_points = 10
    elif avg_response_time_ms < 2000:
        response_points = 5
    else:
        response_points = 0

    health_score = success_points - failure_penalty + response_points
    return max(0, min(100, health_score))


def update_feed_health_metrics(
    feed_id: int, success: bool, response_time_ms: float, error_message: str = None
):
    """Update feed health metrics after a fetch attempt."""
    with session_scope() as s:
        # Get current metrics
        current = s.execute(
            text(
                """
                SELECT fetch_count, success_count, consecutive_failures, 
                       avg_response_time_ms, last_success_at
                FROM feeds WHERE id = :feed_id
            """
            ),
            {"feed_id": feed_id},
        ).fetchone()

        if not current:
            return

        fetch_count = (current[0] or 0) + 1
        success_count = (current[1] or 0) + (1 if success else 0)
        consecutive_failures = 0 if success else (current[2] or 0) + 1

        # Update moving average for response time (weighted towards recent)
        current_avg = current[3] or 0.0
        if fetch_count == 1:
            new_avg = response_time_ms
        else:
            # Exponential moving average with 0.2 weight for new value
            new_avg = (current_avg * 0.8) + (response_time_ms * 0.2)

        # Calculate new health score
        health_score = calculate_health_score(
            fetch_count, success_count, consecutive_failures, new_avg
        )

        # Update metrics
        update_fields = [
            "fetch_count = :fetch_count",
            "success_count = :success_count",
            "consecutive_failures = :consecutive_failures",
            "avg_response_time_ms = :avg_response_time_ms",
            "last_response_time_ms = :last_response_time_ms",
            "health_score = :health_score",
            "last_fetch_at = CURRENT_TIMESTAMP",
        ]

        update_params = {
            "feed_id": feed_id,
            "fetch_count": fetch_count,
            "success_count": success_count,
            "consecutive_failures": consecutive_failures,
            "avg_response_time_ms": new_avg,
            "last_response_time_ms": response_time_ms,
            "health_score": health_score,
        }

        if success:
            update_fields.append("last_success_at = CURRENT_TIMESTAMP")
            update_fields.append("last_error = NULL")
        elif error_message:
            update_fields.append("last_error = :last_error")
            update_params["last_error"] = error_message[
                :500
            ]  # Limit error message length

        sql = f"UPDATE feeds SET {', '.join(update_fields)} WHERE id = :feed_id"
        s.execute(text(sql), update_params)


def import_opml(path: str) -> int:
    """
    Import OPML file from filesystem path.
    Used for auto-import on startup from data/feeds.opml.

    Returns: Number of feeds added
    """
    import logging

    logger = logging.getLogger(__name__)

    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()

        result = import_opml_content(content)
        logger.info(
            f"Auto-import from {path}: {result['added']} added, {result['skipped']} skipped, {result['errors']} errors"
        )
        return result["added"]

    except FileNotFoundError:
        # Silently ignore if file doesn't exist (normal on first run)
        return 0
    except Exception as e:
        logger.error(f"Failed to import OPML from {path}: {e}")
        return 0


def import_opml_content(opml_content: str) -> dict:
    """Enhanced OPML import with detailed parsing and metadata extraction."""
    import xml.etree.ElementTree as ET
    from urllib.parse import urlparse

    result = {
        "feeds_added": 0,
        "feeds_updated": 0,
        "feeds_skipped": 0,
        "errors": [],
        "categories_found": [],
    }

    try:
        # Parse XML content
        root = ET.fromstring(opml_content)

        # Find all outline elements with xmlUrl (feed entries)
        feed_outlines = root.findall(".//outline[@xmlUrl]")
        categories = set()

        with session_scope() as s:
            for outline in feed_outlines:
                try:
                    xml_url = outline.get("xmlUrl")
                    html_url = outline.get("htmlUrl", "")
                    title = outline.get("title", outline.get("text", ""))
                    description = outline.get("description", "")
                    category = outline.get("category", "")

                    # Extract category from parent outline if not set
                    if not category:
                        parent = outline.getparent()
                        if parent is not None and parent.get("text"):
                            category = parent.get("text")

                    if category:
                        categories.add(category)

                    # Check if feed already exists
                    existing = s.execute(
                        text("SELECT id FROM feeds WHERE url = :url"), {"url": xml_url}
                    ).fetchone()

                    if existing:
                        # Update existing feed with metadata if available
                        if title or description or category:
                            s.execute(
                                text(
                                    """
                                    UPDATE feeds 
                                    SET name = COALESCE(:name, name),
                                        description = COALESCE(:description, description),
                                        category = COALESCE(:category, category),
                                        updated_at = CURRENT_TIMESTAMP
                                    WHERE url = :url
                                """
                                ),
                                {
                                    "name": title if title else None,
                                    "description": description if description else None,
                                    "category": category if category else None,
                                    "url": xml_url,
                                },
                            )
                            result["feeds_updated"] += 1
                        else:
                            result["feeds_skipped"] += 1
                    else:
                        # Add new feed
                        feed_id = ensure_feed(xml_url)

                        # Update with metadata
                        if title or description or category:
                            s.execute(
                                text(
                                    """
                                    UPDATE feeds 
                                    SET name = :name, description = :description, 
                                        category = :category, updated_at = CURRENT_TIMESTAMP
                                    WHERE id = :feed_id
                                """
                                ),
                                {
                                    "name": title if title else None,
                                    "description": description if description else None,
                                    "category": category if category else None,
                                    "feed_id": feed_id,
                                },
                            )

                        result["feeds_added"] += 1

                except Exception as e:
                    result["errors"].append(
                        f"Error processing feed {xml_url}: {str(e)}"
                    )
                    continue

        result["categories_found"] = sorted(list(categories))

    except ET.ParseError as e:
        result["errors"].append(f"Invalid OPML format: {str(e)}")
    except Exception as e:
        result["errors"].append(f"Import error: {str(e)}")

    return result


def export_opml() -> str:
    """Generate OPML export of all feeds with metadata."""
    import xml.etree.ElementTree as ET
    from datetime import datetime

    # Create OPML structure
    opml = ET.Element("opml", version="2.0")

    # Head section
    head = ET.SubElement(opml, "head")
    ET.SubElement(head, "title").text = "NewsBrief Feed Export"
    ET.SubElement(head, "dateCreated").text = datetime.now().strftime(
        "%a, %d %b %Y %H:%M:%S %z"
    )
    ET.SubElement(head, "generator").text = "NewsBrief RSS Reader"

    # Body section
    body = ET.SubElement(opml, "body")

    # Get all feeds organized by category
    with session_scope() as s:
        # Get feeds grouped by category
        feeds_result = s.execute(
            text(
                """
                SELECT url, name, description, category, disabled, created_at,
                       COUNT(i.id) as article_count
                FROM feeds f
                LEFT JOIN items i ON f.id = i.feed_id  
                ORDER BY category, name, url
            """
            )
        ).fetchall()

        feeds_by_category = {}
        uncategorized_feeds = []

        for feed in feeds_result:
            category = feed.category if feed.category else None
            feed_data = dict(feed._mapping)

            if category:
                if category not in feeds_by_category:
                    feeds_by_category[category] = []
                feeds_by_category[category].append(feed_data)
            else:
                uncategorized_feeds.append(feed_data)

        # Add categorized feeds
        for category, feeds in feeds_by_category.items():
            category_outline = ET.SubElement(
                body, "outline", text=category, title=category
            )

            for feed in feeds:
                feed_attrs = {
                    "type": "rss",
                    "xmlUrl": feed["url"],
                    "text": feed["name"] if feed["name"] else feed["url"],
                    "title": feed["name"] if feed["name"] else feed["url"],
                }

                if feed["description"]:
                    feed_attrs["description"] = feed["description"]

                # Add metadata as custom attributes
                feed_attrs["nb:articleCount"] = str(feed["article_count"])
                feed_attrs["nb:disabled"] = str(bool(feed["disabled"])).lower()
                feed_attrs["nb:added"] = (
                    feed["created_at"].isoformat() if feed["created_at"] else ""
                )

                ET.SubElement(category_outline, "outline", **feed_attrs)

        # Add uncategorized feeds
        if uncategorized_feeds:
            for feed in uncategorized_feeds:
                feed_attrs = {
                    "type": "rss",
                    "xmlUrl": feed["url"],
                    "text": feed["name"] if feed["name"] else feed["url"],
                    "title": feed["name"] if feed["name"] else feed["url"],
                }

                if feed["description"]:
                    feed_attrs["description"] = feed["description"]

                # Add metadata
                feed_attrs["nb:articleCount"] = str(feed["article_count"])
                feed_attrs["nb:disabled"] = str(bool(feed["disabled"])).lower()
                feed_attrs["nb:added"] = (
                    feed["created_at"].isoformat() if feed["created_at"] else ""
                )

                ET.SubElement(body, "outline", **feed_attrs)

    # Convert to string with pretty formatting
    ET.indent(opml, space="  ", level=0)
    return ET.tostring(opml, encoding="unicode", xml_declaration=True)


def fetch_and_store() -> RefreshStats:
    """
    Iterate all feeds, use ETag/Last-Modified. Respect robots_allowed/disabled.
    Implements fair distribution, configurable limits, and comprehensive reporting.
    """
    start_time = time.time()

    # Clear robots.txt cache at start of each refresh cycle
    global _robots_txt_cache
    _robots_txt_cache = {}

    # Initialize statistics tracking
    stats = RefreshStats(
        total_items=0,
        total_feeds_processed=0,
        feeds_skipped_disabled=0,
        feeds_skipped_robots=0,
        feeds_cached_304=0,
        feeds_error=0,
        items_per_feed={},
        refresh_time_seconds=0.0,
        hit_global_limit=False,
        hit_time_limit=False,
        robots_txt_blocked_articles=0,
    )

    with httpx.Client(
        timeout=HTTP_TIMEOUT,
        headers={"User-Agent": "newsbrief/0.1"},
        verify=certifi.where(),  # Use bundled SSL certificates
    ) as client:
        for fid, url, etag, last_mod, robots_allowed, disabled in list_feeds():
            # Check time limit
            elapsed = time.time() - start_time
            if elapsed > MAX_REFRESH_TIME_SECONDS:
                stats.hit_time_limit = True
                break

            # Track feed-specific statistics
            stats.items_per_feed[fid] = 0

            # Skip disabled feeds
            if disabled:
                stats.feeds_skipped_disabled += 1
                continue

            # Skip feeds blocked by robots.txt
            if not robots_allowed:
                stats.feeds_skipped_robots += 1
                continue

            # Prepare cache headers
            headers = {}
            if etag:
                headers["If-None-Match"] = etag
            if last_mod:
                headers["If-Modified-Since"] = last_mod

            # Fetch feed with response time tracking
            fetch_start_time = time.time()
            fetch_success = False
            error_message = None

            try:
                resp = client.get(url, headers=headers)
                response_time_ms = (time.time() - fetch_start_time) * 1000

                # Handle cached response (still considered successful)
                if resp.status_code == 304:
                    stats.feeds_cached_304 += 1
                    fetch_success = True
                    update_feed_health_metrics(fid, True, response_time_ms)
                    continue

                # Handle error responses
                if resp.status_code >= 400:
                    stats.feeds_error += 1
                    fetch_success = False
                    error_message = f"HTTP {resp.status_code}: {resp.reason_phrase}"
                    update_feed_health_metrics(
                        fid, False, response_time_ms, error_message
                    )
                    continue

                # Success case
                fetch_success = True
                update_feed_health_metrics(fid, True, response_time_ms)

            except Exception as e:
                response_time_ms = (time.time() - fetch_start_time) * 1000
                stats.feeds_error += 1
                fetch_success = False
                error_message = f"Connection error: {str(e)}"
                update_feed_health_metrics(fid, False, response_time_ms, error_message)
                continue

            # Successfully fetched feed
            stats.total_feeds_processed += 1

            # Update caching headers
            new_etag = resp.headers.get("ETag")
            new_last_mod = resp.headers.get("Last-Modified")

            # Parse feed
            parsed = feedparser.parse(resp.content)

            # Store headers and update feed statistics
            # Calculate rolling average response time: new_avg = (old_avg * count + new_value) / (count + 1)
            with session_scope() as s:
                # Get current average for rolling calculation
                current_data = s.execute(
                    text(
                        "SELECT success_count, avg_response_time_ms FROM feeds WHERE id = :id"
                    ),
                    {"id": fid},
                ).first()

                if current_data:
                    prev_success_count = current_data[0] or 0
                    prev_avg = current_data[1] or 0
                    # Calculate new rolling average
                    new_avg = int(
                        (prev_avg * prev_success_count + response_time_ms)
                        / (prev_success_count + 1)
                    )
                else:
                    new_avg = response_time_ms

                s.execute(
                    text(
                        """
                    UPDATE feeds SET 
                        etag=:e, 
                        last_modified=:lm, 
                        updated_at=CURRENT_TIMESTAMP,
                        last_fetch_at=CURRENT_TIMESTAMP,
                        fetch_count=fetch_count + 1,
                        success_count=success_count + 1,
                        last_success_at=CURRENT_TIMESTAMP,
                        consecutive_failures=0,
                        last_response_time_ms=:response_time,
                        avg_response_time_ms=:avg_response_time
                    WHERE id=:id
                """
                    ),
                    {
                        "e": new_etag,
                        "lm": new_last_mod,
                        "id": fid,
                        "response_time": response_time_ms,
                        "avg_response_time": new_avg,
                    },
                )

            # Process feed entries with per-feed limit for fairness
            for entry in parsed.entries:
                # Check global limit
                if stats.total_items >= MAX_ITEMS_PER_REFRESH:
                    stats.hit_global_limit = True
                    break

                # Check per-feed limit for fairness
                if stats.items_per_feed[fid] >= MAX_ITEMS_PER_FEED:
                    break

                # Check time limit
                elapsed = time.time() - start_time
                if elapsed > MAX_REFRESH_TIME_SECONDS:
                    stats.hit_time_limit = True
                    break

                link = entry.get("link") or entry.get("id")
                if not link:
                    continue

                h = url_hash(link)

                # Skip if exists
                with session_scope() as s:
                    exists = s.execute(
                        text("SELECT 1 FROM items WHERE url_hash=:h"), {"h": h}
                    ).first()
                    if exists:
                        continue

                title = entry.get("title") or ""
                author = None
                published = None
                for key in ("published_parsed", "updated_parsed"):
                    if entry.get(key):
                        try:
                            published = datetime.fromtimestamp(time.mktime(entry[key]))
                            break
                        except Exception:
                            pass

                # Initial summary (feed-provided, sanitized for safety)
                summary = sanitize_html(entry.get("summary") or "")

                # Fetch article page for full text (best-effort)
                content_text = None
                try:
                    # Check robots.txt before fetching article content
                    if is_article_url_allowed(link):
                        page = client.get(
                            link, follow_redirects=True, timeout=HTTP_TIMEOUT
                        )
                        if page.status_code < 400 and page.headers.get(
                            "content-type", ""
                        ).startswith(("text/html", "application/xhtml")):
                            _, content_text = extract_readable(page.text)
                    else:
                        stats.robots_txt_blocked_articles += 1
                        # If robots.txt disallows, content_text remains None (graceful degradation)
                except Exception:
                    pass

                # Calculate content hash for AI caching
                content_hash = create_content_hash(title, content_text or summary or "")

                # Classify article topic (v0.4.0)
                topic_result = classify_article_topic(
                    title=title or "",
                    content=content_text or summary or "",
                    use_llm_fallback=False,  # Use keywords only for feed ingestion performance
                )

                # Calculate ranking score (v0.4.0)
                ranking_result = calculate_ranking_score(
                    published=published,
                    source_weight=1.0,  # Default source weight, can be customized per feed later
                    title=title or "",
                    content=content_text or summary or "",
                    topic=topic_result.topic,
                )

                # Insert item with ranking data
                with session_scope() as s:
                    # Calculate ranking and topic classification
                    article_data = {
                        "title": title,
                        "content": content_text,
                        "summary": summary,
                        "published": published.isoformat() if published else None,
                        "url": link,
                    }

                    ranking_score = _calculate_ranking_score_legacy(
                        article_data, source_weight=1.0
                    )
                    topic, topic_confidence = classify_topic(article_data)

                    s.execute(
                        text(
                            """
                    INSERT INTO items(feed_id, title, url, url_hash, published, author, summary, content, content_hash, ranking_score, topic, topic_confidence, source_weight)
                    VALUES(:feed_id, :title, :url, :url_hash, :published, :author, :summary, :content, :content_hash, :ranking_score, :topic, :topic_confidence, :source_weight)
                    """
                        ),
                        {
                            "feed_id": fid,
                            "title": title,
                            "url": link,
                            "url_hash": h,
                            "published": published.isoformat() if published else None,
                            "author": author,
                            "summary": summary,
                            "content": content_text,
                            "content_hash": content_hash,
                            # Ranking fields (v0.4.0)
                            "ranking_score": ranking_score,
                            "topic": topic,
                            "topic_confidence": topic_confidence,
                            "source_weight": 1.0,
                        },
                    )

                stats.total_items += 1
                stats.items_per_feed[fid] += 1

            # Break outer loop if limits hit
            if stats.hit_global_limit or stats.hit_time_limit:
                break

    # Record final timing
    stats.refresh_time_seconds = time.time() - start_time

    # Update health scores for all feeds after refresh
    try:
        update_feed_health_scores()
    except Exception as e:
        # Don't fail the entire refresh if health score update fails
        import logging

        logger = logging.getLogger(__name__)
        logger.warning(f"Failed to update health scores: {e}")

    return stats


def _calculate_ranking_score_legacy(
    article_data: dict, source_weight: float = 1.0
) -> float:
    """Calculate ranking score for an article (legacy version)."""
    score = 0.0

    # Base score from source weight
    score += source_weight

    # Recency boost (newer articles get much higher scores)
    if article_data.get("published"):
        try:
            from datetime import datetime, timezone

            published = datetime.fromisoformat(
                article_data["published"].replace("Z", "+00:00")
            )
            now = datetime.now(timezone.utc)
            days_old = (now - published).days

            # More aggressive recency scoring for better differentiation
            if days_old <= 0:  # Today
                score += 20.0
            elif days_old <= 1:  # Yesterday
                score += 15.0
            elif days_old <= 3:  # Last 3 days
                score += 10.0
            elif days_old <= 7:  # Last week
                score += 5.0
            elif days_old <= 30:  # Last month
                score += 2.0
            else:  # Older
                score += 0.5
        except:
            pass

    # Title quality boost (longer, more descriptive titles)
    title = article_data.get("title", "")
    if len(title) > 100:
        score += 2.0
    elif len(title) > 50:
        score += 1.0
    elif len(title) < 20:
        score -= 0.5  # Penalty for very short titles

    # Content quality boost
    content = article_data.get("content", "") or ""
    if len(content) > 5000:
        score += 3.0
    elif len(content) > 2000:
        score += 2.0
    elif len(content) > 1000:
        score += 1.0
    elif len(content) < 200:
        score -= 1.0  # Penalty for very short content

    # Source quality boost (some sources are more reliable)
    url = article_data.get("url", "")
    if any(
        domain in url.lower()
        for domain in [
            "github.com",
            "stackoverflow.com",
            "arstechnica.com",
            "techcrunch.com",
        ]
    ):
        score += 2.0
    elif any(domain in url.lower() for domain in ["bbc.co.uk", "cnn.com", "npr.org"]):
        score += 1.0

    return max(score, 0.1)  # Ensure minimum positive score


def classify_topic(article_data: dict) -> tuple[str, float]:
    """
    Classify article topic using the unified topic classification service.

    This is a compatibility wrapper for the new centralized topic system.
    Uses keyword-based classification for feed ingestion (faster).
    LLM classification is available for reclassification operations.

    Args:
        article_data: Dictionary with 'title', 'content', 'summary' keys

    Returns:
        Tuple of (topic_id, confidence)
    """
    title = article_data.get("title", "") or ""
    content = article_data.get("content", "") or ""
    summary = article_data.get("summary", "") or ""

    # Use unified topic service (keywords only for ingestion performance)
    result = classify_topic_unified(
        title=title,
        summary=f"{content} {summary}".strip(),
        use_llm=False,  # Use keywords for feed ingestion (faster)
    )

    return result.topic, result.confidence


def recalculate_rankings_and_topics() -> dict:
    """Recalculate ranking scores and topic classifications for all existing articles."""
    from sqlalchemy import text

    from .db import session_scope

    stats = {"articles_processed": 0, "topics_assigned": 0, "rankings_updated": 0}

    with session_scope() as s:
        # Get all articles that need ranking/topic updates
        rows = s.execute(
            text(
                """
                SELECT id, title, url, published, summary, content, ranking_score, topic, topic_confidence
                FROM items
                ORDER BY created_at DESC
            """
            )
        ).all()

        for row in rows:
            (
                article_id,
                title,
                url,
                published,
                summary,
                content,
                current_ranking,
                current_topic,
                current_confidence,
            ) = row

            # Prepare article data
            article_data = {
                "title": title or "",
                "content": content or "",
                "summary": summary or "",
                "published": (
                    published.isoformat()
                    if published and hasattr(published, "isoformat")
                    else str(published) if published else None
                ),
                "url": url,
            }

            # Calculate new ranking and topic
            new_ranking = _calculate_ranking_score_legacy(
                article_data, source_weight=1.0
            )
            new_topic, new_confidence = classify_topic(article_data)

            # Update the article
            s.execute(
                text(
                    """
                    UPDATE items 
                    SET ranking_score = :ranking_score, 
                        topic = :topic, 
                        topic_confidence = :topic_confidence,
                        source_weight = :source_weight
                    WHERE id = :article_id
                """
                ),
                {
                    "article_id": article_id,
                    "ranking_score": new_ranking,
                    "topic": new_topic,
                    "topic_confidence": new_confidence,
                    "source_weight": 1.0,
                },
            )

            stats["articles_processed"] += 1
            if new_topic:
                stats["topics_assigned"] += 1
            if new_ranking != current_ranking:
                stats["rankings_updated"] += 1

    return stats


def update_feed_health_scores() -> dict:
    """Update health scores for all feeds based on their metrics."""
    from sqlalchemy import text

    from .db import session_scope

    stats = {"feeds_updated": 0, "avg_health_score": 0.0}

    with session_scope() as s:
        rows = s.execute(
            text(
                """
                SELECT id, fetch_count, success_count, consecutive_failures, avg_response_time_ms
                FROM feeds
            """
            )
        ).all()

        total_health = 0.0
        for row in rows:
            (
                feed_id,
                fetch_count,
                success_count,
                consecutive_failures,
                avg_response_time_ms,
            ) = row

            health_score = calculate_health_score(
                fetch_count or 0,
                success_count or 0,
                consecutive_failures or 0,
                avg_response_time_ms,
            )

            s.execute(
                text(
                    "UPDATE feeds SET health_score = :health_score WHERE id = :feed_id"
                ),
                {"health_score": health_score, "feed_id": feed_id},
            )

            stats["feeds_updated"] += 1
            total_health += health_score

        if stats["feeds_updated"] > 0:
            stats["avg_health_score"] = total_health / stats["feeds_updated"]

    return stats


def update_feed_names() -> dict:
    """Update existing feeds with proper names from their RSS feeds."""
    from urllib.parse import urlparse

    from sqlalchemy import text

    from .db import session_scope

    stats = {"feeds_updated": 0, "feeds_failed": 0}

    with session_scope() as s:
        # Get all feeds without names or with generic names
        rows = s.execute(
            text(
                "SELECT id, url, name FROM feeds WHERE name IS NULL OR name = '' OR name LIKE 'Feed from %' OR name = 'Unnamed Feed'"
            )
        ).all()

        for row in rows:
            feed_id, feed_url, current_name = row

            # Create a descriptive name from URL domain
            feed_name = None
            try:
                domain = urlparse(feed_url).netloc
                if domain:
                    feed_name = f"Feed from {domain}"
                else:
                    feed_name = "Unnamed Feed"
            except Exception:
                feed_name = "Unnamed Feed"

            # Only update if we have a different name
            if feed_name and feed_name != current_name:
                try:
                    s.execute(
                        text("UPDATE feeds SET name = :name WHERE id = :feed_id"),
                        {"name": feed_name, "feed_id": feed_id},
                    )
                    stats["feeds_updated"] += 1
                except Exception:
                    stats["feeds_failed"] += 1

    return stats

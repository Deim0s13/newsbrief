from __future__ import annotations
import hashlib
import time
from datetime import datetime
from typing import Iterable, Optional, Tuple
import httpx
import feedparser
from sqlalchemy import text
from .db import session_scope
from .readability import extract_readable

MAX_ITEMS_PER_REFRESH = 150         # global cap per run
HTTP_TIMEOUT = 20.0                 # seconds

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
            
        return _check_robots_txt_path(robots_txt, parts.path or '/', user_agent='*')
    except Exception:
        return True  # Error = allow (fail-safe)

def _check_robots_txt_path(robots_txt: str, path: str, user_agent: str = '*') -> bool:
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
    
    for line in robots_txt.split('\n'):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
            
        if line.lower().startswith('user-agent:'):
            current_user_agent = line.split(':', 1)[1].strip()
            if current_user_agent in ('*', user_agent.lower()):
                disallow_patterns = []  # Reset for this user agent
                allow_patterns = []
        elif current_user_agent in ('*', user_agent.lower()):
            if line.lower().startswith('disallow:'):
                pattern = line.split(':', 1)[1].strip()
                if pattern:
                    disallow_patterns.append(pattern)
            elif line.lower().startswith('allow:'):
                pattern = line.split(':', 1)[1].strip()
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
    if pattern == '/':
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
            
        return _check_robots_txt_path(robots_txt, parts.path or '/', user_agent='newsbrief')
    except Exception:
        return True  # Error = allow (fail-safe)

def ensure_feed(feed_url: str) -> int:
    with session_scope() as s:
        row = s.execute(text("SELECT id FROM feeds WHERE url=:u"), {"u": feed_url}).first()
        if row:
            return int(row[0])
        allowed = 1 if is_robot_allowed(feed_url) else 0
        s.execute(text("""
        INSERT INTO feeds(url, robots_allowed) VALUES(:u, :allowed)
        """), {"u": feed_url, "allowed": allowed})
        fid = s.execute(text("SELECT id FROM feeds WHERE url=:u"), {"u": feed_url}).scalar()
        return int(fid)

def list_feeds() -> Iterable[Tuple[int, str, Optional[str], Optional[str], int, int]]:
    with session_scope() as s:
        rows = s.execute(text("SELECT id, url, etag, last_modified, robots_allowed, disabled FROM feeds")).all()
        for r in rows:
            yield int(r[0]), r[1], r[2], r[3], int(r[4]), int(r[5])

def add_feed(url: str) -> int:
    return ensure_feed(url)

def import_opml(path: str) -> int:
    # super light OPML import: look for xmlUrl attributes
    import re
    added = 0
    try:
        with open(path, "r", encoding="utf-8") as f:
            txt = f.read()
        for m in re.finditer(r'xmlUrl="([^"]+)"', txt):
            try:
                ensure_feed(m.group(1))
                added += 1
            except Exception:
                pass
    except FileNotFoundError:
        pass
    return added

def fetch_and_store() -> int:
    """
    Iterate all feeds, use ETag/Last-Modified. Respect robots_allowed/disabled.
    Insert new items up to MAX_ITEMS_PER_REFRESH.
    """
    # Clear robots.txt cache at start of each refresh cycle
    global _robots_txt_cache
    _robots_txt_cache = {}
    
    inserted = 0
    with httpx.Client(timeout=HTTP_TIMEOUT, headers={"User-Agent": "newsbrief/0.1"}) as client:
        for fid, url, etag, last_mod, robots_allowed, disabled in list_feeds():
            if disabled or not robots_allowed:
                continue
            headers = {}
            if etag:
                headers["If-None-Match"] = etag
            if last_mod:
                headers["If-Modified-Since"] = last_mod

            try:
                resp = client.get(url, headers=headers)
            except Exception:
                continue

            if resp.status_code == 304:
                continue

            if resp.status_code >= 400:
                # back off temporarily by marking disabled? For now, continue.
                continue

            # update caching headers
            new_etag = resp.headers.get("ETag")
            new_last_mod = resp.headers.get("Last-Modified")

            # parse feed
            parsed = feedparser.parse(resp.content)
            # store headers
            with session_scope() as s:
                s.execute(text("""
                    UPDATE feeds SET etag=:e, last_modified=:lm, updated_at=CURRENT_TIMESTAMP WHERE id=:id
                """), {"e": new_etag, "lm": new_last_mod, "id": fid})

            for entry in parsed.entries:
                if inserted >= MAX_ITEMS_PER_REFRESH:
                    return inserted

                link = entry.get("link") or entry.get("id")
                if not link:
                    continue
                h = url_hash(link)

                # skip if exists
                with session_scope() as s:
                    exists = s.execute(text("SELECT 1 FROM items WHERE url_hash=:h"), {"h": h}).first()
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
                # initial summary (feed-provided)
                summary = entry.get("summary") or ""

                # fetch article page for full text (best-effort)
                content_text = None
                try:
                    # Check robots.txt before fetching article content
                    if is_article_url_allowed(link):
                        page = client.get(link, follow_redirects=True, timeout=HTTP_TIMEOUT)
                        if page.status_code < 400 and page.headers.get("content-type","").startswith(("text/html","application/xhtml")):
                            _, content_text = extract_readable(page.text)
                    # If robots.txt disallows, content_text remains None (graceful degradation)
                except Exception:
                    pass

                with session_scope() as s:
                    s.execute(text("""
                    INSERT INTO items(feed_id, title, url, url_hash, published, author, summary, content)
                    VALUES(:feed_id, :title, :url, :url_hash, :published, :author, :summary, :content)
                    """), {
                        "feed_id": fid,
                        "title": title,
                        "url": link,
                        "url_hash": h,
                        "published": published.isoformat() if published else None,
                        "author": author,
                        "summary": summary,
                        "content": content_text
                    })
                inserted += 1
    return inserted
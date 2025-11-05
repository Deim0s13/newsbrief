from __future__ import annotations

import hashlib
import os
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Optional, Tuple

import feedparser
import httpx
from sqlalchemy import text

from .db import session_scope
from .models import create_content_hash
from .readability import extract_readable


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
                if hasattr(feed_data.feed, 'title') and feed_data.feed.title:
                    feed_name = feed_data.feed.title
                elif hasattr(feed_data.feed, 'subtitle') and feed_data.feed.subtitle:
                    feed_name = feed_data.feed.subtitle
                elif hasattr(feed_data.feed, 'description') and feed_data.feed.description:
                    # Use first part of description as name
                    desc = feed_data.feed.description
                    feed_name = desc[:50] + "..." if len(desc) > 50 else desc
                elif feed_data.entries and len(feed_data.entries) > 0:
                    # Try to infer name from first entry's source
                    first_entry = feed_data.entries[0]
                    if hasattr(first_entry, 'source') and first_entry.source:
                        feed_name = first_entry.source
                    elif hasattr(first_entry, 'author') and first_entry.author:
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
        logger.info(f"Auto-import from {path}: {result['added']} added, {result['skipped']} skipped, {result['errors']} errors")
        return result['added']
        
    except FileNotFoundError:
        # Silently ignore if file doesn't exist (normal on first run)
        return 0
    except Exception as e:
        logger.error(f"Failed to import OPML from {path}: {e}")
        return 0


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
        timeout=HTTP_TIMEOUT, headers={"User-Agent": "newsbrief/0.1"}
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

            # Fetch feed (track response time)
            feed_start_time = time.time()
            try:
                resp = client.get(url, headers=headers)
                response_time_ms = int((time.time() - feed_start_time) * 1000)
            except Exception as e:
                response_time_ms = int((time.time() - feed_start_time) * 1000)
                stats.feeds_error += 1
                # Update failure statistics
                with session_scope() as s:
                    s.execute(
                        text(
                            """
                        UPDATE feeds SET 
                            last_fetch_at=CURRENT_TIMESTAMP,
                            fetch_count=fetch_count + 1,
                            consecutive_failures=consecutive_failures + 1,
                            last_response_time_ms=:response_time,
                            last_error=:error
                        WHERE id=:id
                    """
                        ),
                        {"id": fid, "error": str(e)[:500], "response_time": response_time_ms},
                    )
                continue

            # Handle cached response
            if resp.status_code == 304:
                stats.feeds_cached_304 += 1
                continue

            # Handle error responses
            if resp.status_code >= 400:
                stats.feeds_error += 1
                # Update failure statistics
                with session_scope() as s:
                    s.execute(
                        text(
                            """
                        UPDATE feeds SET 
                            last_fetch_at=CURRENT_TIMESTAMP,
                            fetch_count=fetch_count + 1,
                            consecutive_failures=consecutive_failures + 1,
                            last_response_time_ms=:response_time,
                            last_error=:error
                        WHERE id=:id
                    """
                        ),
                        {"id": fid, "error": f"HTTP {resp.status_code}: {resp.reason_phrase}", "response_time": response_time_ms},
                    )
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
                    text("SELECT success_count, avg_response_time_ms FROM feeds WHERE id = :id"),
                    {"id": fid}
                ).first()
                
                if current_data:
                    prev_success_count = current_data[0] or 0
                    prev_avg = current_data[1] or 0
                    # Calculate new rolling average
                    new_avg = int((prev_avg * prev_success_count + response_time_ms) / (prev_success_count + 1))
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
                        "avg_response_time": new_avg
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

                # Initial summary (feed-provided)
                summary = entry.get("summary") or ""

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

                # Insert item
                with session_scope() as s:
                    # Calculate ranking and topic classification
                    article_data = {
                        'title': title,
                        'content': content_text,
                        'summary': summary,
                        'published': published.isoformat() if published else None,
                        'url': link
                    }
                    
                    ranking_score = calculate_ranking_score(article_data, source_weight=1.0)
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


def import_opml_content(content: str) -> dict:
    """
    Import OPML content from string.
    
    Returns:
        dict with 'added', 'skipped', 'errors', and 'error_details'
    """
    import re
    import logging
    
    logger = logging.getLogger(__name__)
    
    added = 0
    skipped = 0
    errors = 0
    error_details = []
    
    try:
        # Find all xmlUrl attributes in the OPML
        feed_urls = re.findall(r'xmlUrl="([^"]+)"', content)
        
        if not feed_urls:
            logger.warning("No feeds found in OPML content")
            return {
                "added": 0,
                "skipped": 0,
                "errors": 0,
                "error_details": ["No feed URLs found in OPML file"]
            }
        
        logger.info(f"Found {len(feed_urls)} feeds in OPML")
        
        for url in feed_urls:
            try:
                # Check if feed already exists
                with session_scope() as s:
                    existing = s.execute(
                        text("SELECT id FROM feeds WHERE url=:u"), {"u": url}
                    ).first()
                    
                    if existing:
                        skipped += 1
                        logger.debug(f"Feed already exists: {url}")
                        continue
                
                # Add new feed
                ensure_feed(url)
                added += 1
                logger.info(f"Added feed: {url}")
                
            except Exception as e:
                errors += 1
                error_msg = f"{url}: {str(e)}"
                error_details.append(error_msg)
                logger.error(f"Failed to import feed {url}: {e}")
                
    except Exception as e:
        logger.error(f"Error parsing OPML content: {e}")
        return {
            "added": 0,
            "skipped": 0,
            "errors": 1,
            "error_details": [f"OPML parsing error: {str(e)}"]
        }
    
    logger.info(f"OPML import completed: {added} added, {skipped} skipped (already exist), {errors} errors")
    
    return {
        "added": added,
        "skipped": skipped,
        "errors": errors,
        "error_details": error_details[:5]  # Limit to first 5 errors
    }


def export_opml() -> str:
    """Export all feeds as OPML content."""
    feeds = list_feeds()
    
    opml_content = '''<?xml version="1.0" encoding="UTF-8"?>
<opml version="1.0">
    <head>
        <title>NewsBrief Feeds</title>
        <dateCreated>{}</dateCreated>
    </head>
    <body>
'''.format(datetime.now().strftime('%a, %d %b %Y %H:%M:%S GMT'))
    
    for feed in feeds:
        # feed is a tuple: (id, url, etag, last_modified, robots_allowed, disabled)
        feed_id, url, etag, last_modified, robots_allowed, disabled = feed
        if not disabled:
            # Use URL domain as feed name if no name available
            from urllib.parse import urlparse
            domain = urlparse(url).netloc
            feed_name = domain or 'Unnamed Feed'
            opml_content += f'''        <outline text="{feed_name}" 
            title="{feed_name}" 
            type="rss" 
            xmlUrl="{url}" />
'''
    
    opml_content += '''    </body>
</opml>'''
    
    return opml_content


def calculate_ranking_score(article_data: dict, source_weight: float = 1.0) -> float:
    """Calculate ranking score for an article."""
    score = 0.0
    
    # Base score from source weight
    score += source_weight
    
    # Recency boost (newer articles get much higher scores)
    if article_data.get('published'):
        try:
            from datetime import datetime, timezone
            published = datetime.fromisoformat(article_data['published'].replace('Z', '+00:00'))
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
    title = article_data.get('title', '')
    if len(title) > 100:
        score += 2.0
    elif len(title) > 50:
        score += 1.0
    elif len(title) < 20:
        score -= 0.5  # Penalty for very short titles
    
    # Content quality boost
    content = article_data.get('content', '') or ''
    if len(content) > 5000:
        score += 3.0
    elif len(content) > 2000:
        score += 2.0
    elif len(content) > 1000:
        score += 1.0
    elif len(content) < 200:
        score -= 1.0  # Penalty for very short content
    
    # Source quality boost (some sources are more reliable)
    url = article_data.get('url', '')
    if any(domain in url.lower() for domain in ['github.com', 'stackoverflow.com', 'arstechnica.com', 'techcrunch.com']):
        score += 2.0
    elif any(domain in url.lower() for domain in ['bbc.co.uk', 'cnn.com', 'npr.org']):
        score += 1.0
    
    return max(score, 0.1)  # Ensure minimum positive score


def classify_topic(article_data: dict) -> tuple[str, float]:
    """Classify article topic based on keywords and content."""
    title = (article_data.get('title', '') or '').lower()
    content = (article_data.get('content', '') or '').lower()
    summary = (article_data.get('summary', '') or '').lower()
    
    # Combine all text for analysis
    text = f"{title} {content} {summary}"
    
    # More specific and contextual tech keywords
    tech_keywords = {
        'ai-ml': [
            'artificial intelligence', 'machine learning', 'neural network',
            'deep learning', 'llm', 'gpt', 'chatgpt', 'claude', 'ollama', 'tensorflow',
            'pytorch', 'openai', 'anthropic', 'hugging face', 'transformer', 'nlp',
            'computer vision', 'reinforcement learning', 'data science', 'algorithm',
            'generative ai', 'large language model', 'prompt engineering', 'fine-tuning',
            'deepmind', 'stability ai', 'midjourney', 'dall-e', 'gemini', 'bard',
            'machine learning model', 'ai model', 'neural network', 'deep learning model'
        ],
        'cloud-k8s': [
            'kubernetes', 'k8s', 'docker', 'container', 'aws', 'azure',
            'google cloud', 'gcp', 'microservices', 'serverless', 'lambda',
            'terraform', 'helm', 'istio', 'prometheus', 'grafana', 'jenkins',
            'ci/cd', 'devops', 'infrastructure', 'scaling', 'load balancer',
            'dockerfile', 'pod', 'namespace', 'deployment', 'service mesh',
            'ec2', 's3', 'rds', 'elastic beanstalk', 'cloudflare', 'kubernetes cluster'
        ],
        'security': [
            'cybersecurity', 'vulnerability', 'exploit', 'malware',
            'phishing', 'ransomware', 'firewall', 'encryption', 'ssl', 'tls',
            'authentication', 'authorization', 'oauth', 'jwt', 'penetration test',
            'zero-day', 'cve', 'breach', 'privacy', 'gdpr', 'compliance',
            'security audit', 'threat detection', 'intrusion detection', 'vpn',
            'sql injection', 'xss', 'csrf', 'ddos', 'hacker', 'hacking',
            'security vulnerability', 'data breach', 'cyber attack'
        ],
        'devtools': [
            'programming', 'coding', 'software development', 'api', 'sdk',
            'framework', 'library', 'git', 'github', 'gitlab', 'vscode',
            'ide', 'debugger', 'testing', 'unit test', 'integration test',
            'code review', 'refactoring', 'agile', 'scrum', 'javascript',
            'python', 'java', 'typescript', 'react', 'vue', 'angular',
            'node.js', 'npm', 'yarn', 'webpack', 'babel', 'eslint',
            'github actions', 'pull request', 'merge conflict', 'repository',
            'software engineering', 'programming language', 'development tool'
        ],
        'chips-hardware': [
            'semiconductor', 'silicon', 'fabrication', 'transistor', 'intel', 'amd',
            'nvidia', 'arm', 'risc-v', 'cpu', 'gpu', 'processor', 'chip',
            'memory', 'ram', 'ssd', 'storage', 'motherboard', 'circuit',
            'electronics', 'quantum', 'photonics', 'neuromorphic', 'asic',
            'tsmc', 'samsung', 'micron', 'qualcomm', 'broadcom', 'apple silicon',
            'microprocessor', 'semiconductor industry', 'chip manufacturing'
        ]
    }
    
    # Calculate confidence scores for each topic
    topic_scores = {}
    for topic, keywords in tech_keywords.items():
        score = 0
        for keyword in keywords:
            if keyword in text:
                # Weight by keyword length and specificity
                weight = len(keyword) * 3  # Reduced weight to be less aggressive
                score += weight * text.count(keyword)
        topic_scores[topic] = score
    
    # Find the topic with highest score
    if not topic_scores or max(topic_scores.values()) == 0:
        return 'general', 0.0
    
    best_topic = max(topic_scores.keys(), key=lambda k: topic_scores[k])
    max_score = topic_scores[best_topic]
    
    # Much higher threshold to avoid false positives
    # Require multiple keyword matches or very specific terms
    if max_score < 75:  # Even higher threshold for precision
        return 'general', 0.0
    
    # Calculate confidence (0.0 to 1.0) - more conservative
    confidence = min(max_score / 200.0, 1.0)  # Higher normalization factor
    
    return best_topic, confidence


def recalculate_rankings_and_topics() -> dict:
    """Recalculate ranking scores and topic classifications for all existing articles."""
    from .db import session_scope
    from sqlalchemy import text
    
    stats = {
        'articles_processed': 0,
        'topics_assigned': 0,
        'rankings_updated': 0
    }
    
    with session_scope() as s:
        # Get all articles that need ranking/topic updates
        rows = s.execute(
            text("""
                SELECT id, title, url, published, summary, content, ranking_score, topic, topic_confidence
                FROM items
                ORDER BY created_at DESC
            """)
        ).all()
        
        for row in rows:
            article_id, title, url, published, summary, content, current_ranking, current_topic, current_confidence = row
            
            # Prepare article data
            article_data = {
                'title': title or '',
                'content': content or '',
                'summary': summary or '',
                'published': published.isoformat() if published and hasattr(published, 'isoformat') else str(published) if published else None,
                'url': url
            }
            
            # Calculate new ranking and topic
            new_ranking = calculate_ranking_score(article_data, source_weight=1.0)
            new_topic, new_confidence = classify_topic(article_data)
            
            # Update the article
            s.execute(
                text("""
                    UPDATE items 
                    SET ranking_score = :ranking_score, 
                        topic = :topic, 
                        topic_confidence = :topic_confidence,
                        source_weight = :source_weight
                    WHERE id = :article_id
                """),
                {
                    'article_id': article_id,
                    'ranking_score': new_ranking,
                    'topic': new_topic,
                    'topic_confidence': new_confidence,
                    'source_weight': 1.0
                }
            )
            
            stats['articles_processed'] += 1
            if new_topic:
                stats['topics_assigned'] += 1
            if new_ranking != current_ranking:
                stats['rankings_updated'] += 1
    
    return stats


def calculate_health_score(
    fetch_count: int,
    success_count: int,
    consecutive_failures: int,
    avg_response_time_ms: int | None
) -> float:
    """
    Calculate a health score (0-100) for a feed based on various metrics.
    
    Args:
        fetch_count: Total number of fetch attempts
        success_count: Number of successful fetches
        consecutive_failures: Number of consecutive recent failures
        avg_response_time_ms: Average response time in milliseconds
    
    Returns:
        Health score from 0.0 to 100.0
    """
    if fetch_count == 0:
        return 100.0  # New feeds start with perfect health
    
    # Base score from success rate (0-70 points)
    success_rate = success_count / fetch_count if fetch_count > 0 else 1.0
    base_score = success_rate * 70.0
    
    # Penalty for consecutive failures (up to -50 points)
    failure_penalty = min(consecutive_failures * 10.0, 50.0)
    
    # Bonus for good response time (0-30 points)
    response_bonus = 30.0
    if avg_response_time_ms is not None:
        if avg_response_time_ms > 5000:  # > 5 seconds
            response_bonus = 0.0
        elif avg_response_time_ms > 3000:  # > 3 seconds
            response_bonus = 10.0
        elif avg_response_time_ms > 1000:  # > 1 second
            response_bonus = 20.0
        # else: keeps full 30 points
    
    final_score = base_score - failure_penalty + response_bonus
    return max(0.0, min(100.0, final_score))


def update_feed_health_scores() -> dict:
    """Update health scores for all feeds based on their metrics."""
    from .db import session_scope
    from sqlalchemy import text
    
    stats = {
        'feeds_updated': 0,
        'avg_health_score': 0.0
    }
    
    with session_scope() as s:
        rows = s.execute(
            text("""
                SELECT id, fetch_count, success_count, consecutive_failures, avg_response_time_ms
                FROM feeds
            """)
        ).all()
        
        total_health = 0.0
        for row in rows:
            feed_id, fetch_count, success_count, consecutive_failures, avg_response_time_ms = row
            
            health_score = calculate_health_score(
                fetch_count or 0,
                success_count or 0,
                consecutive_failures or 0,
                avg_response_time_ms
            )
            
            s.execute(
                text("UPDATE feeds SET health_score = :health_score WHERE id = :feed_id"),
                {"health_score": health_score, "feed_id": feed_id}
            )
            
            stats['feeds_updated'] += 1
            total_health += health_score
        
        if stats['feeds_updated'] > 0:
            stats['avg_health_score'] = total_health / stats['feeds_updated']
    
    return stats


def update_feed_names() -> dict:
    """Update existing feeds with proper names from their RSS feeds."""
    from .db import session_scope
    from sqlalchemy import text
    
    stats = {
        'feeds_updated': 0,
        'feeds_failed': 0
    }
    
    with session_scope() as s:
        # Get all feeds without names or with generic names
        rows = s.execute(
            text("SELECT id, url, name FROM feeds WHERE name IS NULL OR name = '' OR name LIKE 'Feed from %' OR name = 'Unnamed Feed'")
        ).all()
        
        for row in rows:
            feed_id, feed_url, current_name = row
            
            # Try to get feed name from RSS feed
            feed_name = None
            try:
                import feedparser
                feed_data = feedparser.parse(feed_url)
                
                # Check if feed is valid and has content
                if feed_data.feed and not feed_data.bozo:
                    # Try multiple attributes for feed name
                    if hasattr(feed_data.feed, 'title') and feed_data.feed.title:
                        feed_name = feed_data.feed.title
                    elif hasattr(feed_data.feed, 'subtitle') and feed_data.feed.subtitle:
                        feed_name = feed_data.feed.subtitle
                    elif hasattr(feed_data.feed, 'description') and feed_data.feed.description:
                        # Use first part of description as name
                        desc = feed_data.feed.description
                        feed_name = desc[:50] + "..." if len(desc) > 50 else desc
                    elif feed_data.entries and len(feed_data.entries) > 0:
                        # Try to infer name from first entry's source
                        first_entry = feed_data.entries[0]
                        if hasattr(first_entry, 'source') and first_entry.source:
                            feed_name = first_entry.source
                        elif hasattr(first_entry, 'author') and first_entry.author:
                            feed_name = first_entry.author
            except Exception:
                pass  # Will fall back to domain name below
            
            # If we still don't have a name, use domain name as fallback
            if not feed_name or feed_name.strip() == "":
                try:
                    from urllib.parse import urlparse
                    domain = urlparse(feed_url).netloc
                    # Create a more descriptive name from domain
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
                        {"name": feed_name, "feed_id": feed_id}
                    )
                    stats['feeds_updated'] += 1
                except Exception:
                    stats['feeds_failed'] += 1
    
    return stats

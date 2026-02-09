# NewsBrief API Documentation

NewsBrief provides a RESTful API for story-based news aggregation and RSS feed management. All endpoints return JSON responses.

## 📍 Base URL

```
http://localhost:8787
```

## 📚 Interactive Documentation

NewsBrief automatically generates interactive API documentation:

- **Swagger UI**: http://localhost:8787/docs
- **ReDoc**: http://localhost:8787/redoc
- **OpenAPI Schema**: http://localhost:8787/openapi.json

## 🔗 Endpoints

### 📰 Story Endpoints (v0.5.0) ✅

Story-based aggregation endpoints for synthesized news briefs.

**Why Story-Based?** NewsBrief v0.5.0 returns to the original vision: replace reading 50+ article summaries with 5-10 synthesized stories. Instead of an article-centric RSS reader, NewsBrief now aggregates related articles into unified narratives—a true TLDR-killer. See [ADR 0002](adr/0002-story-based-aggregation.md) for full context.

**Status**:
- ✅ **Story Generation Pipeline**: Complete (Issue #39)
- ✅ **HTTP Endpoints**: Complete (Issues #47, #55)
- ✅ **Python API**: Available for advanced use cases

All story endpoints are now available via HTTP and Python APIs.

#### **GET /stories**

List all active stories (5-10 synthesized stories from last 24 hours).

**Query Parameters**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `limit` | int | 10 | Maximum stories to return (max: 50) |
| `offset` | int | 0 | Pagination offset |
| `status` | string | "active" | Filter: "active", "archived", or "all" |
| `order_by` | string | "importance" | Sort: "importance", "freshness", "generated_at" |
| `topic` | string | null | Filter by topic |
| `apply_interests` | bool | true | Apply interest-based ranking (v0.6.5) |

**Interest-Based Ranking (v0.6.5)**

When `apply_interests=true` (default), stories are ranked by a blended score combining:
- **Importance** (60%): Article count, source quality, recency
- **Interest** (40%): Topic preference weights from `data/interests.json`

This allows high-interest topics (e.g., AI/ML) to rank above higher-importance but low-interest topics (e.g., politics).

**Response (200)**
```json
{
  "stories": [
    {
      "id": 1,
      "title": "Google Announces Gemini 2.0 with Multimodal Capabilities",
      "synthesis": "Google unveiled Gemini 2.0 today...",
      "key_points": [
        "Released December 2024, available via Google AI Studio",
        "Native multimodal processing (text, image, video, audio)",
        "2x faster than Gemini 1.5 with lower latency"
      ],
      "why_it_matters": "This represents Google's most significant AI release...",
      "topics": ["AI/ML", "Cloud"],
      "entities": ["Google", "Gemini 2.0"],
      "article_count": 5,
      "importance_score": 0.92,
      "freshness_score": 0.98,
      "quality_score": 0.93,
      "title_source": "llm",
      "parse_strategy": "direct",
      "generated_at": "2024-12-06T08:00:00Z",
      "supporting_articles": [
        {
          "id": 123,
          "title": "Google's Gemini 2.0 arrives...",
          "url": "https://techcrunch.com/...",
          "published": "2024-12-06T06:30:00Z"
        }
      ]
    }
  ],
  "total": 7,
  "generated_at": "2024-12-06T08:00:00Z",
  "time_window_hours": 24
}
```

**Example**
```bash
curl http://localhost:8787/stories | jq .
```

---

#### **GET /stories/{id}**

Get detailed view of a specific story with all supporting articles.

**Parameters**
- `id` (path): Story ID

**Response (200)**
```json
{
  "story": {
    "id": 1,
    "title": "Google Announces Gemini 2.0...",
    "synthesis": "Full synthesis text...",
    "key_points": [...],
    "why_it_matters": "...",
    "topics": ["AI/ML", "Cloud"],
    "entities": ["Google", "Gemini 2.0"],
    "article_count": 5,
    "importance_score": 0.92,
    "generated_at": "2024-12-06T08:00:00Z"
  },
  "articles": [
    {
      "id": 123,
      "title": "Google's Gemini 2.0 arrives",
      "url": "https://techcrunch.com/...",
      "summary": "Article summary...",
      "published": "2024-12-06T06:30:00Z",
      "structured_summary": {...}
    }
  ]
}
```

**Example**
```bash
curl http://localhost:8787/stories/1 | jq .
```

---

#### **GET /stories/{id}/articles** ⭐ *New in v0.6.3*

Get all articles associated with a specific story. Convenience endpoint that returns articles ordered by relevance (primary articles first).

**Parameters**
- `id` (path): Story ID

**Response (200)**
```json
[
  {
    "id": 123,
    "title": "Google's Gemini 2.0 arrives with major AI improvements",
    "url": "https://techcrunch.com/...",
    "published": "2024-12-06T06:30:00Z",
    "summary": "Article summary...",
    "ai_summary": "AI-generated summary...",
    "ranking_score": 1.125,
    "topic": "ai-ml",
    "topic_confidence": 0.92
  },
  {
    "id": 124,
    "title": "Gemini 2.0 benchmarks show impressive gains",
    "url": "https://arstechnica.com/...",
    "published": "2024-12-06T07:15:00Z",
    "summary": "Benchmark analysis...",
    "ranking_score": 0.98,
    "topic": "ai-ml"
  }
]
```

**Error Response (404)**
```json
{
  "detail": "Story with ID 999 not found"
}
```

**Example**
```bash
# Get all articles for story #5
curl http://localhost:8787/stories/5/articles | jq .

# Get just titles and URLs
curl http://localhost:8787/stories/5/articles | jq '.[] | {title, url}'

# Count articles in a story
curl http://localhost:8787/stories/5/articles | jq 'length'
```

---

#### **POST /stories/generate**

Manually trigger story generation. Clusters articles from last 24 hours and generates synthesized stories.

**Request Body (optional)**
```json
{
  "hours": 24,
  "min_articles": 2,
  "max_stories": 10,
  "force_regenerate": false
}
```

**Response (200)**
```json
{
  "success": true,
  "stories_generated": 7,
  "articles_processed": 145,
  "clusters_found": 12,
  "errors": 0,
  "generation_time": 45.3
}
```

**Example**
```bash
curl -X POST http://localhost:8787/stories/generate | jq .
```

**Enhanced Synthesis Pipeline** ⭐ *New in v0.8.1*

Story synthesis now uses a multi-pass pipeline for higher quality output:

1. **Story Type Detection** - Classifies cluster as: breaking, evolving, trend, or comparison
2. **Chain-of-Thought Analysis** - Extracts timeline, core facts, tensions, key players
3. **Type-Specific Synthesis** - Generates narrative appropriate to story pattern
4. **Quality Refinement** - Self-critique and polish pass

This produces more coherent narratives with better "why it matters" sections, at the cost of longer generation time (~2 min per story vs ~20s previously).

---

#### **GET /scheduler/status** ⭐ *Updated in v0.6.3*

Get background scheduler status including feed refresh and story generation jobs.

**Response (200)**
```json
{
  "running": true,
  "timezone": "Pacific/Auckland",
  "feed_refresh": {
    "enabled": true,
    "schedule": "30 5 * * *",
    "next_run": "2026-01-02T05:30:00+13:00",
    "in_progress": false
  },
  "story_generation": {
    "schedule": "0 6 * * *",
    "next_run": "2026-01-02T06:00:00+13:00",
    "configuration": {
      "time_window_hours": 24,
      "archive_days": 7,
      "min_articles": 2,
      "model": "llama3.1:8b"
    }
  }
}
```

**Environment Variables** ⭐ *New in v0.6.3*

| Variable | Default | Description |
|----------|---------|-------------|
| `FEED_REFRESH_ENABLED` | `true` | Enable/disable scheduled feed refresh |
| `FEED_REFRESH_SCHEDULE` | `30 5 * * *` | Cron schedule for feed refresh (default: 5:30 AM) |
| `STORY_GENERATION_SCHEDULE` | `0 6 * * *` | Cron schedule for story generation (default: 6:00 AM) |
| `STORY_GENERATION_TIMEZONE` | `Pacific/Auckland` | Timezone for all scheduled jobs |

**Example**
```bash
# Check scheduler status
curl http://localhost:8787/scheduler/status | jq .

# View next scheduled runs
curl http://localhost:8787/scheduler/status | jq '{feed_refresh: .feed_refresh.next_run, story_generation: .story_generation.next_run}'
```

---

#### **GET /stories/stats**

Get story generation statistics.

**Response (200)**
```json
{
  "total_stories": 7,
  "last_generated": "2024-12-06T08:00:00Z",
  "next_scheduled": "2024-12-07T08:00:00Z",
  "avg_articles_per_story": 4.2,
  "avg_generation_time": 38.5
}
```

---

### 📁 Feed Management

### **POST /feeds**

Add a new RSS feed to the system. NewsBrief automatically checks the feed's robots.txt compliance before adding.

#### Request

```http
POST /feeds HTTP/1.1
Content-Type: application/json

{
  "url": "https://feeds.example.com/rss.xml"
}
```

#### Request Body

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `url` | string (URL) | Yes | Valid RSS/Atom feed URL |

#### Response

**Success (200)**
```json
{
  "ok": true,
  "feed_id": 42
}
```

**Validation Error (422)**
```json
{
  "detail": [
    {
      "loc": ["body", "url"],
      "msg": "invalid or missing URL scheme",
      "type": "value_error.url.scheme"
    }
  ]
}
```

#### Example

```bash
curl -X POST http://localhost:8787/feeds \
  -H "Content-Type: application/json" \
  -d '{"url": "https://feeds.bbci.co.uk/news/rss.xml"}'
```

---

## 🎨 **Feed Management Endpoints (v0.5.3)** ⭐ *NEW*

### **GET /feeds**

List all feeds with metadata, statistics, and health monitoring data.

#### Request

```http
GET /feeds HTTP/1.1
```

#### Response

**Success (200)**
```json
[
  {
    "id": 1,
    "url": "https://feeds.bbci.co.uk/news/rss.xml",
    "name": "BBC News",
    "description": "Latest news from BBC",
    "category": "News",
    "priority": 4,
    "disabled": false,
    "robots_allowed": true,
    "etag": "\"abc123\"",
    "last_modified": "Wed, 21 Oct 2025 07:28:00 GMT",
    "created_at": "2025-10-01T10:00:00Z",
    "updated_at": "2025-10-02T14:30:00Z",
    "total_articles": 156,
    "last_fetch_at": "2025-10-02T14:30:00Z",
    "last_success_at": "2025-10-02T14:30:00Z",
    "last_error": null,
    "fetch_count": 48,
    "success_count": 47,
    "consecutive_failures": 0,
    "avg_response_time_ms": 345.2,
    "last_response_time_ms": 312.1,
    "health_score": 95.5,
    "last_modified_check": "2025-10-02T14:30:00Z",
    "etag_check": "2025-10-02T14:30:00Z"
  }
]
```

### **GET /feeds/{feed_id}**

Get detailed information about a specific feed.

#### Response

**Success (200)** - Same structure as individual feed in `GET /feeds`

**Not Found (404)**
```json
{"detail": "Feed not found"}
```

### **PUT /feeds/{feed_id}**

Update an existing feed's metadata.

#### Request Body

```json
{
  "name": "Updated Feed Name",
  "description": "Updated description",
  "category": "Technology",
  "priority": 5,
  "disabled": false
}
```

### **DELETE /feeds/{feed_id}**

Delete a feed and all its associated articles.

#### Response

**Success (200)**
```json
{"message": "Feed deleted successfully"}
```

### **GET /feeds/{feed_id}/stats**

Get comprehensive statistics for a specific feed.

#### Response

**Success (200)**
```json
{
  "feed_id": 1,
  "total_articles": 156,
  "articles_last_24h": 8,
  "articles_last_7d": 42,
  "articles_last_30d": 134,
  "avg_articles_per_day": 4.47,
  "last_fetch_at": "2025-10-02T14:30:00Z",
  "last_error": null,
  "success_rate": 97.9,
  "avg_response_time_ms": 345.2
}
```

### **GET /feeds/categories**

Get all available categories with statistics.

#### Response

**Success (200)**
```json
{
  "categories": [
    {
      "name": "Technology",
      "feed_count": 12,
      "active_count": 11,
      "avg_health": 89.3,
      "total_articles": 467
    },
    {
      "name": "News",
      "feed_count": 0,
      "active_count": 0,
      "avg_health": 100.0,
      "total_articles": 0,
      "is_predefined": true
    }
  ]
}
```

### **POST /feeds/categories/bulk-assign**

Assign a category to multiple feeds at once.

#### Request Body

```json
{
  "feed_ids": [1, 2, 3],
  "category": "Technology"
}
```

#### Response

**Success (200)**
```json
{
  "success": true,
  "message": "Updated 3 feeds",
  "category": "Technology",
  "updated_feed_ids": [1, 2, 3]
}
```

### **POST /feeds/categories/bulk-priority**

Assign priority to multiple feeds at once.

#### Request Body

```json
{
  "feed_ids": [1, 2, 3],
  "priority": 4
}
```

## 📤📥 **OPML Management Endpoints (v0.5.3, updated v0.7.7)**

### **GET /feeds/export/opml**

Export all feeds as an OPML file with metadata and categories.

#### Response

**Success (200)** - Returns OPML XML file with `Content-Disposition` header for download

```xml
<?xml version='1.0' encoding='UTF-8'?>
<opml version="2.0">
  <head>
    <title>NewsBrief Feed Export</title>
    <dateCreated>Thu, 02 Oct 2025 14:30:15 +0000</dateCreated>
    <generator>NewsBrief RSS Reader</generator>
  </head>
  <body>
    <outline text="Technology" title="Technology">
      <outline type="rss" xmlUrl="https://example.com/tech.xml" text="Tech News"
               title="Tech News" description="Latest technology news"
               nb:articleCount="45" nb:disabled="false" nb:added="2025-10-01T10:00:00"/>
    </outline>
  </body>
</opml>
```

### **POST /feeds/import/opml/upload**

Import feeds from an uploaded OPML file. By default, imports are processed asynchronously to prevent timeout issues with large files.

#### Request

```http
POST /feeds/import/opml/upload HTTP/1.1
Content-Type: multipart/form-data

file: [OPML file content]
```

#### Query Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `validate` | boolean | `false` | Validate feed URLs before importing (slower) |
| `async_import` | boolean | `true` | Process import asynchronously |

#### Response

**Success (200) - Async Import** *(default)*
```json
{
  "success": true,
  "filename": "my_feeds.opml",
  "message": "Import started in background. Check /feeds/import/history for status.",
  "async": true,
  "import_id": 42,
  "details": {
    "status": "processing",
    "validation_enabled": false
  }
}
```

**Success (200) - Sync Import** *(async_import=false)*
```json
{
  "success": true,
  "filename": "my_feeds.opml",
  "message": "Import completed: 8 added, 2 updated, 1 skipped",
  "async": false,
  "details": {
    "feeds_added": 8,
    "feeds_updated": 2,
    "feeds_skipped": 1,
    "feeds_failed": 0,
    "errors": [],
    "categories_found": ["Technology", "News", "Science"]
  }
}
```

---

### **GET /feeds/import/status/{import_id}** ⭐ *NEW in v0.7.7*

Get the current status of an async import. Used for polling during imports to show progress.

#### Request

```http
GET /feeds/import/status/42 HTTP/1.1
```

#### Response

**Processing (200)**
```json
{
  "id": 42,
  "imported_at": "2026-02-03T14:30:00+00:00",
  "completed_at": null,
  "filename": "my_feeds.opml",
  "status": "processing",
  "total_feeds": 50,
  "processed_feeds": 25,
  "progress_percent": 50.0,
  "feeds_added": 20,
  "feeds_updated": 3,
  "feeds_skipped": 2,
  "feeds_failed": 0,
  "error_message": null,
  "validation_enabled": false
}
```

**Completed (200)**
```json
{
  "id": 42,
  "imported_at": "2026-02-03T14:30:00+00:00",
  "completed_at": "2026-02-03T14:30:45+00:00",
  "filename": "my_feeds.opml",
  "status": "completed",
  "total_feeds": 50,
  "processed_feeds": 50,
  "progress_percent": 100.0,
  "feeds_added": 45,
  "feeds_updated": 3,
  "feeds_skipped": 2,
  "feeds_failed": 0,
  "error_message": null,
  "validation_enabled": false
}
```

**Failed (200)**
```json
{
  "id": 42,
  "status": "failed",
  "error_message": "Invalid OPML format: mismatched tag at line 15"
}
```

**Not Found (404)**
```json
{
  "detail": "Import not found"
}
```

---

### **POST /refresh**

Fetch latest articles from all configured feeds. Only processes feeds that comply with robots.txt policies. For each article, respects robots.txt before extracting full content.

#### Request

```http
POST /refresh HTTP/1.1
```

#### Response

**Success (200)**
```json
{
  "ingested": 47,
  "stats": {
    "items": {
      "total": 47,
      "per_feed": {
        "1": 20,
        "2": 15,
        "3": 12
      },
      "robots_blocked": 3
    },
    "feeds": {
      "processed": 3,
      "skipped_disabled": 1,
      "skipped_robots": 0,
      "cached_304": 2,
      "errors": 1
    },
    "performance": {
      "refresh_time_seconds": 12.45,
      "hit_global_limit": false,
      "hit_time_limit": false
    },
    "config": {
      "max_items_per_refresh": 150,
      "max_items_per_feed": 50,
      "max_refresh_time_seconds": 300
    }
  }
}
```

#### Response Fields

| Field | Type | Description |
|-------|------|-------------|
| `ingested` | integer | **Total number of new articles added (backward compatibility)** |
| `stats` | object | **Detailed refresh statistics and performance metrics** |
| `stats.items.total` | integer | Total items ingested this refresh |
| `stats.items.per_feed` | object | Items ingested per feed ID (fair distribution tracking) |
| `stats.items.robots_blocked` | integer | Articles blocked by robots.txt policies |
| `stats.feeds.processed` | integer | Feeds successfully processed |
| `stats.feeds.skipped_disabled` | integer | Feeds skipped (disabled) |
| `stats.feeds.skipped_robots` | integer | Feeds skipped (robots.txt blocked) |
| `stats.feeds.cached_304` | integer | Feeds that returned 304 Not Modified |
| `stats.feeds.errors` | integer | Feeds with connection/parsing errors |
| `stats.performance.refresh_time_seconds` | float | Total refresh operation time |
| `stats.performance.hit_global_limit` | boolean | Whether global item limit was reached |
| `stats.performance.hit_time_limit` | boolean | Whether time limit was reached |
| `stats.config.max_items_per_refresh` | integer | Current global item limit |
| `stats.config.max_items_per_feed` | integer | Current per-feed fairness limit |
| `stats.config.max_refresh_time_seconds` | integer | Current time-based safety limit |

#### Behavior

**Feed Processing:**
- Respects ETag and Last-Modified headers for efficient caching
- Skips disabled feeds and feeds blocked by robots.txt policies
- Implements fair distribution with per-feed limits to prevent quota hogging
- Automatically deduplicates articles by URL hash

**Content Extraction:**
- Extracts readable content from article pages using Mozilla Readability
- Respects robots.txt policies before fetching individual article content
- Gracefully degrades when content extraction is blocked or fails

**Limits and Safety:**
- **Global limit**: Configurable via `NEWSBRIEF_MAX_ITEMS_PER_REFRESH` (default: 150)
- **Per-feed limit**: Configurable via `NEWSBRIEF_MAX_ITEMS_PER_FEED` (default: 50)
- **Time limit**: Configurable via `NEWSBRIEF_MAX_REFRESH_TIME` (default: 300 seconds)
- **Multiple exit conditions**: Stops when any limit is reached for predictable runtime

**Comprehensive Monitoring:**
- Tracks item distribution across feeds for fairness verification
- Records feed-level statistics (errors, caching effectiveness, robots.txt blocks)
- Provides performance metrics and limit breach detection
- Exposes runtime configuration for operational transparency

#### Example

```bash
curl -X POST http://localhost:8787/refresh
```

---

### **GET /items**

Retrieve articles from the database, ordered by relevance ranking (v0.4.0+). Articles are ranked using a combination of recency, source importance, and keyword matching.

#### Request

```http
GET /items?limit=10 HTTP/1.1
```

#### Query Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `limit` | integer | No | 50 | Number of items to return (max: 200) |
| `story_id` | integer | No | - | Filter by story ID (returns 404 if story not found) ⭐ *v0.6.3* |
| `topic` | string | No | - | Filter by topic (e.g., `ai-ml`, `security`) ⭐ *v0.6.3* |
| `feed_id` | integer | No | - | Filter by source feed ID ⭐ *v0.6.3* |
| `published_after` | datetime | No | - | Filter articles published after this date (ISO format) ⭐ *v0.6.3* |
| `published_before` | datetime | No | - | Filter articles published before this date (ISO format) ⭐ *v0.6.3* |
| `has_story` | boolean | No | - | Filter by story association (`true`/`false`) ⭐ *v0.6.3* |

#### Response

**Success (200)**
```json
[
  {
    "id": 123,
    "title": "Breaking: AI Breakthrough in Machine Learning",
    "url": "https://example.com/article/123",
    "published": "2025-09-27T10:30:00Z",
    "summary": "This is a brief summary of the article content...",
    "ai_summary": "This article covers a significant AI breakthrough with major implications for machine learning research, highlighting key developments in neural network architectures.",
    "ai_model": "llama3.2:3b",
    "ai_generated_at": "2025-09-27T10:35:15Z",
    "ranking_score": 1.125,
    "topic": "ai-ml",
    "topic_confidence": 0.85,
    "source_weight": 1.2,
    "structured_summary": {
      "bullets": [
        "Researchers develop new neural network architecture with 40% better performance",
        "Breakthrough enables more efficient training on smaller datasets",
        "Technology could revolutionize natural language processing applications"
      ],
      "why_it_matters": "This advancement represents a significant leap in AI efficiency, potentially making advanced machine learning accessible to smaller organizations and enabling new applications in fields like healthcare and education.",
      "tags": ["artificial-intelligence", "machine-learning", "neural-networks", "research", "breakthrough"],
      "content_hash": "a1b2c3d4e5f6",
      "model": "llama3.2:3b",
      "generated_at": "2025-09-27T10:35:15Z"
    },
    "fallback_summary": null,
    "is_fallback_summary": false
  },
  {
    "id": 124,
    "title": "Tech Update: New Framework Released",
    "url": "https://example.com/article/124",
    "published": "2025-09-27T09:15:00Z",
    "summary": "A comprehensive overview of the new features...",
    "ai_summary": null,
    "ai_model": null,
    "ai_generated_at": null,
    "ranking_score": 0.742,
    "topic": "devtools",
    "topic_confidence": 0.72,
    "source_weight": 1.0,
    "structured_summary": null,
    "fallback_summary": "A comprehensive overview of the new features in this developer framework. The latest release includes several performance improvements and new APIs.",
    "is_fallback_summary": true
  }
]
```

#### Item Object ⭐ *Updated in v0.4.0*

| Field | Type | Description |
|-------|------|-------------|
| `id` | integer | Unique article identifier |
| `title` | string or null | Article title |
| `url` | string | Original article URL |
| `published` | string (ISO 8601) or null | Publication timestamp |
| `summary` | string or null | Article summary or excerpt from RSS feed |
| `ai_summary` | string or null | AI-generated intelligent summary (legacy) |
| `ai_model` | string or null | Model used for AI summary generation (legacy) |
| `ai_generated_at` | string (ISO 8601) or null | When AI summary was created (legacy) |
| `structured_summary` | object or null | Structured AI summary with bullets, significance, and tags |
| `fallback_summary` | string or null | First 2 sentences when AI summary unavailable |
| `is_fallback_summary` | boolean | Whether the primary summary is a fallback |
| **`ranking_score`** ⭐ | **number** | **Calculated relevance score for article ranking** |
| **`topic`** ⭐ | **string or null** | **Classified article topic (ai-ml, cloud-k8s, security, devtools, chips-hardware)** |
| **`topic_confidence`** ⭐ | **number** | **Classification confidence level (0.0-1.0)** |
| **`source_weight`** ⭐ | **number** | **Importance weight of the source feed** |

#### Example ⭐ *Enhanced in v0.4.0, v0.6.3*

```bash
# Get top-ranked articles (default behavior in v0.4.0+)
curl "http://localhost:8787/items?limit=5" | jq .

# Get latest 50 articles (default, ordered by ranking_score)
curl http://localhost:8787/items

# ⭐ NEW: View article ranking and topic data
curl "http://localhost:8787/items?limit=5" | jq '.[] | {id, title, ranking_score, topic, topic_confidence}'

# Extract structured summaries from top articles
curl "http://localhost:8787/items?limit=5" | jq '.[] | select(.structured_summary != null) | {id, title, ranking_score, bullets: .structured_summary.bullets, tags: .structured_summary.tags}'

# Find high-confidence AI/ML articles
curl "http://localhost:8787/items?limit=20" | jq '.[] | select(.topic == "ai-ml" and .topic_confidence > 0.8) | {id, title, ranking_score, topic_confidence}'

# Compare ranking scores and topics
curl "http://localhost:8787/items?limit=10" | jq '.[] | {title: .title[:60], score: .ranking_score, topic, confidence: .topic_confidence}'

# ⭐ NEW v0.6.3: Filter by story ID (get articles in a specific story)
curl "http://localhost:8787/items?story_id=5" | jq '.[] | {id, title}'

# ⭐ NEW v0.6.3: Filter by topic
curl "http://localhost:8787/items?topic=security&limit=10" | jq .

# ⭐ NEW v0.6.3: Filter by feed source
curl "http://localhost:8787/items?feed_id=3&limit=20" | jq .

# ⭐ NEW v0.6.3: Filter by date range
curl "http://localhost:8787/items?published_after=2026-01-01T00:00:00&published_before=2026-01-15T23:59:59" | jq .

# ⭐ NEW v0.6.3: Get articles that are part of stories
curl "http://localhost:8787/items?has_story=true&limit=20" | jq .

# ⭐ NEW v0.6.3: Get orphan articles (not in any story)
curl "http://localhost:8787/items?has_story=false&limit=20" | jq .

# ⭐ NEW v0.6.3: Combine filters
curl "http://localhost:8787/items?topic=ai-ml&has_story=true&limit=10" | jq .
```

---

## 🎯 Article Ranking & Topic Endpoints ⭐ *New in v0.4.0*

### **GET /topics**

Get available article topic categories and their descriptions.

#### Request

```http
GET /topics HTTP/1.1
```

#### Response

**Success (200)**
```json
{
  "topics": [
    {
      "key": "ai-ml",
      "name": "AI/ML"
    },
    {
      "key": "cloud-k8s",
      "name": "Cloud/K8s"
    },
    {
      "key": "security",
      "name": "Security"
    },
    {
      "key": "devtools",
      "name": "DevTools"
    },
    {
      "key": "chips-hardware",
      "name": "Chips/Hardware"
    }
  ],
  "description": "Available topic categories for article classification"
}
```

#### Example

```bash
# Get all available topics
curl http://localhost:8787/topics | jq .

# Extract just topic names
curl http://localhost:8787/topics | jq '.topics[] | .name'
```

---

### **GET /items/topic/{topic_key}**

Get articles filtered by topic, ordered by ranking score (highest relevance first).

#### Request

```http
GET /items/topic/ai-ml?limit=10 HTTP/1.1
```

#### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `topic_key` | string | Yes | Topic key (ai-ml, cloud-k8s, security, devtools, chips-hardware) |

#### Query Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `limit` | integer | No | 50 | Number of items to return (max: 200) |

#### Response

**Success (200)**
```json
{
  "topic": "ai-ml",
  "display_name": "AI/ML",
  "count": 15,
  "items": [
    {
      "id": 123,
      "title": "Revolutionary Neural Network Architecture Breakthrough",
      "url": "https://example.com/ai-breakthrough",
      "published": "2025-09-27T10:30:00Z",
      "ranking_score": 1.245,
      "topic": "ai-ml",
      "topic_confidence": 0.92,
      "source_weight": 1.2,
      "structured_summary": {
        "bullets": [
          "New transformer architecture achieves 40% better performance",
          "Breakthrough enables training on 70% less data",
          "Open-source implementation available on GitHub"
        ],
        "why_it_matters": "This advancement democratizes access to state-of-the-art AI models, potentially accelerating innovation across industries while reducing computational costs.",
        "tags": ["neural-networks", "transformers", "efficiency", "open-source"]
      }
    }
  ]
}
```

#### Example

```bash
# Get AI/ML articles
curl http://localhost:8787/items/topic/ai-ml | jq .

# Get top 5 security articles with rankings
curl "http://localhost:8787/items/topic/security?limit=5" | jq '.items[] | {title, ranking_score, topic_confidence}'

# Compare topics by article count
for topic in ai-ml cloud-k8s security devtools chips-hardware; do
  count=$(curl -s "http://localhost:8787/items/topic/$topic?limit=1" | jq .count)
  echo "$topic: $count articles"
done
```

---

### **POST /ranking/recalculate**

Recalculate ranking scores and topic classifications for all articles. Useful when tuning the ranking algorithm or after bulk data imports.

#### Request

```http
POST /ranking/recalculate HTTP/1.1
```

#### Response

**Success (200)**
```json
{
  "success": true,
  "updated_items": 1247,
  "message": "Recalculated rankings for 1247 articles"
}
```

#### Example

```bash
# Recalculate all article rankings
curl -X POST http://localhost:8787/ranking/recalculate | jq .

# Monitor progress (rankings are updated in database immediately)
curl http://localhost:8787/items?limit=5 | jq '.[] | {id, title, ranking_score}'
```

---

## 🤖 AI Summarization Endpoints

### **GET /llm/status**

Check the status and availability of the LLM (Large Language Model) service for AI summarization.

#### Request

```http
GET /llm/status HTTP/1.1
```

#### Response

**Success (200)**
```json
{
  "available": true,
  "base_url": "http://host.containers.internal:11434",
  "current_model": "llama3.2:3b",
  "models_available": ["llama3.2:3b", "mistral:7b"],
  "error": null
}
```

#### Response Fields

| Field | Type | Description |
|-------|------|-------------|
| `available` | boolean | Whether the LLM service is accessible |
| `base_url` | string | Ollama service base URL |
| `current_model` | string | Currently configured default model |
| `models_available` | array | List of available model names |
| `error` | string or null | Error message if service unavailable |

#### Example

```bash
# Check LLM service status
curl http://localhost:8787/llm/status | jq .
```

---

### **POST /summarize**

Generate AI-powered summaries for one or more articles using local LLM integration.

#### Request

```http
POST /summarize HTTP/1.1
Content-Type: application/json

{
  "item_ids": [1, 2, 3],
  "model": "llama3.2:3b",
  "force_regenerate": false,
  "use_structured": true
}
```

#### Request Body

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `item_ids` | array | ✅ | Array of article IDs to summarize |
| `model` | string | ❌ | Optional model override (uses default if not specified) |
| `force_regenerate` | boolean | ❌ | Force regenerate even if summary exists (default: false) |
| `use_structured` | boolean | ❌ | Generate structured JSON summaries (default: true) |

#### Response

**Success (200) - Structured Summary (default)**
```json
{
  "success": true,
  "summaries_generated": 2,
  "errors": 0,
  "results": [
    {
      "item_id": 1,
      "success": true,
      "summary": "{\"bullets\": [\"AI companies are not profitable...\"], \"why_it_matters\": \"This development...\", \"tags\": [\"ai\", \"technology\"]}",
      "model": "llama3.2:3b",
      "error": null,
      "tokens_used": 1245,
      "generation_time": 8.32,
      "structured_summary": {
        "bullets": [
          "AI companies are not profitable and rely on investors' money to stay afloat",
          "The AI industry's growth is driven by replacing workers with AI, leading to job losses",
          "The sector's financials are unsustainable, with massive debt and accounting irregularities"
        ],
        "why_it_matters": "The impending AI apocalypse poses significant economic risks, threatening the livelihoods of millions and reshaping the global economy as investors and policymakers need to address this issue before it's too late.",
        "tags": ["ai-apocalypse", "economic-risks", "job-market-disruption", "financial-stability"],
        "content_hash": "a1b2c3d4e5f6789a",
        "model": "llama3.2:3b",
        "generated_at": "2024-01-15T15:45:22Z"
      },
      "content_hash": "a1b2c3d4e5f6789a",
      "cache_hit": false
    },
    {
      "item_id": 2,
      "success": true,
      "summary": "{\"bullets\": [\"Flash Attention 4 achieves...\"], \"why_it_matters\": \"This breakthrough...\", \"tags\": [\"gpu\", \"performance\"]}",
      "model": "llama3.2:3b",
      "error": null,
      "tokens_used": 987,
      "generation_time": 6.15,
      "structured_summary": {
        "bullets": [
          "Flash Attention 4 achieves a ~20% speedup over previous state-of-the-art",
          "New architecture uses asynchronous 'pipeline' of operations for concurrency"
        ],
        "why_it_matters": "This breakthrough in GPU kernel optimization significantly improves AI model inference speed, enabling more efficient deployment of large language models.",
        "tags": ["ai-processing", "gpu-technology", "cuda-kernels", "performance"],
        "content_hash": "b2c3d4e5f6789ab1",
        "model": "llama3.2:3b",
        "generated_at": "2024-01-15T15:46:10Z"
      },
      "content_hash": "b2c3d4e5f6789ab1",
      "cache_hit": false
    }
  ]
}
```

#### Response Fields

| Field | Type | Description |
|-------|------|-------------|
| `success` | boolean | Overall operation success (true if no errors) |
| `summaries_generated` | integer | Number of summaries successfully created |
| `errors` | integer | Number of items that failed to process |
| `results` | array | Detailed results for each requested item |
| `results[].item_id` | integer | Article ID that was processed |
| `results[].success` | boolean | Whether summarization succeeded for this item |
| `results[].summary` | string or null | Generated summary text (legacy field) |
| `results[].model` | string | Model used for generation |
| `results[].error` | string or null | Error message if failed |
| `results[].tokens_used` | integer or null | Approximate token count for generation |
| `results[].generation_time` | float or null | Time taken in seconds |
| `results[].structured_summary` | object or null | **NEW**: Structured JSON summary with bullets/why_it_matters/tags |
| `results[].structured_summary.bullets` | array | Key points as concise bullet list (3-5 items) |
| `results[].structured_summary.why_it_matters` | string | Explanation of significance and broader impact |
| `results[].structured_summary.tags` | array | Relevant topic tags for categorization and search |
| `results[].structured_summary.content_hash` | string | Content hash for deduplication and caching |
| `results[].structured_summary.model` | string | Model used for this specific summary |
| `results[].structured_summary.generated_at` | string (ISO 8601) | When this summary was generated |
| `results[].structured_summary.is_chunked` | boolean | **NEW v0.3.2**: Whether map-reduce processing was used |
| `results[].structured_summary.chunk_count` | integer or null | **NEW v0.3.2**: Number of chunks processed (null if direct) |
| `results[].structured_summary.total_tokens` | integer or null | **NEW v0.3.2**: Total token count of original content |
| `results[].structured_summary.processing_method` | string | **NEW v0.3.2**: "direct" or "map-reduce" |
| `results[].content_hash` | string or null | **NEW**: Content hash for caching and deduplication |
| `results[].cache_hit` | boolean | **NEW**: Whether this result came from cache (instant response) |

#### Fallback Summary Fields ⭐ *New in v0.3.3*

When AI services are unavailable or summary generation fails, the API automatically provides intelligent fallback summaries:

| Field | Type | Description |
|-------|------|-------------|
| `fallback_summary` | string or null | **NEW v0.3.3**: First 2 sentences when AI summary unavailable |
| `is_fallback_summary` | boolean | **NEW v0.3.3**: Whether the displayed summary is a fallback |

**Fallback Behavior:**
- Triggered when no AI summary exists (neither structured nor legacy)
- Uses intelligent sentence extraction from full article content (not RSS summary)
- Provides first 2 sentences with proper punctuation handling
- Graceful degradation: article content → title → generic message

#### Behavior

**Structured JSON Summaries (v0.3.2)** ⭐ *ENHANCED*
- **Default Format**: `use_structured=true` generates structured JSON with:
  - `bullets`: 3-5 key points as concise sentences (max 80 chars each)
  - `why_it_matters`: Significance explanation (50-150 words)
  - `tags`: 3-6 relevant topic tags for categorization and search
- **Legacy Support**: `use_structured=false` generates plain text summaries
- **JSON Validation**: Strict validation with automatic fallback on malformed responses

**Long Article Processing (v0.3.2)** ⭐ *NEW*
- **Automatic Detection**: Articles exceeding token threshold trigger map-reduce processing
- **Intelligent Chunking**: Respects paragraph and sentence boundaries for context preservation
- **MAP Phase**: Individual chunk summarization with structured extraction
- **REDUCE Phase**: Synthesis of chunk summaries into coherent final result
- **Processing Transparency**: All responses include processing method and chunking metadata

**Hash+Model Caching System** ⭐ *NEW*
- **Content Hashing**: SHA256-based deduplication during article ingestion
- **Cache Keys**: `{content_hash}:{model}` for precise cache invalidation
- **Instant Cache Hits**: Sub-second responses for repeated content/model combinations
- **Smart Invalidation**: Only regenerates when content OR model changes
- **Cross-Article Deduplication**: Identical content cached across different articles

**AI Model Integration:**
- Uses local Ollama LLM service for privacy-preserving summarization
- Configurable models via `NEWSBRIEF_LLM_MODEL` environment variable
- Automatic model pulling if not locally available
- Optimized prompts for consistent structured JSON generation

**Intelligent Processing:**
- Skips items with existing summaries unless `force_regenerate=true`
- Smart caching checks both legacy and structured summary formats
- Handles missing items gracefully with detailed error reporting
- Processes content through Mozilla Readability for clean text input
- Automatic content hash calculation and storage

**Performance & Reliability:**
- Tracks generation time, token usage, and cache hit rates for monitoring
- Implements fallback summarization when LLM service unavailable
- Database persistence with optimized indexing for cache lookups
- Graceful fallbacks to extractive summaries when JSON parsing fails

**Error Handling:**
- Returns partial success when some items fail
- Detailed error messages for debugging and monitoring
- Graceful degradation when Ollama service is offline
- JSON validation with structured fallback creation

#### Examples

```bash
# Generate structured JSON summary (default behavior)
curl -X POST http://localhost:8787/summarize \
  -H "Content-Type: application/json" \
  -d '{"item_ids": [1], "use_structured": true}'

# Extract bullets, significance, and tags from response
curl -X POST http://localhost:8787/summarize \
  -H "Content-Type: application/json" \
  -d '{"item_ids": [1]}' | jq '.results[0].structured_summary | {bullets, why_it_matters, tags}'

# Test caching - second request should show cache_hit: true
curl -X POST http://localhost:8787/summarize \
  -H "Content-Type: application/json" \
  -d '{"item_ids": [1]}' | jq '.results[0].cache_hit'

# Batch structured summarization with custom model
curl -X POST http://localhost:8787/summarize \
  -H "Content-Type: application/json" \
  -d '{"item_ids": [1,2,3], "model": "mistral:7b", "use_structured": true}'

# Legacy plain text summaries (backward compatibility)
curl -X POST http://localhost:8787/summarize \
  -H "Content-Type: application/json" \
  -d '{"item_ids": [1], "use_structured": false}'

# Force regenerate with different model (cache miss expected)
curl -X POST http://localhost:8787/summarize \
  -H "Content-Type: application/json" \
  -d '{"item_ids": [1], "model": "llama3.2:1b", "force_regenerate": true}'

# Monitor performance and cache efficiency
curl -X POST http://localhost:8787/summarize \
  -H "Content-Type: application/json" \
  -d '{"item_ids": [1,2,3]}' | jq '.results[] | {item_id, cache_hit, generation_time}'
```

---

### **GET /items/{item_id}**

Retrieve a specific article with complete details including AI summary.

#### Request

```http
GET /items/1 HTTP/1.1
```

#### Response

**Success (200)**
```json
{
  "id": 1,
  "title": "Revolutionary AI Breakthrough Announced",
  "url": "https://example.com/article/ai-breakthrough",
  "published": "2024-01-15T10:30:00",
  "summary": "Initial article excerpt from RSS feed...",
  "ai_summary": "This groundbreaking article reveals significant advances in artificial intelligence research...",
  "ai_model": "llama3.2:3b",
  "ai_generated_at": "2024-01-15T15:45:22",
  "structured_summary": {
    "bullets": [
      "Researchers announce new model architecture achieving unprecedented reasoning performance",
      "Breakthrough represents significant advance in artificial intelligence research capabilities",
      "New approach could transform industry applications and scientific discovery"
    ],
    "why_it_matters": "This breakthrough represents a fundamental advancement in AI reasoning capabilities, potentially transforming how artificial intelligence systems approach complex problem-solving and accelerating progress across multiple scientific and industrial domains.",
    "tags": ["artificial-intelligence", "research-breakthrough", "model-architecture", "reasoning-systems", "technology"],
    "content_hash": "a1b2c3d4e5f6789a",
    "model": "llama3.2:3b",
    "generated_at": "2024-01-15T15:45:22Z"
  }
}
```

#### Response Fields

| Field | Type | Description |
|-------|------|-------------|
| `id` | integer | Unique article identifier |
| `title` | string or null | Article title |
| `url` | string | Original article URL |
| `published` | string (ISO 8601) or null | Publication timestamp |
| `summary` | string or null | Original article summary from RSS feed |
| `ai_summary` | string or null | AI-generated intelligent summary (legacy) |
| `ai_model` | string or null | Model used for AI summary generation (legacy) |
| `ai_generated_at` | string (ISO 8601) or null | When AI summary was created (legacy) |
| `structured_summary` | object or null | **NEW**: Structured JSON summary with bullets/why_it_matters/tags |
| `structured_summary.bullets` | array | Key points as concise bullet list |
| `structured_summary.why_it_matters` | string | Explanation of significance and broader impact |
| `structured_summary.tags` | array | Relevant topic tags for categorization |
| `structured_summary.content_hash` | string | Content hash for caching |
| `structured_summary.model` | string | Model used for generation |
| `structured_summary.generated_at` | string (ISO 8601) | When this summary was generated |
| `structured_summary.is_chunked` | boolean | **NEW v0.3.2**: Whether map-reduce processing was used |
| `structured_summary.chunk_count` | integer or null | **NEW v0.3.2**: Number of chunks processed |
| `structured_summary.total_tokens` | integer or null | **NEW v0.3.2**: Total token count of content |
| `structured_summary.processing_method` | string | **NEW v0.3.2**: Processing method used |
| `fallback_summary` | string or null | **NEW v0.3.3**: First 2 sentences when AI unavailable |
| `is_fallback_summary` | boolean | **NEW v0.3.3**: Whether fallback summary is being used |

#### Example

```bash
# Get specific article with structured summary
curl http://localhost:8787/items/1 | jq .

# Extract structured summary components
curl http://localhost:8787/items/1 | jq '.structured_summary | {bullets, why_it_matters, tags}'

# Extract just the bullet points
curl http://localhost:8787/items/1 | jq '.structured_summary.bullets'

# Extract topic tags for categorization
curl http://localhost:8787/items/1 | jq '.structured_summary.tags'

# Legacy: Extract plain text AI summary (if available)
curl http://localhost:8787/items/1 | jq '.ai_summary'

# ✨ Map-Reduce Processing Examples ⭐ *New in v0.3.2*

# Check if article was processed using map-reduce
curl http://localhost:8787/items/1 | jq '.structured_summary | {
  processing_method,
  is_chunked,
  chunk_count,
  total_tokens
}'

# Find articles processed with different methods
curl "http://localhost:8787/items" | jq '[.[] | select(.structured_summary != null)] | group_by(.structured_summary.processing_method) | map({
  method: .[0].structured_summary.processing_method,
  count: length,
  avg_tokens: ([.[].structured_summary.total_tokens | select(. != null)] | add / length | floor)
})'

# ✨ Fallback Summary Examples ⭐ *New in v0.3.3*

# Check items with fallback summaries (when AI unavailable)
curl "http://localhost:8787/items" | jq '.[] | select(.is_fallback_summary == true) | {
  id,
  title,
  fallback_summary,
  fallback_length: (.fallback_summary | length)
}'

# Test individual item fallback behavior
curl http://localhost:8787/items/1 | jq '{
  id,
  title,
  has_ai_summary: (.structured_summary != null),
  using_fallback: .is_fallback_summary,
  content_preview: .fallback_summary
}'

# Monitor AI vs fallback summary distribution
curl "http://localhost:8787/items" | jq '{
  total_items: length,
  ai_summaries: [.[] | select(.structured_summary != null)] | length,
  fallback_summaries: [.[] | select(.is_fallback_summary == true)] | length,
  percentage_fallback: (([.[] | select(.is_fallback_summary == true)] | length) / length * 100 | round)
}'
```

---

## 📊 Quality Metrics Endpoints ⭐ *New in v0.8.1*

Monitor LLM output quality and story synthesis performance.

### **GET /api/quality/summary**

Get overall quality metrics summary for the past 7 days.

#### Response (200)
```json
{
  "period_days": 7,
  "by_operation": {
    "synthesis": {
      "total_operations": 122,
      "success_rate": 1.0,
      "avg_quality_score": 0.929,
      "avg_generation_time_ms": 15793
    }
  },
  "synthesis": {
    "quality_distribution": {
      "excellent": 77,
      "good": 45
    },
    "component_averages": {
      "completeness": 1.0,
      "coverage": 0.937,
      "entity_consistency": 0.726,
      "parse_success": 1.0,
      "title_quality": 0.999
    },
    "trends": [
      {
        "date": "2026-02-09",
        "avg_quality": 0.929,
        "count": 122,
        "success_rate": 1.0
      }
    ]
  },
  "recent_low_quality": []
}
```

#### Quality Score Components

| Component | Description | Weight |
|-----------|-------------|--------|
| `completeness` | Has title, synthesis, key_points, why_it_matters | 25% |
| `coverage` | Synthesis length relative to article count | 20% |
| `entity_consistency` | Entities appear in synthesis text | 15% |
| `parse_success` | JSON parsed without retries/repairs | 25% |
| `title_quality` | LLM-generated title (vs fallback) | 15% |

#### Quality Distribution Thresholds

| Rating | Score Range |
|--------|-------------|
| `excellent` | ≥ 0.85 |
| `good` | 0.70 - 0.84 |
| `fair` | 0.50 - 0.69 |
| `poor` | < 0.50 |

#### Example
```bash
curl http://localhost:8787/api/quality/summary | jq .
```

---

### **GET /api/llm/stats**

Get LLM operation statistics including success rates and failure analysis.

#### Query Parameters
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `hours` | int | 24 | Time window in hours |

#### Response (200)
```json
{
  "success_rates": {
    "SynthesisOutput": 1.0
  },
  "failure_summary": {
    "total_failures": 0,
    "time_window_hours": 24,
    "by_category": {},
    "by_model": {},
    "recent_errors": []
  },
  "strategy_distribution": {
    "direct": 122
  },
  "quality_distribution": {
    "excellent": 77,
    "good": 45
  },
  "by_operation": {
    "synthesis": {
      "total_operations": 122,
      "success_rate": 1.0,
      "avg_quality_score": 0.929,
      "avg_generation_time_ms": 15793
    }
  }
}
```

#### Parse Strategy Types

| Strategy | Description |
|----------|-------------|
| `direct` | JSON parsed on first attempt |
| `markdown_block` | Extracted from markdown code fence |
| `brace_match` | Found JSON by brace matching |
| `repair` | Required syntax repairs |

#### Example
```bash
# Last 24 hours
curl "http://localhost:8787/api/llm/stats?hours=24" | jq .

# Last week
curl "http://localhost:8787/api/llm/stats?hours=168" | jq .
```

---

### **GET /api/quality/trends**

Get quality score trends over time.

#### Query Parameters
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `days` | int | 7 | Number of days to include |

#### Response (200)
```json
{
  "days": 7,
  "trends": [
    {
      "date": "2026-02-03",
      "avg_quality": 0.912,
      "count": 15,
      "success_rate": 1.0
    },
    {
      "date": "2026-02-04",
      "avg_quality": 0.935,
      "count": 18,
      "success_rate": 1.0
    }
  ]
}
```

#### Example
```bash
curl "http://localhost:8787/api/quality/trends?days=30" | jq .
```

---

### **GET /admin/quality** (Dashboard)

Web UI dashboard for visualizing quality metrics.

**Features:**
- Overview cards (avg quality, parse success rate, direct parse rate)
- Quality distribution chart
- Parse strategy distribution
- Quality component averages
- Recent low-quality stories table
- Operations by type breakdown

**Access:**
```
http://localhost:8787/admin/quality
```

---

## 🔍 Entity Extraction ⭐ *Enhanced in v0.8.1*

Entity extraction identifies key companies, products, people, technologies, and locations from article content. Enhanced in v0.8.1 (Issue #103) with confidence scores, roles, and disambiguation.

### **Entity Structure (v0.8.1)**

Each entity now includes rich metadata:

```json
{
  "name": "OpenAI",
  "confidence": 0.95,
  "role": "primary_subject",
  "disambiguation": "AI research company"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Entity name with proper capitalization |
| `confidence` | float | 0.0-1.0 extraction confidence score |
| `role` | string | `primary_subject`, `mentioned`, or `quoted` |
| `disambiguation` | string | Optional context to avoid confusion |

### **Entity Roles**

| Role | Description | Example |
|------|-------------|---------|
| `primary_subject` | Central to the story | Company making an announcement |
| `mentioned` | Referenced but not focus | Competitor mentioned in passing |
| `quoted` | Source of statement/quote | CEO providing quotes |

### **Confidence Scoring**

| Range | Meaning |
|-------|---------|
| 0.9+ | Explicitly named and central to article |
| 0.7-0.9 | Clearly mentioned, moderate relevance |
| 0.5-0.7 | Inferred or tangentially mentioned |

### **Backward Compatibility**

The entity system maintains backward compatibility:

- **Legacy format** (v1): Simple string arrays `["Google", "OpenAI"]`
- **Enhanced format** (v2): Objects with metadata (shown above)

When deserializing legacy data, strings are automatically converted to `EntityWithMetadata` objects with default values (confidence: 0.8, role: "mentioned").

### **Entity Overlap Scoring**

Entity overlap between articles uses confidence-weighted Jaccard similarity:

- **High-confidence** matches count more than low-confidence
- **Primary subjects** get 1.5x weight boost
- **Quoted sources** get 1.2x weight boost

This improved scoring helps with more accurate story clustering.

---

## 🛡️ Error Handling

### **Standard Error Response**

```json
{
  "detail": "Error description"
}
```

### **Validation Error Response**

```json
{
  "detail": [
    {
      "loc": ["path", "to", "field"],
      "msg": "Human readable error message",
      "type": "error.type.subtype"
    }
  ]
}
```

### **HTTP Status Codes**

| Status | Description |
|--------|-------------|
| `200` | Success |
| `422` | Validation Error (invalid request data) |
| `500` | Internal Server Error |

## 📊 Data Models

### **FeedIn (Request Model)**

Used when adding new feeds.

```typescript
interface FeedIn {
  url: string;  // Valid HTTP/HTTPS URL
}
```

**Validation Rules:**
- Must be valid HTTP or HTTPS URL
- URL format validation using Pydantic

### **ItemOut (Response Model)**

Used when returning articles.

```typescript
interface ItemOut {
  id: number;
  title?: string;          // Can be null
  url: string;
  published?: string;      // ISO 8601 timestamp, can be null
  summary?: string;        // Can be null
}
```

## 🔄 Feed Processing Pipeline

When `/refresh` is called, NewsBrief processes feeds through this pipeline:

1. **Feed Discovery**: Query all active feeds from database
2. **HTTP Optimization**: Use ETag/Last-Modified headers when available
3. **Feed Parsing**: Parse RSS/Atom using feedparser
4. **Content Extraction**: Extract readable content using Mozilla Readability
5. **Deduplication**: Skip articles that already exist (by URL hash)
6. **Storage**: Insert new articles with metadata

### **Feed Metadata**

Feeds are automatically tracked with:
- ETag and Last-Modified headers for caching
- robots.txt compliance checking
- Enable/disable status
- Creation and update timestamps

### **Article Processing**

Each article goes through:
- URL normalization and hashing
- Publication date parsing (multiple formats supported)
- Content extraction from original article page
- Summary preservation from feed data

## 📝 Usage Examples

### **Complete Workflow Example**

```bash
# 1. Add feeds
curl -X POST http://localhost:8787/feeds \
  -H "Content-Type: application/json" \
  -d '{"url": "https://feeds.bbci.co.uk/news/rss.xml"}'

curl -X POST http://localhost:8787/feeds \
  -H "Content-Type: application/json" \
  -d '{"url": "https://hnrss.org/frontpage"}'

# 2. Fetch articles
curl -X POST http://localhost:8787/refresh

# 3. Read latest articles
curl "http://localhost:8787/items?limit=10" | jq '.[].title'

# 4. Get specific article details
curl "http://localhost:8787/items?limit=1" | jq '.[0]'
```

### **OPML Import**

Place an OPML file at `data/feeds.opml` and restart the application. Feeds will be automatically imported on startup.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<opml version="1.0">
  <head>
    <title>My Feeds</title>
  </head>
  <body>
    <outline text="BBC News"
             xmlUrl="https://feeds.bbci.co.uk/news/rss.xml"/>
    <outline text="Hacker News"
             xmlUrl="https://hnrss.org/frontpage"/>
  </body>
</opml>
```

### **Monitoring & Health Checks**

```bash
# Check if service is running
curl -I http://localhost:8787/docs

# Monitor refresh performance
time curl -X POST http://localhost:8787/refresh

# Check database growth
curl http://localhost:8787/items?limit=1 | jq '.[0].id'
```

---

## 🐍 Python API (v0.5.0)

For story generation, the Python API is currently available while HTTP endpoints are being developed.

### Story Generation

Generate stories from recent articles using hybrid clustering and LLM synthesis.

```python
from app.db import session_scope
from app.stories import generate_stories_simple

with session_scope() as session:
    story_ids = generate_stories_simple(
        session=session,
        time_window_hours=24,      # Lookback period (default: 24)
        min_articles_per_story=1,  # Minimum articles per story (default: 1)
        similarity_threshold=0.3,  # Keyword overlap threshold (default: 0.3)
        model="llama3.1:8b"        # LLM model for synthesis
    )
    print(f"Generated {len(story_ids)} stories: {story_ids}")
```

**Parameters**:
- `time_window_hours` (int): How many hours back to look for articles (default: 24)
- `min_articles_per_story` (int): Minimum articles to form a story (default: 1, allows single-article stories)
- `similarity_threshold` (float): Jaccard similarity threshold for keyword overlap (0.0-1.0, default: 0.3)
- `model` (str): Ollama model to use for synthesis (default: "llama3.1:8b")

**Returns**: List of created story IDs

**Algorithm**:
1. Query articles from last N hours
2. Group by topic (coarse filter)
3. Within each topic, cluster by title keyword overlap (Jaccard similarity)
4. For each cluster, generate LLM synthesis
5. Store story with links to source articles

**Features**:
- ✅ Hybrid clustering: Topic + keyword similarity
- ✅ LLM-powered multi-document synthesis
- ✅ Entity extraction (companies, products, people)
- ✅ Topic auto-classification
- ✅ Graceful fallback when LLM unavailable
- ✅ Comprehensive error handling

---

### Retrieve Stories

```python
from app.db import session_scope
from app.stories import get_stories, get_story_by_id

# Get list of stories
with session_scope() as session:
    stories = get_stories(
        session=session,
        limit=10,                # Get top 10 stories
        offset=0,                # Pagination offset
        status="active",         # Only active stories
        order_by="importance"    # Sort by importance_score DESC
    )

    for story in stories:
        print(f"\n{story.title}")
        print(f"Articles: {story.article_count}")
        print(f"Importance: {story.importance_score:.2f}")
        print(f"Topics: {', '.join(story.topics)}")
        print(f"Entities: {', '.join(story.entities)}")

# Get single story with details
with session_scope() as session:
    story = get_story_by_id(session, story_id=1)
    if story:
        print(f"\n{story.title}")
        print(f"\n{story.synthesis}")
        print(f"\nKey Points:")
        for point in story.key_points:
            print(f"  • {point}")
        print(f"\nWhy It Matters: {story.why_it_matters}")
```

**Parameters**:
- `limit` (int): Max stories to return (default: 50)
- `offset` (int): Pagination offset (default: 0)
- `status` (str): Filter by status ("active", "archived", or None for all)
- `order_by` (str): Sort field ("importance", "freshness", "generated_at")

**Returns**: List of `StoryOut` Pydantic models

---

### Update & Archive Stories

```python
from app.db import session_scope
from app.stories import update_story, archive_story, delete_story

# Update a story
with session_scope() as session:
    update_story(
        session=session,
        story_id=1,
        status="archived",
        importance_score=0.95
    )

# Archive a story (soft delete)
with session_scope() as session:
    archive_story(session, story_id=1)

# Permanently delete a story
with session_scope() as session:
    delete_story(session, story_id=1)
```

---

## 💡 Tips & Best Practices

### **Rate Limiting**
Currently no rate limiting implemented. For production use, consider implementing rate limiting at the reverse proxy level.

### **Monitoring**
- Monitor `/refresh` response times for feed health
- Track `ingested` counts to detect feed issues
- Set up alerts for HTTP 500 errors

### **Performance**
- Default limit of 50 items balances performance with usability
- Use appropriate `limit` values for your use case
- Database automatically handles deduplication

### **Error Recovery**
- Feed fetch failures are logged but don't stop processing other feeds
- Invalid articles are skipped gracefully
- Database constraints prevent duplicate entries

---

For more information, visit the interactive documentation at `/docs` when running NewsBrief locally.

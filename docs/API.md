# NewsBrief API Documentation

NewsBrief provides a RESTful API for managing RSS feeds and retrieving articles. All endpoints return JSON responses.

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

Retrieve articles from the database, ordered by publication date.

#### Request

```http
GET /items?limit=10 HTTP/1.1
```

#### Query Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `limit` | integer | No | 50 | Number of items to return (max: 200) |

#### Response

**Success (200)**
```json
[
  {
    "id": 123,
    "title": "Breaking: Important News Event",
    "url": "https://example.com/article/123",
    "published": "2025-09-27T10:30:00Z",
    "summary": "This is a brief summary of the article content...",
    "ai_summary": "This article covers a significant breaking news event with major implications for the industry, highlighting key developments and their potential impact on stakeholders.",
    "ai_model": "llama3.2:3b",
    "ai_generated_at": "2025-09-27T10:35:15Z"
  },
  {
    "id": 124,
    "title": "Tech Update: New Framework Released",
    "url": "https://example.com/article/124",
    "published": "2025-09-27T09:15:00Z",
    "summary": "A comprehensive overview of the new features...",
    "ai_summary": null,
    "ai_model": null,
    "ai_generated_at": null
  }
]
```

#### Item Object

| Field | Type | Description |
|-------|------|-------------|
| `id` | integer | Unique article identifier |
| `title` | string or null | Article title |
| `url` | string | Original article URL |
| `published` | string (ISO 8601) or null | Publication timestamp |
| `summary` | string or null | Article summary or excerpt from RSS feed |
| `ai_summary` | string or null | AI-generated intelligent summary |
| `ai_model` | string or null | Model used for AI summary generation |
| `ai_generated_at` | string (ISO 8601) or null | When AI summary was created |

#### Example

```bash
# Get latest 5 articles with AI summaries
curl "http://localhost:8787/items?limit=5" | jq .

# Get latest 50 articles (default)
curl http://localhost:8787/items

# Extract structured summaries from recent articles  
curl "http://localhost:8787/items?limit=5" | jq '.[] | select(.structured_summary != null) | {id, title, bullets: .structured_summary.bullets, tags: .structured_summary.tags}'

# Extract just bullet points from articles with structured summaries
curl "http://localhost:8787/items?limit=5" | jq '.[] | select(.structured_summary != null) | {id, title, bullets: .structured_summary.bullets}'
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
| `results[].content_hash` | string or null | **NEW**: Content hash for caching and deduplication |
| `results[].cache_hit` | boolean | **NEW**: Whether this result came from cache (instant response) |

#### Behavior

**Structured JSON Summaries (v0.3.1)** ⭐ *NEW*
- **Default Format**: `use_structured=true` generates structured JSON with:
  - `bullets`: 3-5 key points as concise sentences (max 80 chars each)
  - `why_it_matters`: Significance explanation (50-150 words) 
  - `tags`: 3-6 relevant topic tags for categorization and search
- **Legacy Support**: `use_structured=false` generates plain text summaries
- **JSON Validation**: Strict validation with automatic fallback on malformed responses

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
```

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

## 🚀 Future API Endpoints

These endpoints are planned for future releases:

### **GET /feeds** _(Planned)_
List all configured feeds with metadata

### **DELETE /feeds/{feed_id}** _(Planned)_  
Remove a feed and optionally its articles

### **GET /search** _(Planned)_
Full-text search across articles

### **GET /categories** _(Planned)_
List auto-generated content categories

### **GET /summary/{item_id}** _(Planned)_
Get AI-generated summary for specific article

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

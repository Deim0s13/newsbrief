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

Add a new RSS feed to the system.

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

Fetch latest articles from all configured feeds.

#### Request

```http
POST /refresh HTTP/1.1
```

#### Response

**Success (200)**
```json
{
  "ingested": 47
}
```

| Field | Type | Description |
|-------|------|-------------|
| `ingested` | integer | Number of new articles added |

#### Behavior

- Respects ETag and Last-Modified headers for efficient fetching
- Skips disabled feeds and feeds that don't allow robots
- Processes up to 150 items per refresh (configurable)
- Automatically deduplicates articles by URL
- Extracts readable content from article pages

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
    "summary": "This is a brief summary of the article content..."
  },
  {
    "id": 124,
    "title": "Tech Update: New Framework Released",
    "url": "https://example.com/article/124",
    "published": "2025-09-27T09:15:00Z",
    "summary": "A comprehensive overview of the new features..."
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
| `summary` | string or null | Article summary or excerpt |

#### Example

```bash
# Get latest 5 articles
curl "http://localhost:8787/items?limit=5" | jq .

# Get latest 50 articles (default)
curl http://localhost:8787/items
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

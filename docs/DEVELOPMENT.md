# Development Guide

This guide covers setting up your development environment, running tests, debugging, and contributing to NewsBrief.

## 🛠️ Development Setup

### **Prerequisites**

- **Python 3.11+**: Modern Python with excellent async support
- **Podman or Docker**: Container runtime for local development
- **Make**: Build automation (optional but recommended)
- **Git**: Version control
- **jq**: JSON processing for API testing (optional)

### **Initial Setup**

```bash
# Clone the repository
git clone https://github.com/yourusername/newsbrief.git
cd newsbrief

# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install development dependencies
pip install -U pip
pip install -r requirements.txt
```

### **Verify Installation**

```bash
# Test Python syntax
python3 -m py_compile app/*.py

# Start development server
uvicorn app.main:app --reload --port 8787

# Test API (in another terminal)
curl http://localhost:8787/docs  # Should return OpenAPI docs
```

## 🏃 Running NewsBrief

### **Development Server**

```bash
# Method 1: Direct Python
uvicorn app.main:app --reload --port 8787

# Method 2: Make shortcut
make run-local

# Method 3: Container (production-like)
make build
make run
```

### **Environment Variables**

NewsBrief supports several environment variables for configuration:

#### **Core Configuration**
```bash
# LLM Integration: Ollama service for AI summarization  
export OLLAMA_BASE_URL=http://localhost:11434
export NEWSBRIEF_LLM_MODEL=llama3.2:3b

# Optional: Custom data directory
export DATA_DIR=/path/to/your/data
```

#### **Fetch Limits & Performance** ⭐ *New in v0.2.4*
```bash
# Global item limit per refresh (default: 150)
export NEWSBRIEF_MAX_ITEMS_PER_REFRESH=200

# Per-feed fairness limit (default: 50)
export NEWSBRIEF_MAX_ITEMS_PER_FEED=25

# Time-based safety cap in seconds (default: 300 = 5 minutes)
export NEWSBRIEF_MAX_REFRESH_TIME=600

# Example: Production configuration for high-volume feeds
export NEWSBRIEF_MAX_ITEMS_PER_REFRESH=500
export NEWSBRIEF_MAX_ITEMS_PER_FEED=100
export NEWSBRIEF_MAX_REFRESH_TIME=900  # 15 minutes
```

#### **AI Summarization (LLM) Configuration** ⭐ *New in v0.3.0*

NewsBrief includes integrated AI summarization using local LLM services via Ollama:

```bash
# LLM Service Configuration
export OLLAMA_BASE_URL=http://localhost:11434  # Ollama service URL
export NEWSBRIEF_LLM_MODEL=llama3.2:3b        # Default model for summarization

# Production LLM settings
export OLLAMA_BASE_URL=http://ollama-service:11434  # Internal service
export NEWSBRIEF_LLM_MODEL=mistral:7b              # Larger model for better quality
```

**LLM Setup Requirements:**

1. **Install Ollama** (if running locally):
   ```bash
   # macOS
   brew install ollama
   
   # Start Ollama service
   ollama serve
   
   # Pull recommended models
   ollama pull llama3.2:3b    # Fast, good quality
   ollama pull mistral:7b     # Better quality, slower
   ```

2. **Container Integration:**
   ```bash
   # Connect NewsBreif container to local Ollama
   podman run --rm -d \
     -p 8787:8787 \
     -v ./data:/app/data \
     -e OLLAMA_BASE_URL=http://host.containers.internal:11434 \
     -e NEWSBRIEF_LLM_MODEL=llama3.2:3b \
     --name newsbrief newsbrief-api:latest
   ```

3. **Verify LLM Integration:**
   ```bash
   # Check LLM service status
   curl http://localhost:8787/llm/status | jq .
   
   # Generate test summary
   curl -X POST http://localhost:8787/summarize \
     -H "Content-Type: application/json" \
     -d '{"item_ids": [1]}'
   ```

**Model Recommendations:**
- **Development**: `llama3.2:3b` - Fast inference, good quality
- **Production**: `mistral:7b` - Higher quality, more detailed summaries  
- **High-volume**: `llama3.2:1b` - Fastest inference for large-scale processing

#### **Container Configuration Examples**
```bash
# Development: Fast refresh with low limits + AI summarization
podman run --rm -d \
  -p 8787:8787 \
  -v ./data:/app/data \
  -e NEWSBRIEF_MAX_ITEMS_PER_REFRESH=50 \
  -e NEWSBRIEF_MAX_ITEMS_PER_FEED=10 \
  -e NEWSBRIEF_MAX_REFRESH_TIME=120 \
  -e OLLAMA_BASE_URL=http://host.containers.internal:11434 \
  -e NEWSBRIEF_LLM_MODEL=llama3.2:3b \
  --name newsbrief newsbrief-api:latest

# Production: High-capacity configuration + Advanced LLM
podman run --rm -d \
  -p 8787:8787 \
  -v ./data:/app/data \
  -e NEWSBRIEF_MAX_ITEMS_PER_REFRESH=1000 \
  -e NEWSBRIEF_MAX_ITEMS_PER_FEED=200 \
  -e NEWSBRIEF_MAX_REFRESH_TIME=1800 \
  -e OLLAMA_BASE_URL=http://ollama-service:11434 \
  -e NEWSBRIEF_LLM_MODEL=mistral:7b \
  --name newsbrief newsbrief-api:latest
```

## 🧪 Testing & Debugging

### **Manual API Testing**

```bash
# Add test feeds
curl -X POST http://localhost:8787/feeds \
  -H "Content-Type: application/json" \
  -d '{"url": "https://feeds.bbci.co.uk/news/rss.xml"}'

curl -X POST http://localhost:8787/feeds \
  -H "Content-Type: application/json" \
  -d '{"url": "https://hnrss.org/frontpage"}'

# Fetch articles with enhanced statistics
curl -X POST http://localhost:8787/refresh | jq .

# View just the statistics summary  
curl -X POST http://localhost:8787/refresh | jq .stats

# Monitor performance metrics
curl -X POST http://localhost:8787/refresh | jq '.stats.performance'

# Check per-feed fairness distribution
curl -X POST http://localhost:8787/refresh | jq '.stats.items.per_feed'

# List articles
curl "http://localhost:8787/items?limit=5" | jq .
```

#### **Enhanced Monitoring Examples** ⭐ *New in v0.2.4*

```bash
# Monitor refresh performance
watch -n 30 'curl -s -X POST http://localhost:8787/refresh | jq ".stats.performance"'

# Check if limits are being hit
curl -s -X POST http://localhost:8787/refresh | jq '
  if .stats.performance.hit_global_limit then
    "WARNING: Global limit reached" 
  elif .stats.performance.hit_time_limit then
    "WARNING: Time limit reached"
  else
    "OK: Within limits"
  end'

# View fairness distribution
curl -s -X POST http://localhost:8787/refresh | jq '
  "Per-feed distribution:", 
  (.stats.items.per_feed | to_entries[] | "\(.key): \(.value) items")'

# Configuration check
curl -s -X POST http://localhost:8787/refresh | jq '.stats.config'
```

#### **AI Summarization Testing** ⭐ *New in v0.3.0*

```bash
# Check LLM service status and available models
curl http://localhost:8787/llm/status | jq .

# Test AI summarization on recent articles
curl -X POST http://localhost:8787/summarize \
  -H "Content-Type: application/json" \
  -d '{"item_ids": [1,2,3]}'

# Generate summaries with specific model
curl -X POST http://localhost:8787/summarize \
  -H "Content-Type: application/json" \
  -d '{"item_ids": [1], "model": "mistral:7b"}'

# Force regenerate existing summaries  
curl -X POST http://localhost:8787/summarize \
  -H "Content-Type: application/json" \
  -d '{"item_ids": [1], "force_regenerate": true}'

# View articles with AI summaries
curl "http://localhost:8787/items?limit=5" | jq '.[] | select(.ai_summary != null) | {id, title, ai_model, ai_summary}'

# Get specific article with full AI details
curl http://localhost:8787/items/1 | jq '{id, title, original_summary: .summary, ai_summary, ai_model, ai_generated_at}'

# Monitor AI performance over batch operations
curl -X POST http://localhost:8787/summarize \
  -H "Content-Type: application/json" \
  -d '{"item_ids": [1,2,3,4,5]}' | jq '.results[] | {item_id, tokens_used, generation_time}'
```

### **Database Inspection**

```bash
# SQLite CLI (if installed)
sqlite3 data/newsbrief.sqlite3

# View tables
.tables

# Check feeds
SELECT id, url, robots_allowed, disabled FROM feeds;

# Check recent articles
SELECT id, title, published, url FROM items 
ORDER BY COALESCE(published, created_at) DESC 
LIMIT 5;

# Exit SQLite
.quit
```

### **Debugging Tips**

#### **Common Issues**

1. **Port already in use**
   ```bash
   # Find process using port 8787
   lsof -i :8787
   
   # Kill process or use different port
   uvicorn app.main:app --reload --port 8788
   ```

2. **Database locked errors**
   ```bash
   # Stop all running instances
   pkill -f "uvicorn.*newsbrief"
   
   # Remove lock if exists
   rm -f data/newsbrief.sqlite3-shm data/newsbrief.sqlite3-wal
   ```

3. **Module import errors**
   ```bash
   # Ensure you're in project root
   pwd  # Should end with /newsbrief
   
   # Check PYTHONPATH
   export PYTHONPATH=$PWD:$PYTHONPATH
   ```

#### **Logging & Debugging**

```python
# Add debug logging to any module
import logging
logging.basicConfig(level=logging.DEBUG)

# In feeds.py, add debug prints
print(f"Fetching {len(list(list_feeds()))} feeds...")
print(f"Inserted {inserted} new articles")
```

## 🏗️ Development Workflow

### **Making Changes**

1. **Create feature branch**
   ```bash
   git checkout -b feature/improve-feed-parsing
   ```

2. **Make changes and test**
   ```bash
   # Test syntax
   python3 -m py_compile app/feeds.py
   
   # Test locally
   uvicorn app.main:app --reload
   ```

3. **Build and test container**
   ```bash
   make build
   make run
   ```

4. **Commit changes**
   ```bash
   git add .
   git commit -m "Improve feed parsing error handling"
   ```

### **Code Quality**

#### **Style Guidelines**

- **Python**: Follow PEP 8, use type hints
- **Imports**: Use `from __future__ import annotations`
- **Error handling**: Be explicit with exception types
- **Docstrings**: Add for public functions

```python
# Good example
def fetch_feed(url: str, timeout: float = 20.0) -> tuple[bool, str]:
    """
    Fetch RSS feed from URL with timeout.
    
    Args:
        url: RSS feed URL
        timeout: Request timeout in seconds
        
    Returns:
        Tuple of (success, error_message or content)
    """
    try:
        # Implementation
        pass
    except httpx.TimeoutException as e:
        return False, f"Timeout fetching {url}: {e}"
```

#### **Database Changes**

When modifying database schema:

```python
# In db.py, add migration logic
def init_db() -> None:
    with engine.begin() as conn:
        # Check current schema version
        try:
            version = conn.execute("SELECT version FROM schema_info").scalar()
        except:
            version = None
            
        if version is None:
            # Create initial schema
            conn.exec_driver_sql("CREATE TABLE schema_info (version INTEGER)")
            # ... existing table creation
            conn.exec_driver_sql("INSERT INTO schema_info (version) VALUES (1)")
```

## 📦 Container Development

### **Build System**

```bash
# Build with caching
make build

# Tagged build
make local-release VERSION=v0.3.0-dev

# Automated cleanup + build
make clean-release VERSION=v0.3.0-dev

# View available targets
make help
```

### **Multi-architecture Builds**

```bash
# Build for multiple platforms
podman build --platform=linux/amd64,linux/arm64 -t newsbrief-api .

# Or using buildx (Docker)
docker buildx build --platform linux/amd64,linux/arm64 -t newsbrief-api .
```

### **Container Debugging**

```bash
# Run with shell access
podman run --rm -it newsbrief-api /bin/bash

# Check container logs
podman logs newsbrief

# Inspect running container
podman exec -it newsbrief /bin/bash
```

## 🤖 Robots.txt Compliance

NewsBrief includes comprehensive robots.txt support to ensure respectful web crawling and compliance with website policies.

### **Implementation Overview**

NewsBrief implements robots.txt checking at two levels:

```python
# Key functions in app/feeds.py

is_robot_allowed(feed_url)           # Feed-level checking
is_article_url_allowed(article_url)  # Article-level checking  
_get_robots_txt(domain)             # Cached robots.txt fetching
_check_robots_txt_path(robots_txt, path, user_agent)  # Parser
```

### **How It Works**

**1. Feed Addition**
- When adding feeds, `is_robot_allowed()` fetches and parses robots.txt
- Result stored in `feeds.robots_allowed` column (1=allowed, 0=blocked)
- Blocked feeds are skipped during refresh cycles

**2. Article Content Extraction**
- Before fetching article content, `is_article_url_allowed()` validates each URL
- Uses specific User-agent: `newsbrief` for identification
- If disallowed, article is saved without full content (graceful degradation)

**3. Performance Optimization**
- In-memory cache prevents repeated robots.txt requests
- Cache cleared at start of each refresh cycle for freshness
- Failed requests cached as "allow" to avoid timeout loops

### **Robots.txt Parser Features**

```python
# Supports proper robots.txt syntax:
User-agent: *
Disallow: /admin/
Disallow: /api/
Allow: /rss/

User-agent: newsbrief
Disallow: /private/
```

**Parsing Rules**:
- ✅ Multiple `User-agent` sections  
- ✅ `Disallow:` patterns with path prefixes
- ✅ `Allow:` patterns that override disallows
- ✅ `Disallow: /` blocks entire site
- ✅ Empty `Disallow:` allows everything

### **Database Schema**

```sql
CREATE TABLE feeds (
  id INTEGER PRIMARY KEY,
  url TEXT UNIQUE NOT NULL,
  robots_allowed INTEGER DEFAULT 1,  -- 1=allowed, 0=blocked
  disabled INTEGER DEFAULT 0,
  etag TEXT,
  last_modified TEXT,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### **Testing Robots.txt**

**Test permissive robots.txt:**

```bash
# Add HackerNews RSS (robots.txt allows everything)
curl -X POST http://localhost:8787/feeds \
  -H "Content-Type: application/json" \
  -d '{"url": "https://hnrss.org/frontpage"}'

# Refresh should work normally
curl -X POST http://localhost:8787/refresh
```

**Check restrictive robots.txt:**

```bash
# Check Reddit's restrictive robots.txt
curl -s https://www.reddit.com/robots.txt | head -10
# Output: Disallow: / (blocks everything)

# Adding Reddit RSS would be blocked
curl -X POST http://localhost:8787/feeds \
  -H "Content-Type: application/json" \
  -d '{"url": "https://www.reddit.com/r/programming.rss"}'
```

**Debug robots.txt behavior:**

```bash
# Check feed status in database
sqlite3 data/newsbrief.sqlite3 "SELECT url, robots_allowed FROM feeds;"

# Watch cache behavior in logs
podman logs newsbrief | grep -i robots
```

### **Configuration**

Robots.txt behavior is configured via constants in `app/feeds.py`:

```python
HTTP_TIMEOUT = 20.0                      # robots.txt request timeout  
_robots_txt_cache: dict[str, str | None] = {}  # cache storage
```

**User-Agent Strings**:
- **Feed checking**: `User-agent: *` (matches general policies)
- **Article checking**: `User-agent: newsbrief` (specific identification)

### **Error Handling & Fail-Safe Design**

```python
def is_robot_allowed(feed_url: str) -> bool:
    try:
        robots_txt = _get_robots_txt(domain)
        if robots_txt is None:
            return True  # No robots.txt = allowed
        return _check_robots_txt_path(robots_txt, path, user_agent='*')
    except Exception:
        return True  # Error = allow (fail-safe)
```

**Fail-Safe Principles**:
- Network errors default to "allow"
- Invalid robots.txt defaults to "allow"  
- Parsing errors default to "allow"
- Missing robots.txt defaults to "allow"

This ensures service reliability while respecting robots.txt when available.

## 🎯 Feature Development

### **Adding New API Endpoints**

1. **Define model in `models.py`**
   ```python
   class SearchQuery(BaseModel):
       query: str
       limit: int = Field(10, le=100)
   ```

2. **Add endpoint in `main.py`**
   ```python
   @app.post("/search", response_model=List[ItemOut])
   def search_items(query: SearchQuery):
       # Implementation
       pass
   ```

3. **Test with curl**
   ```bash
   curl -X POST http://localhost:8787/search \
     -H "Content-Type: application/json" \
     -d '{"query": "python", "limit": 5}'
   ```

### **Database Extensions**

For new tables or columns:

```python
# In db.py
def init_db() -> None:
    # ... existing code
    conn.exec_driver_sql("""
    CREATE TABLE IF NOT EXISTS user_preferences (
      id INTEGER PRIMARY KEY,
      key TEXT UNIQUE NOT NULL,
      value TEXT,
      created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)
```

### **Feed Processing Extensions**

For custom feed processing:

```python
# In feeds.py
def custom_feed_processor(entry, feed_url: str) -> dict:
    """Process entry with custom logic based on feed source."""
    
    # Example: Special handling for certain sources
    if "github.com" in feed_url:
        # Extract GitHub-specific metadata
        pass
    
    return {
        "title": entry.title,
        "custom_field": extracted_data
    }
```

## 📋 Release Process

### **Version Management**

```bash
# Update version
git tag -a v0.3.0 -m "Release v0.3.0: Add search functionality"

# Build release container
make clean-release VERSION=v0.3.0

# Verify container
podman run --rm newsbrief-api:v0.3.0 --version
```

### **Pre-release Checklist**

- [ ] All tests pass
- [ ] Documentation updated
- [ ] Container builds successfully
- [ ] API endpoints tested manually
- [ ] Database migrations work
- [ ] No linting errors
- [ ] Version tagged in git

## 🤝 Contributing

### **Project Planning & Issues**

Before starting development, check the **[GitHub Project Board](https://github.com/users/Deim0s13/projects/7/views/1?layout=board)** for:

- **Current epics** and their progress status
- **Open issues** ready for development  
- **Sprint planning** and release milestones
- **Epic breakdowns** with detailed user stories

The project board organizes work into focused epics:
- **epic:ingestion** - RSS feed processing improvements
- **epic:summaries** - ✅ Complete: AI summarization with Ollama integration  
- **epic:ranking** - Content scoring and curation algorithms
- **epic:ui** - Web interface development with HTMX
- **epic:embeddings** - Semantic search and vector operations
- **epic:search** - Full-text search and query capabilities  
- **epic:ops** - DevOps, monitoring, and deployment tooling

### **Pull Request Process**

1. **Choose an issue** from the project board
2. **Fork repository** and create feature branch
3. **Make changes with tests** and update documentation
4. **Reference issue number** in commit messages
5. **Submit pull request** with clear description

### **Commit Message Format**

```
type(scope): brief description

Optional longer description explaining the change.

- Add new feature X
- Fix bug Y
- Update documentation Z
```

Types: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`

## 📞 Getting Help

- **Issues**: Check existing GitHub issues
- **Discussions**: Use GitHub Discussions for questions
- **Code Review**: All PRs welcome review and feedback
- **Documentation**: Update docs for any user-facing changes

---

Happy coding! 🚀

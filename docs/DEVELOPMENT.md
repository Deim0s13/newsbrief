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

```bash
# Optional: Ollama integration (for future LLM features)
export OLLAMA_BASE_URL=http://localhost:11434

# Optional: Custom data directory
export DATA_DIR=/path/to/your/data
```

## 🧪 Testing & Debugging

### **Manual API Testing**

```bash
# Add a test feed
curl -X POST http://localhost:8787/feeds \
  -H "Content-Type: application/json" \
  -d '{"url": "https://feeds.bbci.co.uk/news/rss.xml"}'

# Fetch articles
curl -X POST http://localhost:8787/refresh

# List articles
curl "http://localhost:8787/items?limit=5" | jq .
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
- **epic:summaries** - LLM integration and content summarization  
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

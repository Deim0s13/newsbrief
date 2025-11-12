# NewsBrief

> **AI-powered news aggregator that synthesizes multiple sources into daily story briefs**

NewsBrief is a self-hosted, privacy-focused news aggregator that replaces reading 50+ article summaries with 5-10 synthesized stories. Using local AI, it clusters related articles, extracts key insights, and presents "what happened today" in 2 minutes. Built with modern technologies for speed, reliability, and offline capability.

**Think**: TLDR newsletter, but personalized to your feeds and generated locally.

## 🌟 Features

### **Current (v0.3.4)**
- **RSS Feed Management**: Import feeds from OPML or add individually via API
- **Intelligent Content Extraction**: Clean article content using Mozilla Readability
- **Long Article Processing**: Map-reduce summarization for articles exceeding context limits with intelligent chunking
- **Structured AI Summarization**: Local LLM via Ollama generates structured JSON summaries with bullets, significance analysis, and topic tags
- **Fallback Summary Display**: Intelligent first-2-sentences extraction when AI services are offline or unavailable
- **Advanced Caching System**: Hash+model based caching for instant responses and cross-article deduplication
- **Batch Processing**: Efficient multi-article summarization with comprehensive error handling
- **Robots.txt Compliance**: Respects robots.txt policies at both feed and article levels
- **Enhanced Fetch Caps**: Configurable global and per-feed limits with time-based safety caps
- **Fair Distribution**: Prevents individual feeds from consuming entire refresh quota
- **Comprehensive Monitoring**: Detailed statistics, performance metrics, cache hit rates, and configuration visibility
- **Efficient Caching**: ETag and Last-Modified support to minimize bandwidth
- **Local SQLite Storage**: Fast, reliable, file-based database with optimized indexing
- **Content Deduplication**: SHA256-based hashing with intelligent cache invalidation  
- **RESTful API**: Enhanced JSON endpoints with structured summary support and backward compatibility
- **Container Ready**: Docker/Podman support with optimized builds and environment configuration

### **🚀 DevOps & CI/CD (v0.3.4)**
- **Enterprise CI/CD Pipeline**: Automated testing, building, security scanning, and multi-environment deployment
- **Security-First Approach**: Multi-layer vulnerability scanning with Trivy, Safety, Bandit, and Super-Linter
- **Pre-commit Quality Gates**: Automated code formatting, linting, security checks, and secrets detection
- **Multi-Architecture Builds**: Automated container builds for amd64/arm64 with GitHub Container Registry
- **GitOps-Ready Deployments**: Environment-specific Kubernetes manifests with health checks and rollback support
- **Automated Dependency Management**: Weekly security audits, dependency updates, and base image maintenance
- **Comprehensive Documentation**: Complete CI/CD guides, API documentation, and architecture decision records

### **In Development (v0.5.0 - Story Architecture)**
- ✅ **Story Database Infrastructure**: Complete schema with stories and article links (Issues #36-38)
- ✅ **Story Generation Pipeline**: Hybrid clustering (topic + keyword similarity) with LLM synthesis (Issue #39)
- ✅ **Multi-Document Synthesis**: Ollama-powered synthesis combining multiple sources into coherent narratives
- ✅ **Entity Extraction**: LLM identifies companies, products, and people from article clusters
- ✅ **Topic Auto-Classification**: Stories automatically tagged with relevant topics
- 🚧 **Story API Endpoints**: RESTful endpoints for generating and retrieving stories
- 🚧 **Scheduled Generation**: Cron-based daily story generation
- 🚧 **Story-First UI**: Landing page redesign to show stories, not individual articles
- 🚧 **Manual Refresh**: On-demand story regeneration from UI
- 🚧 **Interest-Based Filtering**: Surface relevant stories based on user-selected topics

### **Future Enhancements**
- **Configurable Time Windows**: 12h, 24h, 48h, 1w story generation
- **Topic Grouping**: Group stories by Security, AI, DevTools, etc.
- **Advanced Embeddings**: Vector-based semantic clustering
- **Full-Text Search**: SQLite FTS5 integration
- **Export/Import**: Data portability and backup features

## 🚀 Quick Start

### **Using Container (Recommended)**

```bash
# Clone and run with Podman/Docker
git clone https://github.com/yourusername/newsbrief.git
cd newsbrief

# Start with compose
podman-compose up -d
# OR
docker-compose up -d

# Access API at http://localhost:8787
```

### **Using Make (Development)**

```bash
# Build and run locally
make clean-release VERSION=v0.3.4
make run

# Check available commands
make help
```

### **Manual Build**

```bash
# Build container
podman build -t newsbrief-api .

# Run with data persistence
podman run --rm -it \
  -p 8787:8787 \
  -v ./data:/app/data \
  -e OLLAMA_BASE_URL=http://host.containers.internal:11434 \
  --name newsbrief newsbrief-api
```

## 📖 Usage

### **Story-Based Workflow** (v0.5.0+)

```bash
# 1. Add your RSS feeds
curl -X POST http://localhost:8787/feeds \
  -H "Content-Type: application/json" \
  -d '{"url": "https://feeds.example.com/rss"}'

# Or import from OPML (place feeds.opml in ./data/)
# Feeds are automatically imported on startup

# 2. Fetch articles from feeds
curl -X POST http://localhost:8787/refresh

# 3. Generate daily story brief (5-10 synthesized stories)
curl -X POST http://localhost:8787/stories/generate | jq .

# 4. View today's stories
curl http://localhost:8787/stories | jq .

# 5. Get specific story with supporting articles
curl http://localhost:8787/stories/1 | jq .
```

### **Current Workflow** (v0.3.4 - Article-Based)

```bash
# Refresh all feeds
curl -X POST http://localhost:8787/refresh

# Get latest articles (to be replaced by stories)
curl "http://localhost:8787/items?limit=10" | jq .
```

### **API Endpoints**

| Endpoint | Method | Purpose | Status |
|----------|--------|---------|--------|
| `/feeds` | POST | Add new RSS feed | ✅ Available |
| `/refresh` | POST | Fetch latest articles from all feeds | ✅ Available |
| `/stories` | GET | List synthesized stories | 🚧 v0.5.0 |
| `/stories/{id}` | GET | Get story with supporting articles | 🚧 v0.5.0 |
| `/stories/generate` | POST | Generate/refresh stories | 🚧 v0.5.0 |
| `/items` | GET | List articles (secondary feature) | ✅ Available |
| `/docs` | GET | Interactive API documentation | ✅ Available |

## 🧠 Story Generation (v0.5.0)

NewsBrief now includes an AI-powered story generation pipeline that synthesizes multiple articles into coherent narratives.

### How It Works

1. **Article Collection**: Queries articles from the last 24 hours (configurable)
2. **Topic Grouping**: Groups articles by their primary topic (AI/ML, Security, etc.)
3. **Keyword Clustering**: Within each topic, clusters articles by title similarity (Jaccard index)
4. **LLM Synthesis**: For each cluster, prompts Ollama to:
   - Generate a coherent narrative from multiple sources
   - Extract key points (3-8 bullets)
   - Identify entities (companies, products, people)
   - Classify topics
   - Explain "why it matters"
5. **Storage**: Stores synthesized stories with links to source articles

### Features

- ✅ **Hybrid Clustering**: Topic grouping + keyword similarity for intelligent article grouping
- ✅ **Multi-Document Synthesis**: Ollama-powered synthesis combining multiple sources
- ✅ **Entity Extraction**: Automatically identifies companies, products, and people
- ✅ **Topic Classification**: Stories auto-tagged with relevant topics
- ✅ **Graceful Fallback**: Works without LLM (uses simple concatenation)
- ✅ **Configurable**: Time windows, similarity thresholds, minimum articles per story

### Usage

```python
from app.db import session_scope
from app.stories import generate_stories_simple

with session_scope() as session:
    story_ids = generate_stories_simple(
        session=session,
        time_window_hours=24,      # Lookback period
        min_articles_per_story=1,  # Minimum articles per story
        similarity_threshold=0.3,  # Keyword overlap threshold
        model="llama3.1:8b"        # LLM model
    )
```

**See**: [Python API Documentation](docs/API.md#-python-api-v050) for complete usage guide.

---

## 🏗️ Architecture

NewsBrief follows **local-first principles** with story-first aggregation:

```
┌─────────────────────────────────────────────┐
│           Story-First Frontend              │
│            (HTMX + Jinja2)                 │
│     Landing: Stories → Story Detail         │
│              [v0.5.0]                       │
├─────────────────────────────────────────────┤
│              FastAPI Server                 │
│         (REST API + Templates)              │
├─────────────────────────────────────────────┤
│             Business Logic                  │
│  ┌──────────┬──────────┬─────────────────┐  │
│  │  Story   │  Entity  │ Multi-Document  │  │
│  │Clustering│Extraction│   Synthesis     │  │
│  ├──────────┼──────────┼─────────────────┤  │
│  │  Feeds   │ Content  │  LLM (Ollama)   │  │
│  │ Manager  │ Extract  │  Llama 3.1 8B   │  │
│  └──────────┴──────────┴─────────────────┘  │
├─────────────────────────────────────────────┤
│              SQLite Database                │
│  Stories + Story-Articles + Articles        │
│              + Feeds + Cache                │
└─────────────────────────────────────────────┘
```

**Key Design Decisions:**
- **Story-First**: Aggregate articles into synthesized narratives, not individual summaries
- **Local LLM**: Ollama (Llama 3.1 8B) for entity extraction and multi-doc synthesis
- **Intelligent Clustering**: Entity overlap + text similarity + time proximity
- **Daily Generation**: Auto-generate 5-10 stories daily + manual refresh
- **SQLite**: Simple, fast, no external dependencies
- **FastAPI**: Modern Python web framework with automatic OpenAPI docs
- **Container-first**: Podman/Docker for easy deployment
- **Privacy-First**: All AI processing runs locally

## 🛠️ Development

### **Prerequisites**
- Python 3.11+
- Podman or Docker
- Make (optional, for convenience commands)

### **Setup Development Environment**

```bash
# Clone repository
git clone https://github.com/yourusername/newsbrief.git
cd newsbrief

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run locally
uvicorn app.main:app --reload --port 8787
```

### **Development Workflow**

NewsBrief uses **enterprise-grade CI/CD** with automated testing, security scanning, and deployment:

```bash
# 🚀 Quick Setup (First Time)
pip install -r requirements.txt -r requirements-dev.txt
pip install pre-commit && pre-commit install

# 🔧 Development with Quality Gates  
# Pre-commit hooks run automatically on commit:
# ✅ Black formatting, isort imports, security scanning
# ✅ Secrets detection, YAML validation, Dockerfile linting

git add . && git commit -m "feat: new feature"  # Triggers quality checks
git push origin feature-branch                 # Triggers full CI/CD pipeline

# 📦 Container Development
make build                      # Build container locally
make run                       # Run container with live reload
make local-release VERSION=v0.3.4  # Tagged release with cleanup

# 🔍 Manual Quality Checks
black app/ && isort app/        # Format code
mypy app/ --ignore-missing-imports  # Type checking
safety check -r requirements.txt    # Security audit
```

**🚀 Automated Pipeline**: Push to `dev` → Testing & Security Scan → Multi-arch Build → Deploy to Development

**📚 Complete CI/CD Guide**: See [`docs/CI-CD.md`](docs/CI-CD.md) for comprehensive workflow documentation.

### **Project Structure**

```
newsbrief/
├── app/                    # Application code
│   ├── main.py            # FastAPI app and routes  
│   ├── db.py              # Database connection and schema
│   ├── feeds.py           # RSS fetching and processing
│   ├── models.py          # Pydantic models
│   ├── readability.py     # Content extraction
│   └── llm.py             # LLM integration with Ollama
├── .github/workflows/      # CI/CD automation
│   ├── ci-cd.yml          # Main pipeline (test, build, deploy)
│   ├── dependencies.yml   # Automated dependency updates
│   ├── project-automation.yml  # GitHub project sync
│   └── gitops-deploy.yml  # GitOps deployment workflows
├── docs/                   # Documentation
│   ├── CI-CD.md           # Complete CI/CD guide
│   ├── DEVELOPMENT.md     # Development setup and workflow
│   ├── API.md             # API reference
│   └── adr/               # Architecture decision records
├── data/                   # Persistent data
│   └── newsbrief.sqlite3  # Database (generated)
├── scripts/               # Automation scripts
├── Dockerfile            # Container definition
├── compose.yaml          # Multi-service setup
├── Makefile             # Build automation
├── requirements.txt     # Production dependencies
├── requirements-dev.txt  # Development dependencies
└── .pre-commit-config.yaml # Code quality automation
```

## 🎯 Roadmap

> **📋 Live Project Board**: Track detailed progress and epic breakdowns at  
> **[GitHub Project Board](https://github.com/users/Deim0s13/projects/7/views/1?layout=board)**

### **v0.5.0 - Story Architecture** 🚀 **In Development**
Transform from article-centric to story-based aggregation

**Phase 1-3: Core Engine** (26-37 hours) - PARTIALLY COMPLETE
- [x] Story database schema and models (Issues #36-37)
- [x] Story CRUD operations (Issue #38)
- [x] Story generation pipeline with hybrid clustering (Issue #39)
- [x] Multi-document synthesis (AI-powered, Issue #39)
- [x] Entity extraction from article clusters (Issue #39)
- [x] Quality scoring basics: importance + freshness (Issue #39)
- [ ] Enhanced entity extraction (dedicated article-level function)
- [ ] Advanced text similarity clustering (embeddings-based)
- [ ] Story deduplication and merging
- [ ] Configurable clustering parameters

**Phase 4: Automation** (4-6 hours) - PARTIALLY COMPLETE
- [x] Story archiving/cleanup CRUD functions (Issue #38)
- [ ] Daily auto-generation (scheduled task)
- [ ] Manual refresh API endpoint
- [ ] Story retention policies and automation

**Phase 5-6: Story-First UI** (10-14 hours)
- [ ] Landing page with story cards (5-10 stories)
- [ ] Story detail page (synthesis + supporting articles)
- [ ] Topic filters and manual refresh button
- [ ] Article view as secondary feature

**Phase 7-8: Refinement** (7-10 hours)
- [ ] Story API endpoints
- [ ] Interest-based filtering
- [ ] Source quality weighting

**See**: [Implementation Plan](docs/IMPLEMENTATION_PLAN.md) | [Detailed Backlog](docs/STORY_ARCHITECTURE_BACKLOG.md)

### **v0.6.0 - Enhanced Intelligence**
- [ ] Configurable time windows (12h, 24h, 48h, 1w)
- [ ] Topic grouping (Security, AI, DevTools sections)
- [ ] Dynamic story generation (quality-based)
- [ ] Vector embeddings for better clustering
- [ ] Full-text search (SQLite FTS5)

### **Epic Organization**

The roadmap above represents high-level milestones. For detailed epic breakdowns, user stories, and current development status, see the **[GitHub Project Board](https://github.com/users/Deim0s13/projects/7/views/1?layout=board)** which includes:

- **Epic: Stories** - 🚀 Story-based aggregation and synthesis (NEW)
- **Epic: Ingestion** - Feed processing and content extraction
- **Epic: Summaries** - AI-powered content summarization with Ollama
- **Epic: Ranking** - Content scoring and intelligent curation
- **Epic: UI** - Web interface and user experience enhancements  
- **Epic: Operations** - DevOps, monitoring, and deployment tooling
- **Epic: Embeddings** - Semantic search and advanced clustering (Future)
- **Epic: Search** - Full-text and semantic search capabilities (Future)

## 🤝 Contributing

We welcome contributions! Here's how to get started:

### **Find Work to Do**
1. **Check the [GitHub Project Board](https://github.com/users/Deim0s13/projects/7/views/1?layout=board)** for current epics and open issues
2. **Look for issues labeled** `good first issue` or `help wanted`  
3. **Comment on issues** you'd like to work on to avoid duplication

### **Development Process**
1. **Fork the repository**
2. **Create feature branch**: `git checkout -b feature/amazing-feature`
3. **Make changes and test**: `make build && make run`
4. **Commit with clear messages**: `git commit -m "Add amazing feature"`
5. **Push and create PR**: `git push origin feature/amazing-feature`

### **Development Guidelines**
- Follow existing code style and patterns
- Add tests for new functionality
- Update documentation for new features
- Use semantic versioning for releases

## 🙏 Acknowledgments

- [Mozilla Readability](https://github.com/mozilla/readability) for content extraction
- [FastAPI](https://fastapi.tiangolo.com/) for the excellent web framework
- [Ollama](https://ollama.ai/) for local LLM capabilities


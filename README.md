# NewsBrief

> **AI-powered news aggregator that synthesizes multiple sources into daily story briefs**

NewsBrief is a self-hosted, privacy-focused news aggregator that replaces reading 50+ article summaries with 5-10 synthesized stories. Using local AI, it clusters related articles, extracts key insights, and presents "what happened today" in 2 minutes. Built with modern technologies for speed, reliability, and offline capability.

**Think**: TLDR newsletter, but personalized to your feeds and generated locally.

## 🌟 Features

### **🎯 Story-Based Aggregation (v0.7.1)** - *Current Release*
Replace reading 50+ article summaries with 5-10 AI-synthesized story briefs. **Time to informed: 30 min → 2 min**

- **Automated Story Generation**: Daily scheduled generation at 6 AM (configurable timezone)
- **🧠 Entity Extraction (v0.6.1)**: Identifies companies, products, people, technologies, and locations
- **🔗 Semantic Similarity (v0.6.1)**: Enhanced clustering with entity overlap (50%) + keywords (30%) + topic bonus (20%)
- **⭐ Quality Scoring (v0.6.1)**: Three-dimensional scoring for importance, freshness, and overall quality
- **Intelligent Clustering**: Hybrid topic grouping + keyword similarity for related article detection
- **Multi-Document Synthesis**: LLM-powered synthesis combining multiple sources into coherent narratives
- **Entity Extraction**: Automatically identifies companies, products, and people from article clusters
- **Topic Auto-Classification**: Stories tagged with Security, AI/ML, DevTools, Cloud/K8s, etc.
- **Story-First UI**: Landing page shows stories (not articles) with filters, sorting, and pagination
- **Supporting Articles**: Each story links to source articles with structured summaries
- **Manual Refresh**: On-demand story generation via UI or API
- **Performance Optimized**: Parallel LLM synthesis (3 workers), caching, batching - 80% faster
- **RESTful Story API**: Complete endpoints for generation, retrieval, filtering, and monitoring
- **Automatic Archiving**: Old stories archived after 7 days (configurable)
- **Scheduler Monitoring**: Real-time status of automated feed refresh and story generation

### **📰 RSS Feed Management**
- **OPML Import/Export**: Bulk feed management with category preservation
- **Feed Health Monitoring**: Multi-factor scoring (response time, success rate, failure tracking)
- **Configurable Fetch Limits**: Global and per-feed caps with fair distribution
- **Robots.txt Compliance**: Respects policies at feed and article levels
- **Efficient Caching**: ETag and Last-Modified support to minimize bandwidth

### **🤖 AI-Powered Content Processing**
- **Structured AI Summarization**: Local LLM via Ollama generates JSON summaries with bullets and significance
- **Intelligent Content Extraction**: Mozilla Readability for clean article content
- **Long Article Handling**: Map-reduce summarization for articles exceeding context limits
- **Fallback Summaries**: Intelligent first-sentence extraction when LLM unavailable
- **Advanced Caching**: Hash+model based caching for instant responses
- **Batch Processing**: Efficient multi-article summarization with error handling

### **🎨 Web Interface**
- **Story-First Landing**: Browse synthesized stories (not individual articles)
- **Story Detail Pages**: Full synthesis with key points, entities, and supporting articles
- **Article Browsing**: Secondary view for exploring individual articles with skim/detail toggle
- **Topic Filtering**: Filter by Security, AI/ML, DevTools, Cloud/K8s, etc.
- **Responsive Design**: Locally-built Tailwind CSS with dark mode support
- **Feed Management Dashboard**: CRUD operations, health monitoring, bulk operations

### **🚀 DevOps & CI/CD (v0.3.4)**
- **Modern CI/CD Pipeline**: Automated testing, building, security scanning, and multi-environment deployment
- **Security-First Approach**: Multi-layer vulnerability scanning with Trivy, Safety, Bandit, and Super-Linter
- **Pre-commit Quality Gates**: Automated code formatting, linting, security checks, and secrets detection
- **Multi-Architecture Builds**: Automated container builds for amd64/arm64 with GitHub Container Registry
- **GitOps-Ready Deployments**: Environment-specific Kubernetes manifests with health checks and rollback support
- **Automated Dependency Management**: Weekly security audits, dependency updates, and base image maintenance
- **Comprehensive Documentation**: Complete CI/CD guides, API documentation, and architecture decision records

### **✅ Completed (v0.7.1 - PostgreSQL Migration)** - Jan 2026
- ✅ **PostgreSQL Support**: Production-ready database via DATABASE_URL
- ✅ **Dual Database Mode**: SQLite for development, PostgreSQL for production
- ✅ **ORM Models**: Central orm_models.py with portable schema
- ✅ **Alembic Migrations**: Schema versioning and migration tooling
- ✅ **Database Commands**: make db-up, db-down, db-psql, db-reset

### **✅ Completed (v0.6.5 - Personalization)** - Jan 2026
- ✅ **Interest-Based Ranking**: Topic weights for personalized story ordering (Issue #57)
- ✅ **Source Quality Weighting**: Feed/domain reputation weights blended into scoring (Issue #58)
- ✅ **Feed Health Improvements**: Response time tracking with slow feed indicators (Issue #71)
- ✅ **Configurable Blending**: 50% importance + 30% interest + 20% source quality
- ✅ **Personalization Toggle**: Enable/disable personalized ranking in UI

### **✅ Completed (v0.6.4 - Code Quality)** - Jan 2026
- ✅ **Type Safety**: mypy passes with 0 errors in 13 source files (Issue #74)
- ✅ **Test Coverage**: Coverage improved 30% → 41% with 192 tests (Issue #75)
- ✅ **Ranking Tests**: Comprehensive tests for recency, keywords, topic classification (Issue #22)
- ✅ **CI/CD Improvements**: pytest-cov integration, coverage reporting

### **✅ Completed (v0.6.3 - Performance)** - Jan 2026
- ✅ **Synthesis Caching**: LLM results cached with TTL and invalidation (Issue #46)
- ✅ **Incremental Updates**: Story versioning with 70% article overlap detection (Issue #49)
- ✅ **API Enhancements**: 6 new filters on `/items`, `/stories/{id}/articles` endpoint (Issue #56)
- ✅ **Scheduled Refresh**: Automatic feed refresh at 5:30 AM (configurable) (Issue #87)

### **✅ Completed (v0.6.2 - UI Polish & Fixes)** - Dec 2025
- ✅ **HTML Sanitization**: Clean article summaries with `bleach` library (Issue #77)
- ✅ **Topic Classification**: Unified topic system with LLM-based classification (Issue #77)
- ✅ **Skim View Fixed**: Local Tailwind CSS build for proper styling (Issue #80)
- ✅ **Story Filters**: Topic filtering on Stories page (Issue #81)
- ✅ **Model/Status Display**: Story detail page shows LLM model and status (Issue #82)
- ✅ **Default LLM Upgrade**: Changed default model to `llama3.1:8b` for better accuracy

### **✅ Completed (v0.6.1 - Enhanced Intelligence)** - Dec 2025
- ✅ **Entity Extraction**: LLM-based extraction of companies, products, people, technologies, locations (Issue #40)
- ✅ **Semantic Similarity**: Enhanced clustering with entity overlap and bigrams/trigrams (Issue #41)
- ✅ **Story Quality Scoring**: Importance, freshness, and quality scoring algorithms (Issue #43)
- ✅ **UX Improvements**: Detailed feedback messages for story generation (Issue #67)
- ✅ **Skim/Detail Toggle**: Flexible viewing modes for articles (Issue #70)
- ✅ **Story Architecture**: Complete database schema, generation pipeline, multi-document synthesis (v0.5.5)
- ✅ **Entity Extraction**: LLM identifies companies, products, and people from article clusters
- ✅ **Topic Auto-Classification**: Stories automatically tagged with relevant topics
- ✅ **Story API Endpoints**: RESTful endpoints for generating and retrieving stories (Issues #47, #55)
- ✅ **Scheduled Generation**: Daily automated story generation at 6 AM (configurable timezone, Issue #48)
- ✅ **Story-First UI**: Landing page shows stories, not individual articles (Issues #50-54)
- ✅ **Performance Optimization**: Parallel LLM synthesis, caching, batching (Issue #66)

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
make clean-release VERSION=v0.5.3
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

### **Story-Based Workflow** (v0.5.5+)

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
| `/stories` | GET | List synthesized stories | ✅ v0.5.5 |
| `/stories/{id}` | GET | Get story with supporting articles | ✅ v0.5.5 |
| `/stories/generate` | POST | Generate/refresh stories | ✅ v0.5.5 |
| `/stories/stats` | GET | Story generation statistics | ✅ v0.5.5 |
| `/scheduler/status` | GET | Monitor automated feed refresh & story generation | ✅ v0.6.3 |
| `/items` | GET | List articles (secondary feature) | ✅ Available |
| `/docs` | GET | Interactive API documentation | ✅ Available |

## 🧠 Story Generation (v0.5.5)

### Why We Changed Approach

**Original Vision**: Replace reading 50+ article summaries (like TLDR newsletters) with 5-10 AI-synthesized story briefs.

**The Problem**: NewsBrief v0.3.x evolved into an article-centric RSS reader where users still scrolled through individual summaries—defeating the original purpose of reducing information overload.

**The Solution (v0.5.5)**: Return to the original scope by pivoting to **story-based aggregation**. Instead of presenting 50+ individual articles, NewsBrief now:
- Clusters related articles into unified narratives
- Synthesizes multiple sources into coherent stories
- Presents 5-10 curated stories daily
- Reduces reading time from 30+ minutes to 2 minutes

**Result**: A true TLDR-killer that provides "what happened today" in minutes, not hours.

**See**: [ADR 0002: Story-Based Aggregation](docs/adr/0002-story-based-aggregation.md) for full context and architectural decisions.

---

### How Story Generation Works

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

**See**: [Python API Documentation](docs/user-guide/API.md#-python-api-v050) for complete usage guide.

---

## 🏗️ Architecture

NewsBrief follows **local-first principles** with story-first aggregation:

```
┌─────────────────────────────────────────────┐
│           Story-First Frontend              │
│            (HTMX + Jinja2)                 │
│     Landing: Stories → Story Detail         │
│              [v0.6.1]                       │
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

# Install Python dependencies
pip install -r requirements.txt

# Install Node.js dependencies (for CSS build)
npm install

# Build CSS (required after CSS changes)
npm run build:css
# Or watch for changes during development:
npm run watch:css

# Run locally
uvicorn app.main:app --reload --port 8787
```

### **Database Configuration**

NewsBrief supports two database backends:
- **SQLite** (default): Zero-config, perfect for development and single-user
- **PostgreSQL**: Production-ready, concurrent access, recommended for deployment

#### SQLite (Default)
No configuration needed. Database is created at `data/newsbrief.sqlite3`.

#### PostgreSQL Setup

```bash
# 1. Create environment file
cp .env.example .env
# Edit .env and set POSTGRES_PASSWORD

# 2. Start PostgreSQL container
make db-up

# 3. Run database migrations
make migrate

# 4. Run app with PostgreSQL
source .env && make run-local
```

#### Database Commands

```bash
make db-up          # Start PostgreSQL container
make db-down        # Stop PostgreSQL container
make db-logs        # View PostgreSQL logs
make db-psql        # Connect with psql
make db-reset       # Reset database (WARNING: deletes all data)

make migrate        # Run migrations to latest
make migrate-stamp  # Mark existing DB as current
make migrate-new MSG="description"  # Create new migration
```

#### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string | *(SQLite if not set)* |
| `POSTGRES_PASSWORD` | Password for docker-compose | *(required for Postgres)* |

### **Development Workflow**

NewsBrief uses **modern CI/CD practices** with automated testing, security scanning, and deployment:

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
make local-release VERSION=v0.4.0  # Tagged release with cleanup

# 🔍 Manual Quality Checks
black app/ && isort app/        # Format code
mypy app/ --ignore-missing-imports  # Type checking
safety check -r requirements.txt    # Security audit
```

**🚀 Automated Pipeline**: Push to `dev` → Testing & Security Scan → Multi-arch Build → Deploy to Development

**📚 Complete CI/CD Guide**: See [`docs/development/CI-CD.md`](docs/development/CI-CD.md) for comprehensive workflow documentation.

### **Project Structure**

```
newsbrief/
├── app/                    # Application code
│   ├── main.py            # FastAPI app and routes  
│   ├── db.py              # Database connection (SQLite/PostgreSQL)
│   ├── orm_models.py      # SQLAlchemy ORM models
│   ├── models.py          # Pydantic schemas
│   ├── feeds.py           # RSS fetching and processing
│   ├── stories.py         # Story generation and CRUD
│   ├── readability.py     # Content extraction
│   └── llm.py             # LLM integration with Ollama
├── alembic/               # Database migrations
│   ├── env.py            # Migration environment config
│   └── versions/         # Migration scripts
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

### **v0.5.5 - Story Architecture** ✅ **COMPLETE** (Nov 2025)
Transform from article-centric to story-based aggregation

**Phase 1: Core Infrastructure** - ✅ COMPLETE
- [x] Story database schema and models (Issues #36-37)
- [x] Story CRUD operations (8 functions, Issue #38)
- [x] Story generation pipeline with hybrid clustering (Issue #39)
- [x] Multi-document synthesis (AI-powered, Issue #39)
- [x] Entity extraction from article clusters (Issue #39)
- [x] Quality scoring basics: importance + freshness (Issue #39)
- [x] Story API endpoints (4 endpoints, Issues #47, #55)
  - [x] POST /stories/generate (on-demand generation)
  - [x] GET /stories (list with filtering/sorting/pagination)
  - [x] GET /stories/{id} (single story details)
  - [x] GET /stories/stats (generation statistics)
  - [x] GET /scheduler/status (monitor feed refresh & story generation)
- [x] Python API fully functional
- [x] Real data testing (150 articles → 379 stories)

**Phase 2: Automation & UI** - ✅ COMPLETE
- [x] Scheduled story generation (daily at 6 AM, configurable, Issue #48)
- [x] Story-First UI landing page (Issue #50)
- [x] Story detail page with supporting articles (Issue #53)
- [x] Story filters and controls (Issue #51)
- [x] Landing page empty states (Issue #52)
- [x] Story to article navigation (Issue #54)
- [x] Manual "Generate Stories" button
- [x] Topic filters and sorting

**Phase 3: Optimization** - ✅ COMPLETE
- [x] Performance optimization (parallel LLM, caching, batching, Issue #66)
- [x] Concurrent story synthesis (3 workers)
- [x] Cached article data
- [x] Batched database commits
- [x] 80% reduction in generation time

**See**: [Implementation Plan](docs/project-management/IMPLEMENTATION_PLAN.md) | [Detailed Backlog](docs/planning/STORY_ARCHITECTURE_BACKLOG.md)

### **v0.6.0 - Enhanced Intelligence** - ✅ COMPLETE
- [x] **v0.6.1 - Enhanced Clustering**: Entity extraction, semantic similarity, quality scoring ✅ COMPLETE (Dec 2025)
- [x] **v0.6.2 - UI Polish & Fixes**: Local Tailwind build, topic filters, HTML sanitization ✅ COMPLETE (Dec 2025)
- [x] **v0.6.3 - Performance**: Synthesis caching, incremental updates, scheduled refresh ✅ COMPLETE (Jan 2026)
- [x] **v0.6.4 - Code Quality**: Type safety, test coverage, CI/CD improvements ✅ COMPLETE (Jan 2026)
- [x] **v0.6.5 - Personalization**: Interest-based ranking, source quality weighting, feed health improvements ✅ COMPLETE (Jan 2026)

### **Project Tracking**

Development is organized with GitHub Projects and Milestones for clear visibility:

📋 **[GitHub Issues](https://github.com/Deim0s13/newsbrief/issues)** - All issues with labels and milestones  
🎯 **[Milestones](https://github.com/Deim0s13/newsbrief/milestones)** - Release targets with progress tracking  
📊 **GitHub Project Board** - Kanban board (Backlog → Next → In Progress → Done)

**Milestones**:
- [v0.5.5 - Story Architecture](https://github.com/Deim0s13/newsbrief/milestone/1) - ✅ **COMPLETE** (Nov 2025)
- [v0.6.1 - Enhanced Clustering](https://github.com/Deim0s13/newsbrief/releases/tag/v0.6.1) - ✅ **COMPLETE** (Dec 2025)
- [v0.6.2 - UI Polish & Fixes](https://github.com/Deim0s13/newsbrief/releases/tag/v0.6.2) - ✅ **COMPLETE** (Dec 2025)
- [v0.6.3 - Performance](https://github.com/Deim0s13/newsbrief/releases/tag/v0.6.3) - ✅ **COMPLETE** (Jan 2026)
- [v0.6.4 - Code Quality](https://github.com/Deim0s13/newsbrief/releases/tag/v0.6.4) - ✅ **COMPLETE** (Jan 2026)
- [v0.6.5 - Personalization](https://github.com/Deim0s13/newsbrief/releases/tag/v0.6.5) - ✅ **COMPLETE** (Jan 2026)
- [v0.7.1 - PostgreSQL Migration](https://github.com/Deim0s13/newsbrief/releases/tag/v0.7.1) - ✅ **COMPLETE** (Jan 2026)

**Epics** (via labels):
- **epic:stories** - Story-based aggregation and synthesis
- **epic:ui** - Web interface and user experience
- **epic:database** - Data layer and migrations
- **epic:security** - Authentication, encryption, hardening
- **epic:ops** - CI/CD, deployment, monitoring  
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


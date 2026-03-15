# NewsBrief

> **AI-powered news aggregator that synthesizes multiple sources into daily story briefs**

NewsBrief is a self-hosted, privacy-focused news aggregator that replaces reading 50+ article summaries with 5-10 synthesized stories. Using local AI, it clusters related articles, extracts key insights, and presents "what happened today" in 2 minutes. Built with modern technologies for speed, reliability, and offline capability.

**Think**: TLDR newsletter, but personalized to your feeds and generated locally.

## 🌟 Features

### **🎯 Story-Based Aggregation (v0.8.0)** - *Current Release*
Replace reading 50+ article summaries with 5-10 AI-synthesized story briefs. **Time to informed: 30 min → 2 min**

- **Automated Story Generation**: Daily scheduled generation at 6 AM (configurable timezone)
- **🧠 Enhanced Entity Extraction (v0.8.1)**: Confidence scores, roles (primary/mentioned/quoted), disambiguation hints
- **🔗 Semantic Similarity (v0.6.1)**: Enhanced clustering with entity overlap (50%) + keywords (30%) + topic bonus (20%)
- **⭐ Quality Metrics (v0.8.1)**: LLM output quality tracking with dashboard at `/admin/quality`
- **🎯 Multi-Topic Classification (v0.8.1)**: Primary + secondary topics with calibrated confidence scores
- **🛡️ Source Credibility (v0.8.2)**: MBFC-powered credibility ratings with visual indicators and synthesis weighting
- **Intelligent Clustering**: Hybrid topic grouping + keyword similarity for related article detection
- **Multi-Pass Synthesis (v0.8.1)**: Story type detection → chain-of-thought analysis → synthesis → refinement
- **Large Cluster Handling (v0.8.1)**: Map-reduce and hierarchical synthesis for 9+ article clusters
- **📊 Story Transparency (v0.8.1)**: Quality breakdown panel + "Why Grouped Together" explanation with shared entities/keywords
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
- **Intelligent Content Extraction**: Tiered extraction (trafilatura → readability-lxml → RSS fallback) with quality scoring
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

### **✅ Previous: v0.8.2 - Source Credibility Integration** (Feb 2026)
Integrate external credibility ratings to improve synthesis quality and transparency (ADR-0028).

- [x] **Source Credibility Schema** (#196): Database schema for credibility data with domain canonicalization
- [x] **MBFC Data Import** (#271): Auto-import and weekly refresh from Media Bias/Fact Check dataset
- [x] **Credibility Admin Dashboard**: Monitor credibility data at `/admin/credibility` with refresh controls
- [x] **UI Credibility Indicators** (#197): Visual badges on stories, articles, and feed management pages
- [x] **Synthesis Integration** (#198): Credibility-weighted article prioritization, ineligible source filtering
- [x] **Story Credibility Tracking**: Aggregate credibility scores stored on synthesized stories

### **✅ Previous: v0.8.1 - LLM Quality & Intelligence** (Feb 2026)
Comprehensive improvements to LLM output quality and content intelligence.

- [x] **Robust LLM Output Validation** (#107): Circuit breakers, retry logic, partial extraction
- [x] **Quality Metrics & Tracking** (#105): Quality scoring for synthesis output with dashboard at `/admin/quality`
- [x] **Enhanced Synthesis Pipeline** (#102): Multi-pass generation (detection → analysis → synthesis → refinement)
- [x] **Enhanced Entity Extraction** (#103): Confidence scores, roles (primary/mentioned/quoted), disambiguation
- [x] **Enhanced Topic Classification** (#104): Multi-topic support, calibrated confidence, edge case detection
- [x] **Context Window Handling** (#106): Smart handling for large clusters (map-reduce/hierarchical synthesis)
- [x] **Quality Breakdown Panel** (#233): Visual breakdown of synthesis quality scores on story pages
- [x] **Why Grouped Together** (#232): Clustering metadata showing shared entities, keywords, and similarity scores
- [x] **Topic Reclassification UI** (#248): Admin page at `/admin/topics` for async bulk topic reclassification
- [x] **LLM Model Evaluation** (#99): Research complete - Qwen 2.5 recommended (see ADR-0025)
- [x] **Model Configuration Profiles** (#100): Fast/Balanced/Quality profiles with Qwen 2.5, admin UI at `/admin/models`
- [x] **RAG Integration Research** (#108): Light RAG with pgvector recommended (see ADR-0026)
- [x] **Fine-Tuning Feasibility** (#109): Deferred - better alternatives first (see ADR-0027)

### **✅ Previous: v0.8.0 - Content Extraction Pipeline Upgrade** (Feb 2026)
Complete overhaul of content extraction with tiered fallback strategy (ADR-0024).

- [x] **Tiered Extraction**: trafilatura (primary) → readability-lxml (fallback) → RSS summary (salvage)
- [x] **Quality Scoring**: 0-1 quality score per article based on extraction method and content
- [x] **Rich Metadata**: Author, date, images, categories, and tags captured when available
- [x] **Extraction Dashboard**: New admin UI at `/admin/extraction` with metrics and failure analysis
- [x] **Observability**: Database columns track extraction method, quality, timing, and errors
- [x] **Regression Tests**: Golden set of synthetic HTML fixtures for quality validation

### **✅ Previous: v0.7.8 - Dev/Prod Environment Parity** (Feb 2026)
Standardized on PostgreSQL for all environments (ADR-0022).

- [x] **PostgreSQL for Dev**: New `make dev-full` target with Docker Compose PostgreSQL
- [x] **Code Cleanup**: Remove `is_postgres()` conditionals and SQLite code paths
- [x] **Single Migration System**: Alembic only, remove inline SQLite migrations

### **✅ Previous: v0.7.7 - Import Progress & Date Fix** (Feb 2026)
- ✅ **Import Progress Indicator**: Real-time progress modal for OPML imports with live stats
- ✅ **Async Import Tracking**: New `/feeds/import/status/{id}` endpoint for polling
- ✅ **Timezone Fix**: Proper UTC handling for article dates in PostgreSQL
- ✅ **Database Schema**: New status/progress columns in `import_history` table

📚 **[Full Release History →](docs/releases/README.md)**

## 🚀 Quick Start

### **Production Deployment (Recommended)**

Deploy the full stack with PostgreSQL, Caddy reverse proxy, and auto-start:

```bash
# Clone repository
git clone https://github.com/Deim0s13/newsbrief.git
cd newsbrief

# First-time setup
make env-init                     # Generate .env with secure password
make hostname-setup               # Add newsbrief.local to /etc/hosts (sudo)
make deploy                       # Start production stack
make deploy-init                  # Initialize database

# Access at https://newsbrief.local

# Optional: Auto-start on login
make autostart-install
```

### **Production with Podman Secrets (Enhanced Security)**

For production deployments with encrypted secrets instead of `.env`:

```bash
# Create encrypted secret (prompts for password)
make secrets-create

# Deploy (automatically uses secrets when available)
make deploy

# Verify secrets in use (look for 🔐 message)
make secrets-list
```

### **Development Mode**

For local development with hot-reload and DEV banner:

```bash
# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Start PostgreSQL + Run app in one command
make dev-full

# OR start separately:
make db-up      # Start PostgreSQL container (requires Docker/Podman)
make dev        # Run development server

# Access at http://localhost:8787
# Orange "DEVELOPMENT MODE" banner distinguishes from production
```

> **Note**: Development requires Docker or Podman for the PostgreSQL container.

### **Quick Container Test**

```bash
# Build and run with compose (dev mode)
podman-compose up -d
# OR
docker-compose up -d

# Access at http://localhost:8787
```

## 🏠 Development vs Production

NewsBrief supports two distinct modes to separate your development work from daily use:

| Aspect | Development | Production |
|--------|-------------|------------|
| **Database** | PostgreSQL (`localhost:5433`) | PostgreSQL (Docker volume) |
| **Data Location** | `newsbrief_dev_data` Docker volume | `newsbrief_data` Docker volume |
| **URL** | `http://localhost:8787` | `https://newsbrief.local` |
| **Visual Indicator** | Orange "DEV" banner + tab prefix | Clean UI (no banner) |
| **Hot Reload** | ✅ Yes | ❌ No |
| **Logs** | Human-readable with colors | JSON structured |
| **Start Command** | `make dev` | `make deploy` |

### Production Commands

```bash
# Deployment
make deploy              # Start production stack
make deploy-stop         # Stop stack (data preserved)
make deploy-status       # Check running containers
make deploy-init         # First-time database setup

# Hostname
make hostname-setup      # Add newsbrief.local to /etc/hosts
make hostname-check      # Verify hostname configured

# Auto-start
make autostart-install   # Enable start on login
make autostart-uninstall # Disable auto-start
make autostart-status    # Check if enabled

# Backup
make db-backup           # Backup to ./backups/
make db-restore FILE=... # Restore from backup
make db-backup-list      # List available backups
```

### Environment Variables

Create a `.env` file (see `.env.example`):

```bash
POSTGRES_PASSWORD=your_secure_password
OLLAMA_BASE_URL=http://host.containers.internal:11434
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

### **API Endpoints**

| Endpoint | Method | Purpose | Status |
|----------|--------|---------|--------|
| `/health` | GET | Comprehensive health check (database, LLM, scheduler) | ✅ v0.7.2 |
| `/healthz` | GET | Kubernetes liveness probe (minimal) | ✅ v0.7.3 |
| `/readyz` | GET | Kubernetes readiness probe (database check) | ✅ v0.7.3 |
| `/ollamaz` | GET | Ollama LLM status with model details | ✅ v0.7.3 |
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
│              Database (PostgreSQL)          │
│  Stories + Story-Articles + Articles        │
│              + Feeds + Cache                │
└─────────────────────────────────────────────┘
```

**Key Design Decisions:**
- **Story-First**: Aggregate articles into synthesized narratives, not individual summaries
- **Local LLM**: Ollama (Llama 3.1 8B) for entity extraction and multi-doc synthesis
- **Intelligent Clustering**: Entity overlap + text similarity + time proximity
- **Daily Generation**: Auto-generate 5-10 stories daily + manual refresh
- **PostgreSQL**: Same database engine in dev and prod (ADR-0022)
- **FastAPI**: Modern Python web framework with automatic OpenAPI docs
- **Container-first**: Podman/Docker with Caddy reverse proxy
- **Privacy-First**: All AI processing runs locally

📐 **[Full Architecture Document →](docs/ARCHITECTURE.md)** - Requirements, principles, diagrams, and component details

## 🛠️ Development

### **Prerequisites**
- Python 3.11+
- Podman or Docker
- Make (optional, for convenience commands)

### **Setup Development Environment**

```bash
# Clone repository
git clone https://github.com/Deim0s13/newsbrief.git
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

NewsBrief uses PostgreSQL for both development and production (ADR-0022).

#### Quick Setup

```bash
# 1. Create environment file
cp .env.example .env
# Edit .env and set POSTGRES_PASSWORD

# 2. Start PostgreSQL + app together
make dev-full

# OR start separately:
make db-up      # Start PostgreSQL container
make migrate    # Run database migrations
make dev        # Run development server
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
| `DATABASE_URL` | PostgreSQL connection string | *(required)* |
| `POSTGRES_PASSWORD` | Password for docker-compose | *(required)* |

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
│   ├── main.py            # FastAPI app factory (mounts routers, startup/shutdown)
│   ├── routers/           # Route modules (health, feeds, stories, items, admin, config, pages)
│   ├── deps.py            # Shared dependencies (session_scope, templates, limiter)
│   ├── db.py              # Database connection (PostgreSQL)
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
│   ├── ARCHITECTURE.md    # Comprehensive architecture document
│   └── development/
│       ├── CI-CD.md       # Complete CI/CD guide
│       ├── DEVELOPMENT.md # Development setup and workflow
│       ├── KUBERNETES.md  # Local K8s setup guide (v0.7.5+)
│   └── adr/               # Architecture decision records
├── k8s/                    # Kubernetes manifests (v0.7.5+)
│   └── infrastructure/     # Registry, RBAC
├── tekton/                 # Tekton CI/CD resources (v0.7.5+)
│   ├── tasks/             # Reusable CI tasks
│   └── pipelines/         # CI/CD pipeline definitions
├── data/                   # Persistent data (logs, cache)
├── scripts/               # Automation scripts
├── Dockerfile            # Multi-stage container build
├── compose.yaml          # Production stack (API + PostgreSQL + Caddy)
├── Caddyfile            # Reverse proxy configuration
├── Makefile             # Build, deploy, and automation commands
├── requirements.txt     # Production dependencies
├── requirements-dev.txt  # Development dependencies
├── .pre-commit-config.yaml # Code quality automation
└── CONTRIBUTING.md      # Development setup guide
```

## 🔧 Operations

### Service Recovery (After Reboot/Sleep)

The Kubernetes-based development environment requires several services to be running. After a laptop reboot or wake from sleep:

```bash
# Full recovery - checks and restarts all services
make recover

# Check status of all services
make status

# Quick restart of just port forwards
make port-forwards
```

See [`ansible/README.md`](ansible/README.md) for detailed operational procedures.

### Service URLs

| Service | URL |
|---------|-----|
| Dev | http://localhost:8787 |
| Prod | https://newsbrief.local |
| Tekton Dashboard | http://localhost:9097 |

### Troubleshooting

**Prod: Browser shows "certificate not trusted" for https://newsbrief.local**

Caddy uses a local root CA. Trust it once on macOS:

```bash
make hostname-trust-cert
# Then run the sudo command it prints (adds CA to system keychain)
# Reload https://newsbrief.local
```

If the export fails, open https://newsbrief.local once (dismiss the warning), then run `make hostname-trust-cert` again.

**Prod: `net::ERR_CERT_DATE_INVALID` (cert expired or wrong date)**

Caddy’s local cert has invalid dates. Regenerate certs and re-trust:

```bash
make hostname-regen-certs
# Then open https://newsbrief.local once, then:
make hostname-trust-cert
# Run the sudo command it prints, then reload. Clear HSTS if needed (see below).
```

**Prod: "You cannot visit newsbrief.local right now because the website uses HSTS"**

After trusting the Caddy cert, the browser may still block the site because it cached HSTS for newsbrief.local from an earlier visit. Clear that cache:

- **Chrome / Edge**: Open `chrome://net-internals/#hsts`. Under **Delete domain security policies**, type `newsbrief.local` and click **Delete**. Then reload https://newsbrief.local.
- **Firefox**: Open `about:config`, search for `security.cert_pinning.enforcement_level`, set to `0` temporarily and reload; or clear site data for newsbrief.local in Settings → Privacy.
- **Safari**: Develop → Empty Caches; or clear website data for newsbrief.local in Settings → Privacy → Manage Website Data (search for newsbrief).

**Dev: Internal server error (500) when using the app**

1. Check the terminal where `make dev` is running for the Python traceback, or `curl -s http://localhost:8787/STORY_URL` and look at the `detail` field in the JSON.
2. Ensure PostgreSQL is up: `make db-status` (if not, run `make db-up`).
3. **If the error mentions a missing column** (e.g. `source_credibility_score does not exist`), the dev DB is behind the schema. Run:
   ```bash
   make migrate-dev
   ```
   Then restart `make dev`.
4. Quick health check: `curl -s http://localhost:8787/health | head -20`

Common causes: database not running, migrations not applied (`make migrate-dev`), missing env (e.g. `DATABASE_URL`), or an unhandled exception in a route.

## 🎯 Roadmap

> **📋 Live Project Board**: Track detailed progress and epic breakdowns at
> **[GitHub Project Board](https://github.com/users/Deim0s13/projects/8)**

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

### **v0.7.0 - Infrastructure** - ✅ COMPLETE
- [x] **v0.7.1 - PostgreSQL Migration**: Dual database support, ORM models, Alembic migrations ✅ COMPLETE (Jan 2026)
- [x] **v0.7.2 - Container & Deployment**: Multi-stage Dockerfile, Caddy proxy, auto-start, CI/CD stabilization ✅ COMPLETE (Jan 2026)

### **v0.7.5 - GitOps & Kubernetes** - ✅ COMPLETE (Jan 2026)
- [x] Local Kubernetes with kind (ADR-0015)
- [x] Tekton CI pipelines (ADR-0016, ADR-0019)
- [x] Secure supply chain: Trivy, Cosign, SBOM (ADR-0018)
- [x] Local container registry
- [x] ArgoCD GitOps deployments (ADR-0017)
- [x] Tekton Triggers with webhook automation

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
- [v0.7.2 - Container & Deployment](https://github.com/Deim0s13/newsbrief/releases/tag/v0.7.2) - ✅ **COMPLETE** (Jan 2026)
- [v0.7.5 - GitOps & Kubernetes](https://github.com/Deim0s13/newsbrief/milestone/14) - ✅ **COMPLETE** (Jan 2026)
- [v0.7.5.1 - Pipeline Notifications](https://github.com/Deim0s13/newsbrief/milestone/22) - ✅ **COMPLETE** (Jan 2026)
- [v0.7.6 - CI/CD Remediation](https://github.com/Deim0s13/newsbrief/milestone/23) - ✅ **COMPLETE** (Feb 2026)
- v0.7.7 - Import Progress & Date Fix - ✅ **COMPLETE** (Feb 2026)
- [v0.7.8 - Dev/Prod Environment Parity](https://github.com/Deim0s13/newsbrief/releases/tag/v0.7.8) - ✅ **COMPLETE** (Feb 2026)
- [v0.8.0 - Content Extraction Pipeline Upgrade](https://github.com/Deim0s13/newsbrief/releases/tag/v0.8.0) - ✅ **COMPLETE** (Feb 2026)
- v0.8.1 - LLM Quality & Intelligence - ✅ **COMPLETE** (Feb 2026)
- v0.8.2 - Source Credibility Integration - ✅ **COMPLETE** (Feb 2026)

**Epics** (via labels):
- **epic:stories** - Story-based aggregation and synthesis
- **epic:ui** - Web interface and user experience
- **epic:database** - Data layer and migrations
- **epic:credibility** - Source credibility ratings and synthesis weighting
- **epic:security** - Authentication, encryption, hardening
- **epic:ops** - CI/CD, deployment, monitoring
- **Epic: Operations** - DevOps, monitoring, and deployment tooling
- **Epic: Embeddings** - Semantic search and advanced clustering (Future)
- **Epic: Search** - Full-text and semantic search capabilities (Future)

## 🤝 Contributing

We welcome contributions! See **[CONTRIBUTING.md](CONTRIBUTING.md)** for detailed setup instructions.

**Key Resources**:
- [Architecture Document](docs/ARCHITECTURE.md) - System design, requirements, and diagrams
- [Development Guide](docs/development/DEVELOPMENT.md) - Setup and workflow
- [Branching Strategy](docs/development/BRANCHING_STRATEGY.md) - Git workflow and **release process**
- [CI/CD Pipeline](docs/development/CI-CD.md) - Automated testing and deployment

### **Quick Start for Contributors**

```bash
# Clone and setup
git clone https://github.com/Deim0s13/newsbrief.git
cd newsbrief
pip install -r requirements.txt -r requirements-dev.txt
pre-commit install

# Create feature branch
git checkout -b feature/amazing-feature

# Make changes (pre-commit hooks auto-format)
git commit -m "feat: add amazing feature"
git push origin feature/amazing-feature
```

### **Find Work to Do**
1. **Check the [GitHub Project Board](https://github.com/users/Deim0s13/projects/8)** for current epics
2. **Look for issues labeled** `good first issue` or `help wanted`
3. **Comment on issues** you'd like to work on

## 🙏 Acknowledgments

- [Trafilatura](https://github.com/adbar/trafilatura) for primary content extraction
- [Readability-lxml](https://github.com/buriy/python-readability) for fallback content extraction
- [FastAPI](https://fastapi.tiangolo.com/) for the excellent web framework
- [Ollama](https://ollama.ai/) for local LLM capabilities
- [Caddy](https://caddyserver.com/) for the reverse proxy
- [PostgreSQL](https://www.postgresql.org/) for production database

# NewsBrief

> **Local-first RSS aggregator with AI-powered content curation**

NewsBrief is a self-hosted, privacy-focused RSS feed aggregator that intelligently curates and summarizes your news sources. Built with modern technologies for speed, reliability, and offline capability.

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

### **Planned (Roadmap)**
- **Enhanced AI Features**: Advanced categorization, sentiment analysis, and content recommendations
- **Web Interface**: HTMX-powered responsive UI for browsing and management
- **Semantic Search**: Vector embeddings for content discovery and similarity matching
- **Full-Text Search**: SQLite FTS5 integration for fast text search
- **Smart Categorization**: Automatic topic clustering and intelligent feeds organization
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

### **Add RSS Feeds**

```bash
# Add a feed
curl -X POST http://localhost:8787/feeds \
  -H "Content-Type: application/json" \
  -d '{"url": "https://feeds.example.com/rss"}'

# Import from OPML (place feeds.opml in ./data/)
# Feeds are automatically imported on startup
```

### **Fetch Latest Articles**

```bash
# Refresh all feeds
curl -X POST http://localhost:8787/refresh

# Get latest articles
curl "http://localhost:8787/items?limit=10" | jq .
```

### **API Endpoints**

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/feeds` | POST | Add new RSS feed |
| `/refresh` | POST | Fetch latest articles from all feeds |
| `/items` | GET | List articles (supports `?limit=N`) |
| `/docs` | GET | Interactive API documentation |

## 🏗️ Architecture

NewsBrief follows **local-first principles** with a clean, scalable architecture:

```
┌─────────────────────────────────────────────┐
│                Frontend                     │
│            (HTMX + Jinja2)                 │
│                [Planned]                    │
├─────────────────────────────────────────────┤
│              FastAPI Server                 │
│         (REST API + Templates)              │
├─────────────────────────────────────────────┤
│             Business Logic                  │
│    ┌─────────┬─────────┬─────────────────┐   │
│    │  Feeds  │ Content │   Future: LLM   │   │
│    │ Manager │Extract. │  Summarization  │   │
│    └─────────┴─────────┴─────────────────┘   │
├─────────────────────────────────────────────┤
│              SQLite Database                │
│        (Articles + Feeds + Metadata)       │
└─────────────────────────────────────────────┘
```

**Key Design Decisions:**
- **SQLite**: Simple, fast, no external dependencies
- **FastAPI**: Modern Python web framework with automatic OpenAPI docs
- **Readability**: Clean content extraction from web articles
- **Container-first**: Podman/Docker for easy deployment
- **Local LLM**: Ollama integration for privacy-preserving AI features

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

### **v0.4.0 - Web Interface**
- [ ] HTMX-powered web UI
- [ ] Article reading interface with AI summaries
- [ ] Feed management dashboard
- [ ] Search and filtering functionality

### **v0.5.0 - Advanced Features**
- [ ] Vector embeddings for semantic search
- [ ] Enhanced content classification and categorization
- [ ] Intelligent content recommendations
- [ ] Sentiment analysis and topic clustering
- [ ] Export/import functionality and data portability
- [ ] Advanced filtering and rules engine

### **Epic Organization**

The roadmap above represents high-level milestones. For detailed epic breakdowns, user stories, and current development status, see the **[GitHub Project Board](https://github.com/users/Deim0s13/projects/7/views/1?layout=board)** which includes:

- **Epic: Ingestion** - Feed processing and content extraction improvements
- **Epic: Summaries** - AI-powered content summarization with Ollama
- **Epic: Ranking** - Content scoring and intelligent curation
- **Epic: UI** - Web interface and user experience enhancements  
- **Epic: Embeddings** - Semantic search and content clustering
- **Epic: Search** - Full-text and semantic search capabilities
- **Epic: Operations** - DevOps, monitoring, and deployment tooling

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


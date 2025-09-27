# NewsBrief

> **Local-first RSS aggregator with AI-powered content curation**

NewsBrief is a self-hosted, privacy-focused RSS feed aggregator that intelligently curates and summarizes your news sources. Built with modern technologies for speed, reliability, and offline capability.

## 🌟 Features

### **Current (v0.2.1)**
- **RSS Feed Management**: Import feeds from OPML or add individually via API
- **Intelligent Content Extraction**: Clean article content using Mozilla Readability
- **Efficient Caching**: ETag and Last-Modified support to minimize bandwidth
- **Local SQLite Storage**: Fast, reliable, file-based database
- **Deduplication**: Automatic detection of duplicate articles across feeds  
- **RESTful API**: JSON endpoints for feeds and articles
- **Container Ready**: Docker/Podman support with optimized builds

### **Planned (Roadmap)**
- **AI Summarization**: Local LLM integration via Ollama for intelligent summaries
- **Semantic Search**: Vector embeddings for content discovery
- **Web Interface**: HTMX-powered responsive UI
- **Full-Text Search**: SQLite FTS5 integration
- **Smart Categorization**: Automatic topic clustering
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
make clean-release VERSION=v0.2.1
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

```bash
# Code quality
python -m py_compile app/*.py   # Syntax check
# (Linting via IDE/editor integration)

# Container development
make build                      # Build container
make run                       # Run container locally
make local-release VERSION=v0.3.0  # Tagged release

# Automated cleanup
make clean-release VERSION=v0.3.0  # Build + auto-cleanup old images
```

### **Project Structure**

```
newsbrief/
├── app/                    # Application code
│   ├── main.py            # FastAPI app and routes
│   ├── db.py              # Database connection and schema
│   ├── feeds.py           # RSS fetching and processing
│   ├── models.py          # Pydantic models
│   ├── readability.py     # Content extraction
│   ├── llm.py             # LLM integration (planned)
│   ├── embed.py           # Embeddings (planned)
│   └── templates/         # HTML templates
├── data/                   # Persistent data
│   ├── newsbrief.sqlite3  # Database
│   └── feeds.opml         # Feed imports
├── scripts/               # Automation scripts
├── Dockerfile            # Container definition
├── compose.yaml          # Multi-service setup
├── Makefile             # Build automation
└── requirements.txt     # Python dependencies
```

## 🎯 Roadmap

### **v0.3.0 - Web Interface**
- [ ] HTMX-powered web UI
- [ ] Article reading interface
- [ ] Feed management dashboard
- [ ] Search functionality

### **v0.4.0 - AI Integration**
- [ ] Ollama LLM integration
- [ ] Article summarization
- [ ] Content classification
- [ ] Intelligent recommendations

### **v0.5.0 - Advanced Features**
- [ ] Vector embeddings for semantic search
- [ ] Topic clustering and categorization
- [ ] Export/import functionality
- [ ] Advanced filtering and rules

## 🤝 Contributing

We welcome contributions! Here's how to get started:

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

## 📄 License

[Add your license here]

## 🙏 Acknowledgments

- [Mozilla Readability](https://github.com/mozilla/readability) for content extraction
- [FastAPI](https://fastapi.tiangolo.com/) for the excellent web framework
- [Ollama](https://ollama.ai/) for local LLM capabilities

---

**Built with ❤️ for privacy-conscious news consumption**
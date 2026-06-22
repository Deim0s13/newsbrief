# NewsBrief

> **AI-powered news aggregator that synthesizes multiple sources into daily story briefs**

NewsBrief is a self-hosted, privacy-focused news aggregator that replaces reading 50+ article summaries with 5-10 synthesized stories. Using local AI, it clusters related articles, extracts key insights, and presents "what happened today" in 2 minutes. Built with modern technologies for speed, reliability, and offline capability.

**Think**: TLDR newsletter, but personalized to your feeds and generated locally.

## 🌟 Features

### **🎯 Story-Based Aggregation**
Replace reading 50+ article summaries with 5-10 AI-synthesized story briefs. **Time to informed: 30 min → 2 min**

- **Automated Story Generation**: Daily scheduled generation at 6 AM (configurable timezone)
- **Enhanced Entity Extraction**: Confidence scores, roles (primary/mentioned/quoted), disambiguation hints
- **Semantic Similarity Clustering**: Entity overlap (50%) + keywords (30%) + topic bonus (20%)
- **Quality Metrics**: LLM output quality tracking with dashboard at `/admin/quality`
- **Multi-Topic Classification**: Primary + secondary topics with calibrated confidence scores
- **Source Credibility**: MBFC-powered credibility ratings with visual indicators and synthesis weighting
- **Intelligent Clustering**: Hybrid topic grouping + keyword similarity for related article detection
- **Multi-Pass Synthesis**: Story type detection → chain-of-thought analysis → synthesis → refinement
- **Standard vs Deep Synthesis**: Stories route to a standard or deep reasoning path based on cluster complexity
- **Confidence Scoring & Publish Gate**: Each story gets a calibrated confidence score; low-confidence stories are held back by a publish gate
- **Large Cluster Handling**: Map-reduce and hierarchical synthesis for 9+ article clusters
- **Story Transparency**: Quality breakdown panel + "Why Grouped Together" explanation
- **Story-First UI**: Landing page shows stories with filters, sorting, and pagination
- **Supporting Articles**: Each story links to source articles with structured summaries
- **Performance Optimised**: Parallel LLM synthesis (3 workers), caching, batching — 80% faster

### **📰 RSS Feed Management**
- **OPML Import/Export**: Bulk feed management with category preservation
- **Feed Health Monitoring**: Multi-factor scoring (response time, success rate, failure tracking)
- **Configurable Fetch Limits**: Global and per-feed caps with fair distribution
- **Robots.txt Compliance**: Respects policies at feed and article levels

### **🤖 AI-Powered Content Processing**
- **Local LLM via Ollama**: Qwen 2.5 14B (default) for synthesis; fast/balanced/quality profiles configurable at `/admin/models`
- **Tiered Content Extraction**: trafilatura (primary) → readability-lxml (fallback) → RSS summary (salvage)
- **Embeddings**: `nomic-embed-text` via Ollama → pgvector for semantic search (768 dimensions)
- **Long Article Handling**: Map-reduce summarization for articles exceeding context limits
- **Synthesis Caching**: Hash+model based caching for instant responses on repeated content

### **🔧 Admin & Operations**
- `/admin/pipeline` — manual pipeline runs, dead-letter retry/discard, operator audit log
- `/admin/quality` — LLM output quality scores and trends
- `/admin/models` — switch active LLM profile at runtime
- `/admin/topics` — bulk topic reclassification
- `/admin/extraction` — content extraction metrics and failure analysis
- `/admin/credibility` — MBFC data management and refresh
- **Data Retention**: Configurable per-type retention (articles, stories, pipeline logs) with a daily purge job, dry-run preview, and admin controls — story-linked articles are always preserved

### **🚀 CI/CD & Deployment**
- **GitHub Actions CI**: lint → test → multi-arch build → push to GHCR → update k8s manifest
- **ArgoCD GitOps**: local kind cluster on each machine; auto-reconciles on startup from GHCR
- **Infrastructure auto-start**: launchd (macOS) and Windows Task Scheduler keep the cluster running
- **Supply chain security**: Trivy scanning, Cosign image signing, CycloneDX SBOM on every prod release
- **Pre-commit quality gates**: black, isort, secrets detection, Dockerfile linting

📚 **[Full Release History →](docs/releases/README.md)**

### Pipeline Monitoring

These endpoints describe in-app pipeline backlog and stage runs. They do not depend on Tekton, Argo, or CI/CD machinery.

| Endpoint | Purpose |
|----------|---------|
| `GET /api/admin/pipeline/stages` | Counts per `processing_state` for items and stories |
| `GET /api/admin/pipeline/run-metrics?window_hours=24` | Per-stage success rate, duration, retry counts |
| `GET /api/admin/pipeline/stuck?max_age_seconds=&limit=` | In-flight runs with no `finished_at` past the threshold |

**Stuck threshold:** default 3600 seconds (`PIPELINE_STUCK_AFTER_SECONDS`). Alert if `stuck` returns `count > 0`.

---

## 💻 Supported Platforms

NewsBrief runs as a production service on two machines simultaneously:

| Concern | macOS MBP | Windows |
|---|---|---|
| Container runtime | Podman Desktop | Podman Desktop for Windows |
| Prod CD | kind + ArgoCD (GitOps, auto-sync) | Podman Compose + GHCR image polling (daily 06:00) |
| Prod access URL | `https://newsbrief.local` (Caddy TLS) | `http://localhost:8787` (no Caddy) |
| Development (Python, tests) | macOS terminal | WSL2 (dev tooling only — not required to run the app) |
| Ollama | Ollama.app (native) | Ollama.exe (native, GPU-accelerated) |
| Ollama URL (containers) | `host.containers.internal:11434` | Same — identical |
| Infra auto-start | launchd | Windows Task Scheduler |

Both platforms use Podman Desktop, which means `host.containers.internal` resolves correctly on both — no platform-specific container configuration needed. The Caddy reverse proxy and the `newsbrief.local` hostname are **macOS-only**; on Windows the app is reached directly at `http://localhost:8787`. See [ADR-0032](docs/adr/0032-cross-platform-cd-strategy.md) for the cross-platform CD strategy.

---

## 🚀 Quick Start

### **Production Deployment (Recommended)**

Deploy the full stack with PostgreSQL and auto-start. `make deploy` is idempotent — it creates the `db_password` secret if missing, brings the stack up, and runs migrations automatically (no separate init step).

**macOS** (Podman Compose + Caddy TLS):

```bash
# Clone repository
git clone https://github.com/Deim0s13/newsbrief.git
cd newsbrief

# First-time setup
make env-init                     # Generate .env with secure password
make hostname-setup               # Add newsbrief.local to /etc/hosts (sudo)
make deploy                       # Start production stack (runs migrations)

# Access at https://newsbrief.local

# Auto-start infrastructure on login (kind + ArgoCD)
make infra-autostart-install
```

**Windows** (Podman Compose + GHCR polling — no Caddy):

```bash
make env-init                     # Generate .env with secure password
make compose-start                # Start the stack (runs migrations)

# Access at http://localhost:8787

# Install auto-start + daily image-update tasks (run once from PowerShell, not WSL2)
# powershell -ExecutionPolicy Bypass -File scripts\compose-task-install.ps1
```

### **Development Mode**

```bash
# On Windows: run these commands in WSL2 (dev tooling only)
# Production containers run natively in Podman Desktop for Windows — no WSL2 needed to run the app

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
pre-commit install
make env-init

# Start PostgreSQL + run app with hot-reload
make dev-full

# OR start separately:
make db-up      # Start PostgreSQL container
make dev        # Run development server

# Access at http://localhost:8790
# Orange "DEVELOPMENT MODE" banner distinguishes from production
```

### **Quick Container Test**

```bash
podman-compose up -d
# Access at http://localhost:8787
```

---

## 🏠 Development vs Production

| Aspect | Development | Production |
|--------|-------------|------------|
| **Database** | PostgreSQL (`localhost:5433`) | PostgreSQL (container volume) |
| **URL** | `http://localhost:8787` | `https://newsbrief.local` (macOS) · `http://localhost:8787` (Windows) |
| **Visual Indicator** | Orange "DEV" banner | Clean UI |
| **Hot Reload** | Yes | No |
| **Logs** | Human-readable with colours | JSON structured |
| **Start Command** | `make dev` | `make deploy` |

### Production Commands

```bash
make deploy              # Start production stack (idempotent; runs migrations)
make deploy-stop         # Stop stack (data preserved)
make deploy-status       # Check running containers
make compose-start       # Windows: start stack via compose.windows.yaml
make compose-watch       # Windows: pull latest GHCR image and redeploy if newer

make hostname-setup      # macOS only: add newsbrief.local to /etc/hosts
make hostname-trust-cert # macOS only: trust Caddy local CA

make db-backup           # Backup to ./backups/
make db-restore FILE=... # Restore from backup
```

### Environment Variables

Create a `.env` file (see `.env.example`):

```bash
POSTGRES_PASSWORD=your_secure_password
OLLAMA_BASE_URL=http://host.containers.internal:11434
```

---

## 📖 Usage

### **API Endpoints**

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/health` | GET | Comprehensive health check (database, LLM, scheduler) |
| `/healthz` | GET | Kubernetes liveness probe |
| `/readyz` | GET | Kubernetes readiness probe |
| `/feeds` | POST | Add new RSS feed |
| `/refresh` | POST | Fetch latest articles from all feeds |
| `/stories` | GET | List synthesized stories |
| `/stories/{id}` | GET | Get story with supporting articles |
| `/stories/generate` | POST | Generate/refresh stories |
| `/stories/stats` | GET | Story generation statistics |
| `/scheduler/status` | GET | Monitor automated feed refresh & story generation |
| `/items` | GET | List articles |
| `/docs` | GET | Interactive API documentation |

### **Story-Based Workflow**

```bash
# 1. Add your RSS feeds
curl -X POST http://localhost:8787/feeds \
  -H "Content-Type: application/json" \
  -d '{"url": "https://feeds.example.com/rss"}'

# 2. Fetch articles and generate stories
curl -X POST http://localhost:8787/refresh
curl -X POST http://localhost:8787/stories/generate | jq .

# 3. View today's stories
curl http://localhost:8787/stories | jq .
```

📚 **[Full API Documentation →](docs/user-guide/API.md)**

---

## 🏗️ Architecture

NewsBrief follows **local-first principles** with story-first aggregation:

```
┌─────────────────────────────────────────────┐
│           Story-First Frontend               │
│            (HTMX + Jinja2)                  │
│     Landing: Stories → Story Detail          │
├─────────────────────────────────────────────┤
│              FastAPI Server                  │
│         (REST API + Templates)               │
├─────────────────────────────────────────────┤
│             Business Logic                   │
│  ┌──────────┬──────────┬─────────────────┐   │
│  │  Story   │  Entity  │ Multi-Document  │   │
│  │Clustering│Extraction│   Synthesis     │   │
│  ├──────────┼──────────┼─────────────────┤   │
│  │  Feeds   │ Content  │  LLM (Ollama)   │   │
│  │ Manager  │ Extract  │  Qwen 2.5 14B   │   │
│  └──────────┴──────────┴─────────────────┘   │
├─────────────────────────────────────────────┤
│      Database (PostgreSQL + pgvector)        │
│  Stories + Articles + Feeds + Embeddings     │
└─────────────────────────────────────────────┘
```

**Key Design Decisions:**
- **Story-First**: Aggregate articles into synthesized narratives, not individual summaries
- **Local LLM Only**: Ollama for all inference; cloud LLM APIs are out of scope (privacy principle)
- **PostgreSQL Only**: Same database engine in dev and prod — no SQLite fallback (ADR-0022)
- **Embeddings Optional**: pgvector for semantic search; all embedding writes are fire-and-forget
- **GitHub Actions CI + ArgoCD CD**: Hosted runners build and push to GHCR; local ArgoCD pulls and deploys

📐 **[Full Architecture Document →](docs/ARCHITECTURE.md)** — requirements, principles, diagrams, ADR index

---

## 🛠️ Development

### **Prerequisites**
- Python 3.11+
- Podman Desktop (macOS or Windows) — or Docker
- Ollama running natively (Ollama.app / Ollama.exe)

### **Setup**

```bash
git clone https://github.com/Deim0s13/newsbrief.git
cd newsbrief
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
pre-commit install
make env-init
```

### **Tests**

```bash
pytest tests/ -v                              # All non-LLM tests (requires dev DB)
pytest tests/ -v -m "not requires_ollama"     # Same — explicit (what CI runs)
pytest tests/ -v -m "requires_ollama"         # LLM tests (requires Ollama running)
pytest tests/ --cov=app --cov-report=term     # With coverage
```

Tests use a real PostgreSQL instance — start one with `make db-up` and set:
```
DATABASE_URL=postgresql://newsbrief:newsbrief_dev@localhost:5433/newsbrief
```

### **Database Migrations**

```bash
make migrate-new MSG="add xyz column"  # Create new revision
make migrate-dev                        # Apply to dev DB
make db-psql                            # Connect via psql
```

Always commit migration files under `alembic/versions/` together with the code that requires them.

### **Project Structure**

```
newsbrief/
├── app/                    # Application code
│   ├── main.py            # FastAPI app factory
│   ├── routers/           # HTTP layer (feeds, stories, items, admin, config, pages, health)
│   ├── stories.py         # Story generation: clustering, synthesis, archiving
│   ├── feeds.py           # RSS fetch, parse, feed health scoring
│   ├── llm.py             # Ollama integration, chunking, synthesis cache
│   ├── embedding_service.py  # Async Ollama embedding generation
│   ├── pipeline_runner.py # Orchestrated stage execution (ADR-0029)
│   ├── orm_models.py      # SQLAlchemy ORM models
│   └── ...                # See CLAUDE.md for full module map
├── alembic/               # Database migrations
├── .github/workflows/     # GitHub Actions CI
│   ├── ci-dev.yml         # dev branch: lint → test → build → push → deploy
│   └── ci-prod.yml        # main branch: same + Trivy + Cosign + SBOM + release
├── k8s/                   # Kubernetes manifests (Kustomize overlays for dev/prod)
├── launchd/               # macOS LaunchAgent plist for infra auto-start
├── scripts/               # infra-start.sh, infra-start.ps1, infra-task-install.ps1
├── data/                  # model_config.json, settings.json, interests.json
├── compose.yaml           # Production stack (API + PostgreSQL + Caddy)
├── Caddyfile              # Reverse proxy configuration
├── Makefile               # Build, deploy, and development commands
└── CLAUDE.md              # Guidance for Claude Code AI assistant
```

### **CI/CD Workflow**

```
Push to dev  →  GitHub Actions (ci-dev.yml)
                  lint + test + build (linux/amd64,arm64)
                  push ghcr.io/deim0s13/newsbrief:sha-{SHA}
                  update k8s/overlays/dev/kustomization.yaml
                  → macOS: ArgoCD auto-deploys

Push to main →  GitHub Actions (ci-prod.yml)
                  same + Trivy scan + Cosign sign + SBOM
                  GitHub release created + push :latest tag
                  update k8s/overlays/prod/kustomization.yaml
                  → macOS:   ArgoCD auto-deploys (hourly poll)
                  → Windows: compose-watch picks up :latest next morning (06:00)
```

**Pre-commit hooks** run automatically on commit: black, isort, secrets detection, YAML validation.

📚 **[CI/CD Guide →](docs/development/CI-CD.md)**

---

## 🔧 Operations

### Service Recovery

Day-to-day, infrastructure starts automatically at login (launchd on macOS, Task Scheduler on Windows). For manual control:

```bash
make infra-start    # Start kind cluster + ArgoCD + port-forwards
make port-forwards  # Restart port-forwards only
make argo-ui        # Port-forward ArgoCD UI to localhost:8443
make recover        # Full Ansible recovery (after major failure)
make status         # Check status of all services
```

### Service URLs

| Service | URL |
|---------|-----|
| Dev app | http://localhost:8789 |
| Prod app (macOS) | https://newsbrief.local (https://localhost:8788) |
| Prod app (Windows) | http://localhost:8787 |
| ArgoCD UI (macOS) | https://localhost:8443 |

### Troubleshooting

**`https://newsbrief.local` shows certificate error**

Caddy uses a local root CA. Trust it once on macOS:
```bash
make hostname-trust-cert
# Run the sudo command it prints, then reload the page
```

**`ERR_CERT_DATE_INVALID` (cert expired)**
```bash
make hostname-regen-certs
make hostname-trust-cert
```

**HSTS blocking `newsbrief.local`**

- Chrome/Edge: `chrome://net-internals/#hsts` → Delete `newsbrief.local` → reload
- Firefox: Clear site data for newsbrief.local in Settings → Privacy
- Safari: Develop → Empty Caches, or clear website data for newsbrief.local

**500 errors in dev**

1. Check terminal for Python traceback
2. Ensure PostgreSQL is up: `make db-status` (if not: `make db-up`)
3. If error mentions a missing column: `make migrate-dev` then restart `make dev`
4. Quick check: `curl -s http://localhost:8787/health | head -20`

---

## 🎯 Roadmap

> **📋 [GitHub Project Board](https://github.com/users/Deim0s13/projects/8)** for current sprint and epics

### Completed releases

| Release | Summary |
|---------|---------|
| v0.8.5 | Pipeline completion & stability: confidence scoring + publish gate, standard/deep synthesis split, per-type data retention, E2E pipeline tests, stuck-item observability |
| v0.8.4.x | Cross-platform CD (ArgoCD on macOS, Compose + GHCR polling on Windows), native WSL2 dev PostgreSQL, date-fallback fixes |
| v0.8.3.1 | Ollama embedding backfill CLI, story embedding persistence |
| v0.8.2 | Source credibility (MBFC integration), credibility admin dashboard |
| v0.8.1 | LLM quality metrics, enhanced entity extraction, multi-topic classification, pipeline operator UI |
| v0.8.0 | Tiered content extraction (trafilatura → readability-lxml → RSS), extraction dashboard |
| v0.7.8 | Dev/prod PostgreSQL parity (ADR-0022), removed SQLite |
| v0.7.5 | GitOps with kind + ArgoCD, secure supply chain (Trivy, Cosign, SBOM) |
| v0.6.x | Semantic clustering, synthesis caching, interest-based ranking, source quality weighting |
| v0.5.5 | Story-based aggregation: clustering, multi-document synthesis, story-first UI |

📚 **[Full release notes →](docs/releases/README.md)**

### Upcoming

- **RAG / Semantic Search** (v0.8.6 — Semantic Foundation): pgvector embeddings already stored; semantic query interface next (ADR-0026)
- **Entity Intelligence System** (v0.9.0): deeper entity linking and disambiguation
- **Fine-tuning feasibility**: Deferred — better alternatives first (ADR-0027)

---

## 🤝 Contributing

**Key Resources**:
- [Architecture Document](docs/ARCHITECTURE.md) — system design, requirements, diagrams
- [Development Guide](docs/development/DEVELOPMENT.md) — full setup and workflow
- [CI/CD Pipeline](docs/development/CI-CD.md) — automated testing and deployment
- [ADR Index](docs/adr/) — all architecture decisions

### Quick Start for Contributors

```bash
git clone https://github.com/Deim0s13/newsbrief.git
cd newsbrief
pip install -r requirements.txt -r requirements-dev.txt
pre-commit install

git checkout -b feature/amazing-feature
git commit -m "feat: add amazing feature"   # pre-commit hooks run automatically
git push origin feature/amazing-feature
```

---

## 🙏 Acknowledgments

- [Trafilatura](https://github.com/adbar/trafilatura) for primary content extraction
- [Readability-lxml](https://github.com/buriy/python-readability) for fallback content extraction
- [FastAPI](https://fastapi.tiangolo.com/) for the excellent web framework
- [Ollama](https://ollama.ai/) for local LLM capabilities
- [Caddy](https://caddyserver.com/) for the reverse proxy
- [PostgreSQL](https://www.postgresql.org/) + [pgvector](https://github.com/pgvector/pgvector) for the database and vector search

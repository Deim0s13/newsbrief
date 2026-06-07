# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Platform Overview

The app runs on **two machines** — a macOS MBP and a Windows machine — both treated as production hosts.

| Concern | macOS | Windows |
|---|---|---|
| Container runtime | Podman Desktop | Podman Desktop for Windows |
| Prod CD | kind/ArgoCD (GitOps, auto-sync) | Podman Compose + GHCR image polling |
| Dev deployment | Podman Compose | Podman Compose (WSL2) |
| Development (Python, tests) | macOS terminal | **WSL2 only** |
| Ollama | Ollama.app (native) | Ollama.exe (native, GPU) |
| Ollama URL (containers) | `host.containers.internal:11434` | Same — identical |
| Infra auto-start | launchd (`make infra-autostart-install`) | Task Scheduler (`scripts\compose-task-install.ps1`) |

---

## Commands

### Setup (run in WSL2 on Windows, or macOS terminal)
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
pre-commit install
make env-init    # generate .env from template
```

### Development server
```bash
make db-up          # Start PostgreSQL on localhost:5433
make migrate-dev    # Apply Alembic migrations to dev DB
make dev            # Run uvicorn with reload (requires db-up first)
make dev-full       # db-up + wait + dev in one command
```

### Tests
```bash
pytest tests/ -v                                    # All non-LLM tests (requires dev DB at localhost:5433)
pytest tests/ -v -m "not requires_ollama"           # Same — explicit (what CI runs)
pytest tests/ -v -m "requires_ollama"               # LLM tests only (requires Ollama running)
pytest tests/test_stories.py -v                     # Single test file
pytest tests/ -v -k "test_ranking"                  # Single test by name
pytest tests/ --cov=app --cov-report=term           # With coverage (threshold: 34%)
```

Tests are split into three categories:
- **Unit / mocked** — always safe, no external deps
- **DB integration** — hit real PostgreSQL; skip automatically without `DATABASE_URL`
- **LLM tests** (`@pytest.mark.requires_ollama`) — require live Ollama; excluded from CI via `-m "not requires_ollama"`

Integration tests hit a **real PostgreSQL** (no mocks). Set `DATABASE_URL=postgresql://newsbrief:newsbrief_dev@localhost:5433/newsbrief` or start the dev DB with `make db-up`.

### Code Quality
```bash
black app/ tests/
isort --profile=black app/ tests/
mypy app/ --ignore-missing-imports
flake8 app/ tests/
pre-commit run --all-files
```

### Database Migrations
```bash
make migrate-new MSG="add xyz column"   # Create new revision (autogenerate)
make migrate-dev                         # Apply to dev DB
make migrate-history                     # Show history
make db-psql                             # Connect via psql
```

Always commit migration files under `alembic/versions/` together with the code that requires them.

### Container & Deployment
```bash
make build          # Build OCI image (Podman)
make deploy         # Start prod stack (auto-creates db_password secret, runs migrations)
make deploy-stop    # Stop prod stack (preserves data volumes)
make deploy-status  # Check prod container status
```

`make deploy` is idempotent: it creates the `db_password` Podman secret from `.env` if missing, brings Compose up, waits for the DB, then runs `alembic upgrade head`. No separate `make deploy-init` needed.

### Windows CD — Compose + GHCR polling
```bash
# Install Task Scheduler tasks (run once from PowerShell, not WSL2):
powershell -ExecutionPolicy Bypass -File scripts\compose-task-install.ps1
# Or from WSL2:
make compose-autostart-install

# Manual triggers:
make compose-start   # Idempotent stack start (safe to call on boot)
make compose-watch   # Pull latest GHCR image and redeploy if newer
```

Two tasks are registered:
- **NewsBrief Compose Start** — runs `compose-start.sh` at login (30 s delay); uses hidden PowerShell window
- **NewsBrief Compose Watch** — runs `compose-watch.sh` daily at 06:00; pulls `ghcr.io/deim0s13/newsbrief:latest`, redeploys if digest changed, runs migrations, sends ntfy push

### CI/CD — GitHub Actions
CI runs automatically on push. No local trigger commands needed.

- **Push to `dev`** → `.github/workflows/ci-dev.yml` → lint + test + build (multi-arch) + push `ghcr.io/deim0s13/newsbrief:sha-{SHA}` + update `k8s/overlays/dev/kustomization.yaml` → ArgoCD auto-deploys (macOS)
- **Push to `main`** → `.github/workflows/ci-prod.yml` → same + Trivy scan + Cosign sign + SBOM + GitHub release + update `k8s/overlays/prod/kustomization.yaml` → ArgoCD auto-deploys (macOS); Windows picks up new image next morning (06:00) via `compose-watch.sh`

**GitHub secrets required** (set in repo Settings → Secrets):

| Secret | Purpose |
|---|---|
| `COSIGN_PRIVATE_KEY` | Image signing (prod only) |
| `COSIGN_PASSWORD` | Cosign key passphrase |
| `NTFY_TOPIC` | ntfy.sh topic for pipeline notifications |

### Kubernetes / ArgoCD (macOS only)
```bash
make infra-start           # Start kind + ArgoCD + port-forwards; applies App CRs if missing
make port-forwards         # Restart port-forwards only
make recover               # Full Ansible recovery (after major failure)
make argo-ui               # Port-forward ArgoCD UI to localhost:8443
```

Port map after `make infra-start`:
- `localhost:8788` — prod app (newsbrief-prod namespace)
- `localhost:8789` — dev app (newsbrief-dev namespace)
- `localhost:8443` — ArgoCD UI

ArgoCD polls Git every hour (`timeout.reconciliation: 3600s` in `k8s/argocd/argocd-cm.yaml`). `infra-start.sh` auto-applies Application CRs from `k8s/argocd/` if they're missing after cluster recreation — the script is idempotent.

### Infrastructure Auto-Start
```bash
# macOS — launchd; install once, runs on every login:
make infra-autostart-install
make infra-autostart-status   # Verify launchd plist is loaded

# Windows — Task Scheduler; run once from PowerShell:
powershell -ExecutionPolicy Bypass -File scripts\compose-task-install.ps1
# (re-run to update task configuration — it unregisters and re-registers)
```

---

## Key Documents

| Document | Purpose |
|----------|---------|
| `docs/ARCHITECTURE.md` | Authoritative architecture reference (component diagram, data model, deployment, ADR index) |
| `docs/adr/` | All Architecture Decision Records — read these before changing major design choices |
| `docs/development/DEVELOPMENT.md` | Full dev setup, environment variables, embeddings schema, pipeline operator controls |
| `docs/development/KUBERNETES.md` | kind cluster setup, ArgoCD sync waves, port-forward map |
| `docs/development/CI-CD.md` | Pipeline stages, migration strategy, security gates |
| `docs/user-guide/API.md` | REST API reference |
| `docs/user-guide/MODEL-PROFILES.md` | LLM profile tuning guide |
| `data/model_config.json` | LLM model profiles, embedding config, synthesis strategy thresholds |
| `data/settings.json` | Runtime active profile selection |
| `data/interests.json` | Per-topic interest weights for story ranking |
| `data/source_weights.json` | Per-feed/domain quality weights for ranking |

---

## Architecture

### Technology Stack

| Layer | Technology |
|-------|------------|
| Web Framework | FastAPI (async, auto OpenAPI) |
| Templates | Jinja2 (server-rendered; Tailwind CSS built locally) |
| Database | PostgreSQL 16 + pgvector (`pgvector/pgvector:pg16` image) |
| ORM / Migrations | SQLAlchemy 2.0 / Alembic |
| LLM | Ollama (local; default Qwen 2.5 14B via `data/model_config.json`) |
| Embeddings | Ollama `nomic-embed-text` → `vector(768)` in pgvector |
| Scheduler | APScheduler (background jobs: feed refresh, story generation) |
| Content Extraction | Trafilatura (primary) + readability-lxml (fallback) |
| Reverse Proxy | Caddy (TLS termination; `newsbrief.local` in production) |
| Container Runtime | Podman Desktop (macOS + Windows) |
| CI | GitHub Actions (hosted runners, `.github/workflows/`) |
| CD (macOS) | ArgoCD on local kind cluster (GitOps, hourly poll, auto-sync) |
| CD (Windows) | Podman Compose + GHCR polling via Task Scheduler (daily 06:00) |
| Image Registry | `ghcr.io/deim0s13/newsbrief` (public) |

### Module Map (`app/`)

```
app/
├── main.py              # FastAPI app, router registration, startup hooks
├── routers/             # HTTP layer: feeds, stories, items, admin, config, pages, health
├── stories.py           # Story generation: clustering, synthesis, archiving
├── feeds.py             # RSS fetch, parse, feed health scoring
├── llm.py               # Ollama integration, chunking, synthesis cache calls
├── llm_output.py        # JSON parsing, repair, schema validation, circuit breaker
├── entities.py          # Named entity extraction (NER)
├── extraction.py        # Tiered article content extraction
├── ranking.py           # Interest + source-quality blended scoring
├── credibility.py       # Source credibility lookup (MBFC data)
├── scheduler.py         # APScheduler job definitions
├── settings.py          # Model profile management (data/model_config.json + data/settings.json)
├── context_manager.py   # Article selection/chunking for large clusters
├── quality_metrics.py   # LLM output quality tracking
├── pipeline_runner.py   # Orchestrated stage execution (ADR-0029)
├── pipeline_monitoring.py # Stage-run metrics and stuck-item detection
├── processing_states.py # ArticleProcessingState / StoryProcessingState enums + transitions
├── operator_audit.py    # Audit log for manual admin actions
├── embedding_service.py # Async Ollama embedding generation
├── item_embeddings.py   # Embed article title+summary after summarize
├── story_embeddings.py  # Embed story title+synthesis after synthesis
├── embed_backfill.py    # CLI: backfill embeddings for existing rows
├── ingest_idempotency.py # url_hash / content_hash dedup (ADR-0031)
├── orm_models.py        # SQLAlchemy models (Feed, Item, Story, StoryArticle, ...)
├── db.py                # Engine, session factory, init_db
├── models.py            # Pydantic schemas (request/response + helpers)
├── prompts/             # Prompt templates: synthesis, map_reduce, refinement, analysis
└── cli/                 # CLI entrypoints (e.g. embed-backfill)
```

### Data Flow

1. **Ingest**: APScheduler calls `feeds.py` → fetches RSS → `extraction.py` extracts article text → stored as `Item` rows with `processing_state = enriched`.
2. **Summarize**: `llm.py` summarizes each article; `item_embeddings.py` embeds title+summary via Ollama; `synthesis_cache.py` caches LLM responses.
3. **Cluster → Synthesize**: `stories.py` clusters `Item`s by similarity → `context_manager.py` selects/chunks articles → `llm.py` synthesizes a narrative (direct / map-reduce / hierarchical based on cluster size in `model_config.json`) → `story_embeddings.py` embeds result.
4. **Rank**: `ranking.py` blends importance + freshness + source credibility + user interest weights (`data/interests.json`, `data/source_weights.json`).
5. **Serve**: FastAPI routers return JSON or Jinja2 HTML; Caddy terminates TLS in production.

### Pipeline Orchestration (ADR-0029, in progress)

Story processing is moving toward explicit staged orchestration. `pipeline_runner.py` wraps coarse stages (`ingest`, `story_generation`); `processing_states.py` defines canonical `ArticleProcessingState` / `StoryProcessingState` enums with valid transitions. Pipeline runs are persisted to `pipeline_stage_runs`; the admin dashboard at `/admin/pipeline` exposes run lists, dead-letter retry/discard, and operator audit logs.

### LLM Model Profiles

Three profiles defined in `data/model_config.json` and selectable at runtime via `data/settings.json` or the `/config` UI:

| Profile | Model | Use Case |
|---------|-------|----------|
| `fast` | mistral:7b | Testing, quick summaries |
| `balanced` | qwen2.5:14b | Daily generation (default) |
| `quality` | qwen2.5:32b | Important stories, deep analysis |

The embedding model (`nomic-embed-text`, 768 dimensions) is separate and configured under `data/model_config.json` → `embedding`. The DB column width (`_EMBEDDING_DIMENSIONS = 768` in `orm_models.py`) must match.

### Environment Variables (key ones)

| Variable | Default | Purpose |
|----------|---------|---------|
| `DATABASE_URL` | — | PostgreSQL connection string (required) |
| `OLLAMA_BASE_URL` | `http://host.containers.internal:11434` | Ollama server — same URL on macOS and Windows |
| `NEWSBRIEF_LLM_MODEL` | from settings | Override active model |
| `NEWSBRIEF_EMBEDDING_ENABLED` | `true` | Disable embeddings |
| `ENVIRONMENT` | `development` | `development` shows DEV banner; `production` uses JSON logging |
| `FEED_REFRESH_SCHEDULE` | `30 5 * * *` | Cron for scheduled feed refresh |
| `STORY_GENERATION_SCHEDULE` | `0 6 * * *` | Cron for scheduled story generation |

### Branching & CI/CD

- **`dev`** — daily development. Push triggers `ci-dev.yml`: lint → test → build → push `ghcr.io/deim0s13/newsbrief:sha-{SHA}` → update `k8s/overlays/dev/kustomization.yaml`.
- **`main`** — releases only (merge from `dev`). Push triggers `ci-prod.yml`: same + Trivy scan → Cosign sign → SBOM → GitHub release → update `k8s/overlays/prod/kustomization.yaml` + push `:latest` tag to GHCR.
- **macOS CD**: ArgoCD polls Git hourly, detects new tag in kustomization, runs `newsbrief-db-migrate` Job (sync wave 0) then rolls the API Deployment — fully automatic.
- **Windows CD**: `compose-watch.sh` runs once daily at 06:00 via Task Scheduler, compares running container SHA against `ghcr.io/deim0s13/newsbrief:latest`, redeploys + migrates if changed.
- Dev DB (`compose.dev.yaml`) runs on `newsbrief_dev_network`; prod DB runs on `newsbrief_default` — isolated to prevent DNS round-robin.
- `make env-init` generates a single random password and substitutes it into both `POSTGRES_PASSWORD` and `DATABASE_URL` in `.env` — credentials are always in sync.
- Pipeline CI notifications go to ntfy.sh topic set in `NTFY_TOPIC` env/secret. Deploy notifications sent by `compose-watch.sh` (Windows) use the same topic from `.env`.

### Key Design Constraints

- **PostgreSQL only** — no SQLite fallback; dev and prod both use Postgres for parity (ADR-0022). Tests use real DB (see `tests/pg_testutil.py`).
- **Local LLM only** — Ollama is the sole inference backend; cloud LLM APIs are out of scope (ADR-0025, privacy principle).
- **Embeddings optional** — all embedding writes are fire-and-forget; the rest of the pipeline succeeds even if Ollama embedding fails.
- **LLM output is untrusted** — `llm_output.py` repairs and validates every JSON response; a circuit breaker (`get_circuit_breaker()`) trips after repeated failures.
- **Synthesis strategies scale with cluster size** — direct (≤8 articles), map-reduce (9–15), hierarchical (≥16); thresholds are in `model_config.json → synthesis_strategies`.

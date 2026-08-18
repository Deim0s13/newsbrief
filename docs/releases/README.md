# Release History

Quick reference for all NewsBrief releases. For detailed release notes, see [GitHub Releases](https://github.com/Deim0s13/newsbrief/releases).

---

## v0.8.x - Content Quality

### v0.8.7 - Model Optimisation & Platform Intelligence (Current)
**August 2026** · [GitHub Release](https://github.com/Deim0s13/newsbrief/releases/tag/v0.8.7)

Hardware-informed, device-aware model selection so each machine runs the right model automatically — see [ADR-0033](../adr/0033-hardware-informed-model-selection.md).

**Highlights:**
- **Device-Aware Model Resolution**: `SettingsService` resolves the active model per-platform via `data/model_config.json`'s `device_profiles` block, surfaced in the `/config` UI (#317, #319-322)
- **oMLX Backend on macOS**: Pluggable LLM backend abstraction (`app/llm_backends.py`); macOS switches from Ollama to oMLX — up to 5x faster under the pipeline's real concurrency pattern, validated end-to-end on production data (24.9 min vs ~3h+ baseline) (#335-339)
- **Windows Live Validation**: Confirmed `llama3.1:8b`/`qwen3:14b`/`deepseek-r1:14b` on the actual RTX 4090 host; fixed a `<think>` reasoning-block leak affecting any Ollama thinking model (#332)
- **Automatic Per-Article Enrichment**: New `summarize` pipeline stage closes the gap where AI summaries + embeddings were never generated automatically, starving v0.8.6's RAG features (#328)
- **Synthesis Crash Fix**: Guarded against `None` LLM/field responses crashing ~21% of clusters (#340)
- **Embedding Model Re-evaluation**: `nomic-embed-text` retained after benchmarking `qwen3-embedding:0.6b` and `mxbai-embed-large` against real production data — no meaningful precision gain (#330)
- **Model-Fitness Harness**: `scripts/model_fitness.py` formalizes model-swap validation into reusable dev tooling, run against NewsBrief's real prompts and JSON parser (#341)
- **Migrations**: `028_widen_model_columns` (oMLX model IDs are longer than Ollama tags)

### v0.8.6 - RAG Milestone Completion
**August 2026** · [GitHub Release](https://github.com/Deim0s13/newsbrief/releases/tag/v0.8.6)

Completes the semantic retrieval / RAG milestone started in v0.8.5.

**Highlights:**
- **Embeddings as a Pipeline Stage**: `embedding_error` tracking, automatic re-embedding of outdated vectors, admin observability (#278)
- **Semantic Deduplication**: Post-hoc detection of paraphrased duplicate articles via embedding similarity, with an admin review view (#257)
- **Light RAG Context Injection**: Structured historical context anchors injected into synthesis prompts for evolving stories (#259, #281)
- **Bounded Retrieval Hook**: `app/retrieval.py` + `app/context_retrieval.py` power `/search/semantic`, `/stories/{id}/related`, and `/items/{id}/similar` (#279)
- **Historical Linking**: Stories automatically detect and link to the story they continue (`app/historical_linking.py`)
- **Cluster Complexity Scoring**: Numeric 0.0-1.0 score routes clusters between standard and deep synthesis (#280)
- **RAG Evaluation Harness**: `scripts/rag_evaluation.py` checks the four go/no-go gates from ADR-0026; results and a conditional "go" decision are documented in the ADR (#262)
- **Migrations**: `021_historical_story_links`, `022_retrieval_traces`, `023_item_embedding_error`, `024_semantic_dedup`, `025_synthesis_anchors`, `026_context_anchors`, `027_cluster_complexity_score`

### v0.8.5 - Pipeline Completion & Stability
**June 2026** · [GitHub Release](https://github.com/Deim0s13/newsbrief/releases/tag/v0.8.5)

Stability and trust improvements across the story pipeline.

**Highlights:**
- **Confidence Scoring & Publish Gate**: Calibrated confidence score per story; low-confidence stories are held back from publishing (`app/publish_gate.py`)
- **Standard vs Deep Synthesis**: Stories route to a standard or deep reasoning path based on cluster complexity
- **Data Retention**: Configurable per-type retention (articles, stories, pipeline logs) with a daily purge job, dry-run preview, and admin controls; story-linked articles always preserved (`app/retention.py`)
- **Pipeline Observability**: Stuck-item detection, unified per-stage run metrics, and routing tests
- **E2E Tests**: State-transition and recovery coverage (`tests/test_pipeline_e2e.py`, `tests/test_synthesis_routing.py`)
- **Migrations**: `018_confidence_score`, `019_synthesis_path`, `020_confidence_warning`

### v0.8.4.x - Cross-Platform CD
**June 2026** · [GitHub Release](https://github.com/Deim0s13/newsbrief/releases/tag/v0.8.4.2)

Hybrid CD strategy (ADR-0032): ArgoCD on macOS, Podman Compose + GHCR image polling on Windows. Native WSL2 dev PostgreSQL replaces the containerised dev DB; article date-fallback fixes (`COALESCE(published, created_at)`); prod pipeline version-check gate.

### v0.8.3.1 - Embedding Persistence
**April 2026** · [GitHub Release](https://github.com/Deim0s13/newsbrief/releases/tag/v0.8.3.1)

Ollama embedding backfill CLI (`app/cli/`) and story embedding persistence into pgvector.

### v0.8.2 - Source Credibility
**March 2026** · [GitHub Release](https://github.com/Deim0s13/newsbrief/releases/tag/v0.8.2)

MBFC-powered source credibility ratings with synthesis weighting, visual indicators, and a credibility admin dashboard (`/admin/credibility`). See ADR-0028.

### v0.8.1 - Quality Metrics & Entity Extraction
**March 2026** · [GitHub Release](https://github.com/Deim0s13/newsbrief/releases/tag/v0.8.1)

LLM output quality metrics, enhanced entity extraction (confidence, roles, disambiguation), multi-topic classification, and the pipeline operator UI.

### v0.8.0 - Content Extraction Pipeline Upgrade
**February 2026** · [GitHub Release](https://github.com/Deim0s13/newsbrief/releases/tag/v0.8.0)

Complete overhaul of content extraction with tiered fallback strategy for improved article quality.

**Highlights:**
- **Tiered Extraction**: Trafilatura (primary) → Readability-lxml (fallback) → RSS summary (salvage)
- **Quality Scoring**: 0-1 quality score per article based on extraction method and content length
- **Rich Metadata**: Author, date, images, categories, and tags captured when available
- **Extraction Dashboard**: New admin UI at `/admin/extraction` with success rates, method distribution, and failure analysis
- **Observability**: New database columns track extraction method, quality, timing, and errors
- **Regression Tests**: Golden set of synthetic HTML fixtures for extraction quality validation

**Technical Changes:**
- New `app/extraction.py` module with `ExtractionResult` dataclass
- Removed legacy `app/readability.py`
- Database migration `004_extraction_metadata` adds tracking columns
- Trafilatura 2.0.0 API compatibility

**Documentation:**
- ADR-0024: Content Extraction Libraries decision
- Updated ARCHITECTURE.md with new extraction component

---

## v0.7.x - Infrastructure & Operations

### v0.7.8 - Dev/Prod Environment Parity
**February 2026** · [GitHub Release](https://github.com/Deim0s13/newsbrief/releases/tag/v0.7.8)

PostgreSQL for all environments (ADR-0022), removed SQLite support entirely, new `make dev-full` target, updated CI pipeline for PostgreSQL-only testing, comprehensive documentation updates.

### v0.7.7 - Import Progress & Date Fix
**February 2026** · [GitHub Release](https://github.com/Deim0s13/newsbrief/releases/tag/v0.7.7)

Real-time OPML import progress modal with live stats, async import tracking via `/feeds/import/status/{id}`, proper UTC handling for article dates in PostgreSQL.

### v0.7.6 - CI/CD Remediation
**January 2026** · [GitHub Release](https://github.com/Deim0s13/newsbrief/releases/tag/v0.7.6)

Persistent storage for prod environment with PVC, registry standardization (`kind-registry:5000`), Cosign key-based image signatures with Bitwarden integration, Smee webhook relay, Ansible recovery automation (`make recover`).

### v0.7.5.1 - Pipeline Notifications
**January 2026** · [GitHub Release](https://github.com/Deim0s13/newsbrief/releases/tag/v0.7.5)

Pipeline notifications via ntfy.sh (macOS/iOS push), Slack webhook groundwork (disabled by default), finally blocks for all pipelines with success/failure alerts, Tekton Dashboard for pipeline monitoring.

### v0.7.5 - GitOps & Automation
**January 2026** · [GitHub Release](https://github.com/Deim0s13/newsbrief/releases/tag/v0.7.5)

Local Kubernetes with kind, Tekton CI/CD pipelines (lint, test, build, scan, sign), ArgoCD GitOps deployments, secure supply chain (Trivy, Cosign, SBOM), Tekton Triggers for webhook automation, **semantic versioning automation** (conventional commits), automated cleanup tasks (branches, images, runs), fixed registry DNS for cross-namespace access.

### v0.7.4 - Security
**January 2026** · [GitHub Release](https://github.com/Deim0s13/newsbrief/releases/tag/v0.7.4)

HTTPS/TLS with Caddy automatic certificates, Podman Secrets for encrypted credentials, API rate limiting (slowapi), security headers (HSTS, X-Frame-Options).

### v0.7.3 - Operations & Observability
**January 2026** · [GitHub Release](https://github.com/Deim0s13/newsbrief/releases/tag/v0.7.3)

Structured logging (JSON/human-readable), Kubernetes-style health probes (`/healthz`, `/readyz`, `/ollamaz`), feed management UI fixes, dev/prod visual separation with DEV banner.

### v0.7.2 - Container & Deployment
**January 2026** · [GitHub Release](https://github.com/Deim0s13/newsbrief/releases/tag/v0.7.2)

Multi-stage Dockerfile, health endpoint, production deployment (`make deploy`), database backup/restore, Caddy reverse proxy for `newsbrief.local`, launchd auto-start.

### v0.7.1 - PostgreSQL Migration
**January 2026** · [GitHub Release](https://github.com/Deim0s13/newsbrief/releases/tag/v0.7.1)

PostgreSQL support via `DATABASE_URL`, SQLAlchemy ORM models, Alembic migrations (SQLite later dropped; see ADR-0022).

---

## v0.6.x - Features & Quality

### v0.6.5 - Personalization
**January 2026** · [GitHub Release](https://github.com/Deim0s13/newsbrief/releases/tag/v0.6.5)

Interest-based ranking with topic weights, source quality weighting, feed health monitoring, configurable score blending (50% importance + 30% interest + 20% source).

### v0.6.4 - Code Quality
**January 2026** · [GitHub Release](https://github.com/Deim0s13/newsbrief/releases/tag/v0.6.4)

Type safety (mypy 0 errors), test coverage 30%→41% (192 tests), comprehensive ranking tests, pytest-cov integration.

### v0.6.3 - Performance
**January 2026** · [GitHub Release](https://github.com/Deim0s13/newsbrief/releases/tag/v0.6.3)

LLM synthesis caching with TTL, incremental story updates (70% overlap detection), API enhancements (6 new filters), scheduled feed refresh.

### v0.6.2 - UI Polish & Fixes
**December 2025** · [GitHub Release](https://github.com/Deim0s13/newsbrief/releases/tag/v0.6.2)

Local Tailwind CSS build, HTML sanitization with bleach, unified topic classification, story page filters, model/status display.

### v0.6.1 - Enhanced Intelligence
**December 2025** · [GitHub Release](https://github.com/Deim0s13/newsbrief/releases/tag/v0.6.1)

Entity extraction (companies, products, people), semantic similarity clustering, story quality scoring, skim/detail toggle.

---

## v0.5.x - Story Architecture

### v0.5.5 - Story-Based Aggregation
**November 2025** · [GitHub Release](https://github.com/Deim0s13/newsbrief/releases/tag/v0.5.5)

Major release: story generation from clustered articles, multi-document synthesis, story-first UI, scheduled generation, automatic archiving.

---

## Versioning

NewsBrief follows [Semantic Versioning](https://semver.org/):
- **Major** (x.0.0): Breaking changes
- **Minor** (0.x.0): New features
- **Patch** (0.0.x): Bug fixes

## Links

- [GitHub Releases](https://github.com/Deim0s13/newsbrief/releases) - Full release notes
- [Milestones](https://github.com/Deim0s13/newsbrief/milestones) - Planned work
- [Project Board](https://github.com/users/Deim0s13/projects/8) - Current status

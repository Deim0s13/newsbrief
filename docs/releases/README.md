# Release History

Quick reference for all NewsBrief releases. For detailed release notes, see [GitHub Releases](https://github.com/Deim0s13/newsbrief/releases).

> **Note (August 2026):** entries below are an unedited historical record of what shipped in each release at the time. Several v0.7.x entries mention Tekton (Dashboard/Triggers/pipelines), the kind local registry, Smee, and Ansible recovery automation — all of these were later removed (Tekton/registry: ADR-0016/ADR-0032/#325; Smee: same Tekton removal, its only purpose was relaying webhooks to Tekton; Ansible: #352). Current infrastructure is GitHub Actions (CI) + ArgoCD/GHCR (CD on macOS) + Podman Compose/GHCR polling (CD on Windows) — see [ADR-0032](../adr/0032-cross-platform-cd-strategy.md) and `CLAUDE.md`.

---

## v0.9.x - Intelligence Platform

### v0.9.0 - Entity Intelligence System (Current)
**September 2026** · [GitHub Release](https://github.com/Deim0s13/newsbrief/releases/tag/v0.9.0)

Phase 2 of the intelligence platform strategy ([ADR-0023](../adr/0023-intelligence-platform-strategy.md)) — builds a normalized entity graph on top of the per-article entity extraction that already existed, and uses it to connect stories, browse entities, and improve continuity linking.

**Highlights:**
- **Normalized Entity Graph**: `entities`/`entity_mentions` tables; canonicalization/dedup wired into the existing per-article extraction at cluster time; one-time backfill script (`make entity-backfill`) (#199)
- **Entity-Based Story Connections**: Shared-entity query ranked by count + prominence + temporal proximity; `GET /stories/{id}/entity-connections`; `/stories?entity=<id>` filter with a UI banner (#202)
- **Entity Profile Pages**: `/entities/{id}` (mention timeline, co-mentioned entities) and `/entities?q=` search/browse; clickable entity chips on story detail pages (#201)
- **Entity-Aware Continuity Linking**: `historical_linking.py` re-ranks embedding-qualified candidates with a small, capped entity-overlap boost — breaks near-ties, never overrides a materially stronger embedding match (#284)
- **Migrations**: `029_entity_intelligence`

## v0.8.x - Content Quality

### v0.8.9 - Code Health & Tech Debt
**August 2026** · [GitHub Release](https://github.com/Deim0s13/newsbrief/releases/tag/v0.8.9)

One-time code-health audit across `app/`, `tests/`, `scripts/`, and infra/docs — findings-only pass with cleanup executed issue-by-issue, not a feature release. Full methodology and findings in [`docs/development/CODE-REVIEW-2026-08.md`](../development/CODE-REVIEW-2026-08.md).

**Highlights:**
- **App-code cleanup**: confirmed dead code + 2 unused dependencies removed; `generate_stories_simple`/`fetch_and_store` (the two most complex functions in the app) decomposed into smaller helpers; Story CRUD API duplication investigated and documented (#345-347)
- **Infra cleanup**: `make recover` fixed, stale Tekton/kind-registry references purged from ADRs/docs, CI workflows deduplicated into a shared reusable workflow, orphaned/duplicate infra files removed, ambiguous Windows autostart paths resolved, prod/dev DB password moved out of git into a K8s Secret (#352-357)
- **Test-suite fixes**: a real DB sequence-desync bug fixed (`resync_sequences()` helper, now run after every test), duplicated test setup helpers consolidated, coverage-threshold doc drift fixed (34%→45% floor, matching actual 51%) — and, found along the way, a real assertion-bypass bug in `test_models.py` where 18 tests could never actually fail under pytest (#358-360)
- **CI reliability**: removed the flaky ntfy `Notify` step from `ci-dev.yml`/`ci-prod.yml` — its `curl` call had no timeout/retry, so a network blip reaching ntfy.sh repeatedly showed unrelated, otherwise-passing runs as failed (ADR-0021 amendment)

### v0.8.8 - Backlog & Ops Triage
**August 2026** · [GitHub Release](https://github.com/Deim0s13/newsbrief/releases/tag/v0.8.8)

Ops/reliability triage milestone — no new user-facing features, focused on closing gaps found while stabilizing dev/prod after the v0.8.7 release.

**Highlights:**
- **Pipeline Tracking for Manual Triggers**: `/refresh` and `/stories/generate` now route through tracked `PipelineStageRun` stages instead of calling `fetch_and_store()`/`generate_stories_simple()` directly, fixing the audit-trail gap and feed-refresh fairness (#327, #344, #348)
- **oMLX Wired Up in K8s**: Fixed hardcoded `NEWSBRIEF_LLM_MODEL` + missing `OMLX_BASE_URL`/`NEWSBRIEF_DEVICE_TYPE` env vars so macOS-deployed pods actually use the oMLX backend from v0.8.7 (#343)
- **embed-backfill Reliability**: Truncate oversized embed text and isolate per-item batch failures so one bad item no longer 500s the whole PostSync job (#349)
- **Config Volume Shadowing Fix**: Persistent data volume no longer shadows shipped `model_config.json`/`interests.json`/`source_weights.json`/`topics.json` on redeploy (#326)
- **ArgoCD/kind Stability**: Recovered from a control-plane OOM-kill (bumped Podman machine memory), added an ArgoCD-independent drift check script, removed orphaned live-cluster infra (Tekton, ApplicationSet controller, kind-registry) that had survived earlier git-level cleanups (#325)
- **Self-Healing Port-Forwards**: launchd-supervised `kubectl port-forward` watchdog; tests now guarded against accidentally targeting the prod DB

### v0.8.7 - Model Optimisation & Platform Intelligence
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

# NewsBrief Architectural Roadmap

> **Living Document** - Last Updated: August 2026

This document outlines the architectural evolution of NewsBrief, from its current state through planned enhancements. It serves as a technical compass for development decisions and helps contributors understand where the project is heading.

> **Strategic Vision**: See [ADR-0023: Intelligence Platform Strategy](0023-intelligence-platform-strategy.md) for the comprehensive plan to transform NewsBrief from a news aggregator into an intelligence platform.

**Pipeline orchestration**: Story processing is implemented as an orchestrated pipeline (explicit state, stages, retries, retrieval hooks, confidence gates, stage-aware observability). Core workstream issues #273–#291 closed April 2026. The extension points originally tracked for v0.8.4–v0.8.5 — retrieval hook, confidence gate, synthesis routing — are now all complete, and the RAG milestone (v0.8.4–v0.8.6) has also shipped semantic dedup, light RAG anchors, and historical linking. See [ADR-0029: Pipeline-oriented orchestration](0029-pipeline-oriented-orchestration.md), [ADR-0031: Pipeline idempotency and article re-ingest](0031-pipeline-idempotency-and-reingest.md), and [ADR-0026: RAG integration strategy](0026-rag-integration-strategy.md).

---

## 1. Current Architecture (v0.8.6)

### Overview

NewsBrief is a **local-first, story-based news aggregator** that synthesizes multiple RSS sources into AI-generated story briefs.

```
┌─────────────────────────────────────────────────────────────────┐
│                        Client Layer                              │
│              Browser (Tailwind CSS + Vanilla JS)                │
│              DEV banner in development mode                      │
└─────────────────────────┬───────────────────────────────────────┘
                          │ HTTP/HTML
┌─────────────────────────▼───────────────────────────────────────┐
│                     Reverse Proxy                                │
│                  Caddy (newsbrief.local)                        │
└─────────────────────────┬───────────────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────────────┐
│                        API Layer                                 │
│                     FastAPI + Jinja2                            │
│           Health probes: /healthz, /readyz, /ollamaz            │
├─────────────────────────────────────────────────────────────────┤
│                     Business Logic                               │
│  ┌──────────┬──────────┬──────────┬──────────┬────────────────┐ │
│  │   Feed   │  Story   │  Topic   │  Entity  │   Scheduler    │ │
│  │ Manager  │Generator │Classifier│Extractor │  (APScheduler) │ │
│  └──────────┴──────────┴──────────┴──────────┴────────────────┘ │
├─────────────────────────────────────────────────────────────────┤
│                    Observability Layer                           │
│        Structured Logging (JSON prod / Human-readable dev)      │
├─────────────────────────────────────────────────────────────────┤
│                       LLM Layer                                  │
│                    Ollama (Local)                               │
│           Qwen 2.5 14B (default, configurable profiles)         │
├─────────────────────────────────────────────────────────────────┤
│                       Data Layer                                 │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │              PostgreSQL 16 (Dev + Production)           │    │
│  │         Container with persistent volume (ADR-0022)     │    │
│  └─────────────────────────────────────────────────────────┘    │
│                    Alembic Migrations                            │
└─────────────────────────────────────────────────────────────────┘
```

### Core Technology Stack

| Component | Technology | Rationale |
|-----------|------------|-----------|
| **Web Framework** | FastAPI | Async support, auto OpenAPI docs, Pydantic validation |
| **Database** | PostgreSQL 16 | ACID, concurrent writes, dev/prod parity (ADR-0022) |
| **ORM** | SQLAlchemy | PostgreSQL database abstraction, async support |
| **Migrations** | Alembic | Schema versioning, reproducible deployments |
| **Reverse Proxy** | Caddy | Automatic TLS, simple config, friendly URL |
| **Templates** | Jinja2 | Server-rendered, simple, no build step |
| **Styling** | Tailwind CSS (local build) | Utility-first, production-optimized |
| **LLM** | Ollama (Qwen 2.5 14B, configurable profiles) | Local privacy, no API costs — see ADR-0025 |
| **Scheduler** | APScheduler | Python-native, background task scheduling |
| **Content Extraction** | Trafilatura (primary) + readability-lxml (fallback) | Tiered extraction with quality scoring — see ADR-0024 |
| **Logging** | Python logging + JSON formatter | Structured logs in production |
| **Container** | Podman/Docker Compose | Multi-service orchestration |

### Key Characteristics

- **Monolithic**: Single Python application, all components in one process
- **PostgreSQL**: Same database engine in all environments (ADR-0022)
- **Local-first**: All data stored locally, works offline (after feed fetch)
- **Privacy-focused**: No telemetry, no external API calls (except feed fetching)
- **Container-ready**: Multi-stage Dockerfile, Compose with Caddy + PostgreSQL
- **Observable**: Structured logging, health endpoints, timing instrumentation

### Environment Separation

| Aspect | Development | Production |
|--------|-------------|------------|
| **Access** | `localhost:8787` | `newsbrief.local` |
| **Database** | PostgreSQL (`localhost:5433`) | PostgreSQL (Docker volume) |
| **Command** | `make dev-full` | `make deploy` |
| **Visual** | DEV banner + tab prefix | Clean UI |
| **Logging** | Human-readable | JSON structured |
| **Container** | None (local Python) | Podman Compose |

### Current Capabilities (v0.8.4)

| Feature | Status | Reference |
|---------|--------|-----------|
| Story-based aggregation | ✅ Complete | [ADR-0002](0002-story-based-aggregation.md) |
| LLM synthesis caching | ✅ Complete | [ADR-0003](0003-synthesis-caching.md) |
| Incremental story updates | ✅ Complete | [ADR-0004](0004-incremental-story-updates.md) |
| Interest-based ranking | ✅ Complete | [ADR-0005](0005-interest-based-ranking.md) |
| Source quality weighting | ✅ Complete | [ADR-0006](0006-source-quality-weighting.md) |
| PostgreSQL support | ✅ Complete | [ADR-0007](0007-postgresql-database-migration.md) |
| Caddy reverse proxy | ✅ Complete | [ADR-0010](0010-caddy-reverse-proxy.md) |
| Structured logging | ✅ Complete | [ADR-0011](0011-structured-logging.md) |
| HTTPS/TLS encryption | ✅ Complete | [ADR-0012](0012-https-tls-encryption.md) |
| Podman Secrets | ✅ Complete | [ADR-0013](0013-podman-secrets.md) |
| API rate limiting | ✅ Complete | [ADR-0014](0014-api-rate-limiting.md) |
| Tiered content extraction | ✅ Complete | [ADR-0024](0024-content-extraction-libraries.md) |
| LLM quality & model profiles | ✅ Complete | v0.8.1 |
| Entity extraction (confidence + roles) | ✅ Complete | v0.8.1 |
| Quality metrics & context manager | ✅ Complete | v0.8.1 |
| LLM output repair + circuit breaker | ✅ Complete | v0.8.1 |
| Source credibility (MBFC) | ✅ Complete | [ADR-0028](0028-source-credibility-architecture.md) |
| Pipeline orchestration + state model | ✅ Complete | [ADR-0029](0029-pipeline-oriented-orchestration.md) / [ADR-0030](0030-article-story-processing-states.md) / [ADR-0031](0031-pipeline-idempotency-and-reingest.md) |
| pgvector embeddings (items + stories) | ✅ Complete | [ADR-0026](0026-rag-integration-strategy.md) |
| Cross-platform CD (GitHub Actions + GHCR) | ✅ Complete | [ADR-0032](0032-cross-platform-cd-strategy.md) |
| Confidence scoring + publish gate | ✅ Complete | v0.8.5 |
| Standard vs deep synthesis routing | ✅ Complete | v0.8.5 |
| Data retention (per-type, dry-run, purge job) | ✅ Complete | v0.8.5 |
| Semantic search (`/search/semantic`) + related/similar endpoints | ✅ Complete | [ADR-0026](0026-rag-integration-strategy.md) — v0.8.6 |
| Semantic deduplication of paraphrased articles | ✅ Complete | [ADR-0026](0026-rag-integration-strategy.md) — v0.8.6 |
| Historical linking (story continuation detection) | ✅ Complete | [ADR-0026](0026-rag-integration-strategy.md) — v0.8.6 |
| Light RAG context anchors in synthesis prompts | ✅ Complete | [ADR-0026](0026-rag-integration-strategy.md) — v0.8.6 |
| Numeric cluster complexity scoring | ✅ Complete | [ADR-0026](0026-rag-integration-strategy.md) — v0.8.6 |

### Remaining Limitations

| Limitation | Impact | Future Solution | Milestone |
|------------|--------|-----------------|-----------|
| Relatedness-precision gate not yet validated at scale | ADR-0026 go/no-go run against a small (16-article) synthetic seed, not real corpus volume | Re-run `scripts/rag_evaluation.py` after ~1-2 weeks of normal ingestion | Follow-up (unscheduled) |
| No user accounts | Single-user only | Auth layer | v1.0.x |
| No full-text search | Limited article discovery | PostgreSQL FTS | v1.0.x |
| No deeper entity linking/disambiguation | Entities extracted per-article, not linked across stories over time | Entity Intelligence System | v0.9.0 |

---

## 2. Completed Milestones (v0.7.x — v0.8.4)

### v0.7.4 - Security ✅ Complete

**Focus**: HTTPS/TLS encryption and secure credential management

**Completed**:
- ✅ TLS certificates via Caddy ([ADR-0012](0012-https-tls-encryption.md))
- ✅ Security headers (HSTS, X-Frame-Options, etc.)
- ✅ Podman Secrets for production ([ADR-0013](0013-podman-secrets.md))
- ✅ API rate limiting ([ADR-0014](0014-api-rate-limiting.md))

### v0.7.5 - GitOps & Kubernetes ✅ Complete

**Focus**: Infrastructure as Code and local Kubernetes CI/CD

**Completed**:
- ✅ Local Kubernetes with kind ([ADR-0015](0015-local-kubernetes-distribution.md))
- ✅ Tekton CI/CD pipelines ([ADR-0016](0016-cicd-platform-migration.md), [ADR-0019](0019-cicd-pipeline-design.md))
- ✅ Secure supply chain: Trivy, Cosign, SBOM ([ADR-0018](0018-secure-supply-chain.md))
- ✅ Local container registry with Buildah rootless builds
- ✅ ArgoCD GitOps deployment ([ADR-0017](0017-gitops-tooling.md))
- ✅ Kustomize overlays for dev/prod environments

> **Note**: Tekton, local registry, and smee.io webhook relay were operational during v0.7.5 but have since been superseded. CI migrated to GitHub Actions + GHCR in June 2026 — see [ADR-0032](0032-cross-platform-cd-strategy.md).

### v0.8.0 - Content Extraction Pipeline Upgrade ✅ Complete

- Tiered content extraction: Trafilatura → readability-lxml → RSS fallback ([ADR-0024](0024-content-extraction-libraries.md))
- Extraction metadata and quality scoring per article

### v0.8.1 - LLM Quality & Intelligence ✅ Complete

- Model configuration profiles (fast / balanced / quality) via `data/model_config.json`
- Improved synthesis prompts and multi-pass refinement
- Entity extraction with confidence scores and role metadata
- Quality metrics (completeness, coverage, entity consistency)
- Context manager: token budgeting, direct/map-reduce/hierarchical strategy selection
- LLM output JSON repair + circuit breaker

### v0.8.2 - Source Credibility System ✅ Complete

- MBFC credibility data import and scheduled refresh
- Domain canonicalization + eligibility filtering in synthesis ([ADR-0028](0028-source-credibility-architecture.md))

### v0.8.3 - Infrastructure Reliability ✅ Complete

- Pipeline orchestration: article + story state machines, stage runner, retries, dead-letter ([ADR-0029](0029-pipeline-oriented-orchestration.md) / [ADR-0030](0030-article-story-processing-states.md) / [ADR-0031](0031-pipeline-idempotency-and-reingest.md))
- Cross-platform CD: GitHub Actions + GHCR → ArgoCD (macOS) + Compose polling (Windows) ([ADR-0032](0032-cross-platform-cd-strategy.md))

### v0.8.4 - Semantic Foundation (RAG, part 1) ✅ Complete

- pgvector embeddings for articles and stories at ingestion
- Cross-platform CD hardening (native WSL2 dev PostgreSQL, ArgoCD 5-minute reconciliation)

### v0.8.5 - Pipeline Completion & Stability ✅ Complete

- Confidence scoring + publish gate — low-confidence stories held or flagged before publish (`app/publish_gate.py`)
- Standard vs deep synthesis routing based on cluster complexity
- Per-type data retention (articles, stories, pipeline logs) with dry-run preview and daily purge job (`app/retention.py`)
- Pipeline observability: stuck-item detection, per-stage run metrics
- E2E state-transition and recovery test coverage

### v0.8.6 - RAG Milestone Completion ✅ Complete

Completes the RAG integration strategy started in v0.8.4 (see [ADR-0026](0026-rag-integration-strategy.md)):

- Embeddings promoted to a first-class pipeline step: `embedding_error` tracking, automatic re-embedding of outdated vectors, admin observability (#278)
- Post-hoc semantic deduplication of paraphrased articles via embedding similarity (#257)
- Light RAG: structured historical context anchors injected into synthesis prompts (#259, #281)
- Bounded retrieval hook powering `/search/semantic`, `/stories/{id}/related`, `/items/{id}/similar` (#279)
- Historical linking — stories detect and link to the story they continue (`app/historical_linking.py`)
- Numeric cluster complexity scoring (0.0-1.0) routing standard vs deep synthesis (#280)
- `scripts/rag_evaluation.py` — go/no-go evaluation harness against ADR-0026's four gates; results documented in the ADR with a conditional "go" decision and a follow-up re-evaluation condition at larger corpus scale (#262)

---

## 3. Medium-Term Vision (v1.0+)

### v1.0.0 - Production Ready

**Focus**: Stability, polish, and deployment flexibility

**Architecture Goal**: Maintain simplicity while adding optional enterprise features

```
┌─────────────────────────────────────────────────────────────────┐
│                    Deployment Options                            │
│  ┌───────────────┐  ┌───────────────┐  ┌───────────────────┐    │
│  │   Personal    │  │    Team       │  │   Enterprise      │    │
│  │  (PostgreSQL) │  │  (PostgreSQL) │  │   (PostgreSQL +   │    │
│  │               │  │               │  │    Auth + Multi)  │    │
│  └───────────────┘  └───────────────┘  └───────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
```

**Planned Changes**:
- Optional authentication (API keys, OAuth)
- Multi-user support (team deployment)
- Apple Containers support ([ADR-0008](0008-apple-containers-deferred.md))
- Full-text search (PostgreSQL FTS)
- Vector search for semantic similarity

### Platform Extensions

#### macOS Widget (v1.1+)

```
┌─────────────────────────────────────────────────────────────────┐
│                    Platform Integration                          │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │                   macOS Widget                             │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐    │  │
│  │  │  WidgetKit  │◄─│  REST API   │◄─│  NewsBrief API  │    │  │
│  │  │  (Swift)    │  │  Client     │  │                 │    │  │
│  │  └─────────────┘  └─────────────┘  └─────────────────┘    │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 4. Long-Term Considerations (v2.0+)

These are exploratory directions, not committed plans:

### Option A: Microservices (If Scale Demands)

**When to Consider**: 100+ concurrent users, need for independent scaling

### Option B: Plugin Architecture

**When to Consider**: Community contributions, diverse use cases

---

## 5. Technology Decision Framework

### When Adding New Technology

Before introducing new dependencies, evaluate:

| Criterion | Question |
|-----------|----------|
| **Necessity** | Can we solve this with existing stack? |
| **Complexity** | Does it add significant operational burden? |
| **Privacy** | Does it require external API calls? |
| **Offline** | Does it work without internet? |
| **Maintenance** | Is it actively maintained? |
| **Size** | Does it significantly increase container size? |

### Core Principles (Do Not Compromise)

1. **Privacy First**: No telemetry, no required external APIs
2. **Local First**: Core functionality works offline
3. **Simplicity**: Prefer simple solutions over clever ones
4. **User Control**: Data ownership, easy backup/export
5. **Monolith Default**: Don't split until complexity demands it

### Technology Watch List

| Technology | Use Case | Status |
|------------|----------|--------|
| **pgvector** | Vector embeddings | ✅ Chosen — [ADR-0026](0026-rag-integration-strategy.md) |
| **ArgoCD** | GitOps deployments (macOS) | ✅ Chosen — [ADR-0017](0017-gitops-tooling.md) |
| **GitHub Actions** | CI/CD | ✅ Chosen — [ADR-0032](0032-cross-platform-cd-strategy.md) |
| **Trivy** | Container scanning | ✅ Implemented v0.7.5 |
| **Cosign** | Image signing | ✅ Implemented v0.7.5 |
| **Tekton** | Kubernetes CI/CD | ⛔ Removed — superseded by GitHub Actions ([ADR-0032](0032-cross-platform-cd-strategy.md)) |
| **PostgreSQL FTS** | Full-text search | Planned for v1.0.x |
| **WidgetKit** | macOS widget | Planned for v1.1.x |
| **htmx** | Dynamic UI without JS complexity | Considering |
| **Ruff** | Fast Python linting | Considering |

---

## 6. Milestone Summary

| Version | Theme | Key Architectural Changes |
|---------|-------|---------------------------|
| **v0.7.1–0.7.4** | Infrastructure & Security | PostgreSQL, Caddy, structured logging, HTTPS, Podman secrets, rate limiting |
| **v0.7.5** | GitOps & Kubernetes | kind cluster, Tekton CI/CD (now superseded), ArgoCD, secure supply chain |
| **v0.8.0–0.8.3** | Foundation (complete) | Tiered extraction, LLM quality, model profiles, credibility, pipeline orchestration, cross-platform CD |
| **v0.8.4** | Semantic Foundation (RAG, part 1) | pgvector embeddings for items + stories |
| **v0.8.5** | Pipeline Completion | Confidence gate, synthesis routing, pipeline tests, data retention |
| **v0.8.6** | RAG Milestone Completion | Semantic search/related/similar, semantic dedup, light RAG anchors, historical linking, complexity scoring, go/no-go evaluation |
| **v0.8.7** (in progress) | Model Optimisation & Platform Intelligence | Hardware-informed, device-aware model profiles ([ADR-0033](0033-hardware-informed-model-selection.md)); oMLX backend adopted on macOS (Ollama retained on Windows); embedding model re-evaluated — `nomic-embed-text` retained (no change) |
| **v0.9.x** | Intelligence Layer | Entity intelligence, multi-perspective synthesis, story evolution, smart extraction |
| **v0.10.x** | Context Layer | Why this matters, trend detection, confidence & transparency UI |
| **v0.11.x** | Experience Layer | Reading tiers, audio/TTS, enhanced visualizations |
| **v1.0.x** | Production Ready | Auth, multi-user capability, data portability |

---

## 7. Contributing to Architecture

### Proposing Changes

1. **Small changes**: Open issue with `architecture` label
2. **Major changes**: Create ADR (Architecture Decision Record) in `docs/adr/`
3. **Breaking changes**: Discuss in issue before implementation

### ADR Template

See `docs/adr/0001-architecture.md` for format reference.

---

## References

- [GitHub Project Board](https://github.com/users/Deim0s13/projects/8)
- [Milestones](https://github.com/Deim0s13/newsbrief/milestones)
- [All ADRs](./README.md)

---

*This document is reviewed and updated with each minor version release.*

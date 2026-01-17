# NewsBrief Architectural Roadmap

> **Living Document** - Last Updated: January 2026

This document outlines the architectural evolution of NewsBrief, from its current state through planned enhancements. It serves as a technical compass for development decisions and helps contributors understand where the project is heading.

---

## 1. Current Architecture (v0.7.x)

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
│               llama3.1:8b (default)                             │
├─────────────────────────────────────────────────────────────────┤
│                       Data Layer                                 │
│  ┌─────────────────────┐  ┌─────────────────────────────────┐   │
│  │  SQLite (Dev)       │  │  PostgreSQL 16 (Production)     │   │
│  │  Single-file DB     │  │  Container with persistent vol  │   │
│  └─────────────────────┘  └─────────────────────────────────┘   │
│                    Alembic Migrations                            │
└─────────────────────────────────────────────────────────────────┘
```

### Core Technology Stack

| Component | Technology | Rationale |
|-----------|------------|-----------|
| **Web Framework** | FastAPI | Async support, auto OpenAPI docs, Pydantic validation |
| **Database (Dev)** | SQLite | Zero-config, single-file backup, fast for development |
| **Database (Prod)** | PostgreSQL 16 | ACID, concurrent writes, production-ready |
| **ORM** | SQLAlchemy | Database abstraction, supports both SQLite and PostgreSQL |
| **Migrations** | Alembic | Schema versioning, reproducible deployments |
| **Reverse Proxy** | Caddy | Automatic TLS, simple config, friendly URL |
| **Templates** | Jinja2 | Server-rendered, simple, no build step |
| **Styling** | Tailwind CSS (local build) | Utility-first, production-optimized |
| **LLM** | Ollama (llama3.1:8b) | Local privacy, no API costs, configurable models |
| **Scheduler** | APScheduler | Python-native, background task scheduling |
| **Content Extraction** | Mozilla Readability | Clean article extraction, well-maintained |
| **Logging** | Python logging + JSON formatter | Structured logs in production |
| **Container** | Podman/Docker Compose | Multi-service orchestration |

### Key Characteristics

- **Monolithic**: Single Python application, all components in one process
- **Dual Database**: SQLite for dev (simple), PostgreSQL for prod (robust)
- **Local-first**: All data stored locally, works offline (after feed fetch)
- **Privacy-focused**: No telemetry, no external API calls (except feed fetching)
- **Container-ready**: Multi-stage Dockerfile, Compose with Caddy + PostgreSQL
- **Observable**: Structured logging, health endpoints, timing instrumentation

### Environment Separation

| Aspect | Development | Production |
|--------|-------------|------------|
| **Access** | `localhost:8787` | `newsbrief.local` |
| **Database** | SQLite | PostgreSQL |
| **Command** | `make dev` | `make deploy` |
| **Visual** | DEV banner + tab prefix | Clean UI |
| **Logging** | Human-readable | JSON structured |
| **Container** | None (local Python) | Podman Compose |

### Current Capabilities (v0.7.4)

| Feature | Status | ADR |
|---------|--------|-----|
| Story-based aggregation | ✅ Complete | [ADR-0002](0002-story-based-aggregation.md) |
| LLM synthesis caching | ✅ Complete | [ADR-0003](0003-synthesis-caching.md) |
| Incremental story updates | ✅ Complete | [ADR-0004](0004-incremental-story-updates.md) |
| Interest-based ranking | ✅ Complete | [ADR-0005](0005-interest-based-ranking.md) |
| Source quality weighting | ✅ Complete | [ADR-0006](0006-source-quality-weighting.md) |
| PostgreSQL support | ✅ Complete | [ADR-0007](0007-postgresql-database-migration.md) |
| Caddy reverse proxy | ✅ Complete | [ADR-0010](0010-caddy-reverse-proxy.md) |
| Structured logging | ✅ Complete | [ADR-0011](0011-structured-logging.md) |
| Health endpoints | ✅ Complete | v0.7.3 |
| Database backup/restore | ✅ Complete | v0.7.2 |
| Auto-start (launchd) | ✅ Complete | v0.7.2 |
| HTTPS/TLS encryption | ✅ Complete | [ADR-0012](0012-https-tls-encryption.md) |
| Podman Secrets | ✅ Complete | [ADR-0013](0013-podman-secrets.md) |
| API rate limiting | ✅ Complete | [ADR-0014](0014-api-rate-limiting.md) |

### Remaining Limitations

| Limitation | Impact | Future Solution | Milestone |
|------------|--------|-----------------|-----------|
| No semantic search | Keyword-only filtering | Vector embeddings | v0.9.x |
| Single LLM provider | Ollama dependency | Pluggable providers | v0.9.x |
| No user accounts | Single-user only | Auth layer | v1.0.x |
| No full-text search | Limited article discovery | SQLite FTS5 | v0.9.x |
| Manual pipeline runs | Requires CLI intervention | Tekton Triggers | v0.7.7 |

---

## 2. Near-Term Evolution (v0.7.x - v0.8.x)

### v0.7.4 - Security ✅ Complete

**Focus**: HTTPS/TLS encryption and secure credential management

**Completed**:
- ✅ TLS certificates via Caddy ([ADR-0012](0012-https-tls-encryption.md))
- ✅ Security headers (HSTS, X-Frame-Options, etc.)
- ✅ Podman Secrets for production ([ADR-0013](0013-podman-secrets.md))
- ✅ API rate limiting ([ADR-0014](0014-api-rate-limiting.md))

### v0.7.5 - GitOps & Kubernetes 🚧 In Progress

**Focus**: Infrastructure as Code and Kubernetes-native CI/CD

```
┌─────────────────────────────────────────────────────────────────┐
│                    kind cluster (newsbrief-dev)                 │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                   Tekton Pipelines                        │  │
│  │                                                           │  │
│  │  ┌─────────┐  ┌──────┐  ┌───────┐  ┌──────┐  ┌────────┐  │  │
│  │  │  lint   │  │ test │  │ build │  │ scan │  │  sign  │  │  │
│  │  └─────────┘  └──────┘  └───────┘  └──────┘  └────────┘  │  │
│  └──────────────────────────────────────────────────────────┘  │
│                              │                                  │
│                              ▼                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │              Local Container Registry                     │  │
│  │                  (registry:5000)                          │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**Completed**:
- ✅ Local Kubernetes with kind ([ADR-0015](0015-local-kubernetes-distribution.md))
- ✅ Tekton CI/CD pipelines ([ADR-0016](0016-cicd-platform-migration.md), [ADR-0019](0019-cicd-pipeline-design.md))
- ✅ Secure supply chain: Trivy, Cosign, SBOM ([ADR-0018](0018-secure-supply-chain.md))
- ✅ Local container registry with Buildah rootless builds

**Remaining**:
- [ ] ArgoCD GitOps deployment ([ADR-0017](0017-gitops-tooling.md))
- [ ] Tekton Triggers for automatic pipeline execution
- [ ] Tekton Dashboard for visual monitoring

### v0.8.0 - Ranking & Personalization

**Focus**: User preferences and smarter content curation

**Planned Changes**:
- User preference storage
- Enhanced topic prioritization
- Bookmarks and read-later
- Advanced personalized ranking

### v0.9.0 - LLM Quality & Intelligence

**Focus**: Better AI quality and flexibility

```
┌─────────────────────────────────────────────────────────────────┐
│                       LLM Layer (Enhanced)                       │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                    LLM Provider Interface                 │   │
│  ├──────────────────────────────────────────────────────────┤   │
│  │  Ollama  │  LM Studio  │  OpenAI-compatible  │  Future   │   │
│  └──────────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  Prompt Templates  │  Response Caching  │  Quality Eval  │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

**Planned Changes**:
- Pluggable LLM provider interface
- Improved prompt engineering
- Response quality evaluation
- Support for larger context models
- Model performance comparison

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
│  │   (SQLite)    │  │  (PostgreSQL) │  │   (PostgreSQL +   │    │
│  │               │  │               │  │    Auth + Multi)  │    │
│  └───────────────┘  └───────────────┘  └───────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
```

**Planned Changes**:
- Optional authentication (API keys, OAuth)
- Multi-user support (team deployment)
- Apple Containers support ([ADR-0008](0008-apple-containers-deferred.md))
- Full-text search (SQLite FTS5)
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
| **Chroma** | Vector embeddings | Evaluating for v0.9.0 |
| **SQLite FTS5** | Full-text search | Planned for v1.0.0 |
| **WidgetKit** | macOS widget | Planned for v1.1.0 |
| **htmx** | Dynamic UI without JS complexity | Considering |
| **Ruff** | Fast Python linting | Considering |
| **ArgoCD** | GitOps deployments | ✅ Chosen for v0.7.5 |
| **Tekton** | Kubernetes CI/CD | ✅ Implemented v0.7.5 |
| **Trivy** | Container scanning | ✅ Implemented v0.7.5 |
| **Cosign** | Image signing | ✅ Implemented v0.7.5 |

---

## 6. Milestone Summary

| Version | Theme | Key Architectural Changes |
|---------|-------|---------------------------|
| **v0.7.1-0.7.4** | Infrastructure & Security | Dual database, Caddy proxy, structured logging, health endpoints, HTTPS, Podman secrets, rate limiting |
| **v0.7.5** | GitOps & Kubernetes | kind cluster, Tekton CI/CD, secure supply chain (Trivy, Cosign, SBOM), local registry, ArgoCD |
| **v0.8.x** | Personalization | Enhanced preferences, advanced ranking |
| **v0.9.x** | Intelligence | Pluggable LLM providers, prompt improvements |
| **v1.0.x** | Production | Optional auth, multi-user, search |
| **v1.1.x** | Platform | macOS widget, platform integrations |

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

- [GitHub Project Board](https://github.com/users/Deim0s13/projects/2)
- [Milestones](https://github.com/Deim0s13/newsbrief/milestones)
- [All ADRs](./README.md)

---

*This document is reviewed and updated with each minor version release.*

# NewsBrief Architectural Roadmap

> **Living Document** - Last Updated: December 2025

This document outlines the architectural evolution of NewsBrief, from its current state through planned enhancements. It serves as a technical compass for development decisions and helps contributors understand where the project is heading.

---

## 1. Current Architecture (v0.6.x)

### Overview

NewsBrief is a **local-first, story-based news aggregator** that synthesizes multiple RSS sources into AI-generated story briefs.

```
┌─────────────────────────────────────────────────────────────────┐
│                        Client Layer                              │
│              Browser (Tailwind CSS + Vanilla JS)                │
└─────────────────────────┬───────────────────────────────────────┘
                          │ HTTP/HTML
┌─────────────────────────▼───────────────────────────────────────┐
│                        API Layer                                 │
│                     FastAPI + Jinja2                            │
├─────────────────────────────────────────────────────────────────┤
│                     Business Logic                               │
│  ┌──────────┬──────────┬──────────┬──────────┬────────────────┐ │
│  │   Feed   │  Story   │  Topic   │  Entity  │   Scheduler    │ │
│  │ Manager  │Generator │Classifier│Extractor │  (APScheduler) │ │
│  └──────────┴──────────┴──────────┴──────────┴────────────────┘ │
├─────────────────────────────────────────────────────────────────┤
│                       LLM Layer                                  │
│                    Ollama (Local)                               │
│               llama3.1:8b (default)                             │
├─────────────────────────────────────────────────────────────────┤
│                       Data Layer                                 │
│              SQLite + JSON Config Files                         │
└─────────────────────────────────────────────────────────────────┘
```

### Core Technology Stack

| Component | Technology | Rationale |
|-----------|------------|-----------|
| **Web Framework** | FastAPI | Async support, auto OpenAPI docs, Pydantic validation |
| **Database** | SQLite | Zero-config, single-file backup, excellent for read-heavy workloads |
| **Templates** | Jinja2 | Server-rendered, simple, no build step |
| **Styling** | Tailwind CSS (local build) | Utility-first, production-optimized |
| **LLM** | Ollama (llama3.1:8b) | Local privacy, no API costs, configurable models |
| **Scheduler** | APScheduler | Python-native, background task scheduling |
| **Content Extraction** | Mozilla Readability | Clean article extraction, well-maintained |

### Key Characteristics

- **Monolithic**: Single Python application, all components in one process
- **Local-first**: All data stored locally, works offline (after feed fetch)
- **Privacy-focused**: No telemetry, no external API calls (except feed fetching)
- **Container-ready**: Dockerfile for consistent deployment

### Current Limitations

| Limitation | Impact | Future Solution |
|------------|--------|-----------------|
| SQLite write concurrency | Limited multi-user support | PostgreSQL option |
| No semantic search | Keyword-only filtering | Vector embeddings |
| Single LLM provider | Ollama dependency | Pluggable providers |
| No user accounts | Single-user only | Auth layer |
| No full-text search | Limited article discovery | SQLite FTS5 |

---

## 2. Near-Term Evolution (v0.7.x - v0.8.x)

### v0.7.0 - LLM Improvements

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
- Better caching strategies
- Support for larger context models

### v0.8.0 - Ranking & Personalization

**Focus**: User preferences and smarter content curation

**Planned Changes**:
- User preference storage
- Topic prioritization
- Bookmarks and read-later
- Personalized story ranking
- Improved importance scoring

### v0.9.0 - Search & Discovery

**Focus**: Finding content efficiently

```
┌─────────────────────────────────────────────────────────────────┐
│                       Search Layer (New)                         │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────┐   │
│  │  SQLite FTS5     │  │  Vector Search   │  │   Hybrid     │   │
│  │  (Full-text)     │  │  (Semantic)      │  │   Ranking    │   │
│  └──────────────────┘  └──────────────────┘  └──────────────┘   │
│                              │                                   │
│                    ┌─────────▼─────────┐                        │
│                    │  Chroma / SQLite  │                        │
│                    │  Vector Store     │                        │
│                    └───────────────────┘                        │
└─────────────────────────────────────────────────────────────────┘
```

**Planned Changes**:
- SQLite FTS5 for full-text search
- Vector embeddings for semantic search
- Hybrid search (keyword + semantic)
- Similar story suggestions

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
- Database abstraction layer (SQLite/PostgreSQL)
- Optional authentication (API keys, OAuth)
- Multi-user support (team deployment)
- Kubernetes deployment manifests
- Health checks and monitoring endpoints

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
│  ┌───────────────────────────────────────────────────────────┐  │
│  │                   Future: iOS App                          │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 4. Long-Term Considerations (v2.0+)

### Potential Architecture Evolution

These are exploratory directions, not committed plans:

#### Option A: Microservices (If Scale Demands)

```
┌─────────────────────────────────────────────────────────────────┐
│                    API Gateway                                   │
├─────────────────────────────────────────────────────────────────┤
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────┐    │
│  │   Feed   │  │  Story   │  │  Search  │  │     LLM      │    │
│  │ Service  │  │ Service  │  │ Service  │  │   Service    │    │
│  └──────────┘  └──────────┘  └──────────┘  └──────────────┘    │
│       │             │             │              │              │
│       └─────────────┴─────────────┴──────────────┘              │
│                           │                                      │
│                    Message Queue                                 │
│                   (Redis / RabbitMQ)                            │
└─────────────────────────────────────────────────────────────────┘
```

**When to Consider**: 100+ concurrent users, need for independent scaling

#### Option B: Edge Deployment

```
┌─────────────────────────────────────────────────────────────────┐
│                    Edge Configuration                            │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │   Cloudflare Workers / Vercel Edge                        │  │
│  │   ┌──────────────────────────────────────────────────┐    │  │
│  │   │  Static Assets + API Proxy                        │    │  │
│  │   └──────────────────────────────────────────────────┘    │  │
│  └───────────────────────────────────────────────────────────┘  │
│                           │                                      │
│                    ┌──────▼──────┐                              │
│                    │  Origin     │                              │
│                    │  Server     │                              │
│                    └─────────────┘                              │
└─────────────────────────────────────────────────────────────────┘
```

**When to Consider**: Global user base, CDN requirements

#### Option C: Plugin Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    Plugin System                                 │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │                   Plugin Manager                           │  │
│  ├───────────────────────────────────────────────────────────┤  │
│  │  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────────┐  │  │
│  │  │  Feed   │  │   LLM   │  │ Storage │  │  Notifier   │  │  │
│  │  │ Plugins │  │ Plugins │  │ Plugins │  │  Plugins    │  │  │
│  │  ├─────────┤  ├─────────┤  ├─────────┤  ├─────────────┤  │  │
│  │  │• RSS    │  │• Ollama │  │• SQLite │  │• Slack      │  │  │
│  │  │• Atom   │  │• OpenAI │  │• Postgres│ │• Discord    │  │  │
│  │  │• JSON   │  │• Claude │  │• MySQL  │  │• Email      │  │  │
│  │  └─────────┘  └─────────┘  └─────────┘  └─────────────┘  │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

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

Technologies being monitored for potential adoption:

| Technology | Use Case | Status |
|------------|----------|--------|
| **Chroma** | Vector embeddings | Evaluating for v0.9.0 |
| **SQLite FTS5** | Full-text search | Planned for v0.9.0 |
| **WidgetKit** | macOS widget | Planned for v1.1.0 |
| **htmx** | Dynamic UI without JS complexity | Considering |
| **Pydantic v2** | Already using, monitor updates | Adopted |
| **Ruff** | Fast Python linting | Considering for DX |

---

## 6. Milestone Summary

| Version | Theme | Key Architectural Changes |
|---------|-------|---------------------------|
| **v0.6.x** | Current | Monolith, SQLite, Local Ollama |
| **v0.7.x** | LLM | Pluggable LLM providers, better prompts |
| **v0.8.x** | Personalization | User preferences, ranking improvements |
| **v0.9.x** | Search | FTS5, vector embeddings, semantic search |
| **v1.0.x** | Production | Multi-backend, optional auth, stability |
| **v1.1.x** | Platform | macOS widget, platform integrations |
| **v2.0.x** | TBD | Based on user needs and scale requirements |

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

- [ADR 0001: Core Architecture](0001-architecture.md)
- [ADR 0002: Story-Based Aggregation](0002-story-based-aggregation.md)
- [GitHub Project Board](https://github.com/Deim0s13/newsbrief/projects)
- [Milestones](https://github.com/Deim0s13/newsbrief/milestones)

---

*This document is reviewed and updated with each minor version release.*


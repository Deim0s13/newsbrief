# 0001 — Architecture Decision: Local-First RSS Aggregator

**Status**: Accepted  
**Date**: 2025-09-27  
**Updated**: 2025-09-27  

## Context

Modern RSS readers are often cloud-based services that compromise privacy, require internet connectivity, and may disappear without notice. There's a need for a local-first RSS aggregator that:

- Preserves user privacy (no data leaves the local system)
- Works offline after initial setup
- Provides intelligent content curation without relying on external services
- Remains under user control and can be easily backed up/migrated
- Scales from personal use to small team deployments

## Decision

### Core Architecture: FastAPI + SQLite + Container-First

**Web Framework**: FastAPI
- Modern Python framework with excellent async support
- Automatic OpenAPI documentation generation
- Built-in request validation with Pydantic models
- High performance comparable to Node.js and Go
- Native support for both JSON APIs and HTML templating

**Database**: SQLite with planned FTS5 integration
- Zero-configuration, serverless database
- Single file for easy backup and migration  
- Excellent performance for read-heavy workloads
- Built-in full-text search capabilities (FTS5)
- ACID compliance and robust concurrent access
- No external database server required

**Frontend Strategy**: Progressive Enhancement with HTMX
- Server-rendered HTML with Jinja2 templates
- HTMX for dynamic updates without JavaScript complexity
- No build step required, no client-side framework dependencies
- Graceful degradation for users without JavaScript
- Faster initial page loads compared to SPA approaches

**Containerization**: Podman/Docker with Future Apple Containers
- Container-first design for consistent deployment
- Podman preferred for better security model (rootless)
- Future experiment with Apple Containers on macOS
- Easy scaling from development to production

**AI Integration**: Local LLM via Ollama
- Privacy-preserving AI summaries and categorization
- No data sent to external services
- Ollama provides easy local LLM deployment
- Support for multiple models (Llama, Mistral, etc.)
- Planned features: summarization, embeddings, categorization

### Data Architecture

```
┌─────────────────────────────────────────┐
│              Client Layer               │
│         (Browser + HTMX)               │
└─────────────┬───────────────────────────┘
              │ HTTP/JSON
┌─────────────▼───────────────────────────┐
│             API Layer                   │
│           (FastAPI)                     │
├─────────────────────────────────────────┤
│         Business Logic                  │
│  ┌─────────┬─────────┬─────────────────┐ │
│  │  Feed   │Content  │    Future:      │ │
│  │Manager  │Extract  │ LLM Integration │ │
│  └─────────┴─────────┴─────────────────┘ │
├─────────────────────────────────────────┤
│           Data Layer                    │
│    ┌─────────────┬─────────────────────┐ │
│    │   SQLite    │    Future: Vector   │ │
│    │   Database  │    Embeddings DB    │ │
│    └─────────────┴─────────────────────┘ │
└─────────────────────────────────────────┘
```

### Key Design Decisions

#### 1. Local-First Philosophy
- **All data stored locally**: SQLite database, no cloud dependencies
- **Privacy by design**: No telemetry, tracking, or external API calls
- **Offline capable**: Core functionality works without internet
- **User ownership**: Complete control over data and configuration

#### 2. RSS/Atom Processing Pipeline
- **Efficient caching**: ETag and Last-Modified headers reduce bandwidth
- **Content extraction**: Mozilla Readability for clean article text
- **Deduplication**: URL-based hashing prevents duplicate articles
- **Robots.txt compliance**: Two-tier checking (feed-level + article-level) with caching
- **Respectful fetching**: Configurable timeouts, fail-safe error handling, User-Agent identification

#### 3. Robots.txt Compliance Strategy
- **Dual-layer checking**: Feed URLs validated on addition, article URLs validated before content extraction
- **Performance-optimized**: In-memory caching with refresh-cycle invalidation
- **Standards compliance**: Proper parsing of User-agent, Disallow, and Allow directives
- **Fail-safe design**: Network/parsing errors default to "allow" for service reliability
- **Graceful degradation**: Blocked articles saved without full content rather than rejected

#### 4. Enhanced Fetch Cap Strategy ⭐ *Added in v0.2.4*
- **Multi-layer limits**: Global, per-feed, and time-based safety caps for predictable runtime
- **Fair distribution**: Per-feed limits prevent individual feeds from consuming entire refresh quota
- **Configurable via environment**: Production-ready flexibility without code changes
- **Comprehensive monitoring**: Detailed statistics for operational insights and debugging
- **Backward compatibility**: Enhanced API maintains existing integrations while adding new capabilities
- **Performance optimization**: Early exit conditions and efficient limit checking minimize overhead

#### 5. Extensible Architecture
- **Plugin-ready**: Clean separation of concerns for future extensions
- **API-first**: All functionality exposed via REST endpoints
- **Modular components**: Easy to swap implementations (e.g., database)
- **Container native**: Seamless deployment across environments

### Technology Justifications

#### FastAPI vs. Alternatives
| Aspect | FastAPI | Flask | Django | Express.js |
|--------|---------|--------|--------|------------|
| Performance | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ |
| Auto-documentation | ⭐⭐⭐⭐⭐ | ⭐ | ⭐⭐ | ⭐⭐ |
| Type safety | ⭐⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ |
| Learning curve | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐ |
| Ecosystem | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |

#### SQLite vs. Alternatives
| Aspect | SQLite | PostgreSQL | MySQL | MongoDB |
|--------|--------|------------|-------|---------|
| Setup complexity | ⭐⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐ | ⭐⭐⭐ |
| Backup/migration | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐ |
| Full-text search | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ |
| Concurrency | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| Resource usage | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ |

## Consequences

### Positive

**Simplicity**
- Single binary deployment with container
- No complex infrastructure requirements
- Easy backup (single SQLite file)
- Straightforward development environment setup

**Privacy & Control**
- Complete data ownership by user
- No external dependencies for core functionality
- Auditable codebase and clear data flow
- Resistant to service shutdowns or policy changes

**Performance**
- Fast startup time (< 2 seconds)
- Efficient memory usage (< 100MB base)
- Local database eliminates network latency
- Optimized for read-heavy RSS consumption patterns

**Developer Experience**
- Automatic API documentation
- Type-safe request/response handling
- Hot-reload during development
- Clear separation of concerns

### Negative

**Scalability Constraints**
- SQLite write concurrency limitations
- Single-node deployment model
- Manual backup/sync across devices

**Limited Ecosystem**
- Fewer third-party integrations compared to cloud services
- Manual feed discovery (no recommendation engine)
- No built-in social features or sharing

**Maintenance Overhead**
- Users responsible for updates and backups
- No managed hosting option (by design)
- Requires technical knowledge for advanced configuration

### Risk Mitigation

**SQLite Limitations**
- Plan migration path to PostgreSQL for high-concurrency use cases
- Implement connection pooling and write queue for heavy loads
- Use WAL mode for better concurrent read performance

**Container Complexity**
- Provide simple installation scripts
- Document common deployment scenarios
- Maintain both container and native Python deployment options

**Future Scaling**
- Design APIs to be stateless and horizontally scalable
- Plan database abstraction layer for multiple backend support
- Consider distributed deployment for team usage

## Future Considerations

> **📋 Implementation Tracking**: Detailed epic breakdowns and current development status available at  
> **[GitHub Project Board](https://github.com/users/Deim0s13/projects/7/views/1?layout=board)**

### Planned Enhancements (v0.3.x - v0.5.x)

The following enhancements are organized into epics with detailed user stories and acceptance criteria tracked on the GitHub project board:

**Web Interface** (v0.3.0) - Epic: UI
- HTMX-powered responsive web UI
- Article reading interface with clean typography
- Feed management dashboard
- Search and filtering capabilities

**AI Integration** (v0.4.0) - Epic: Summaries + Epic: Embeddings
- Ollama integration for article summarization
- Automatic content categorization
- Duplicate detection improvement
- Smart feed recommendations

**Advanced Features** (v0.5.0) - Epic: Search + Epic: Operations
- Vector embeddings for semantic search
- Export/import functionality (OPML, JSON)
- Multi-user support with access controls
- API rate limiting and authentication

### Epic Organization

The project board breaks development into focused, deliverable epics:

- **epic:ingestion** - Core RSS/feed processing pipeline improvements
- **epic:summaries** - Local LLM integration for content summarization
- **epic:ranking** - Content scoring, curation, and recommendation algorithms
- **epic:ui** - Complete web interface using HTMX and progressive enhancement
- **epic:embeddings** - Vector embeddings for semantic search and clustering
- **epic:search** - Full-text search with SQLite FTS5 and advanced filtering
- **epic:ops** - DevOps tooling, monitoring, deployment, and operational concerns

### Potential Architecture Evolution

**Database Layer**
- Plugin architecture for multiple database backends
- Optional PostgreSQL support for high-concurrency deployments
- Vector database integration (Chroma, Weaviate) for embeddings

**AI/ML Pipeline**
- Pluggable LLM providers (Ollama, OpenAI-compatible)
- Local embedding models for semantic features
- Content classification and topic modeling

**Deployment Options**
- Kubernetes manifests for production deployment
- ARM/Apple Silicon optimized containers
- Integration with home automation systems (Home Assistant)

## References

- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [SQLite FTS5 Documentation](https://www.sqlite.org/fts5.html)
- [HTMX Documentation](https://htmx.org/)
- [Ollama Project](https://ollama.ai/)
- [Mozilla Readability](https://github.com/mozilla/readability)
- [RSS 2.0 Specification](https://cyber.harvard.edu/rss/rss.html)
- [Atom 1.0 Specification](https://tools.ietf.org/html/rfc4287)
# ADR 0008: Apple Containers Support Deferred

## Status

**Accepted**

## Date

2026-01-05

## Context

Apple introduced "Apple Containers" as a native container runtime in macOS Tahoe (macOS 26). This offers potential benefits for macOS users who prefer native tooling over Docker Desktop or Podman.

We initially planned to support Apple Containers in v0.7.2 with the following issues:
- #23: Run image with Apple Containers CLI
- #24: Host access to Ollama in Apple Containers
- #25: Document differences vs Podman

### The Challenge

NewsBrief is moving from SQLite to PostgreSQL for production deployments (ADR 0007). This introduces a multi-container architecture:

```
┌─────────────────┐       ┌─────────────────┐
│   api           │──────▶│   db            │
│   (NewsBrief)   │       │   (PostgreSQL)  │
└─────────────────┘       └─────────────────┘
```

This architecture requires:
1. **Multi-container networking**: App container must reach database container via hostname
2. **Compose-like orchestration**: Starting multiple containers with dependencies
3. **Healthchecks**: Wait for database to be ready before starting app

### Apple Containers Limitations (as of 2026-01)

| Feature | Docker/Podman | Apple Containers |
|---------|---------------|------------------|
| Single container execution | ✅ | ✅ |
| Volume mounts | ✅ | ✅ (needs verification) |
| Port mapping | ✅ | ✅ (needs verification) |
| Multi-container networking | ✅ | ❓ Unknown |
| Compose equivalent | docker-compose / podman-compose | ❓ Not available |
| Healthcheck dependencies | ✅ | ❓ Unknown |

Without compose-like tooling and verified multi-container networking, running NewsBrief + PostgreSQL on Apple Containers would require:
- Running PostgreSQL on the host (Homebrew/Postgres.app)
- Using a cloud-hosted database
- Mixing Apple Containers (app) with Docker/Podman (database)

All of these defeat the simplicity goal of a self-contained deployment.

## Decision

**Defer Apple Containers support to v1.0.0 (Platform Expansion) milestone.**

### Rationale

1. **Technology Maturity**: Apple Containers is new; multi-container workflows may improve
2. **Focus**: Prioritize proven technology (Docker/Podman) for production readiness
3. **No Blocking**: This doesn't prevent macOS users from using Docker Desktop or Podman
4. **Revisit Later**: When Apple Containers has compose-like tooling, reassess feasibility

### Actions Taken

- Moved issues #23, #24, #25 from v0.7.2 to v1.0.0 - Platform Expansion
- v0.7.2 milestone renamed/repurposed or closed

## Alternatives Considered

### 1. Support Apple Containers for single-container (SQLite) mode only
- **Pros**: Some Apple Containers users could use NewsBrief
- **Cons**: Creates two deployment paths, SQLite isn't production-recommended
- **Verdict**: Adds complexity without significant value

### 2. Test and document Apple Containers limitations now
- **Pros**: Data-driven decision
- **Cons**: Time investment for uncertain outcome
- **Verdict**: Not worth the effort at this stage; technology will evolve

### 3. Drop Apple Containers entirely
- **Pros**: Simplest roadmap
- **Cons**: May miss future opportunity if Apple Containers matures
- **Verdict**: Deferring is better than dropping

## Consequences

### Positive

1. **Simpler v0.7.x**: Focus on proven container runtimes
2. **Clear Documentation**: Users know Docker/Podman is supported
3. **Future Option**: Can revisit when technology matures
4. **No Technical Debt**: Not committing to unproven patterns

### Negative

1. **macOS Users**: Must use Docker Desktop or Podman (minor inconvenience)
2. **Native Experience**: Miss opportunity for tighter macOS integration

### Neutral

1. **Documentation**: Already cover Docker and Podman
2. **CI/CD**: No changes needed (uses Docker)

## Revisit Criteria

Consider implementing Apple Containers support when:

1. Apple releases compose-like multi-container orchestration
2. Multi-container networking is documented and stable
3. Community adoption provides validation and patterns
4. PostgreSQL + application has been verified working by others

## References

- ADR 0007: PostgreSQL Database Migration
- Issue #23: Run image with Apple Containers CLI
- Issue #24: Host access to Ollama in Apple Containers
- Issue #25: Document differences vs Podman
- [Apple Container Documentation](https://developer.apple.com/documentation/) (when available)


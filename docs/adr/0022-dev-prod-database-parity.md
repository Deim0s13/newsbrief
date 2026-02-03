# ADR 0022: Dev/Prod Database Parity - PostgreSQL Only

## Status

**Proposed**

## Date

2026-02-04

## Supersedes / Amends

- **[ADR 0007: PostgreSQL Database Migration](0007-postgresql-database-migration.md)** - Superseded
  - ADR 0007 established dual database support (PostgreSQL for prod, SQLite for dev)
  - This ADR supersedes that decision by mandating PostgreSQL for all environments

- **[ADR 0001: Architecture Decision](0001-architecture.md)** - Partially Amended
  - ADR 0001 specified SQLite as the core database (sections: Core Architecture, Data Architecture diagram, Technology Justifications)
  - The database-related sections are superseded by ADR 0007 and this ADR
  - Other architectural decisions (FastAPI, HTMX, Ollama, containerization) remain valid

## Context

ADR 0007 established dual database support: PostgreSQL for production and SQLite for development. While this provided flexibility, it has created maintenance burden and production bugs that only surface after deployment.

### Problems with Dual Database Support

**Code Complexity:**
- 9 `is_postgres()` conditional branches in the codebase
- SQL dialect differences requiring duplicate code paths:
  - `RETURNING id` (PostgreSQL) vs `last_insert_rowid()` (SQLite)
  - `NOW()` vs `datetime('now')`
  - Different date arithmetic syntax
  - Different parameter placeholder handling

**Production Bugs Not Caught in Dev:**
- **Timezone Issue (v0.7.7)**: `datetime.fromtimestamp()` behaves differently; dates appeared "in the future" in prod but worked correctly in dev
- Alembic migrations tested on SQLite may fail on PostgreSQL
- SQL queries that work on SQLite may have subtle behavioral differences on PostgreSQL

**Dual Migration Systems:**
- PostgreSQL: Alembic migrations only
- SQLite: Inline SQL migrations in `init_db()` (lines 108-244 in `db.py`)
- Schema changes must be maintained in two places

**Maintenance Burden:**
- Every database-touching feature requires testing on both backends
- CI should test both but currently doesn't
- Documentation must cover both configurations

### Current `is_postgres()` Locations

| File | Count | Purpose |
|------|-------|---------|
| `app/db.py` | 1 | Different initialization paths |
| `app/feeds.py` | 8 | SQL syntax differences (RETURNING, NOW, date arithmetic) |
| **Total** | **9** | |

## Decision

**Mandate PostgreSQL as the only supported database for both development and production environments.**

### Implementation

1. **Development Setup**: Require PostgreSQL via Docker Compose
   ```bash
   # New dev workflow
   make db-up        # Start PostgreSQL container
   make dev          # Run app with hot-reload against PostgreSQL
   ```

2. **Remove SQLite Support**:
   - Delete SQLite code paths from `app/db.py`
   - Remove all `is_postgres()` conditionals
   - Delete inline migrations from `init_db()`
   - Update `alembic.ini` to remove SQLite default

3. **Single Migration System**: Alembic only
   - All schema changes via Alembic migrations
   - No more `init_db()` inline SQL for schema management

4. **CI/CD**: Test against PostgreSQL only
   - Simplify CI pipeline configuration
   - Remove SQLite test matrix

## Alternatives Considered

### Alternative A: Keep Dual Database, Improve Abstraction
- Create database abstraction layer to hide dialect differences
- **Pros**: Keeps lightweight dev experience
- **Cons**: Still two code paths, abstraction adds complexity, doesn't prevent all parity issues
- **Verdict**: Rejected - doesn't solve the core problem

### Alternative B: Full Containerized Development (K8s locally)
- Run dev environment in Kind cluster matching prod exactly
- **Pros**: 100% parity including orchestration
- **Cons**: Slow iteration, high resource usage, complex setup
- **Verdict**: Rejected - overkill for the problem being solved

### Alternative C: PostgreSQL Everywhere (Selected)
- Require PostgreSQL for dev via simple Docker Compose
- **Pros**: Eliminates all database parity issues, simple setup
- **Cons**: Requires Docker/Podman for development
- **Verdict**: Selected - best balance of simplicity and parity

## Consequences

### Issues Resolved (High Value)

| Issue | Resolution |
|-------|------------|
| 9 `is_postgres()` conditionals | **Eliminated** - single code path |
| Dual migration systems | **Eliminated** - Alembic only |
| Timezone handling differences | **Eliminated** - same datetime behavior |
| SQL dialect differences | **Eliminated** - single PostgreSQL dialect |
| "Works in dev, fails in prod" | **Greatly reduced** - same database |
| Migration testing gap | **Eliminated** - test once, deploy anywhere |

### Remaining Gaps (Lower Risk)

| Gap | Mitigation | Risk Level |
|-----|------------|------------|
| Container build issues | CI builds and tests image before deploy | Low |
| Multi-replica behavior | Already tested in Kind before promoting | Low |
| K8s resource limits | Prod config already tuned and stable | Low |
| K8s networking differences | Transparent to application code | Low |

### Positive Consequences

1. **Simplified Codebase**: Remove ~200 lines of SQLite-specific code
2. **Single Migration Path**: Alembic migrations work identically in dev and prod
3. **Catch Bugs Earlier**: Database issues surface in dev, not prod
4. **Reduced Testing Matrix**: One database backend to test
5. **Clearer Documentation**: Single setup path to document

### Negative Consequences

1. **Docker Required for Dev**: Developers must have Docker/Podman installed
2. **Slightly Slower Dev Setup**: Need to start PostgreSQL container first
3. **More Resources**: PostgreSQL uses more memory than SQLite (~50-100MB)
4. **Migration Required**: Existing SQLite users need to migrate data

### Neutral Consequences

1. **Dev Workflow Change**: `make dev` now requires `make db-up` first (or combined target)
2. **Existing PostgreSQL Users**: No change - they already use this setup

## Implementation Plan

### Phase 1: Preparation
- [ ] Create `make dev-full` target that starts PostgreSQL and app together
- [ ] Update `.env.example` with PostgreSQL defaults
- [ ] Document new dev setup in README

### Phase 2: Code Cleanup
- [ ] Remove `is_postgres()` function and all conditionals
- [ ] Delete inline SQLite migrations from `init_db()`
- [ ] Simplify `init_db()` to PostgreSQL-only verification
- [ ] Remove SQLite-specific connection args

### Phase 3: Configuration Cleanup
- [ ] Update `alembic.ini` to require `DATABASE_URL`
- [ ] Remove SQLite fallback from `alembic/env.py`
- [ ] Update CI to PostgreSQL-only testing

### Phase 4: Documentation
- [ ] Update README with new dev setup
- [ ] Update DEVELOPMENT.md
- [ ] Archive SQLite migration documentation
- [ ] Update ADR 0007 status to "Superseded by ADR 0022"

## Migration Path for Existing SQLite Users

For developers with existing SQLite databases:

1. **Export Data**: `sqlite3 data/newsbrief.sqlite3 .dump > backup.sql`
2. **Start PostgreSQL**: `make db-up`
3. **Run Migrations**: `alembic upgrade head`
4. **Import Data**: Manual import or fresh start (dev data is typically disposable)

## Success Metrics

- [ ] Zero `is_postgres()` calls in codebase
- [ ] Single `init_db()` code path
- [ ] All developers using PostgreSQL for local development
- [ ] No database-related bugs discovered only in production

## References

- [ADR 0007: PostgreSQL Database Migration](0007-postgresql-database-migration.md) - Original dual-database decision (superseded)
- [12-Factor App: Dev/Prod Parity](https://12factor.net/dev-prod-parity)
- [PostgreSQL Docker Image](https://hub.docker.com/_/postgres)

# ADR 0007: PostgreSQL Database Migration

## Status

**Proposed**

## Date

2026-01-05

## Context

NewsBrief currently uses SQLite as its database backend. While SQLite has served well for development and single-user deployments, we need to evaluate whether it meets our requirements for production use.

### Current State (SQLite)

**Advantages:**
- Zero configuration - just works
- Single file database (`data/newsbrief.sqlite3`)
- No external dependencies
- Perfect for development and testing
- Portable - easy to backup/restore

**Limitations:**
- Single writer at a time (database locks on writes)
- Limited concurrent connection handling
- No built-in replication or clustering
- Backup requires file copy (potential consistency issues during writes)
- Limited support for advanced data types
- No native network access (file-based only)

### Production Requirements

As NewsBrief matures toward production readiness, we anticipate:

1. **Concurrent Operations**: Feed refresh, story generation, and API requests happening simultaneously
2. **Scalability**: Potential for multiple API instances behind a load balancer
3. **Reliability**: Production-grade backup, restore, and point-in-time recovery
4. **Monitoring**: Database performance metrics and query analysis
5. **Container Orchestration**: Kubernetes/Docker Swarm deployments with separate database pods

## Decision

**Migrate to PostgreSQL as the primary production database while maintaining SQLite support for development and simple deployments.**

### Implementation Approach

1. **Dual Database Support**: Application supports both SQLite and PostgreSQL via `DATABASE_URL` environment variable
2. **Default Behavior**: 
   - If `DATABASE_URL` is set → Use PostgreSQL
   - If `DATABASE_URL` is not set → Fall back to SQLite
3. **Container Architecture**: Separate `db` service in Docker Compose using official `postgres:16` image
4. **Schema Management**: SQLAlchemy ORM handles schema creation for both databases

### Technical Details

**PostgreSQL Version**: 16 (latest LTS with performance improvements)

**Connection String Format**:
```
DATABASE_URL=postgresql://user:password@host:5432/database
```

**Docker Compose Architecture**:
```yaml
services:
  db:
    image: postgres:16
    # Separate container, persistent volume, healthcheck
    
  api:
    depends_on:
      db:
        condition: service_healthy
    environment:
      DATABASE_URL: postgresql://...@db:5432/newsbrief
```

**SQLAlchemy Compatibility**:
- Use SQLAlchemy ORM (already in use) for database-agnostic queries
- Avoid SQLite-specific SQL syntax
- Use `text()` for raw SQL with parameter binding

## Alternatives Considered

### 1. Stay with SQLite
- **Pros**: No migration effort, simpler deployment
- **Cons**: Production limitations remain, scalability ceiling
- **Verdict**: Not suitable for production growth path

### 2. MySQL/MariaDB
- **Pros**: Widely used, good tooling
- **Cons**: Licensing considerations (Oracle), less feature-rich than PostgreSQL
- **Verdict**: PostgreSQL preferred for features and ecosystem

### 3. Cloud-managed Database (RDS, Cloud SQL)
- **Pros**: Zero maintenance, automatic backups
- **Cons**: Vendor lock-in, cost, requires network access
- **Verdict**: Future option, not required for self-hosted focus

### 4. Embedded PostgreSQL
- **Pros**: Single binary like SQLite
- **Cons**: Not production-ready, limited tooling
- **Verdict**: Not mature enough

## Consequences

### Positive

1. **Production Ready**: PostgreSQL is battle-tested for production workloads
2. **Concurrent Writes**: MVCC allows multiple simultaneous writers
3. **Scalability**: Connection pooling, read replicas possible
4. **Backup Tooling**: `pg_dump`, `pg_basebackup`, WAL archiving, PITR
5. **Monitoring**: `pg_stat_statements`, extensive metrics
6. **Kubernetes Native**: Standard pattern with StatefulSets or operators
7. **JSON Support**: Native JSONB type for flexible data storage
8. **Full-Text Search**: Built-in FTS capabilities if needed

### Negative

1. **Increased Complexity**: Additional container to manage
2. **Resource Usage**: PostgreSQL uses more memory than SQLite
3. **Development Setup**: Developers need to run `docker-compose up` or have local Postgres
4. **Migration Effort**: Existing SQLite databases need migration path
5. **Learning Curve**: PostgreSQL administration knowledge helpful

### Neutral

1. **SQLAlchemy Abstraction**: Most code unchanged due to ORM usage
2. **Testing**: Can continue using SQLite for fast unit tests
3. **CI/CD**: May need PostgreSQL service in CI pipeline

## Implementation Plan

### Phase 1: Infrastructure (Issue #27)
- Add PostgreSQL service to `compose.yaml`
- Configure healthcheck and volumes
- Set up environment variables

### Phase 2: Application Support (Issues #28-30)
- Update `db.py` to parse `DATABASE_URL`
- Add `psycopg2-binary` to requirements
- Ensure SQLAlchemy models work with both databases

### Phase 3: Migration Tooling (Issue #31)
- Add Alembic for schema migrations
- Create migration scripts for schema changes
- Document migration process

### Phase 4: Validation (Issue #32)
- Test full application with PostgreSQL backend
- Performance comparison with SQLite
- Document any behavioral differences

## Migration Path for Existing Users

For users with existing SQLite databases:

1. **Export**: Provide script to export data from SQLite
2. **Import**: Script to import data into PostgreSQL
3. **Verification**: Validate data integrity post-migration
4. **Documentation**: Step-by-step migration guide

## References

- [PostgreSQL 16 Release Notes](https://www.postgresql.org/docs/16/release-16.html)
- [SQLAlchemy PostgreSQL Dialect](https://docs.sqlalchemy.org/en/20/dialects/postgresql.html)
- [Docker PostgreSQL Image](https://hub.docker.com/_/postgres)
- [12-Factor App: Backing Services](https://12factor.net/backing-services)


# ADR 0009: Secrets Management Strategy

## Status

**Accepted**

## Date

2026-01-05

## Context

With the migration to PostgreSQL (ADR 0007), NewsBrief needs to manage database credentials securely. This pattern will extend to other secrets like API keys, OAuth tokens, and encryption keys.

The challenge is balancing:
- **Security**: Credentials should not be in version control
- **Developer Experience**: Local development should be simple
- **Production Readiness**: Production deployments need proper secrets management

## Options Considered

### Option A: No Default (Require Environment Variable)

```yaml
environment:
  POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required}
```

| Pros | Cons |
|------|------|
| No secrets in any file | Developers must set env var every time |
| Forces explicit configuration | Poor DX for quick local testing |
| Clear error if not set | |

### Option B: Environment File (.env) ✅ SELECTED

```yaml
# compose.yaml
environment:
  POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
```

```bash
# .env (gitignored)
POSTGRES_PASSWORD=your_secure_password
```

| Pros | Cons |
|------|------|
| Secrets not in committed files | Requires .env file creation |
| Standard Docker pattern | Secrets in plaintext on disk |
| Good balance of security/DX | Not suitable for production |
| Easy to document | |

### Option C: Base64 Encoded Default

```yaml
environment:
  POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-bmV3c2JyaWVmX2Rldg==}
```

| Pros | Cons |
|------|------|
| Not immediately readable | Easily decoded (not encryption) |
| Works without setup | False sense of security |
| | Secrets still in version control |

### Option D: Docker Secrets

```yaml
secrets:
  db_password:
    file: ./secrets/db_password.txt
services:
  db:
    secrets:
      - db_password
```

| Pros | Cons |
|------|------|
| Production-grade approach | More complex setup |
| Secrets mounted as files | Requires Swarm mode for some features |
| Industry best practice | Overkill for local development |

### Option E: External Secrets Manager (Vault, AWS Secrets Manager)

| Pros | Cons |
|------|------|
| Enterprise-grade security | Significant infrastructure overhead |
| Rotation, auditing, access control | External dependency |
| Centralized secrets management | Complex for self-hosted users |

## Decision

**Option B: Environment File (.env)** for the current release, with a plan to implement **Option D: Docker Secrets** in v0.7.4 (Security).

### Rationale

1. **Immediate Need**: We need a working solution for v0.7.1
2. **Security**: Secrets not committed to version control
3. **Developer Experience**: Simple `.env` file creation
4. **Standard Practice**: Docker Compose natively supports `.env`
5. **Clear Upgrade Path**: Docker Secrets is a natural evolution

## Implementation

### Files

```
newsbrief/
├── .env.example          # Template with placeholder values (committed)
├── .env                  # Actual secrets (gitignored)
├── .gitignore            # Includes .env
└── compose.yaml          # References ${VARIABLES}
```

### .env.example (committed)

```bash
# Copy to .env and fill in values
POSTGRES_PASSWORD=change_me_to_secure_password
# Future secrets:
# API_KEY=
# OAUTH_CLIENT_SECRET=
```

### .gitignore addition

```
# Secrets
.env
*.env.local
secrets/
```

## Consequences

### Positive

1. No secrets in version control
2. Simple setup for developers
3. Clear documentation pattern
4. Works with existing Docker tooling

### Negative

1. Secrets in plaintext on developer machines
2. No secret rotation mechanism
3. Not suitable for production without enhancement

### Mitigations

1. Document that production should use Docker Secrets or external manager
2. Create issue for v0.7.4 to implement proper secrets management
3. Add security checklist to deployment documentation

## Future Work

- **v0.7.4**: Implement Docker Secrets for production deployments
- **v1.0+**: Consider HashiCorp Vault integration for enterprise users

## References

- [Docker Compose Environment Variables](https://docs.docker.com/compose/environment-variables/)
- [Docker Secrets](https://docs.docker.com/engine/swarm/secrets/)
- [12-Factor App: Config](https://12factor.net/config)

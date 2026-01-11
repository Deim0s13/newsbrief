# ADR 0013: Podman Secrets for Production Credentials

## Status

Accepted

## Date

2026-01-11

## Context

ADR 0009 established `.env` files as an interim solution for secrets management. This ADR implements the upgrade to Podman Secrets for production deployments, as planned.

Current state:
- `.env` file contains `POSTGRES_PASSWORD` in plaintext
- Works for development but not production-grade
- No secret rotation mechanism

## Decision

Implement **Podman Secrets** for production and **improved `.env` workflow** for development:

| Environment | Secrets Method | Improvements |
|-------------|---------------|--------------|
| **Development** | `.env` file | Auto-generation, validation, stronger defaults |
| **Production** | Podman Secrets | Encrypted storage, no plaintext files |

### Why Podman Secrets?

1. **Native to our stack** - Already using Podman
2. **Simple** - Just `podman secret create` and reference in compose
3. **Secure** - Secrets stored encrypted, mounted as files in containers
4. **No external dependencies** - No Vault, no cloud services
5. **Stepping stone** - Easy migration to Kubernetes Secrets or SOPS later (v0.7.5)

## Alternatives Considered

| Option | Pros | Cons |
|--------|------|------|
| **Podman Secrets** ✅ | Native, simple, secure | Podman-specific |
| **SOPS** | GitOps-ready, encrypted in Git | No GitOps yet (planned v0.7.5) |
| **HashiCorp Vault** | Enterprise-grade | Heavy infrastructure |
| **Keep .env** | Simplest | Plaintext secrets |

## Implementation

### Secret Creation

```bash
# Create the secret (one-time setup)
# Note: Secret MUST be named "db_password" (podman-compose limitation)
echo "your_secure_password" | podman secret create db_password -

# Or from a file
podman secret create db_password ./secrets/db_password.txt
```

### Podman-Compose Limitation

Podman-compose (as of v1.5.0) does not support custom `name` references for external secrets.
The secret name in `podman secret create` must match the key in the compose file exactly.
We use `db_password` as a simple, descriptive name.

### compose.yaml Updates

```yaml
services:
  db:
    image: postgres:16
    environment:
      POSTGRES_DB: newsbrief
      POSTGRES_USER: newsbrief
      POSTGRES_PASSWORD_FILE: /run/secrets/db_password
    secrets:
      - db_password

  api:
    # ... existing config ...
    environment:
      # Read password from secret file for DATABASE_URL construction
      DATABASE_URL: postgresql://newsbrief:${POSTGRES_PASSWORD:-newsbrief_dev}@db:5432/newsbrief
    secrets:
      - db_password

secrets:
  db_password:
    external: true
    name: newsbrief_db_password
```

### PostgreSQL Secret File Support

PostgreSQL supports `*_FILE` variants for all environment variables. When `POSTGRES_PASSWORD_FILE` is set, it reads the password from that file path.

### Application Changes

The API container needs to read the secret file to construct `DATABASE_URL`. Options:

1. **Entrypoint script** - Read secret file and export as env var
2. **Application code** - Read from `/run/secrets/db_password` if file exists
3. **Keep both** - Secret for DB container, env var for API (simpler)

For simplicity, we'll use option 3: PostgreSQL uses the secret file, API continues using `DATABASE_URL` from environment (which can be set from `.env` in dev or derived from secret in prod).

### Development: Improved .env Workflow

#### Auto-generation with `make env-init`

```makefile
env-init:
	@if [ -f .env ]; then \
		echo "⚠️  .env already exists. Delete it first or edit manually."; \
	else \
		cp .env.example .env && \
		PASSWORD=$$(openssl rand -base64 24 | tr -dc 'a-zA-Z0-9' | head -c 32) && \
		sed -i '' "s/POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD=$$PASSWORD/" .env && \
		echo "✅ Created .env with generated password"; \
		echo "📝 Edit .env to customize other settings"; \
	fi
```

#### Enhanced .env.example

```bash
# NewsBrief Environment Configuration
# Copy to .env: make env-init (auto-generates secure password)
# Or manually: cp .env.example .env

# =============================================================================
# DATABASE (Required for production, optional for dev - defaults to SQLite)
# =============================================================================
POSTGRES_PASSWORD=CHANGE_ME_GENERATE_SECURE_PASSWORD

# Full DATABASE_URL (constructed automatically if not set)
# DATABASE_URL=postgresql://newsbrief:${POSTGRES_PASSWORD}@db:5432/newsbrief

# =============================================================================
# LLM CONFIGURATION
# =============================================================================
# Ollama endpoint (default works for Docker Desktop)
OLLAMA_BASE_URL=http://host.docker.internal:11434
# For Podman on macOS: http://host.containers.internal:11434

# =============================================================================
# FUTURE SECRETS (uncomment when needed)
# =============================================================================
# API_KEY=
# OAUTH_CLIENT_SECRET=
```

#### Validation at Startup

The application will validate required environment variables and fail fast with helpful error messages if misconfigured.

### Production: Makefile Helpers

```makefile
# Secret management for production
secrets-create:
	@read -sp "Enter database password: " pwd && echo && \
	echo "$$pwd" | podman secret create db_password - && \
	echo "✅ Secret created: db_password"

secrets-list:
	podman secret ls

secrets-delete:
	podman secret rm db_password
```

## Migration Path

### New Development Setup

1. Clone repository
2. Run `make env-init` (generates `.env` with secure random password)
3. Run `make dev` (starts development server)

### New Production Setup

1. Create the secret: `make secrets-create` (prompts for password)
2. Run `make deploy`
3. (Optional) Keep `.env` for reference or delete it

### Existing Installations

1. Create secret from existing password: `make secrets-create`
2. Restart: `make deploy`
3. Containers will use secret instead of `.env`

### To SOPS/GitOps (Future v0.7.5)

1. Encrypt secrets with SOPS
2. Store in Git
3. ArgoCD decrypts during deployment
4. Podman Secrets still used in containers

## Consequences

### Positive

- Secrets encrypted at rest by Podman
- No plaintext passwords in files
- Standard container secrets pattern
- Easy rotation: delete and recreate secret

### Negative

- Extra setup step for new deployments
- Secrets not in Git (can't recreate environment from repo alone)
- Podman-specific (doesn't work with Docker without changes)

### Neutral

- Development still uses `.env` (acceptable trade-off)
- Future migration to SOPS will supersede this for GitOps

## Security Considerations

1. **Secret files are mode 0400** - Only container user can read
2. **In-memory tmpfs** - Secrets mounted in RAM, not on disk
3. **No secret in `podman inspect`** - Value hidden from inspection
4. **Rotation** - Delete and recreate secret, then restart containers

## Related

- ADR 0009: Secrets Management Strategy (superseded for production)
- Issue #136: Implement proper secrets management
- Future: v0.7.5 GitOps will introduce SOPS

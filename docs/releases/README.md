# Release History

Quick reference for all NewsBrief releases. For detailed release notes, see [GitHub Releases](https://github.com/Deim0s13/newsbrief/releases).

---

## v0.7.x - Infrastructure & Operations

### v0.7.5 - GitOps & Automation (Current)
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

PostgreSQL support via `DATABASE_URL`, dual database mode (SQLite dev, Postgres prod), SQLAlchemy ORM models, Alembic migrations.

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
- [Project Board](https://github.com/users/Deim0s13/projects/2) - Current status

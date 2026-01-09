# v0.7.3 Release Notes - Operations & Observability

**Release Date**: January 2026

## Overview

v0.7.3 enhances operational visibility with structured logging, Kubernetes-style health probes, and improved developer experience. This release resolves 3 milestone issues plus several bug fixes discovered during development.

## Key Changes

### 📊 Structured Logging (Issue #20)

#### JSON Logging for Production
- **Added**: `app/logging_config.py` with `JSONFormatter` and `DevFormatter`
- **Added**: `configure_logging()` function called at app startup
- **Added**: `@log_timing` decorator for instrumenting operations
- **Architecture**: Documented in [ADR-0011](../../adr/0011-structured-logging.md)

**Production (JSON format)**:
```json
{
  "timestamp": "2026-01-10T12:00:00Z",
  "level": "INFO",
  "logger": "app.feeds",
  "message": "Feed refresh completed",
  "duration_ms": 1234,
  "feeds_processed": 15,
  "articles_ingested": 42
}
```

**Development (human-readable)**:
```
2026-01-10 12:00:00 INFO     [app.feeds] Feed refresh completed (1234ms, 15 feeds, 42 articles)
```

#### Instrumented Operations
- Feed refresh: duration, feeds processed, articles ingested, errors
- Story generation: duration, stories created, clusters, timing breakdown
- LLM synthesis: duration, model, tokens used, method

### 🏥 Health Endpoints (Issue #19)

#### New Kubernetes-Style Probes
| Endpoint | Purpose | Returns |
|----------|---------|---------|
| `/healthz` | Liveness probe | `{"status": "ok"}` |
| `/readyz` | Readiness probe | Database connectivity check |
| `/ollamaz` | LLM status | Ollama availability + model list |

All endpoints return 503 on failure for container orchestration compatibility.

**Example `/ollamaz` response**:
```json
{
  "status": "healthy",
  "url": "http://localhost:11434",
  "default_model": "llama3.1:8b",
  "models_available": 3,
  "models": [...]
}
```

### 🎨 Feed Management UI (Issue #135)

#### Layout Fixes
- **Fixed**: Table columns were squished into one line
- **Added**: Fixed table layout with proper column widths
- **Added**: Minimum width constraints for feed name column
- **Removed**: `whitespace-nowrap` forcing content onto single lines
- **Rebuilt**: Tailwind CSS with new utility classes

### 🏷️ Dev/Prod Environment Separation

#### Visual Indicators
- **Added**: Orange "DEVELOPMENT MODE" banner in development
- **Added**: "DEV - " prefix in browser tab title
- **Changed**: Production UI remains clean (no banner)

#### Configuration
- **Added**: `ENVIRONMENT` variable in `compose.yaml` (production)
- **Added**: `make dev` command sets `ENVIRONMENT=development`
- **Changed**: Removed port 8787 mapping from production container
- **Result**: Production only accessible via `http://newsbrief.local`

### 🔧 Bug Fixes

#### Route Ordering (422 Errors)
- **Fixed**: `/feeds/categories` returning 422 "unable to parse string as integer"
- **Cause**: Route `/feeds/{feed_id}` was matching before specific routes
- **Solution**: Moved specific routes (`/feeds/categories`, `/feeds/export/opml`, etc.) before parameterized routes

## Files Changed

| Category | Files |
|----------|-------|
| **New Files** | `app/logging_config.py`, `docs/adr/0011-structured-logging.md` |
| **Modified** | `app/main.py`, `app/feeds.py`, `app/stories.py`, `app/llm.py` |
| **UI** | `app/templates/base.html`, `app/templates/feed_management.html` |
| **Config** | `compose.yaml`, `Makefile` |
| **CSS** | `app/static/css/output.css` |

## Breaking Changes

None. All changes are backward compatible.

## New Dependencies

None. Uses Python standard library `logging` module.

## Upgrade Instructions

1. **Pull latest code**:
   ```bash
   git pull origin main
   ```

2. **Rebuild production containers**:
   ```bash
   make deploy-stop
   make deploy
   ```

3. **For development**, use the new command:
   ```bash
   make dev  # Shows DEV banner, uses SQLite
   ```

4. **Verify health endpoints**:
   ```bash
   curl http://newsbrief.local/healthz
   curl http://newsbrief.local/readyz
   curl http://newsbrief.local/ollamaz
   ```

## Issues Resolved

| Issue | Title | Type |
|-------|-------|------|
| #20 | Structured logging | Feature |
| #19 | Health endpoints | Feature |
| #135 | Fix feed management page legibility | Bug |

## Contributors

- Development completed with AI pair programming assistance

## Next Steps

- **v0.7.4**: Security - HTTPS/TLS encryption
- **v0.7.5**: GitOps & Kubernetes
- **v0.8.0**: Ranking & Personalization

See [Project Board](https://github.com/users/Deim0s13/projects/2) for detailed roadmap.

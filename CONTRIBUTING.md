# Contributing to NewsBrief

Thank you for your interest in contributing to NewsBrief! This guide will help you get set up for development.

## Development Setup

### Prerequisites

- Python 3.11+
- [Ollama](https://ollama.com/) (for LLM features)
- Docker/Podman (for container testing)

### 1. Clone and Install

```bash
git clone https://github.com/Deim0s13/newsbrief.git
cd newsbrief

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Windows: run this inside WSL2, not PowerShell

# Install dependencies
pip install -r requirements.txt -r requirements-dev.txt
```

On Windows, development tooling (this venv, tests, migrations) runs in **WSL2** — production containers run natively under Podman Desktop for Windows and don't need WSL2 at runtime. See `CLAUDE.md` → "Platform Overview".

### 2. Set Up Pre-commit Hooks

**This is required** to ensure consistent code formatting and catch issues before they reach CI:

```bash
# Install pre-commit hooks
pre-commit install

# Verify installation
pre-commit run --all-files
```

The hooks will automatically:
- Format code with Black
- Sort imports with isort
- Validate Python syntax
- Check YAML/JSON files
- Trim trailing whitespace
- Lint Dockerfiles

### 3. Start Ollama

```bash
# Start the Ollama service (or use the native Ollama.app / Ollama.exe)
ollama serve

# Pull the default (balanced profile) model
ollama pull qwen2.5:14b
```

### 4. Run the Application

```bash
make env-init      # generate .env
make db-up         # start PostgreSQL (native pg_isready check on WSL2; container on macOS)
make migrate-dev    # apply migrations
make dev            # run uvicorn with reload

# Or in one step:
make dev-full       # db-up + wait + dev
```

`make run` builds and runs the **production container image** directly (Podman/Docker) — useful for a quick smoke test of a built image, not for day-to-day development.

## Code Style

We use the following tools for code quality:

| Tool | Purpose | Configuration |
|------|---------|---------------|
| Black | Code formatting | Line length: 88 |
| isort | Import sorting | Profile: black |
| mypy | Type checking | Strict optional disabled |
| flake8 | Linting | Default rules |

### Manual Formatting

If you need to format manually:

```bash
# Format code
black app/ tests/
isort --profile=black app/ tests/

# Check types
mypy app/ --ignore-missing-imports
```

## Testing

### Run Tests

```bash
# All tests
pytest tests/ -v

# With coverage
pytest tests/ --cov=app --cov-report=term

# Specific test file
pytest tests/test_stories.py -v

# Skip LLM-dependent tests (what CI runs)
pytest tests/ -v -m "not requires_llm_backend"
```

Non-LLM tests require a dev PostgreSQL database at `localhost:5433` (`make db-up`); DB-dependent tests skip automatically if `DATABASE_URL` isn't set.

### Test Categories

| Category | Requires LLM backend | Description |
|----------|-----------------------|-------------|
| Unit / mocked | No | Core logic, utilities — always safe |
| Integration tests | No | Real PostgreSQL (`DATABASE_URL`); skip automatically without it |
| LLM tests (`@pytest.mark.requires_llm_backend`) | Yes (Ollama or oMLX) | Story generation, synthesis; excluded from CI |

Coverage threshold in CI is 34% (`pytest tests/ --cov=app --cov-report=term`).

## Database

NewsBrief uses **PostgreSQL only** for application data (dev/prod parity — [ADR-0022](docs/adr/0022-dev-prod-database-parity.md)).

### Local PostgreSQL

```bash
# Start PostgreSQL (e.g. Podman; default port often 5433 — see Makefile)
make db-up

# Apply migrations (set DATABASE_URL if not using defaults from docs)
make migrate-dev
# Or: make migrate   # uses .venv and DATABASE_URL from your environment

# Connect with psql
make db-psql
```

Create new revisions with `make migrate-new MSG="describe change"` and commit the file under `alembic/versions/` with the code that depends on it.

### Kubernetes (Argo CD)

For cluster deploys, **do not rely on `make migrate` on the node**. Argo CD applies a **`Job`** named **`newsbrief-db-migrate`** that runs **`alembic upgrade head`** using the same image and config as the API, **before** the `Deployment` rolls (sync waves). See [docs/development/KUBERNETES.md](docs/development/KUBERNETES.md#sync-waves).

### After merge: don’t skip migrations

When a PR **adds or changes** files under `alembic/versions/`, every environment that receives the new app version must have **`alembic upgrade head`** applied against its database **before** that code serves traffic (or the first request that needs the new columns will fail).

- **GitOps / Argo:** Confirm the migrate `Job` succeeds on each sync (see [CI-CD.md](docs/development/CI-CD.md#database-migrations-alembic)).
- **Any manual or scripted deploy:** Run `make migrate` (or `alembic upgrade head` with the same `DATABASE_URL` and image) **per environment** as part of the promote checklist — the same way you verify config and health checks.

## Branching Strategy

Single-maintainer workflow: **work on `dev`**, **cut releases with a direct merge to `main`**. There's no PR gate or branch protection — see [BRANCHING_STRATEGY.md](docs/development/BRANCHING_STRATEGY.md) for the full rationale and release checklist.

| Branch | Purpose |
|--------|---------|
| `dev` | Day-to-day development; push here (directly, or via a short-lived `feature/*`/`fix/*` branch). GitHub Actions runs `.github/workflows/ci-dev.yml` automatically on push — no local trigger needed. |
| `main` | Production releases only — cut with `git merge dev --no-ff` when you ship (after bumping `pyproject.toml` version). Push triggers `.github/workflows/ci-prod.yml` automatically. |

CI runs entirely on GitHub Actions hosted runners — there's nothing to start locally, port-forward, or relay. Check pipeline status with:

```bash
gh run list --branch dev --limit 5
gh run list --branch main --limit 5
gh run view <run-id> --log-failed
```

## Pull Request Checklist

Before pushing to `dev` (or before opening a PR, if you use one for notes/review):

- [ ] Pre-commit hooks pass (`pre-commit run --all-files`)
- [ ] Tests pass (`pytest tests/ -v`)
- [ ] New code has tests (if applicable)
- [ ] **Schema changes:** new Alembic revision under `alembic/versions/` in the same PR (`make migrate-new MSG="…"`), or N/A
- [ ] **If schema changed:** rollout plan confirms **`alembic upgrade head`** (or Argo migrate Job) for **dev → staging → prod** (or your pipeline); see [Database → After merge](#after-merge-dont-skip-migrations)
- [ ] Documentation updated (if applicable)
- [ ] Commit messages are clear and descriptive

## Troubleshooting

### Pre-commit Fails on First Run

The first run may take longer as it sets up environments:

```bash
# Force reinstall
pre-commit clean
pre-commit install --install-hooks
```

### Black/isort Conflicts

If Black and isort produce different results:

```bash
# Run isort first, then black
isort --profile=black app/ tests/
black app/ tests/
```

### LLM Tests Failing

Ensure Ollama is running with the correct model:

```bash
# Check Ollama status
curl http://localhost:11434/api/tags

# Pull model if missing
ollama pull qwen2.5:14b
```

## Getting Help

- Open an issue for bugs or feature requests
- Check existing issues before creating new ones
- Include reproduction steps for bugs

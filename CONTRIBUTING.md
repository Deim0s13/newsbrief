# Contributing to NewsBrief

Thank you for your interest in contributing to NewsBrief! This guide will help you get set up for development.

## Development Setup

### Prerequisites

- Python 3.11+
- [Ollama](https://ollama.com/) (for LLM features)
- Docker/Podman (for container testing)

### 1. Clone and Install

```bash
git clone https://github.com/your-org/newsbrief.git
cd newsbrief

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt -r requirements-dev.txt
```

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
# Start the Ollama service
ollama serve

# Pull the default model
ollama pull llama3.1:8b
```

### 4. Run the Application

```bash
# Start development server
make run

# Or with Docker Compose
make dev
```

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

# Skip LLM-dependent tests
CI=true pytest tests/ -v
```

### Test Categories

| Category | Requires Ollama | Description |
|----------|-----------------|-------------|
| Unit tests | No | Core logic, utilities |
| Integration tests | No | Database, API endpoints |
| LLM tests | Yes | Story generation, synthesis |

LLM-dependent tests automatically skip when Ollama is not available.

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

Single-maintainer workflow: **work on `dev`**, **cut releases from `main`**.

| Branch | Purpose |
|--------|---------|
| `dev` | Day-to-day development; push here. Tekton `ci-dev` runs on **`push` to `dev`** (when the [webhook relay](docs/development/KUBERNETES.md) path is up). |
| `main` | Production releases only — merge or promote from `dev` when you ship. Tekton `ci-prod` runs on **`push` to `main`**. |

Long-lived `feature/*` / `fix/*` branches are optional; avoid them unless you truly need isolation, since they add merge overhead for a solo setup.

### Tekton `ci-dev` after you push (recommended)

Git has **no post-push hook**, and the **GitHub → Smee → laptop** path only runs `ci-dev` when **port-forward + smee-client** are up. For reliable checks before you later merge to `main`, use:

```bash
make push-dev
```

That **`git push origin dev`** and then starts **`ci-dev`** on your cluster (same workload as the webhook: clone `dev`, lint, pytest). Push only without the pipeline: `SKIP_CI_DEV=1 make push-dev`. To re-run CI without pushing: `make ci-dev`.

### GitHub webhook → Tekton (automatic `ci-dev` / `ci-prod`)

After a reboot or when pipelines stop firing on push, start the relay:

```bash
make webhook-relay-start   # background: kubectl port-forward + smee
make webhook-relay-status  # optional health check
```

Stop with `make webhook-relay-stop`. Logs: `logs/eventlistener-port-forward.log`, `logs/smee-client.log` (ignored by git). Configuration matches `tekton/triggers/smee-config.yaml`. **GitHub “Delivery: OK”** only means Smee received the POST; the EventListener still needs this relay and a **`github-webhook-secret`** that matches GitHub. Details: [KUBERNETES.md — Webhooks](docs/development/KUBERNETES.md).

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
ollama pull llama3.1:8b
```

## Getting Help

- Open an issue for bugs or feature requests
- Check existing issues before creating new ones
- Include reproduction steps for bugs

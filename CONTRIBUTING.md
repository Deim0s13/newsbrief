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

### SQLite (Development)

```bash
# Initialize database
make init-db
```

### PostgreSQL (Container)

```bash
# Start PostgreSQL container
make db-up

# Run migrations
make migrate

# Connect to psql
make db-psql
```

## Branching Strategy

| Branch | Purpose |
|--------|---------|
| `main` | Production releases |
| `dev` | Integration branch |
| `feature/*` | New features |
| `fix/*` | Bug fixes |

### Workflow

1. Create feature branch from `dev`
2. Make changes with pre-commit hooks active
3. Push and create PR to `dev`
4. After review, merge to `dev`
5. Periodically merge `dev` to `main` for releases

## Pull Request Checklist

Before submitting a PR:

- [ ] Pre-commit hooks pass (`pre-commit run --all-files`)
- [ ] Tests pass (`pytest tests/ -v`)
- [ ] New code has tests (if applicable)
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

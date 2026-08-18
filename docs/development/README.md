# Development Documentation

Documentation for developers contributing to NewsBrief.

## 🛠️ Contents

### [DEVELOPMENT.md](DEVELOPMENT.md)
Development environment setup and guidelines:
- Project structure
- Development workflow
- Coding standards
- Testing guidelines

### [CI-CD.md](CI-CD.md)
Continuous Integration and Deployment:
- GitHub Actions workflows (`ci-dev.yml`, `ci-prod.yml`)
- Dual-platform CD: ArgoCD (macOS) + Compose/GHCR polling (Windows)
- Testing automation, pre-commit hooks
- Migration strategy, security gates (Trivy, Cosign, SBOM)

### [KUBERNETES.md](KUBERNETES.md)
Local Kubernetes development setup (macOS only):
- kind cluster setup and recovery
- ArgoCD applications, sync waves
- Port-forward map, Kustomize overlay structure

### [BRANCHING_STRATEGY.md](BRANCHING_STRATEGY.md)
Git workflow and branching strategy:
- `dev` for day-to-day work, direct merge to `main` to release
- No required PRs or branch protection (solo-maintainer workflow, see rationale)
- Release checklist

## 🚀 Getting Started

```bash
# Clone and setup
git clone https://github.com/Deim0s13/newsbrief.git
cd newsbrief
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt -r requirements-dev.txt
npm install   # Tailwind CSS build tooling

# Setup pre-commit hooks
pre-commit install

# Start PostgreSQL + apply migrations + run dev server
make db-up
make migrate-dev
make dev
```

## 🧪 Testing

```bash
# All non-LLM tests (requires dev DB at localhost:5433 — make db-up)
pytest tests/ -v -m "not requires_ollama"

# With coverage
pytest tests/ --cov=app --cov-report=term

# Run specific tests
pytest tests/test_stories.py -v

# Type checking / linting
mypy app/ --ignore-missing-imports
flake8 app/ tests/
```

**Coverage threshold (CI)**: 34%

## 📚 Further Reading

- **User Guide**: [../user-guide/](../user-guide/)
- **Architecture Decisions**: [../adr/](../adr/)
- **Project Board**: [GitHub Projects](https://github.com/users/Deim0s13/projects/8)

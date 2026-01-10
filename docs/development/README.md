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
- GitHub Actions workflows
- Testing automation
- Pre-commit hooks

### [BRANCHING_STRATEGY.md](BRANCHING_STRATEGY.md)
Git workflow and branching strategy:
- Branch naming conventions
- Feature branch workflow
- Release process

### [GITHUB_PROJECT_BOARD_SETUP.md](GITHUB_PROJECT_BOARD_SETUP.md)
GitHub Project board configuration:
- Board structure and views
- Issue workflow
- Milestone tracking

## 🚀 Getting Started

```bash
# Clone and setup
git clone https://github.com/Deim0s13/newsbrief.git
cd newsbrief
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
npm install

# Setup pre-commit hooks
pip install pre-commit
pre-commit install

# Run development server
make dev

# Run tests
make test

# Run linters
make lint
```

## 🧪 Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=app --cov-report=html

# Run specific tests
pytest tests/test_story_crud.py -v

# Type checking
mypy app/ --ignore-missing-imports
```

**Current Coverage**: ~41% (192 tests)

## 📚 Further Reading

- **User Guide**: [../user-guide/](../user-guide/)
- **Architecture Decisions**: [../adr/](../adr/)
- **Project Board**: [GitHub Projects](https://github.com/users/Deim0s13/projects/2)

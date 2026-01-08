# Development Documentation

Documentation for developers contributing to NewsBrief.

## 🛠️ Contents

### [DEVELOPMENT.md](DEVELOPMENT.md)
Development environment setup and guidelines:
- Project structure
- Development workflow
- Coding standards
- Testing guidelines
- Debugging tips

### [CI-CD.md](CI-CD.md)
Continuous Integration and Deployment pipeline:
- GitHub Actions workflows
- Testing automation
- Build and deployment process
- Environment configurations

### [BRANCHING_STRATEGY.md](BRANCHING_STRATEGY.md)
Git workflow and branching strategy:
- Branch naming conventions
- Feature branch workflow
- Release process
- Hotfix procedures

### [TECHNICAL_DEBT_v0.6.0.md](TECHNICAL_DEBT_v0.6.0.md)
Known technical debt items for v0.6.0:
- Code quality improvements needed
- Refactoring opportunities
- Performance optimizations
- Security enhancements

## 🚀 Getting Started

```bash
# Clone the repository
git clone https://github.com/Deim0s13/newsbrief.git
cd newsbrief

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Install development dependencies
pip install pytest pytest-asyncio pytest-cov black isort mypy

# Run tests
pytest

# Run linters
black --check app/
isort --check-only app/
mypy app/ --ignore-missing-imports
```

See [DEVELOPMENT.md](DEVELOPMENT.md) for detailed development setup.

## 📚 Further Reading

- **User Guide**: See [../user-guide/](../user-guide/)
- **Project Management**: See [../project-management/](../project-management/)
- **Architecture Decisions**: See [../adr/](../adr/)

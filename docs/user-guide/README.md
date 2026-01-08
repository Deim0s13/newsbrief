# User Guide

Documentation for NewsBrief users.

## 📖 Contents

### [API.md](API.md)
Complete API reference including:
- Story endpoints (`/api/stories`, `/api/stories/{id}`)
- Article endpoints (`/api/items`)
- Feed management (`/api/feeds`)
- Scheduler status (`/scheduler/status`)

### [QUICK-START.md](QUICK-START.md)
Get up and running with NewsBrief:
- Installation instructions
- Configuration options
- Running the application
- Basic usage

### [MIGRATION_v0.5.0.md](MIGRATION_v0.5.0.md)
Migration guide for upgrading to v0.5.0:
- Breaking changes
- New features
- Configuration updates
- Database migrations

## 🚀 Quick Start

```bash
# Clone the repository
git clone https://github.com/Deim0s13/newsbrief.git
cd newsbrief

# Install dependencies
pip install -r requirements.txt

# Run the application
uvicorn app.main:app --reload
```

See [QUICK-START.md](QUICK-START.md) for detailed instructions.

## 📚 Further Reading

- **Development**: See [../development/](../development/)
- **API Reference**: See [API.md](API.md)
- **Latest Release**: See [../releases/v0.5.5/](../releases/v0.5.5/)

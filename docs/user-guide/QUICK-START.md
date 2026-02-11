# Quick Start Guide

> **⚡ Get NewsBrief running in 5 minutes**

---

## 🚀 Option 1: Production Deployment (Recommended)

Deploy the full stack with PostgreSQL, Caddy reverse proxy, and auto-start:

```bash
# Clone and configure
git clone https://github.com/Deim0s13/newsbrief.git
cd newsbrief
make env-init                     # Generate .env with secure password

# Add newsbrief.local to hosts file
make hostname-setup               # Or manually: echo "127.0.0.1 newsbrief.local" | sudo tee -a /etc/hosts

# Start production stack
make deploy

# Initialize database (first time only)
make deploy-init

# Access at https://newsbrief.local
```

### Enhanced Security with Podman Secrets

For production deployments, use encrypted secrets instead of `.env`:

```bash
make secrets-create               # Prompts for password, stores encrypted
make deploy                       # Automatically uses secrets
```

### Production Commands

| Command | Description |
|---------|-------------|
| `make deploy` | Start all containers |
| `make deploy-stop` | Stop all containers |
| `make deploy-status` | Check container status |
| `make deploy-logs` | View container logs |
| `make db-backup` | Backup database |
| `make db-restore` | Restore database |
| `make secrets-create` | Create encrypted secret |
| `make secrets-list` | List secrets |

---

## 🛠️ Option 2: Development Setup

Run locally with PostgreSQL for development (requires Docker/Podman):

```bash
# Clone repository
git clone https://github.com/Deim0s13/newsbrief.git
cd newsbrief

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
npm install

# Setup pre-commit hooks
pip install pre-commit
pre-commit install

# Start PostgreSQL + dev server together
make dev-full

# OR start separately:
make db-up      # Start PostgreSQL container
make dev        # Start dev server

# Access at http://localhost:8787 (shows DEV banner)
```

> **Note**: As of v0.7.8, development uses PostgreSQL for dev/prod parity (ADR-0022).

### Development Commands

| Command | Description |
|---------|-------------|
| `make dev-full` | Start PostgreSQL + dev server |
| `make db-up` | Start PostgreSQL container |
| `make dev` | Start dev server (requires DB running) |
| `make refresh` | Refresh all feeds (fetch new articles) |
| `make stories-generate` | Generate stories from recent articles |
| `make api-health` | Check API health status |
| `make test` | Run test suite |
| `make lint` | Run linters |
| `npm run build:css` | Rebuild Tailwind CSS |

---

## 🎯 First Steps

### Add Some Feeds

```bash
# Via API
curl -X POST "https://newsbrief.local/feeds?url=https://hnrss.org/frontpage"
curl -X POST "https://newsbrief.local/feeds?url=https://feeds.arstechnica.com/arstechnica/technology-lab"

# Refresh feeds and generate stories
curl -X POST "https://newsbrief.local/refresh"
curl -X POST "https://newsbrief.local/stories/generate"

# Or use make shortcuts (development only)
make refresh
make stories-generate
```

### Set Up Ollama (for AI Features)

```bash
# Install Ollama
curl -fsSL https://ollama.ai/install.sh | sh

# Pull the balanced model (recommended)
ollama pull qwen2.5:14b

# Verify connection
curl https://newsbrief.local/ollamaz
```

---

## 🤖 Model Configuration ⭐ *New in v0.8.1*

NewsBrief supports three model profiles optimized for different use cases:

| Profile | Model | Speed | Quality | Best For |
|---------|-------|-------|---------|----------|
| **Fast** | Mistral 7B | ~50 tok/s | Good | Testing, quick refreshes |
| **Balanced** | Qwen 2.5 14B | ~25-35 tok/s | Very Good | **Daily use (default)** |
| **Quality** | Qwen 2.5 32B | ~15-20 tok/s | Excellent | Important stories |

### Change Model Profile

**Via Admin UI (Recommended)**

Navigate to `/admin/models` to see profile cards with quality indicators and switch with one click.

**Via API**

```bash
# Check current profile
curl https://newsbrief.local/api/models/profiles/active | jq .

# Switch to quality profile
curl -X PUT "https://newsbrief.local/api/models/profiles/active?profile_id=quality"

# Switch to fast profile (for testing)
curl -X PUT "https://newsbrief.local/api/models/profiles/active?profile_id=fast"

# Switch back to balanced (default)
curl -X PUT "https://newsbrief.local/api/models/profiles/active?profile_id=balanced"
```

### Pre-Download Models

Models are automatically downloaded when first used, but you can pre-download them:

```bash
# Balanced profile (default) - ~8GB
ollama pull qwen2.5:14b

# Quality profile - ~18GB
ollama pull qwen2.5:32b

# Fast profile - ~4GB
ollama pull mistral:7b
```

### When to Use Each Profile

- **Fast**: Development, testing, quick iterations. Lower quality but 2-3x faster.
- **Balanced**: Daily scheduled generation. Best trade-off for regular use.
- **Quality**: Use *selectively* for important stories or weekly summaries. Not recommended for full batch generation due to time.

> **Tip**: The Quality profile takes 2-3 minutes per story. Use it for your top 3-5 stories rather than the entire batch.

---

## 🏥 Health Checks

```bash
# Full health status
curl https://newsbrief.local/health | jq .

# Liveness probe (container alive)
curl https://newsbrief.local/healthz

# Readiness probe (database connected)
curl https://newsbrief.local/readyz

# LLM status
curl https://newsbrief.local/ollamaz | jq .
```

---

## 🐛 Troubleshooting

### Container Issues

```bash
# Check container status
make deploy-status

# View logs
make deploy-logs

# Restart containers
make deploy-stop && make deploy
```

### Database Issues

```bash
# Reset production database (CAUTION: data loss)
make deploy-stop
podman volume rm newsbrief_postgres_data
make deploy && make deploy-init
```

### Port Already in Use

```bash
# Find process using port 8787
lsof -i :8787

# Use different port for development
uvicorn app.main:app --reload --port 8788
```

### newsbrief.local Not Resolving

```bash
# Verify hosts file entry
grep newsbrief /etc/hosts

# Should show:
# 127.0.0.1 newsbrief.local

# If missing, add it:
echo "127.0.0.1 newsbrief.local" | sudo tee -a /etc/hosts
```

---

## 📚 Next Steps

- **API Reference**: [API.md](API.md)
- **Development Guide**: [../development/](../development/)
- **Architecture**: [../adr/](../adr/)

---

**🎉 You're ready to use NewsBrief!**

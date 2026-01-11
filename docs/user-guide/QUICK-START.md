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

Run locally with SQLite for development:

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

# Run development server
make dev

# Access at http://localhost:8787 (shows DEV banner)
```

### Development Commands

| Command | Description |
|---------|-------------|
| `make dev` | Start dev server with hot reload |
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

# Refresh feeds
curl -X POST "https://newsbrief.local/refresh"

# Generate stories
curl -X POST "https://newsbrief.local/stories/generate"
```

### Set Up Ollama (for AI Features)

```bash
# Install Ollama
curl -fsSL https://ollama.ai/install.sh | sh

# Pull recommended model
ollama pull llama3.1:8b

# Verify connection
curl https://newsbrief.local/ollamaz
```

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

# User Guide

Documentation for NewsBrief users.

## 📖 Contents

### [QUICK-START.md](QUICK-START.md)
Get up and running with NewsBrief:
- Production deployment with Podman/Docker
- Development setup with local Python
- First steps: adding feeds, generating stories
- **Model configuration profiles** (Fast/Balanced/Quality)
- Health checks and troubleshooting

### [API.md](API.md)
Complete API reference including:
- Story endpoints (`/stories`, `/stories/{id}`, `/stories/generate`)
- Article endpoints (`/items`, `/items/{id}`)
- Feed management (`/feeds`, OPML import/export)
- **Model profiles** (`/api/models/profiles`, `/api/models`)
- Health probes (`/healthz`, `/readyz`, `/ollamaz`)
- Scheduler status (`/scheduler/status`)

### [MODEL-PROFILES.md](MODEL-PROFILES.md)
LLM model configuration guide:
- **Fast** (mistral:7b) - Quick testing, batch processing
- **Balanced** (qwen2.5:14b) - Daily use, recommended default
- **Quality** (qwen2.5:32b) - Deep analysis, important stories
- Output characteristics and hardware requirements
- Switching profiles via UI and API

## 🚀 Quick Start

**Production** (recommended):
```bash
git clone https://github.com/Deim0s13/newsbrief.git
cd newsbrief
cp .env.example .env
echo "127.0.0.1 newsbrief.local" | sudo tee -a /etc/hosts
make deploy && make deploy-init
# Access at https://newsbrief.local
```

**Development**:
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
make dev
# Access at http://localhost:8787 (shows DEV banner)
```

See [QUICK-START.md](QUICK-START.md) for detailed instructions.

## 📚 Further Reading

- **Development Guide**: [../development/](../development/)
- **Architecture Decisions**: [../adr/](../adr/)
- **Release History**: [../releases/](../releases/)

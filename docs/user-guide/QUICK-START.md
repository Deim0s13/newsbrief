# Quick Start Guide

> **⚡ Get NewsBrief running locally in 5 minutes**

## 🚀 Option 1: Container (Recommended)

```bash
# Clone and run
git clone https://github.com/Deim0s13/newsbrief.git
cd newsbrief
podman-compose up -d  # or docker-compose up -d

# Access at http://localhost:8787
```

## 🛠️ Option 2: Development Setup

### **Prerequisites**
- Python 3.11+
- Git
- (Optional) Podman or Docker

### **Setup**
```bash
# 1. Clone repository
git clone https://github.com/Deim0s13/newsbrief.git
cd newsbrief

# 2. Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# .venv\Scripts\activate   # Windows

# 3. Install dependencies
pip install -r requirements.txt -r requirements-dev.txt

# 4. Set up development tools (IMPORTANT!)
pip install pre-commit
pre-commit install

# 5. Initialize database
python -c "from app.db import init_db; init_db()"

# 6. Run locally
uvicorn app.main:app --reload --port 8787
```

### **Verify Setup**
```bash
# Check API
curl http://localhost:8787/

# Check pre-commit hooks
pre-commit run --all-files

# Import some feeds
curl -X POST "http://localhost:8787/feeds" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://feeds.feedburner.com/oreilly/radar"}'
```

## 🎯 First Steps

### **Add Some Feeds**
```bash
# Tech news
curl -X POST "http://localhost:8787/feeds" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://feeds.feedburner.com/oreilly/radar"}'

curl -X POST "http://localhost:8787/feeds" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://hnrss.org/frontpage"}'

# Refresh feeds
curl -X POST "http://localhost:8787/refresh"

# View articles
curl "http://localhost:8787/items?limit=10"
```

### **Set Up AI Summarization (Optional)**
```bash
# Install Ollama
curl -fsSL https://ollama.ai/install.sh | sh

# Pull a model
ollama pull llama3.1:8b

# Set environment variable
export OLLAMA_BASE_URL=http://localhost:11434

# Test AI summaries
curl -X POST "http://localhost:8787/summarize" \
  -H "Content-Type: application/json" \
  -d '{"item_ids": [1, 2], "model": "llama3.1:8b"}'
```

## 📚 Next Steps

- **API Documentation**: [`docs/API.md`](API.md)
- **Development Guide**: [`docs/DEVELOPMENT.md`](DEVELOPMENT.md)  
- **CI/CD Pipeline**: [`docs/CI-CD.md`](CI-CD.md)
- **Architecture**: [`docs/adr/0001-architecture.md`](adr/0001-architecture.md)

## 🐛 Troubleshooting

### **Common Issues**

**Port already in use:**
```bash
# Find process using port 8787
lsof -i :8787
# Kill process or use different port
uvicorn app.main:app --reload --port 8788
```

**Permission denied (pre-commit):**
```bash
# Fix pre-commit permissions
pre-commit clean
pre-commit install --install-hooks
```

**Module not found:**
```bash
# Ensure virtual environment is activated
source .venv/bin/activate
# Reinstall dependencies
pip install -r requirements.txt
```

**Database errors:**
```bash
# Reset database
rm -f data/newsbrief.sqlite3
python -c "from app.db import init_db; init_db()"
```

## 💡 Development Tips

### **Workflow**
1. Create feature branch: `git checkout -b feature/my-feature`
2. Make changes (pre-commit hooks run automatically)
3. Push branch (triggers CI/CD pipeline)
4. Create pull request

### **Quality Tools**
```bash
# Format code
black app/ && isort app/

# Type checking  
mypy app/ --ignore-missing-imports

# Security scan
bandit -r app/
safety check -r requirements.txt
```

### **Container Development**
```bash
# Build and test locally
make build
make run

# Tagged release
make local-release VERSION=v0.4.0
```

---

**🎉 You're ready to contribute to NewsBrief!**

For questions, check the docs or open an issue on GitHub.

# Development Guide

This guide covers setting up your development environment, running tests, debugging, and contributing to NewsBrief.

## 🛠️ Development Setup

### **Prerequisites**

- **Python 3.11+**: Modern Python with excellent async support
- **Podman or Docker**: Container runtime for local development
- **Make**: Build automation (optional but recommended)
- **Git**: Version control
- **jq**: JSON processing for API testing (optional)

### **Initial Setup**

```bash
# Clone the repository
git clone https://github.com/Deim0s13/newsbrief.git
cd newsbrief

# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install development dependencies
pip install -U pip
pip install -r requirements.txt
```

### **Verify Installation**

```bash
# Test Python syntax
python3 -m py_compile app/*.py

# Start development server
uvicorn app.main:app --reload --port 8787

# Test API (in another terminal)
curl http://localhost:8787/docs  # Should return OpenAPI docs
```

## 🏃 Running NewsBrief

### **Development Server**

```bash
# Method 1: Direct Python
uvicorn app.main:app --reload --port 8787

# Method 2: Make shortcut (recommended)
make dev

# Method 3: Production containers
make deploy        # Start PostgreSQL + API + Caddy
make deploy-init   # Initialize database (first time)
# Access at http://newsbrief.local
```

### **Development vs Production** ⭐ *v0.7.x*

NewsBrief supports separate development and production environments:

| Aspect | Development | Production |
|--------|-------------|------------|
| **URL** | `http://localhost:8787` | `http://newsbrief.local` |
| **Database** | SQLite (`data/newsbrief.sqlite3`) | PostgreSQL (container) |
| **Command** | `make dev` | `make deploy` |
| **Visual** | Orange DEV banner + tab prefix | Clean UI |
| **Logging** | Human-readable | JSON structured |
| **Container** | None (local Python) | Podman Compose |

**Development mode** shows a visible DEV banner and "DEV -" prefix in the browser tab to clearly distinguish from production.

```bash
# Development (local Python, SQLite)
make dev
# → Shows DEV banner at http://localhost:8787

# Production (containers, PostgreSQL)
make deploy
make deploy-init  # First time only
# → Clean UI at http://newsbrief.local
```

See [ADR-0007](../adr/0007-postgresql-database-migration.md) for database architecture details.

### **Environment Variables**

NewsBrief supports several environment variables for configuration:

#### **Core Configuration**
```bash
# LLM Integration: Ollama service for AI summarization
export OLLAMA_BASE_URL=http://localhost:11434
export NEWSBRIEF_LLM_MODEL=llama3.1:8b

# Optional: Custom data directory
export DATA_DIR=/path/to/your/data
```

#### **Scheduler Configuration** ⭐ *New in v0.6.3*
```bash
# Feed Refresh (automatic before story generation)
export FEED_REFRESH_ENABLED=true           # Enable/disable scheduled refresh
export FEED_REFRESH_SCHEDULE="30 5 * * *"  # Cron: 5:30 AM daily

# Story Generation
export STORY_GENERATION_SCHEDULE="0 6 * * *"  # Cron: 6:00 AM daily
export STORY_GENERATION_TIMEZONE="Pacific/Auckland"

# Story Configuration
export STORY_ARCHIVE_DAYS=7           # Archive stories older than 7 days
export STORY_TIME_WINDOW_HOURS=24     # Generate from last 24 hours
export STORY_MIN_ARTICLES=2           # Minimum articles per story
export STORY_MODEL=llama3.1:8b        # LLM model for synthesis
```

#### **Interest-Based Ranking** ⭐ *New in v0.6.5*

Configure topic preferences for personalized story ranking in `data/interests.json`:

```json
{
  "enabled": true,
  "blend": {
    "importance_weight": 0.6,
    "interest_weight": 0.4
  },
  "topic_weights": {
    "ai-ml": 1.5,        // Boost AI/ML stories 50%
    "security": 1.2,     // Boost security 20%
    "politics": 0.5,     // Demote politics 50%
    "sports": 0.3        // Demote sports 70%
  },
  "default_weight": 1.0
}
```

**How it works:**
- Stories are ranked by blended score: `(importance × 0.6) + (interest × 0.4)`
- Higher `topic_weights` boost stories, lower weights demote them
- Weight of `0` demotes to bottom (doesn't hide)
- Toggle in UI or via API: `?apply_interests=false`

See [ADR 0005](../adr/0005-interest-based-ranking.md) for full details.

#### **Source Quality Weighting** ⭐ *New in v0.6.5*

Configure source reputation weights in `data/source_weights.json`:

```json
{
  "enabled": true,
  "blend_weight": 0.2,
  "feed_weights": {
    "Hacker News": 1.5,
    "Ars Technica": 1.3,
    "TechCrunch": 1.2
  },
  "domain_weights": {
    "news.ycombinator.com": 1.5,
    "arstechnica.com": 1.3
  },
  "default_weight": 1.0
}
```

**How it works:**
- Stories ranked by: `(importance × 0.5) + (interest × 0.3) + (source × 0.2)`
- Matches by feed name first, then domain fallback
- Higher weights boost stories from reputable sources

See [ADR 0006](../adr/0006-source-quality-weighting.md) for full details.

#### **Fetch Limits & Performance** ⭐ *New in v0.2.4*
```bash
# Global item limit per refresh (default: 150)
export NEWSBRIEF_MAX_ITEMS_PER_REFRESH=200

# Per-feed fairness limit (default: 50)
export NEWSBRIEF_MAX_ITEMS_PER_FEED=25

# Time-based safety cap in seconds (default: 300 = 5 minutes)
export NEWSBRIEF_MAX_REFRESH_TIME=600

# Example: Production configuration for high-volume feeds
export NEWSBRIEF_MAX_ITEMS_PER_REFRESH=500
export NEWSBRIEF_MAX_ITEMS_PER_FEED=100
export NEWSBRIEF_MAX_REFRESH_TIME=900  # 15 minutes
```

#### **AI Summarization (LLM) Configuration** ⭐ *New in v0.3.0*

NewsBrief includes integrated AI summarization using local LLM services via Ollama:

```bash
# LLM Service Configuration
export OLLAMA_BASE_URL=http://localhost:11434  # Ollama service URL
export NEWSBRIEF_LLM_MODEL=llama3.1:8b        # Default model for summarization

# Production LLM settings
export OLLAMA_BASE_URL=http://ollama-service:11434  # Internal service
export NEWSBRIEF_LLM_MODEL=mistral:7b              # Larger model for better quality
```

**LLM Setup Requirements:**

1. **Install Ollama** (if running locally):
   ```bash
   # macOS
   brew install ollama

   # Start Ollama service
   ollama serve

   # Pull recommended models
   ollama pull llama3.1:8b    # Recommended for accuracy
   ollama pull mistral:7b     # Better quality, slower
   ```

2. **Container Integration:**
   ```bash
   # Connect NewsBreif container to local Ollama
   podman run --rm -d \
     -p 8787:8787 \
     -v ./data:/app/data \
     -e OLLAMA_BASE_URL=http://host.containers.internal:11434 \
     -e NEWSBRIEF_LLM_MODEL=llama3.1:8b \
     --name newsbrief newsbrief-api:latest
   ```

3. **Verify LLM Integration:**
   ```bash
   # Check LLM service status
   curl http://localhost:8787/llm/status | jq .

   # Generate test summary
   curl -X POST http://localhost:8787/summarize \
     -H "Content-Type: application/json" \
     -d '{"item_ids": [1]}'
   ```

**Model Recommendations:**
- **Development**: `llama3.1:8b` - Good balance of speed and accuracy
- **Production**: `mistral:7b` - Higher quality, more detailed summaries
- **High-volume**: `llama3.2:1b` - Fastest inference for large-scale processing

#### **Long Article Processing (Map-Reduce)** ⭐ *New in v0.3.2*

NewsBrief automatically handles long articles that exceed typical LLM context windows using intelligent chunking and map-reduce summarization:

```bash
# Map-Reduce Processing Configuration
export NEWSBRIEF_CHUNKING_THRESHOLD=3000    # Token threshold to trigger chunking (default: 3000)
export NEWSBRIEF_CHUNK_SIZE=1500            # Target chunk size in tokens (default: 1500)
export NEWSBRIEF_MAX_CHUNK_SIZE=2000        # Maximum chunk size limit (default: 2000)
export NEWSBRIEF_CHUNK_OVERLAP=200          # Overlap between chunks for context (default: 200)

# Advanced chunking configuration for different content types
export NEWSBRIEF_CHUNKING_THRESHOLD=2500    # Lower threshold for academic papers
export NEWSBRIEF_CHUNK_SIZE=1800            # Larger chunks for technical content
export NEWSBRIEF_MAX_CHUNK_SIZE=2200        # Higher max for dense content
export NEWSBRIEF_CHUNK_OVERLAP=300          # More overlap for complex articles
```

**Processing Method Selection:**
- **Direct Processing**: Articles under `NEWSBRIEF_CHUNKING_THRESHOLD` tokens
- **Map-Reduce Processing**: Articles exceeding the threshold are automatically chunked
- **Intelligent Chunking**: Respects paragraph and sentence boundaries for coherent analysis
- **Enhanced Metadata**: All responses include processing method, chunk count, and token information

**Chunking Strategy:**
1. **Hierarchical Splitting**: Paragraphs → Sentences → Words (preserves context)
2. **Boundary Respect**: Never splits mid-sentence or mid-paragraph when possible
3. **Context Preservation**: First chunk includes article title and context
4. **Overlap Management**: Configurable overlap prevents information loss at chunk boundaries

#### **Container Configuration Examples**
```bash
# Development: Fast refresh with low limits + AI summarization + map-reduce
podman run --rm -d \
  -p 8787:8787 \
  -v ./data:/app/data \
  -e NEWSBRIEF_MAX_ITEMS_PER_REFRESH=50 \
  -e NEWSBRIEF_MAX_ITEMS_PER_FEED=10 \
  -e NEWSBRIEF_MAX_REFRESH_TIME=120 \
  -e OLLAMA_BASE_URL=http://host.containers.internal:11434 \
  -e NEWSBRIEF_LLM_MODEL=llama3.1:8b \
  -e NEWSBRIEF_CHUNKING_THRESHOLD=2000 \
  -e NEWSBRIEF_CHUNK_SIZE=1200 \
  --name newsbrief newsbrief-api:v0.3.3

# Production: High-capacity configuration + Advanced LLM + Optimized chunking
podman run --rm -d \
  -p 8787:8787 \
  -v ./data:/app/data \
  -e NEWSBRIEF_MAX_ITEMS_PER_REFRESH=1000 \
  -e NEWSBRIEF_MAX_ITEMS_PER_FEED=200 \
  -e NEWSBRIEF_MAX_REFRESH_TIME=1800 \
  -e OLLAMA_BASE_URL=http://ollama-service:11434 \
  -e NEWSBRIEF_LLM_MODEL=mistral:7b \
  -e NEWSBRIEF_CHUNKING_THRESHOLD=3500 \
  -e NEWSBRIEF_CHUNK_SIZE=1800 \
  -e NEWSBRIEF_MAX_CHUNK_SIZE=2200 \
  --name newsbrief newsbrief-api:v0.4.0
```

#### **Article Ranking & Topic Classification** ⭐ *New in v0.4.0*

NewsBrief now includes intelligent article ranking and topic classification to improve content discovery:

```bash
# Ranking Algorithm Configuration (currently hardcoded weights)
# These values are defined in app/ranking.py and may become configurable in future versions

# Current ranking formula:
# final_score = (recency × 0.4) + (source_weight × 0.3) + (keywords × 0.3) × topic_multiplier

# Topic multipliers (defined in app/ranking.py):
# - AI/ML: 1.2x boost (hot topic)
# - Security: 1.15x boost (always important)
# - Cloud/K8s: 1.1x boost
# - Chips/Hardware: 1.1x boost
# - DevTools: 1.0x (baseline)
```

**Topic Categories:**

NewsBrief automatically classifies articles into these categories:

- **`ai-ml`**: AI/ML, machine learning, neural networks, LLM, GPT, transformers
- **`cloud-k8s`**: Cloud platforms (AWS, Azure, GCP), Kubernetes, containers, serverless
- **`security`**: Cybersecurity, vulnerabilities, crypto, blockchain, authentication
- **`devtools`**: Programming languages, frameworks, development tools, IDEs
- **`chips-hardware`**: Semiconductors, CPUs, GPUs, hardware manufacturing

**Container Configuration Examples:**

```bash
# Development: Standard ranking (v0.4.0+)
podman run --rm -d \
  -p 8787:8787 \
  -v ./data:/app/data \
  -e OLLAMA_BASE_URL=http://host.containers.internal:11434 \
  -e NEWSBRIEF_LLM_MODEL=llama3.1:8b \
  --name newsbrief newsbrief-api:v0.4.0

# Production: High-capacity + AI + Ranking (v0.4.0+)
podman run --rm -d \
  -p 8787:8787 \
  -v ./data:/app/data \
  -e NEWSBRIEF_MAX_ITEMS_PER_REFRESH=1000 \
  -e NEWSBRIEF_MAX_ITEMS_PER_FEED=200 \
  -e OLLAMA_BASE_URL=http://ollama-service:11434 \
  -e NEWSBRIEF_LLM_MODEL=mistral:7b \
  -e NEWSBRIEF_CHUNKING_THRESHOLD=3500 \
  -e NEWSBRIEF_CHUNK_SIZE=1800 \
  --name newsbrief newsbrief-api:v0.4.0
```

## 🏥 Health Endpoints ⭐ *v0.7.3*

NewsBrief provides Kubernetes-style health probes for container orchestration:

| Endpoint | Purpose | Response |
|----------|---------|----------|
| `/healthz` | Liveness probe | `{"status": "ok"}` - container alive |
| `/readyz` | Readiness probe | Database connectivity check |
| `/ollamaz` | LLM status | Ollama availability + models |
| `/health` | Full status | Database, LLM, scheduler status |

```bash
# Check if app is alive
curl http://localhost:8787/healthz

# Check if ready to serve (database connected)
curl http://localhost:8787/readyz

# Check LLM availability
curl http://localhost:8787/ollamaz | jq .

# Full health status
curl http://localhost:8787/health | jq .
```

**Logging** is environment-aware (see [ADR-0011](../adr/0011-structured-logging.md)):
- **Development**: Human-readable format with timestamps
- **Production**: Structured JSON for log aggregation

## 🧪 Testing & Debugging

### **Manual API Testing**

```bash
# Add test feeds
curl -X POST http://localhost:8787/feeds \
  -H "Content-Type: application/json" \
  -d '{"url": "https://feeds.bbci.co.uk/news/rss.xml"}'

curl -X POST http://localhost:8787/feeds \
  -H "Content-Type: application/json" \
  -d '{"url": "https://hnrss.org/frontpage"}'

# Fetch articles with enhanced statistics
curl -X POST http://localhost:8787/refresh | jq .

# View just the statistics summary
curl -X POST http://localhost:8787/refresh | jq .stats

# Monitor performance metrics
curl -X POST http://localhost:8787/refresh | jq '.stats.performance'

# Check per-feed fairness distribution
curl -X POST http://localhost:8787/refresh | jq '.stats.items.per_feed'

# List articles
curl "http://localhost:8787/items?limit=5" | jq .
```

#### **Enhanced Monitoring Examples** ⭐ *New in v0.2.4*

```bash
# Monitor refresh performance
watch -n 30 'curl -s -X POST http://localhost:8787/refresh | jq ".stats.performance"'

# Check if limits are being hit
curl -s -X POST http://localhost:8787/refresh | jq '
  if .stats.performance.hit_global_limit then
    "WARNING: Global limit reached"
  elif .stats.performance.hit_time_limit then
    "WARNING: Time limit reached"
  else
    "OK: Within limits"
  end'

# View fairness distribution
curl -s -X POST http://localhost:8787/refresh | jq '
  "Per-feed distribution:",
  (.stats.items.per_feed | to_entries[] | "\(.key): \(.value) items")'

# Configuration check
curl -s -X POST http://localhost:8787/refresh | jq '.stats.config'
```

#### **AI Summarization Testing** ⭐ *Updated in v0.3.3*

```bash
# Check LLM service status and available models
curl http://localhost:8787/llm/status | jq .

# Test structured JSON summarization (default behavior)
curl -X POST http://localhost:8787/summarize \
  -H "Content-Type: application/json" \
  -d '{"item_ids": [1,2,3]}'

# Extract structured components from response
curl -X POST http://localhost:8787/summarize \
  -H "Content-Type: application/json" \
  -d '{"item_ids": [1]}' | jq '.results[0].structured_summary | {bullets, why_it_matters, tags}'

# Test hash+model caching system (second request should be instant)
echo "First request (cache miss):"
time curl -s -X POST http://localhost:8787/summarize \
  -H "Content-Type: application/json" \
  -d '{"item_ids": [1]}' | jq '.results[0].cache_hit'

echo "Second request (cache hit):"
time curl -s -X POST http://localhost:8787/summarize \
  -H "Content-Type: application/json" \
  -d '{"item_ids": [1]}' | jq '.results[0].cache_hit'

# Generate summaries with specific model (cache miss due to model change)
curl -X POST http://localhost:8787/summarize \
  -H "Content-Type: application/json" \
  -d '{"item_ids": [1], "model": "mistral:7b"}'

# Legacy plain text summaries (backward compatibility)
curl -X POST http://localhost:8787/summarize \
  -H "Content-Type: application/json" \
  -d '{"item_ids": [1], "use_structured": false}'

# Force regenerate existing summaries
curl -X POST http://localhost:8787/summarize \
  -H "Content-Type: application/json" \
  -d '{"item_ids": [1], "force_regenerate": true}'

# View articles with structured summaries
curl "http://localhost:8787/items?limit=5" | jq '.[] | select(.structured_summary != null) | {id, title, bullets: .structured_summary.bullets, tags: .structured_summary.tags}'

# Get specific article with full structured details
curl http://localhost:8787/items/1 | jq '{id, title, original_summary: .summary, structured_summary}'

# Monitor performance and caching efficiency
curl -X POST http://localhost:8787/summarize \
  -H "Content-Type: application/json" \
  -d '{"item_ids": [1,2,3,4,5]}' | jq '.results[] | {item_id, cache_hit, tokens_used, generation_time}'

# Batch processing with structured output inspection
curl -X POST http://localhost:8787/summarize \
  -H "Content-Type: application/json" \
  -d '{"item_ids": [1,2,3]}' | jq '{summaries_generated, cache_hits: [.results[] | select(.cache_hit == true)] | length, bullet_counts: [.results[].structured_summary.bullets | length]}'

# ✨ Map-Reduce Testing (Long Article Processing) ⭐ *New in v0.3.2*

# Check processing method and chunking metadata
curl -X POST http://localhost:8787/summarize \
  -H "Content-Type: application/json" \
  -d '{"item_ids": [1], "force_regenerate": true}' | jq '.results[0].structured_summary | {processing_method, is_chunked, chunk_count, total_tokens}'

# Test chunking threshold by temporarily lowering it
# (Restart container with NEWSBRIEF_CHUNKING_THRESHOLD=500 to trigger chunking on normal articles)
curl -X POST http://localhost:8787/summarize \
  -H "Content-Type: application/json" \
  -d '{"item_ids": [1], "force_regenerate": true}' | jq '.results[0] | {
    item_id,
    success,
    processing_method: .structured_summary.processing_method,
    is_chunked: .structured_summary.is_chunked,
    chunks: .structured_summary.chunk_count,
    tokens: .structured_summary.total_tokens,
    generation_time
  }'

# Compare direct vs map-reduce processing performance
echo "=== Processing Method Comparison ==="
curl -s -X POST http://localhost:8787/summarize \
  -H "Content-Type: application/json" \
  -d '{"item_ids": [1,2,3], "force_regenerate": true}' | jq '.results[] | {
    id: .item_id,
    method: .structured_summary.processing_method,
    chunked: .structured_summary.is_chunked,
    chunks: .structured_summary.chunk_count // 1,
    tokens: .structured_summary.total_tokens,
    time: .generation_time
  }'

# Inspect chunking metadata across all summaries
curl -s "http://localhost:8787/items" | jq '[.[] | select(.structured_summary != null)] | group_by(.structured_summary.processing_method) | map({method: .[0].structured_summary.processing_method, count: length})'

# ✨ Fallback Summary Testing (Offline AI Handling) ⭐ *New in v0.3.3*

# Test fallback behavior when AI services are unavailable
# Note: This shows first 2 sentences of article content when no AI summary exists

# Check items with and without AI summaries
curl -s "http://localhost:8787/items?limit=5" | jq '.[] | {
  id,
  title,
  has_ai_summary: (.structured_summary != null or .ai_summary != null),
  has_fallback: .is_fallback_summary,
  fallback_preview: (.fallback_summary // "none")[0:80]
}'

# Test individual item fallback behavior
curl -s http://localhost:8787/items/1 | jq '{
  id,
  title,
  ai_available: (.structured_summary != null),
  fallback_used: .is_fallback_summary,
  fallback_content: .fallback_summary
}'

# Simulate AI service offline scenario
# (Stop Ollama service: pkill -f ollama)
# Then check if new items get fallback summaries automatically

# Test fallback summary extraction quality
curl -s "http://localhost:8787/items" | jq '[.[] | select(.is_fallback_summary == true)] | map({
  id,
  title,
  fallback_length: (.fallback_summary | length),
  fallback_preview: (.fallback_summary[0:100] + "...")
})'

# Monitor fallback vs AI summary distribution
curl -s "http://localhost:8787/items" | jq '{
  total_items: length,
  ai_summaries: [.[] | select(.structured_summary != null)] | length,
  fallback_summaries: [.[] | select(.is_fallback_summary == true)] | length,
  no_summary: [.[] | select(.structured_summary == null and .is_fallback_summary == false)] | length
}'

# ✨ Article Ranking & Topic Testing ⭐ *New in v0.4.0*

# View articles with ranking and topic data
curl -s "http://localhost:8787/items?limit=5" | jq '.[] | {
  id,
  title: .title[0:50],
  ranking_score,
  topic,
  topic_confidence,
  source_weight
}'

# Get available topic categories
curl -s http://localhost:8787/topics | jq .

# Browse articles by topic
curl -s "http://localhost:8787/items/topic/ai-ml?limit=3" | jq '.items[] | {
  id,
  title,
  ranking_score,
  topic_confidence
}'

# Compare ranking scores across topics
for topic in ai-ml cloud-k8s security devtools chips-hardware; do
  echo "=== $topic articles ==="
  curl -s "http://localhost:8787/items/topic/$topic?limit=3" | jq '.items[] | {
    title: .title[0:40],
    score: .ranking_score,
    confidence: .topic_confidence
  }'
  echo
done

# Analyze ranking distribution and topic classification
curl -s "http://localhost:8787/items?limit=20" | jq '{
  total_items: length,
  average_ranking: ([.[] | .ranking_score] | add / length),
  topic_distribution: (group_by(.topic) | map({topic: .[0].topic, count: length})),
  high_confidence_topics: [.[] | select(.topic_confidence > 0.8)] | length,
  unclassified: [.[] | select(.topic == null)] | length
}'

# Test ranking recalculation
curl -X POST http://localhost:8787/ranking/recalculate | jq .

# Monitor ranking changes after recalculation
curl -s "http://localhost:8787/items?limit=5" | jq '.[] | {
  id,
  title: .title[0:30],
  ranking_score,
  topic
}'

# Find highest-ranked articles per topic
for topic in ai-ml security cloud-k8s devtools chips-hardware; do
  top_article=$(curl -s "http://localhost:8787/items/topic/$topic?limit=1" | jq -r '.items[0] | "\(.title[0:40]) (score: \(.ranking_score))"')
  echo "$topic top: $top_article"
done

# Test keyword matching effectiveness
curl -s "http://localhost:8787/items?limit=50" | jq '[.[] | select(.topic == "ai-ml")] | map({
  title,
  score: .ranking_score,
  confidence: .topic_confidence,
  ai_related: ((.title | ascii_downcase) | contains("ai") or contains("ml") or contains("gpt") or contains("llm"))
}) | group_by(.ai_related) | map({has_ai_keywords: .[0].ai_related, count: length, avg_confidence: ([.[].confidence] | add / length)})'
```

### **Database Inspection**

```bash
# SQLite CLI (if installed)
sqlite3 data/newsbrief.sqlite3

# View tables
.tables

# Check feeds
SELECT id, url, robots_allowed, disabled FROM feeds;

# Check recent articles with ranking data ⭐ *Updated in v0.4.0*
SELECT id, title, published, ranking_score, topic, topic_confidence, source_weight FROM items
ORDER BY ranking_score DESC, COALESCE(published, created_at) DESC
LIMIT 5;

# Analyze ranking distribution
SELECT
  topic,
  COUNT(*) as article_count,
  ROUND(AVG(ranking_score), 3) as avg_ranking,
  ROUND(AVG(topic_confidence), 3) as avg_confidence
FROM items
WHERE topic IS NOT NULL
GROUP BY topic
ORDER BY avg_ranking DESC;

# Find top-ranked articles
SELECT id, title, ranking_score, topic FROM items
ORDER BY ranking_score DESC
LIMIT 10;

# Exit SQLite
.quit
```

### **Debugging Tips**

#### **Common Issues**

1. **Port already in use**
   ```bash
   # Find process using port 8787
   lsof -i :8787

   # Kill process or use different port
   uvicorn app.main:app --reload --port 8788
   ```

2. **Database locked errors**
   ```bash
   # Stop all running instances
   pkill -f "uvicorn.*newsbrief"

   # Remove lock if exists
   rm -f data/newsbrief.sqlite3-shm data/newsbrief.sqlite3-wal
   ```

3. **Module import errors**
   ```bash
   # Ensure you're in project root
   pwd  # Should end with /newsbrief

   # Check PYTHONPATH
   export PYTHONPATH=$PWD:$PYTHONPATH
   ```

#### **Logging & Debugging**

```python
# Add debug logging to any module
import logging
logging.basicConfig(level=logging.DEBUG)

# In feeds.py, add debug prints
print(f"Fetching {len(list(list_feeds()))} feeds...")
print(f"Inserted {inserted} new articles")
```

## 🏗️ Development Workflow

NewsBrief uses **modern CI/CD practices** with automated quality gates and security scanning.

### **🚀 First-Time Setup**

```bash
# Install all dependencies
pip install -r requirements.txt -r requirements-dev.txt

# Set up pre-commit hooks (IMPORTANT!)
pip install pre-commit
pre-commit install

# Verify pre-commit setup
pre-commit run --all-files
```

### **📋 Development Process**

#### **1. Create Feature Branch**
```bash
git checkout dev
git pull origin dev
git checkout -b feature/improve-feed-parsing
```

#### **2. Development with Quality Gates**
```bash
# Make your changes
# Pre-commit hooks automatically run on commit:
# ✅ Code formatting (Black, isort)
# ✅ Linting (Flake8, mypy)
# ✅ Security scanning (Bandit)
# ✅ Secrets detection
# ✅ YAML/JSON validation

# Commit triggers automatic checks
git add .
git commit -m "feat: improve feed parsing error handling"

# Push triggers full CI/CD pipeline
git push origin feature/improve-feed-parsing
```

#### **3. CI/CD Pipeline (Automatic)**
```yaml
🧪 Test & Quality:
  ✅ Code formatting validation
  ✅ Type checking with mypy
  ✅ Security scanning
  ✅ Dependency vulnerability checks

🔨 Container Build:
  ✅ Multi-architecture builds (amd64/arm64)
  ✅ Push to GitHub Container Registry
  ✅ Generate deployment tags

🔒 Security Scan:
  ✅ Container vulnerability scanning (Trivy)
  ✅ Upload results to GitHub Security tab
  ✅ Block deployment if critical issues found
```

#### **4. Manual Testing (Optional)**
```bash
# Local development
uvicorn app.main:app --reload --port 8787

# Container testing
make build && make run

# Manual quality checks
black app/ && isort app/
mypy app/ --ignore-missing-imports
safety check -r requirements.txt
```

### **🔗 CI/CD Integration**

#### **Branch Strategy**
```
main (production)
 ├── staging (pre-production)
 └── dev (development)
     ├── feature/new-feature
     └── bugfix/fix-issue
```

#### **Deployment Flow**
- **Push to `dev`** → Deploy to Development environment
- **Push to `main`** → Deploy to Staging environment
- **Create Release** → Deploy to Production environment

#### **Monitoring Your Pipeline**
```bash
# Check workflow status
gh run list --workflow=ci-cd.yml --limit 5

# View detailed logs
gh run view <run-id> --log

# Check security scan results
# → GitHub → Security tab → Code scanning
```

#### **Troubleshooting**
```bash
# Pre-commit hook failures
pre-commit run --all-files  # Fix all issues at once

# CI/CD pipeline failures
gh run rerun <run-id>       # Retry failed workflow

# Container build issues
make build                  # Test locally first
```

**📚 Complete Guide**: See [`docs/CI-CD.md`](CI-CD.md) for comprehensive CI/CD documentation, security features, and deployment strategies.

### **Code Quality**

#### **Style Guidelines**

- **Python**: Follow PEP 8, use type hints
- **Imports**: Use `from __future__ import annotations`
- **Error handling**: Be explicit with exception types
- **Docstrings**: Add for public functions

```python
# Good example
def fetch_feed(url: str, timeout: float = 20.0) -> tuple[bool, str]:
    """
    Fetch RSS feed from URL with timeout.

    Args:
        url: RSS feed URL
        timeout: Request timeout in seconds

    Returns:
        Tuple of (success, error_message or content)
    """
    try:
        # Implementation
        pass
    except httpx.TimeoutException as e:
        return False, f"Timeout fetching {url}: {e}"
```

#### **Database Changes**

When modifying database schema:

```python
# In db.py, add migration logic
def init_db() -> None:
    with engine.begin() as conn:
        # Check current schema version
        try:
            version = conn.execute("SELECT version FROM schema_info").scalar()
        except:
            version = None

        if version is None:
            # Create initial schema
            conn.exec_driver_sql("CREATE TABLE schema_info (version INTEGER)")
            # ... existing table creation
            conn.exec_driver_sql("INSERT INTO schema_info (version) VALUES (1)")
```

## 📦 Container Development

### **Build System**

```bash
# Build with caching
make build

# Tagged build
make local-release VERSION=v0.3.0-dev

# Automated cleanup + build
make clean-release VERSION=v0.3.0-dev

# View available targets
make help
```

### **Multi-architecture Builds**

```bash
# Build for multiple platforms
podman build --platform=linux/amd64,linux/arm64 -t newsbrief-api .

# Or using buildx (Docker)
docker buildx build --platform linux/amd64,linux/arm64 -t newsbrief-api .
```

### **Container Debugging**

```bash
# Run with shell access
podman run --rm -it newsbrief-api /bin/bash

# Check container logs
podman logs newsbrief

# Inspect running container
podman exec -it newsbrief /bin/bash
```

## 🤖 Robots.txt Compliance

NewsBrief includes comprehensive robots.txt support to ensure respectful web crawling and compliance with website policies.

### **Implementation Overview**

NewsBrief implements robots.txt checking at two levels:

```python
# Key functions in app/feeds.py

is_robot_allowed(feed_url)           # Feed-level checking
is_article_url_allowed(article_url)  # Article-level checking
_get_robots_txt(domain)             # Cached robots.txt fetching
_check_robots_txt_path(robots_txt, path, user_agent)  # Parser
```

### **How It Works**

**1. Feed Addition**
- When adding feeds, `is_robot_allowed()` fetches and parses robots.txt
- Result stored in `feeds.robots_allowed` column (1=allowed, 0=blocked)
- Blocked feeds are skipped during refresh cycles

**2. Article Content Extraction**
- Before fetching article content, `is_article_url_allowed()` validates each URL
- Uses specific User-agent: `newsbrief` for identification
- If disallowed, article is saved without full content (graceful degradation)

**3. Performance Optimization**
- In-memory cache prevents repeated robots.txt requests
- Cache cleared at start of each refresh cycle for freshness
- Failed requests cached as "allow" to avoid timeout loops

### **Robots.txt Parser Features**

```python
# Supports proper robots.txt syntax:
User-agent: *
Disallow: /admin/
Disallow: /api/
Allow: /rss/

User-agent: newsbrief
Disallow: /private/
```

**Parsing Rules**:
- ✅ Multiple `User-agent` sections
- ✅ `Disallow:` patterns with path prefixes
- ✅ `Allow:` patterns that override disallows
- ✅ `Disallow: /` blocks entire site
- ✅ Empty `Disallow:` allows everything

### **Database Schema**

```sql
CREATE TABLE feeds (
  id INTEGER PRIMARY KEY,
  url TEXT UNIQUE NOT NULL,
  robots_allowed INTEGER DEFAULT 1,  -- 1=allowed, 0=blocked
  disabled INTEGER DEFAULT 0,
  etag TEXT,
  last_modified TEXT,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### **Testing Robots.txt**

**Test permissive robots.txt:**

```bash
# Add HackerNews RSS (robots.txt allows everything)
curl -X POST http://localhost:8787/feeds \
  -H "Content-Type: application/json" \
  -d '{"url": "https://hnrss.org/frontpage"}'

# Refresh should work normally
curl -X POST http://localhost:8787/refresh
```

**Check restrictive robots.txt:**

```bash
# Check Reddit's restrictive robots.txt
curl -s https://www.reddit.com/robots.txt | head -10
# Output: Disallow: / (blocks everything)

# Adding Reddit RSS would be blocked
curl -X POST http://localhost:8787/feeds \
  -H "Content-Type: application/json" \
  -d '{"url": "https://www.reddit.com/r/programming.rss"}'
```

**Debug robots.txt behavior:**

```bash
# Check feed status in database
sqlite3 data/newsbrief.sqlite3 "SELECT url, robots_allowed FROM feeds;"

# Watch cache behavior in logs
podman logs newsbrief | grep -i robots
```

### **Configuration**

Robots.txt behavior is configured via constants in `app/feeds.py`:

```python
HTTP_TIMEOUT = 20.0                      # robots.txt request timeout
_robots_txt_cache: dict[str, str | None] = {}  # cache storage
```

**User-Agent Strings**:
- **Feed checking**: `User-agent: *` (matches general policies)
- **Article checking**: `User-agent: newsbrief` (specific identification)

### **Error Handling & Fail-Safe Design**

```python
def is_robot_allowed(feed_url: str) -> bool:
    try:
        robots_txt = _get_robots_txt(domain)
        if robots_txt is None:
            return True  # No robots.txt = allowed
        return _check_robots_txt_path(robots_txt, path, user_agent='*')
    except Exception:
        return True  # Error = allow (fail-safe)
```

**Fail-Safe Principles**:
- Network errors default to "allow"
- Invalid robots.txt defaults to "allow"
- Parsing errors default to "allow"
- Missing robots.txt defaults to "allow"

This ensures service reliability while respecting robots.txt when available.

## 🎯 Feature Development

### **Adding New API Endpoints**

1. **Define model in `models.py`**
   ```python
   class SearchQuery(BaseModel):
       query: str
       limit: int = Field(10, le=100)
   ```

2. **Add endpoint in `main.py`**
   ```python
   @app.post("/search", response_model=List[ItemOut])
   def search_items(query: SearchQuery):
       # Implementation
       pass
   ```

3. **Test with curl**
   ```bash
   curl -X POST http://localhost:8787/search \
     -H "Content-Type: application/json" \
     -d '{"query": "python", "limit": 5}'
   ```

### **Database Extensions**

For new tables or columns:

```python
# In db.py
def init_db() -> None:
    # ... existing code
    conn.exec_driver_sql("""
    CREATE TABLE IF NOT EXISTS user_preferences (
      id INTEGER PRIMARY KEY,
      key TEXT UNIQUE NOT NULL,
      value TEXT,
      created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)
```

### **Feed Processing Extensions**

For custom feed processing:

```python
# In feeds.py
def custom_feed_processor(entry, feed_url: str) -> dict:
    """Process entry with custom logic based on feed source."""

    # Example: Special handling for certain sources
    if "github.com" in feed_url:
        # Extract GitHub-specific metadata
        pass

    return {
        "title": entry.title,
        "custom_field": extracted_data
    }
```

## 📋 Release Process

### **Version Management**

```bash
# Update version
git tag -a v0.3.0 -m "Release v0.3.0: Add search functionality"

# Build release container
make clean-release VERSION=v0.3.0

# Verify container
podman run --rm newsbrief-api:v0.3.0 --version
```

### **Pre-release Checklist**

- [ ] All tests pass
- [ ] Documentation updated
- [ ] Container builds successfully
- [ ] API endpoints tested manually
- [ ] Database migrations work
- [ ] No linting errors
- [ ] Version tagged in git

## 🤝 Contributing

### **Project Planning & Issues**

Before starting development, check the **[GitHub Project Board](https://github.com/users/Deim0s13/projects/7/views/1?layout=board)** for:

- **Current epics** and their progress status
- **Open issues** ready for development
- **Sprint planning** and release milestones
- **Epic breakdowns** with detailed user stories

The project board organizes work into focused epics:
- **epic:ingestion** - RSS feed processing improvements
- **epic:summaries** - ✅ Complete: AI summarization with Ollama integration
- **epic:ranking** - Content scoring and curation algorithms
- **epic:ui** - Web interface development with HTMX
- **epic:embeddings** - Semantic search and vector operations
- **epic:search** - Full-text search and query capabilities
- **epic:ops** - DevOps, monitoring, and deployment tooling

### **Pull Request Process**

1. **Choose an issue** from the project board
2. **Fork repository** and create feature branch
3. **Make changes with tests** and update documentation
4. **Reference issue number** in commit messages
5. **Submit pull request** with clear description

### **Commit Message Format**

```
type(scope): brief description

Optional longer description explaining the change.

- Add new feature X
- Fix bug Y
- Update documentation Z
```

Types: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`

## 🎨 **Feed Management Testing (v0.5.3)** ⭐ *NEW*

NewsBrief v0.5.3 introduces comprehensive feed management capabilities. Here's how to test the new features:

### **Web Interface Testing**

```bash
# Start the application
make run VERSION=v0.5.3

# Open the Feed Management interface
open http://localhost:8787/feeds-manage
```

### **OPML Import/Export Testing**

```bash
# Export current feeds
curl -o "export_$(date +%Y%m%d).opml" http://localhost:8787/feeds/export/opml

# Test import (using form upload)
curl -X POST http://localhost:8787/feeds/import/opml/upload \
  -F "file=@your_feeds.opml"
```

### **Bulk Operations Testing**

```bash
# Get all feeds with IDs
curl http://localhost:8787/feeds | jq '.[] | {id, name, category}'

# Bulk assign category
curl -X POST http://localhost:8787/feeds/categories/bulk-assign \
  -H "Content-Type: application/json" \
  -d '{"feed_ids": [1, 2, 3], "category": "Technology"}'

# Bulk assign priority
curl -X POST http://localhost:8787/feeds/categories/bulk-priority \
  -H "Content-Type: application/json" \
  -d '{"feed_ids": [1, 2], "priority": 5}'
```

### **Health Monitoring Testing**

```bash
# View feed health data
curl http://localhost:8787/feeds | jq '.[] | {
  name,
  health_score,
  consecutive_failures,
  avg_response_time_ms,
  last_success_at
}'

# Check category statistics
curl http://localhost:8787/feeds/categories | jq '.categories[] | {
  name,
  feed_count,
  avg_health,
  total_articles
}'

# View detailed feed statistics
curl http://localhost:8787/feeds/1/stats | jq
```

### **Performance Testing**

```bash
# Test feed refresh and monitor response times
time curl -X POST http://localhost:8787/refresh

# Monitor health score changes after refresh
curl http://localhost:8787/feeds | jq '.[] | select(.health_score < 90) | {
  name,
  health_score,
  consecutive_failures,
  last_error
}'
```

### **Category Management Testing**

```bash
# List all available categories
curl http://localhost:8787/feeds/categories | jq '.categories'

# Filter feeds by category (web interface)
open http://localhost:8787/feeds-manage

# Test category filtering with statistics
curl http://localhost:8787/feeds | jq 'group_by(.category) | map({
  category: .[0].category // "Uncategorized",
  count: length,
  avg_health: (map(.health_score // 100) | add / length)
})'
```

## 📞 Getting Help

- **Issues**: Check existing GitHub issues
- **Discussions**: Use GitHub Discussions for questions
- **Code Review**: All PRs welcome review and feedback
- **Documentation**: Update docs for any user-facing changes

---

Happy coding! 🚀

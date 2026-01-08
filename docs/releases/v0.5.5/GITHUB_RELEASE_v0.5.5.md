# How to Create GitHub Release for v0.5.5

## 🎯 Quick Steps

1. **Go to GitHub Releases**: https://github.com/Deim0s13/newsbrief/releases/new

2. **Select Tag**: Choose `v0.5.5` from the dropdown

3. **Release Title**:
   ```
   v0.5.5 - Story Architecture: Return to Original Scope
   ```

4. **Release Description**: Copy the content below

---

## 📋 Release Description (Copy this to GitHub)

```markdown
# v0.5.5 - Story Architecture: Return to Original Scope

**Release Date**: November 18, 2025
**Status**: ✅ Production Ready

---

## 🎯 Overview

NewsBrief v0.5.5 marks our return to the original project vision after exploring alternative approaches in v0.5.1-v0.5.4. This release transforms NewsBrief from an article-centric RSS reader to a story-based news aggregator that **reduces information overload by 90%**.

**Key Achievement**: Stay informed in **2 minutes** instead of 30+ minutes.

---

## ✨ What's New

### Story-Based Aggregation
- **Automated Story Generation**: Daily scheduled generation at 6 AM (configurable timezone)
- **Intelligent Clustering**: Hybrid topic grouping + keyword similarity for related article detection
- **Multi-Document Synthesis**: LLM-powered synthesis combining multiple sources into coherent narratives
- **Entity Extraction**: Automatically identifies companies, products, and people from article clusters
- **Topic Auto-Classification**: Stories tagged with Security, AI/ML, DevTools, Cloud/K8s, etc.

### Story-First UI
- **Landing Page**: Shows synthesized stories (not individual articles)
- **Story Detail Pages**: Full synthesis with key points, entities, and supporting articles
- **Filters & Sorting**: By topic, time window, and status
- **Responsive Design**: Professional Tailwind CSS with dark mode support

### Performance & Automation
- **80% Faster Generation**: Parallel LLM synthesis with 3 workers, caching, batching
- **Automatic Archiving**: Old stories archived after 7 days (configurable)
- **Scheduler Monitoring**: Real-time status of automated generation via `/scheduler/status`

---

## 📈 Key Metrics

| Metric | Before (v0.4.x) | After (v0.5.5) | Improvement |
|--------|----------------|----------------|-------------|
| **Time to Informed** | 30+ minutes | 2 minutes | **93% faster** |
| **Items to Review** | 50+ articles | 5-10 stories | **90% reduction** |
| **Generation Time** | 171 seconds | ~34 seconds | **80% faster** |
| **Automation** | Manual only | Daily automated | **100% automated** |

---

## 🚀 New Features

### Story API Endpoints
- `GET /stories` - List synthesized stories with filtering and pagination
- `GET /stories/{id}` - Get story with supporting articles
- `POST /stories/generate` - On-demand story generation
- `GET /stories/stats` - Story generation statistics
- `GET /scheduler/status` - Monitor automated story generation

### Configuration (Environment Variables)
- `STORY_GENERATION_SCHEDULE` - Cron schedule (default: `0 6 * * *` = 6 AM daily)
- `STORY_GENERATION_TIMEZONE` - Timezone (default: `Pacific/Auckland`)
- `STORY_ARCHIVE_DAYS` - Archive threshold (default: 7 days)
- `STORY_TIME_WINDOW_HOURS` - Lookback period (default: 24 hours)
- `STORY_MIN_ARTICLES` - Minimum articles per story (default: 2)
- `STORY_MODEL` - LLM model (default: `llama3.1:8b`)

---

## 🐛 Bug Fixes

- Fixed SSL certificate errors during feed refresh
- Corrected SQL query syntax for SQLite IN clauses
- Fixed import paths for content extraction utilities
- Resolved story detail page loading errors

---

## 🔧 Technical Changes

### Code Quality
- All Python code formatted with black
- Imports sorted with isort
- 100% test pass rate (25/25 tests)
- Type hints and validation improved

### Version Metadata
- Added `__version__ = "0.5.5"` to `app/__init__.py`
- Container images now include version labels (OCI format)
- Proper build metadata in Dockerfile

### Database
- New `stories` table with full schema
- New `story_articles` junction table
- Automatic migration on startup (non-destructive)

---

## 📦 Installation & Upgrade

### Using Container (Recommended)

```bash
# Pull latest image
docker pull ghcr.io/deim0s13/newsbrief:v0.5.5

# Or use docker-compose
git pull origin main
docker-compose up -d
```

### From Source

```bash
# Pull latest code
git pull origin main
git checkout v0.5.5

# Install dependencies
pip install -r requirements.txt

# Database migration is automatic on startup
uvicorn app.main:app --port 8787
```

---

## 🔄 Breaking Changes

**None**. This release is fully backward compatible with v0.4.x.

- Existing `items` table preserved
- Existing feeds continue working
- New `stories` and `story_articles` tables added automatically

---

## 📚 Documentation

- **[README.md](https://github.com/Deim0s13/newsbrief/blob/main/README.md)** - Updated with v0.5.5 features
- **[API Documentation](https://github.com/Deim0s13/newsbrief/blob/main/docs/API.md)** - Story endpoints documented
- **[Implementation Plan](https://github.com/Deim0s13/newsbrief/blob/main/docs/IMPLEMENTATION_PLAN.md)** - All phases complete
- **[Migration Guide](https://github.com/Deim0s13/newsbrief/blob/main/docs/MIGRATION_v0.5.0.md)** - Database migration details

---

## 🙏 Credits

**Epic**: epic:stories - Story-based aggregation and synthesis
**Milestone**: v0.5.5 - Story Architecture
**Issues Closed**: 29 issues (#36-39, #47-48, #50-55, #66, etc.)
**Commits**: 30+ commits
**Lines Changed**: 4,100+ lines added

---

## 📌 Version Notes

**Why v0.5.5?**

Versions v0.5.1 through v0.5.4 explored alternative approaches to the news aggregation problem. v0.5.5 represents our return to the original scope and vision: a story-based aggregator that synthesizes multiple sources to reduce information overload.

This versioning maintains chronological order and clearly signals the evolution of the project rather than deleting previous work.

---

## 🎯 What's Next

### v0.6.0 - Enhanced Intelligence (Q1 2026)
- Configurable time windows (12h, 24h, 48h, 1w)
- Topic grouping in UI
- Vector embeddings for better clustering
- Full-text search (SQLite FTS5)
- Dynamic story generation (quality-based)

---

**Full Changelog**: https://github.com/Deim0s13/newsbrief/compare/v0.5.4...v0.5.5

**Container Image**: `ghcr.io/deim0s13/newsbrief:v0.5.5`
```

---

## 5. **Mark as Latest Release**: ✅ Check this box

6. **Publish Release**: Click the green "Publish release" button

---

## ✅ After Publishing

The release will:
- Show v0.5.5 as the "Latest Release" on GitHub
- Replace v0.5.4 as the default release
- Trigger production deployment workflow (if configured)
- Create a permanent snapshot at this version

---

**Status**: Ready to publish! 🚀

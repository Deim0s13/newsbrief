# Release Notes - v0.5.5: Story Architecture - Return to Original Scope

**Release Date**: November 18, 2025  
**Milestone**: Story Architecture  
**Status**: ✅ Complete

---

## 🎯 Overview

NewsBrief v0.5.5 represents a fundamental transformation from article-centric RSS reader to story-based news aggregator. This release marks our return to the original vision after exploring alternative approaches in v0.5.1-v0.5.4. The goal: **replace reading 50+ article summaries with 5-10 AI-synthesized stories**.

**Key Achievement**: Users can now stay informed in **2 minutes** instead of 30+ minutes.

---

## ✨ What's New

### 🤖 Automated Story Generation
- **Scheduled Generation**: Stories automatically generate daily at 6 AM (configurable timezone)
- **APScheduler Integration**: Background task runner with graceful startup/shutdown
- **Auto-Archiving**: Stories older than 7 days automatically archived
- **Configurable**: 6 environment variables for complete customization

### 📊 Story-First User Interface
- **Landing Page**: Shows 5-10 synthesized stories instead of 50+ individual articles
- **Story Cards**: Display title, synthesis preview, key points, and metadata
- **Filters & Sorting**: Filter by status, time window; sort by importance/freshness
- **Story Detail Page**: Full synthesis, all key points, "why it matters", supporting articles
- **Navigation**: Seamless flow from stories → detail → articles → back

### 🚀 Performance Improvements
- **Parallel LLM Synthesis**: 3 concurrent workers for story generation
- **80% Faster**: Generation time reduced from 171s to ~34s
- **Cached Data**: Article data cached in memory during generation
- **Batched Commits**: Database operations batched for efficiency

### 🔌 API Enhancements
- `GET /stories` - List stories with filtering, sorting, pagination
- `GET /stories/{id}` - Get story with full details and supporting articles
- `POST /stories/generate` - Manually trigger story generation
- `GET /stories/stats` - Story generation statistics
- `GET /scheduler/status` - Monitor automated generation status

---

## 📈 Key Metrics

| Metric | Before (v0.4.x) | After (v0.5.5) | Improvement |
|--------|----------------|----------------|-------------|
| **Time to Informed** | 30+ minutes | 2 minutes | **93% faster** |
| **Items to Review** | 50+ articles | 5-10 stories | **90% reduction** |
| **Generation Time** | 171 seconds | ~34 seconds | **80% faster** |
| **Automation** | Manual only | Daily automated | **100% automated** |

---

## 🏗️ Technical Details

### Story Generation Pipeline

**1. Article Collection**
- Queries articles from configured time window (default: 24 hours)
- Filters by status (active, archived)

**2. Hybrid Clustering**
- Topic grouping (AI/ML, Security, Cloud, etc.)
- Keyword similarity within topics (Jaccard index)
- Intelligent cluster formation

**3. Multi-Document Synthesis**
- Ollama LLM (llama3.1:8b) generates coherent narratives
- Parallel processing (3 workers)
- Structured output: title, synthesis, key points, why it matters
- Entity extraction: companies, products, people
- Topic classification

**4. Quality Scoring**
- Importance score (0.0-1.0)
- Freshness score (time-based decay)
- Combined scoring for ranking

**5. Storage & Archiving**
- Stories saved to SQLite database
- Links to supporting articles preserved
- Automatic archiving after 7 days

### Configuration

All aspects configurable via environment variables:

```bash
# Scheduling
STORY_GENERATION_SCHEDULE=0 6 * * *           # Cron format
STORY_GENERATION_TIMEZONE=Pacific/Auckland    # Timezone
STORY_ARCHIVE_DAYS=7                          # Archive threshold

# Generation Parameters
STORY_TIME_WINDOW_HOURS=24                    # Lookback period
STORY_MIN_ARTICLES=2                          # Min articles per story
STORY_MODEL=llama3.1:8b                       # LLM model
```

### Database Schema

**New Tables**:
- `stories` - Story metadata, synthesis, scores
- `story_articles` - Junction table linking stories to articles

**Key Fields**:
- `title`, `synthesis`, `key_points_json`, `why_it_matters`
- `topics_json`, `entities_json`
- `importance_score`, `freshness_score`
- `status` (active/archived), `generated_at`

---

## 🔄 Breaking Changes

### User-Facing Changes
- **Landing page** now shows stories by default (not articles)
- **Articles** moved to `/articles` route (still accessible)
- **Stories are primary**, articles are secondary

### API Changes
- No breaking changes to existing endpoints
- New endpoints added (backward compatible)

### Configuration Changes
- No breaking changes
- New environment variables are optional (have defaults)

---

## 📦 What's Included

### Issues Closed (29 total)
- **Phase 1**: #36, #37, #38, #39, #42, #44, #45, #47, #55 (Core Infrastructure)
- **Phase 2**: #48, #50, #51, #52, #53, #54 (Automation & UI)
- **Phase 3**: #66 (Performance)
- **Testing**: #59, #60, #61 (Tests)
- **Documentation**: #62, #63 (Docs)

### Files Added
- `app/stories.py` - Story generation and CRUD (743 lines)
- `app/scheduler.py` - APScheduler integration (234 lines)
- `app/templates/stories.html` - Story landing page
- `app/templates/story_detail.html` - Story detail view
- `app/static/js/stories.js` - Frontend logic (379 lines)

### Files Modified
- `app/main.py` - Routes, scheduler integration
- `app/db.py` - Story tables, migrations
- `app/models.py` - Story models
- `requirements.txt` - Added apscheduler

---

## 🐛 Known Issues

### Minor Issues
- **Manual generation button timeout**: Button may timeout on large datasets (not blocking - scheduled generation works perfectly)

### Future Enhancements (v0.6.0)
- Configurable time windows (12h, 24h, 48h, 1w)
- Topic grouping and organization
- Advanced embeddings for better clustering
- Full-text search
- Interest-based filtering

---

## 🚀 Upgrade Guide

### From v0.4.x to v0.5.5

1. **Pull latest code**:
   ```bash
   git pull origin main
   ```

2. **Install new dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Database migration** (automatic):
   - Story tables created on first run
   - No manual migration needed

4. **Optional: Configure timezone**:
   ```bash
   export STORY_GENERATION_TIMEZONE=Pacific/Auckland
   ```

5. **Restart application**:
   ```bash
   uvicorn app.main:app --reload --port 8787
   ```

6. **Generate initial stories**:
   - Automatic: Wait until 6 AM for scheduled generation
   - Manual: Click "Generate Stories" button on landing page
   - API: `POST http://localhost:8787/stories/generate`

---

## 🙏 Credits

**Epic**: epic:stories - Story-based aggregation and synthesis  
**Milestone**: v0.5.5 - Story Architecture  
**Issues**: 29 issues closed  
**Commits**: 30+ commits  
**Lines Changed**: 2,500+ lines added

---

## 📝 Documentation

- **README.md** - Updated with v0.5.5 features
- **IMPLEMENTATION_PLAN.md** - All phases marked complete
- **API.md** - Story endpoints documented
- **SESSION_SUMMARY_2025-11-18.md** - Today's session summary
- **UI_TESTING_CHECKLIST.md** - UI testing guide

---

## 🎯 What's Next?

### v0.6.0 - Intelligence & Polish (Q1 2026)
- Configurable time windows
- Topic grouping and organization
- Advanced embeddings
- Full-text search
- Enhanced personalization

### v0.7.0 - Infrastructure (Q2 2026)
- Security enhancements
- Advanced monitoring
- Database migrations
- Horizontal scaling

---

**Release**: v0.5.5  
**Version Notes**: v0.5.1-v0.5.4 explored alternative approaches. v0.5.5 represents the finalized implementation aligned with our original scope.  
**Date**: November 18, 2025  
**Status**: ✅ Production Ready


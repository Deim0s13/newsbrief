# Database Migration to v0.5.0 (Story Architecture)

**Date**: 2025-11-06 (Updated: 2025-11-12)
**Version**: v0.5.0-alpha (Phase 1 Complete)
**Type**: Schema Addition (Non-Breaking)

## ✅ Phase 1 Status: COMPLETE

- **Database Schema**: `stories` and `story_articles` tables deployed
- **Story Generation**: Hybrid clustering + LLM synthesis implemented
- **CRUD Operations**: Complete story management functions
- **Testing**: Comprehensive test coverage (automated + manual)
- **Migration**: Idempotent schema updates (safe to run multiple times)

## Why This Change?

**The Pivot**: NewsBrief v0.5.0 represents a return to the **original project vision**.

**Background**: NewsBrief v0.3.x evolved into an article-centric RSS reader where users browsed individual article summaries. While functional, this deviated from the original intent: replacing reading 50+ article summaries (TLDR newsletters, RSS fatigue) with AI-synthesized story briefs.

**The Problem**: Information overload persisted. Users still spent 30+ minutes reading summaries instead of 2 minutes scanning key stories.

**The Solution**: Story-based aggregation. Instead of 50+ individual articles, present 5-10 synthesized stories that provide unified narratives from multiple sources.

**See**: [ADR 0002: Story-Based Aggregation](adr/0002-story-based-aggregation.md) for full architectural rationale.

---

## Overview

NewsBrief v0.5.0 introduces story-based aggregation, requiring new database tables. This migration is **automatic** and **non-destructive**.

## What Changes

### New Tables

**1. `stories` table**
Stores synthesized story information:
- `id`: Primary key
- `title`: Story title (synthesized from articles)
- `synthesis`: AI-generated unified narrative
- `key_points_json`: JSON array of key bullets
- `why_it_matters`: Significance analysis
- `topics_json`: JSON array of topics
- `entities_json`: JSON array of entities (companies, products, people)
- `article_count`: Number of supporting articles
- `importance_score`: Story importance (0.0-1.0)
- `freshness_score`: Time-based relevance (0.0-1.0)
- `cluster_method`: Algorithm used for clustering
- `story_hash`: Unique hash for deduplication
- `generated_at`, `first_seen`, `last_updated`: Timestamps
- `time_window_start`, `time_window_end`: Article time range
- `model`: LLM model used for synthesis
- `status`: 'active' or 'archived'

**2. `story_articles` junction table**
Links stories to supporting articles (many-to-many):
- `id`: Primary key
- `story_id`: Foreign key to stories
- `article_id`: Foreign key to items
- `relevance_score`: How relevant this article is to the story (0.0-1.0)
- `is_primary`: Whether this is the primary source
- `added_at`: When article was added to story

### New Indexes

Performance indexes for story queries:
- `idx_stories_generated_at`: Sort stories by date
- `idx_stories_importance`: Sort stories by importance
- `idx_stories_status`: Filter active/archived stories
- `idx_story_articles_story`: Query articles by story
- `idx_story_articles_article`: Query stories by article

### Existing Tables

**No changes to existing tables**:
- `feeds` - Unchanged
- `items` - Unchanged

All existing data is preserved.

## Migration Behavior

### For New Installations
- All tables created from scratch
- No migration needed

### For Existing v0.3.x Databases
1. **Automatic Detection**: `init_db()` checks if `stories` table exists
2. **Table Creation**: Creates `stories` and `story_articles` tables if missing
3. **Index Creation**: Creates all story-related indexes
4. **Logging**: Logs migration progress:
   ```
   🔄 Migrating database to v0.5.0 (story architecture)...
   ✅ Story tables created successfully
   🎉 Database migration to v0.5.0 complete!
   ```

### Idempotency
- Uses `CREATE TABLE IF NOT EXISTS`
- Uses `CREATE INDEX IF NOT EXISTS`
- Safe to run multiple times
- No data loss

## Migration Process

### Automatic (Recommended)
Migration happens automatically on app startup:

```bash
# Just start the app - migration runs automatically
uvicorn app.main:app --reload
```

Logs will show:
```
🔄 Migrating database to v0.5.0 (story architecture)...
✅ Story tables created successfully
🎉 Database migration to v0.5.0 complete!
```

### Manual Verification
Check migration succeeded:

```bash
sqlite3 data/newsbrief.sqlite3
```

```sql
-- Verify tables exist
.tables
-- Should show: feeds, items, stories, story_articles

-- Verify stories table schema
.schema stories

-- Check indexes
.indexes stories
```

## Rollback

If needed, you can rollback by:

1. **Drop story tables** (safe - doesn't affect articles):
   ```sql
   DROP TABLE IF EXISTS story_articles;
   DROP TABLE IF EXISTS stories;
   ```

2. **Restore from backup**:
   ```bash
   cp data/newsbrief.sqlite3.backup data/newsbrief.sqlite3
   ```

## Data Flow After Migration

```
v0.3.x (Before):
  Feeds → Items (Articles) → Display in list

v0.5.0 (After):
  Feeds → Items (Articles) → Stories → Display as briefs
                           ↘ Also available as secondary view
```

## Testing Migration

### Test with Existing Database

```bash
# 1. Backup current database
cp data/newsbrief.sqlite3 data/newsbrief.sqlite3.backup

# 2. Start app (triggers migration)
uvicorn app.main:app --reload

# 3. Verify in logs
# Look for: "🎉 Database migration to v0.5.0 complete!"

# 4. Check tables
sqlite3 data/newsbrief.sqlite3 ".tables"
# Should show stories and story_articles
```

### Test with Fresh Database

```bash
# 1. Remove existing database
rm data/newsbrief.sqlite3

# 2. Start app (creates fresh schema)
uvicorn app.main:app --reload

# 3. Verify
sqlite3 data/newsbrief.sqlite3 ".schema stories"
```

## Troubleshooting

### Migration Doesn't Run
**Symptoms**: No migration logs, stories table doesn't exist

**Solutions**:
1. Check database file permissions: `ls -la data/newsbrief.sqlite3`
2. Verify `init_db()` is called on startup
3. Check logs for errors

### Migration Fails Partway
**Symptoms**: stories table exists but story_articles doesn't

**Solutions**:
1. Check error logs for SQL syntax errors
2. Verify SQLite version: `sqlite3 --version` (requires 3.24+)
3. Run migration again (idempotent, safe to retry)

### Database Locked
**Symptoms**: "database is locked" error during migration

**Solutions**:
1. Stop all running instances of NewsBrief
2. Close any open sqlite3 sessions
3. Restart app

## Performance Impact

- **Migration Time**: < 1 second for typical databases
- **Downtime**: None (migration during startup)
- **Disk Space**: Minimal (empty tables, ~few KB)
- **Query Performance**: No impact on existing queries

## Backward Compatibility

- **v0.3.x → v0.5.0**: Full compatibility, automatic migration
- **v0.5.0 → v0.3.x**: Not supported (missing tables error)

## Next Steps After Migration

1. ✅ Migration complete
2. ⏳ Generate first stories: `POST /stories/generate`
3. ⏳ View stories: `GET /stories`

See [Implementation Plan](IMPLEMENTATION_PLAN.md) for story generation setup.

## Support

If migration issues occur:
1. Check logs for error messages
2. Restore from backup: `cp data/newsbrief.sqlite3.backup data/newsbrief.sqlite3`
3. Report issue with logs and SQLite version

---

**Status**: ✅ Migration tested and production-ready
**Last Updated**: 2025-11-06

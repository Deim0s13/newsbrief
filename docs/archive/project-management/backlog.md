# NewsBrief Backlog

> **🚀 PRIMARY FOCUS**: Story Architecture (v0.5.0)
> **See**: [Story Architecture Backlog](STORY_ARCHITECTURE_BACKLOG.md) | [Implementation Plan](IMPLEMENTATION_PLAN.md)
>
> The items below are secondary/future enhancements. Current development focuses on story-based aggregation.

---

## Feed Refresh & Monitoring Improvements

### Priority: Medium
**Epic**: Operations / UI Polish

### Issues to Address:

#### 1. Refresh Time Display Enhancement
**Current State**:
- Timestamps now show correctly in UTC with proper timezone handling
- "X hours ago" calculations are accurate

**Improvements Needed**:
- More granular time display (e.g., "2 minutes ago", "just now")
- Better visual indicators for feeds that haven't updated in a long time
- Real-time countdown or "refreshing now" indicator
- Show last refresh duration in monitoring dashboard

#### 2. Refresh Process UX
**Current State**:
- Refresh works correctly (respects 304 caching, deduplication)
- Background refresh with 150 item limit and 5-minute timeout
- Updates happen but may not be immediately visible without page reload

**Improvements Needed**:
- **Progress indicator during refresh** - Show which feeds are being fetched
- **Live updates** - Auto-refresh article list when new items arrive (WebSocket or SSE)
- **Manual refresh button** - Add "Refresh Now" button on main articles page
- **Background refresh scheduling** - Optional cron-style automatic refreshes
- **Partial refresh** - Allow refreshing individual feeds on demand
- **Smarter rate limiting** - Per-feed cooldown to avoid hammering sources

#### 3. Feed Health & Monitoring
**Current State**:
- Health scores calculated based on success rate and response time
- Monitoring dashboard shows feed statistics
- 304 responses now update last_fetch_at correctly

**Improvements Needed**:
- **Feed health alerts** - Notification when feeds fail repeatedly
- **Historical performance graphs** - Track feed health over time
- **Better error messages** - Surface specific errors to UI
- **Feed validation** - Test feeds before adding them
- **Retry logic** - Exponential backoff for failing feeds
- **Feed recommendations** - Suggest similar/alternative feeds when one fails

#### 4. Article Display & Freshness
**Issues**:
- New articles may not appear immediately after refresh without page reload
- No visual indicator for "new since last visit"
- Ranking may not properly surface newest articles

**Improvements Needed**:
- **"New" badge** - Mark articles added since last user visit
- **Auto-reload after refresh** - Automatically update article list
- **Optimistic UI updates** - Show new articles as they're fetched
- **Better sorting options** - By date, by ranking, by source, by topic
- **"Mark all as read"** - Track read/unread state

### Technical Debt
- Consider moving to proper datetime objects with timezone awareness throughout
- Add integration tests for refresh workflow
- Document refresh algorithm and limits
- Add metrics/telemetry for refresh performance

### Estimated Effort
- **Quick wins (1-2 hours)**: Progress indicator, refresh button, better time formatting
- **Medium (4-6 hours)**: Live updates, feed validation, retry logic
- **Longer term (8+ hours)**: Historical tracking, WebSocket updates, advanced monitoring

### Related Epics
- Epic: Operations (monitoring, health checks)
- Epic: UI (user experience improvements)
- Epic: Performance (optimization, caching strategies)

---

## Other Backlog Items

### Testing & Quality
- [ ] Add unit tests for ranking algorithm
- [ ] Add integration tests for feed refresh
- [ ] Add contract tests for structured summaries
- [ ] Set up automated E2E tests

### Documentation
- [ ] Update API documentation with new endpoints
- [ ] Add troubleshooting guide
- [ ] Document timezone handling
- [ ] Create user guide for feed management

### Future Features (from roadmap)
- [ ] Skim/Detail view toggle
- [ ] Keyboard shortcuts (j/k navigation)
- [ ] Visual feedback improvements
- [ ] Semantic search with embeddings
- [ ] Full-text search with FTS5
- [ ] Export/import user preferences

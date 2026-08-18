# Code Improvement Plan

This document consolidates findings from multiple code reviews and aligns them with [CODE_REVIEW_RECOMMENDATIONS.md](CODE_REVIEW_RECOMMENDATIONS.md). Use it as the single source of truth for planning and tracking improvements.

**Related**: If you have a tracking issue (e.g. GitHub issue #272), link it here for visibility.

---

## 0. Current state (as of last review)

Use this section to see at a glance what’s done and what’s next. Update it as you complete work.

| Item | Status | Notes |
|------|--------|------|
| **Security: story list count query** | ✅ Done | Stories router `list_stories`: count uses `count_params` / `count_parts` / `topic_pattern` (parameterized). |
| **Phase 1: Remove dead `get_available_topics()` from ranking.py** | ✅ Done | Removed from `app/ranking.py`; only `topics.get_available_topics` is used. |
| **Phase 1: Rename `feeds.classify_topic` → `classify_article_for_feed`** | ✅ Done | Renamed in feeds.py; both call sites (fetch_and_store, recalculate_rankings_and_topics) updated. |
| **Phase 1: Unify robots.txt helper** | ✅ Done | Added `_check_url_allowed(url, user_agent)`; `is_robot_allowed` and `is_article_url_allowed` call it. |
| **Phase 1: Extract `_build_in_clause_params()` in stories.py** | ✅ Done | Helper added; all IN-clause blocks replaced (article_ids, feed_ids, cluster_hashes). |
| **Phase 2: Fix double-counting feed metrics** | ✅ Done | Success path now updates only etag, last_modified, updated_at; metrics from update_feed_health_metrics only. |
| **Phase 2: Use ranking module results in fetch_and_store INSERT** | ✅ Done | INSERT uses ranking_result.score, topic_result.topic, topic_result.confidence. |
| **Phase 3: Split main.py into routers** | ✅ Done | Routers: health, feeds, stories, items, admin, config, pages; main.py is app factory only. |
| **Optional: `session_scope()` type** | ❌ Not started | `db.py` still has `session_scope() -> Iterator`. |

**Next suggested step:** Optional `session_scope()` typing in `db.py`, or run full test suite with DATABASE_URL to validate Phase 3 + synthesis cleanup.

---

## 1. Validation of Previous Summaries

### 1.1 Corrections (verified against code)

| Claim | Verdict | Notes |
|-------|---------|------|
| **Duplicate `get_available_topics()`** | **Correct** | `app/topics.py` and `app/ranking.py` both define it. Only `topics.get_available_topics` is used (main.py, test_topics.py). Ranking’s version is **dead code** → remove from `ranking.py`. |
| **Duplicate `classify_topic()`** | **Clarification** | `feeds.classify_topic()` is a **wrapper** that adds feed category hints and calls `topics.classify_topic`. Not a duplicate; renaming to `classify_article_for_feed()` improves clarity. |
| **Three `_get_default_config()`** | **Not duplicates** | `topics.py` → topic config (settings + topics). `source_weights.py` → source weights schema. `interests.py` → interests schema. Different schemas per module → **no consolidation needed**. |

### 1.2 Confirmed bugs (reproduced in code)

| Bug | Location | What’s wrong |
|-----|----------|--------------|
| **Wasted ranking/topic computation** | `feeds.py` ~1628–1694 | `classify_article_topic()` and `calculate_ranking_score()` from `ranking` are called and their results **never used**. The INSERT uses `_calculate_ranking_score_legacy()` and `classify_topic()` (feeds). So we do 2x work and persist the legacy path only. |
| **Double-counting feed metrics** | `feeds.py` ~1456 + 1496–1521 | On successful fetch (non-304): (1) `update_feed_health_metrics(fid, True, …)` increments `fetch_count` and `success_count`; (2) the following `UPDATE feeds SET fetch_count=fetch_count+1, success_count=success_count+1 ...` increments them again. Every successful fetch is counted twice. |

### 1.3 Confirmed improvements (safe to do)

| Improvement | Location | Action |
|-------------|----------|--------|
| **Robots.txt** | `feeds.py` | `is_robot_allowed()` and `is_article_url_allowed()` both call `_check_robots_txt_path()` with different `user_agent` (* vs newsbrief). Unify behind a single helper e.g. `_check_url_allowed(url, user_agent="*")` and have both call it. |
| **IN-clause boilerplate** | `stories.py` | Same placeholder-building pattern appears multiple times. Extract e.g. `_build_in_clause_params(ids, prefix="id")` → `(placeholders_str, params_dict)`. |
| **main.py size** | `app/main.py` | ✅ Done: Split into FastAPI routers (health, feeds, stories, items, admin, config, pages); main is app factory only. |

---

## 2. Single Phased Plan

Phases are ordered by risk and dependency: cleanup first, then bug fixes, then structural changes.

### Phase 1: Safe cleanup (low risk)

- [x] **Remove dead `get_available_topics()` from `ranking.py`**
  - Only `app.topics.get_available_topics` is used. Delete the function (and any topic list only used by it) from `ranking.py`. Run tests after.
- [x] **Rename `classify_topic()` in `feeds.py` → `classify_article_for_feed()`**
  - Clarifies that it’s the feed-ingestion wrapper (category hints). Update all call sites in `feeds.py` (fetch_and_store, recalculate_rankings_and_topics).
- [x] **Unify robots.txt entry point**
  - Add `_check_url_allowed(url, user_agent="*")` (or similar) that parses domain, gets robots.txt, and calls `_check_robots_txt_path`. Have `is_robot_allowed` and `is_article_url_allowed` call it with the appropriate user_agent.
- [x] **Extract `_build_in_clause_params(ids, prefix="id")` in `stories.py`**
  - Return `(placeholders_str, params_dict)` and replace the repeated placeholder-building blocks. Keeps behavior identical; only reduces duplication.

**Exit criteria**: All tests pass; no behavior change beyond naming and structure.

---

### Phase 2: Bug fixes (medium risk, high value)

- [x] **Fix double-counting of feed metrics**
  - `update_feed_health_metrics(fid, True, response_time_ms)` already sets: `fetch_count`, `success_count`, `consecutive_failures`, `avg_response_time_ms`, `last_response_time_ms`, `health_score`, `last_fetch_at`, and on success `last_success_at`, `last_error=NULL`.
  - The following block (lines ~1476–1521) does another UPDATE that **again** increments `fetch_count` and `success_count` and sets the same timing fields → double count.
  - **Fix**: In that second block, update **only** cache headers and timestamp: `etag`, `last_modified`, `updated_at`. Remove `fetch_count+1`, `success_count+1`, `last_success_at`, `consecutive_failures=0`, `last_response_time_ms`, `avg_response_time_ms`, and `last_fetch_at` from that UPDATE (they are already set by `update_feed_health_metrics`).
  - Verify that after a refresh, `fetch_count` and `success_count` increase by 1 per successful fetch.
- [x] **Fix wasted ranking/topic computation in `fetch_and_store()`**
  - Remove the unused `classify_article_topic()` and `calculate_ranking_score()` calls (and any variables only used for them).
  - Use the **ranking module** results for the INSERT: use `ranking_result.score` and `topic_result.topic` / `topic_result.confidence` (and any other fields the INSERT expects) instead of `_calculate_ranking_score_legacy` and `classify_topic()`.
  - If the ranking module’s return shape doesn’t match the INSERT exactly, adapt the mapping once (e.g. small helper or inline mapping).
  - After this, consider deprecating or removing `_calculate_ranking_score_legacy` if it’s no longer used elsewhere (e.g. `recalculate_rankings_and_topics` still uses it — see below).

**Note**: `recalculate_rankings_and_topics()` still uses `_calculate_ranking_score_legacy` and `classify_article_for_feed()`. You can either (a) leave it as-is for now and only fix the fetch path, or (b) switch it to the ranking module in the same phase. Prefer (a) if you want a smaller change set; (b) if you want to remove the legacy path entirely.

**Exit criteria**: Tests pass; feed health metrics increment correctly; new articles get topic/ranking from the ranking module in fetch_and_store.

#### Phase 2 implementation details (for implementer)

**Task 1 — Double-counting (feeds.py)**

- **Where**: Success path only (after `update_feed_health_metrics(fid, True, response_time_ms)` at ~1459). The 304 path calls `update_feed_health_metrics` then `continue`, so it never hits the second UPDATE.
- **Current second block** (~1480–1524): A `with session_scope()` that (1) SELECTs `success_count`, `avg_response_time_ms` to compute a rolling average, (2) UPDATEs feeds with etag, last_modified, updated_at, last_fetch_at, fetch_count+1, success_count+1, last_success_at, consecutive_failures, last_response_time_ms, avg_response_time_ms.
- **Fix**:
  1. Remove the SELECT and the `new_avg` / `prev_success_count` / `prev_avg` logic (only used for the UPDATE).
  2. Replace the UPDATE with one that sets only: `etag=:e`, `last_modified=:lm`, `updated_at=CURRENT_TIMESTAMP`, `WHERE id=:id`. Params: `{"e": new_etag, "lm": new_last_mod, "id": fid}`.
- **Why**: `update_feed_health_metrics` already uses an exponential moving average (0.8×current + 0.2×new) for `avg_response_time_ms` and increments counts. The second block was both double-counting and overwriting that average with a different formula.

**Task 2 — Ranking/topic in fetch_and_store (feeds.py)**

- **Where**: ~1630–1697. `classify_article_topic()` and `calculate_ranking_score()` are already called (~1631–1645); their results are unused. The INSERT block (~1647–1697) calls `_calculate_ranking_score_legacy(article_data, source_weight=1.0)` and `classify_article_for_feed(article_data, feed_category=feed_category)` and uses those for `ranking_score`, `topic`, `topic_confidence`.
- **Ranking module types** (app/ranking.py): `TopicResult` has `topic: Optional[str]`, `confidence: float`. `RankingResult` has `score: float`. INSERT expects `ranking_score`, `topic`, `topic_confidence`.
- **Fix**:
  1. Keep the existing `topic_result` and `ranking_result` calls (same args). Do not add feed_category to the ranking module call; the INSERT currently uses the feed wrapper for topic. For consistency with the plan (use ranking module for INSERT), use `topic_result.topic` and `topic_result.confidence` for the INSERT. Option: if product wants feed-aware topic at ingest, we could pass feed_category into a single classification path later; for this task, use ranking module only.
  2. In the INSERT block, remove the `article_data` dict construction only used for legacy (or keep it if still needed for other fields), remove the calls to `_calculate_ranking_score_legacy` and `classify_article_for_feed` for this INSERT.
  3. Use for the INSERT: `ranking_score=ranking_result.score`, `topic=topic_result.topic`, `topic_confidence=topic_result.confidence`. Handle None: DB may expect NULL for topic; confidence 0.0 is fine.
- **Feed category**: Currently the INSERT uses `classify_article_for_feed(..., feed_category=feed_category)`, which applies feed-based topic hints. The ranking module’s `classify_article_topic()` has no feed_category parameter. For this task, use ranking module output only (no feed hint at ingest). If product later wants feed-aware topic at ingest, either extend the ranking module to accept optional feed_category or call a thin wrapper; out of scope for Phase 2.
- **Leave unchanged**: `recalculate_rankings_and_topics()` (~1971–1974) continues to use `_calculate_ranking_score_legacy` and `classify_article_for_feed` (option (a)). No change to legacy function or to `classify_article_for_feed` in this task.
- **Order**: Do Task 1 first (fewer files, clear scope), then Task 2.

---

### Phase 3: Structural (higher effort)

- [x] **Split `main.py` into FastAPI routers**
  - As in CODE_REVIEW_RECOMMENDATIONS: e.g. `routers/health.py`, `routers/feeds.py`, `routers/stories.py`, `routers/items.py`, `routers/admin.py`.
  - `main.py` becomes app factory: logging, mount routers, startup/shutdown (scheduler, migrations, credibility import).
  - **`app/deps.py`**: Shared dependencies (session_scope, get_llm_service, templates, get_version, get_client_ip) so routers do not depend on main.
  - **HTML pages** in `routers/pages.py` (Option A).
  - **Incremental** steps: deps → health → feeds → stories → items → admin → config → pages.
  - **Split**: `admin.py` = admin HTML + credibility, quality, extraction, api/llm/stats; `config.py` (or `api_config.py`) = topics (HTML + API), api/models, ranking/recalculate, scheduler/status.
- [x] **Optional: consolidate synthesis/context helpers in `stories.py`** ✅ Done (Feb 2026)
  - Implemented: `_prepare_articles_for_synthesis()`, pipeline takes `prepared_articles`, `_fallback_synthesis(Sequence[ArticleForSynthesis])`. See **§ Optional cleanup: stories.py synthesis helpers** below for the original outline.

**Exit criteria**: All routes respond as before; tests and manual smoke checks pass.

**Documentation updates (Feb 2026):** After Phase 3 and the optional synthesis cleanup, the following docs were updated to match the codebase: **CODE_IMPROVEMENT_PLAN.md** (this file: current state table, next step, §1.3); **CODE_REVIEW_RECOMMENDATIONS.md** (summary, §2.1 marked implemented, checklist, §1.1 location); **README.md** (project structure: main.py, routers/, deps.py); **ARCHITECTURE.md** (API layer diagram: main.py + app/routers/); **DEVELOPMENT.md** (add-route instructions: use app/routers/).

---

### Optional cleanup: stories.py synthesis helpers (outline; implemented Feb 2026)

**Goal:** Reduce duplication and fix the cache/raw inconsistency so fallback and pipeline share one article representation.

**1. Unify “fetch + normalize” into a single path**

- **Where:** `_enhanced_synthesis_pipeline` (lines ~1995–2051) and `_generate_story_synthesis` (lines ~2258–2281) both:
  - Branch on `articles_cache`: if present, use cache; else run a `SELECT` (with slightly different columns: pipeline has `ranking_score, published`, synthesis fetch does not).
  - Convert “raw” data to a usable form: pipeline builds `ArticleForSynthesis` from either cache dicts (`.get(...)`) or DB tuples (indexed `article[0]`, `article[1]`, …); synthesis only holds raw list for cache/DB.
- **Option A – Single “prepare articles” helper:** Add one function (e.g. `_prepare_articles_for_synthesis(session, article_ids, articles_cache=None)`) that:
  - Fetches from DB when cache is missing (use the richer query: id, title, summary, ai_summary, topic, ranking_score, published).
  - Normalizes to a single in-memory shape (e.g. list of dicts with fixed keys, or list of `ArticleForSynthesis`) whether data came from cache or DB.
  - Returns that list (and optionally the same list as “raw” for code that still expects tuples/dicts, or migrate callers to the normalized form).
- **Option B – Normalize at use site:** Keep two fetch sites but introduce a small `_raw_article_to_article_for_synthesis(article: Union[tuple, dict])` and call it in one place so conversion from cache vs tuple is in one function.
- **Recommendation:** Option A so both the pipeline and `_generate_story_synthesis` call the same fetcher and get the same type; then pipeline and fallback can assume one representation.

**2. Shared fallback that accepts the unified representation**

- **Where:** `_fallback_synthesis(articles)` (lines ~2474–2528) today assumes `articles` is a list of **tuples** and uses `article[1]` (title), `article[4]` (topic). When `_generate_story_synthesis` uses `articles_cache`, `articles` is a list of **dicts**; on exception it calls `_fallback_synthesis(articles)` and would break (tuple indices on dicts).
- **Fix:** Change `_fallback_synthesis` to accept the **same** normalized type as the rest of the pipeline (e.g. list of `ArticleForSynthesis` or list of dicts with known keys). Then:
  - After introducing the “prepare articles” helper, pass its result (or a subset) into `_fallback_synthesis`.
  - Inside `_fallback_synthesis`, read title/topic (and any other needed fields) via that type only (e.g. `article.title`, `article.topic` or `article["title"]`, `article["topic"]`).
- **Result:** One representation from fetch through pipeline and into fallback; no cache vs raw branches in multiple places; fallback safe when cache was used.

**3. Optional: single SELECT and reuse**

- Pipeline and `_generate_story_synthesis` currently use two different SELECTs (pipeline: + ranking_score, published; synthesis: 5 columns). If both call `_prepare_articles_for_synthesis`, that helper can run one SELECT (the richer one) and return normalized articles; callers that don’t need ranking/published can ignore those fields. Reduces duplication and keeps one source of truth for “articles for synthesis.”

**4. Scope and order**

- **Scope:** `app/stories.py` only (synthesis pipeline, fallback, and any new helper).
- **Order:** (1) Add normalized type and `_prepare_articles_for_synthesis` (or Option B normalizer); (2) Switch `_enhanced_synthesis_pipeline` and `_generate_story_synthesis` to use it; (3) Change `_fallback_synthesis` to take the normalized type and use it; (4) Optionally unify the SELECT in the new helper.
- **Exit criteria:** All synthesis paths (cache and DB) produce the same behavior; exception path in `_generate_story_synthesis` always calls `_fallback_synthesis` with the same type (no tuple-only assumption); tests and manual story generation (with and without cache) pass.

---

## 3. Alignment with CODE_REVIEW_RECOMMENDATIONS.md

| Recommendation | Where it’s covered in this plan |
|-----------------|---------------------------------|
| Parameterized story list count query | Already done (see CODE_REVIEW_RECOMMENDATIONS). |
| Topic allowlist for list_stories | Optional; can add when doing Phase 1 or later. |
| Split main.py into routers | Phase 3. |
| Type `session_scope()` as `Iterator[Session]` | Can do in Phase 1 or 2 as a small change. |
| Pydantic v2 `field_validator` in models.py | Separate from this plan; track in CODE_REVIEW_RECOMMENDATIONS or a dedicated “Pydantic cleanup” task. |
| Mypy/lint in main.py | Same; good to run in CI and fix in batches. |
| Remove duplicate get_available_topics | Phase 1 (ranking.py). |
| Consolidate _get_default_config() | Not recommended; see 1.1. |

---

## 4. How to Use This Plan

1. **Track progress**: Check off items in Phase 1, then 2, then 3. Optionally mirror each item as a GitHub issue and link from here.
2. **Issue #272**: If that issue describes “code quality / refactor / cleanup”, you can set its description to point to this doc and use sub-tasks or labels for Phase 1 / 2 / 3.
3. **Before Phase 2**: Run the test suite and, if possible, verify current feed metrics (e.g. fetch_count for a known feed) so you can confirm the double-count fix.
4. **Order**: Do Phase 1 first (quick wins, no behavior change). Then Phase 2 (fix real bugs). Phase 3 when you’re ready for a larger refactor.

---

## 5. Quick reference

- **Security**: Story list count query is fixed (parameterized). See CODE_REVIEW_RECOMMENDATIONS.
- **Bugs**: (1) Double feed metric updates on success. (2) Ranking/topic computed twice in fetch_and_store and legacy result used.
- **Dead code**: `ranking.get_available_topics()`.
- **Naming**: `feeds.classify_topic` → `classify_article_for_feed`.
- **No change**: The three `_get_default_config()` functions are intentionally different; do not consolidate.

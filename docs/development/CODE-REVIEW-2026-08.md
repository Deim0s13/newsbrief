# Code Health Audit — August 2026 (v0.8.9)

**Status**: Audit complete, findings-only. No code was deleted or refactored as part of this
pass — see the individual GitHub issues linked below for follow-up execution work.

**Scope**: `app/` (27,526 LOC / 62 files), `tests/` (14,481 LOC / 46 files), `scripts/`,
`requirements*.txt`. Docs were spot-checked but no new issues found (the tekton-removal doc
pass earlier in v0.8.7 already cleaned up stale references; remaining "tekton" mentions are
correctly-labelled historical ADRs).

**Method**: automated scans with [vulture](https://github.com/jendrikseipp/vulture) (dead
code), [radon](https://radon.readthedocs.io/) (cyclomatic complexity + maintainability index),
and [deptry](https://deptry.com/) (dependency usage), each cross-checked by hand against actual
call sites (`grep`/`Grep`) to filter framework false positives (FastAPI routes, Pydantic
validators/fields, SQLAlchemy columns, APScheduler jobs). Every finding below was manually
verified to have zero callers outside its own definition and (where noted) tests, before being
listed.

These three tools are now in `requirements-dev.txt` for future ad-hoc use; they are **not**
wired into CI or pre-commit yet — that's a separate decision once we see how useful they are on
a second pass.

---

## 1. Safe removals (confirmed dead, no functional risk)

All items below have **zero references** anywhere in `app/`, `scripts/`, or `tests/` outside
their own definition (or are only reachable from other dead code in this same list).

| Item | Location | Notes |
|---|---|---|
| Unused import `create_cache_key` | [app/llm.py:16-20](../../app/llm.py) | Defined in `models.py`, never called from `llm.py` |
| Unused import `StoryGenerationResponse` | [app/routers/stories.py:15-21](../../app/routers/stories.py) | `generate_stories_endpoint` returns a plain dict, not this model |
| Unused parameter `resolved_feed_id` | [app/feeds.py:1226](../../app/feeds.py) `update_failed_import_status()` | Accepted but never read in the function body |
| Unreachable code block | [app/llm_output.py:275-279](../../app/llm_output.py) `validate_edge_case` validator | A numeric-coercion branch (`if isinstance(v, (int, float))...`) sits after an unconditional `return None` — copy-paste residue from a nearby `coerce_confidence` validator, can never execute |
| `update_feed_names()` | [app/feeds.py:2077](../../app/feeds.py) | Zero references anywhere, including tests |
| `cleanup_old_import_history()` | [app/feeds.py:1243](../../app/feeds.py) | Zero references anywhere, including tests |
| `LLMService.batch_summarize()` | [app/llm.py:1088](../../app/llm.py) | Zero references anywhere, including tests |
| `parse_with_retry()` | [app/llm_output.py:1300](../../app/llm_output.py) | Zero references anywhere, including tests |
| **Dead legacy ranking/topic chain** (see below) | [app/feeds.py:1754-2076](../../app/feeds.py) | ~320 lines, confirmed superseded |
| Unused dependency `python-slugify` | [requirements.txt](../../requirements.txt) | `slugify` not imported anywhere in the repo |
| Unused dependency `aiofiles` | [requirements.txt](../../requirements.txt) | `aiofiles` not imported anywhere in the repo |

### The dead legacy ranking/topic chain

`recalculate_rankings_and_topics()` ([app/feeds.py:1944](../../app/feeds.py)) is imported into
`main.py` but never called. Its only two callees, `_calculate_ranking_score_legacy()`
(line 1754, radon complexity **C/20**) and `classify_article_for_feed()` (line 1889), have no
other callers either — the whole chain is dead.

This isn't a new discovery: `docs/archive/planning/CODE_IMPROVEMENT_PLAN.md` from an earlier
cleanup effort explicitly notes *"`recalculate_rankings_and_topics()` still uses
`_calculate_ranking_score_legacy`... leave it as-is for now"* — the migration to the newer
`app/ranking.py` module + `app/routers/config.py::_recalculate_rankings()` (the function
actually wired to `POST /ranking/recalculate`) happened, but the old path was never deleted
afterwards.

---

## 2. Consolidation candidates (need a design decision, not a blind removal)

### 2a. Story CRUD API is fully tested but never called by the production pipeline

> **Resolved (#346):** split decision. `cleanup_archived_stories()` was wired into
> `retention.py::run_retention()` (option (a) below, low-risk — it fixed a real unbounded-growth
> bug where archived stories were reported as "eligible for purge" but never actually deleted).
> `create_story`, `link_articles_to_story`, `update_story`, `archive_story`, `delete_story` were
> removed (option (b) — no production callers, and the live pipeline's `generate_stories_simple()`
> had grown ~15 fields beyond what this layer's frozen signatures ever supported). Their test
> coverage was preserved by moving equivalent test-setup fixtures into `tests/pg_testutil.py`.

`app/stories.py` defines a complete CRUD layer — `create_story`, `link_articles_to_story`,
`update_story`, `archive_story`, `delete_story`, `cleanup_archived_stories` (lines 268-1050) —
with substantial dedicated test coverage across `tests/test_story_crud.py`,
`tests/test_incremental_updates.py`, and `tests/test_pipeline_e2e.py`.

**None of these functions are called from `generate_stories_simple()`** (the function the real
`/stories/generate` endpoint and scheduled job actually use), nor from `app/retention.py` (which
does its own raw `UPDATE`/`DELETE` SQL for archived-story cleanup instead of calling
`cleanup_archived_stories()`). This is a fully parallel, test-covered implementation that the
live pipeline doesn't use.

Two ways to resolve, both legitimate — needs a maintainer call:
- **(a)** Wire `generate_stories_simple()` / `retention.py` to use this CRUD layer, removing the
  duplicated raw-SQL logic scattered through those functions, or
- **(b)** If this layer was an earlier design that got superseded, remove it along with its
  ~700 lines of dedicated tests.

### 2b. `/refresh` and `/stories/generate` bypass `PipelineStageRun` tracking (ADR-0029)

`POST /refresh` ([app/routers/feeds.py:624](../../app/routers/feeds.py)) calls
`fetch_and_store()` directly; `POST /stories/generate`
([app/routers/stories.py:67](../../app/routers/stories.py)) calls `generate_stories_simple()`
directly. Both bypass the `PipelineStageRun`-tracked path in `app/pipeline_runner.py` that the
scheduled jobs and the `/admin/pipeline` API use — meaning manual triggers of these two
endpoints leave no audit trail, no dead-letter/retry support, and (as found this morning) no
visibility into partial completion.

This is the direct root cause behind [#344](https://github.com/Deim0s13/newsbrief/issues/344)
(feed refresh silently skipping feeds with no fairness across calls) and is related to
[#327](https://github.com/Deim0s13/newsbrief/issues/327) (blocking-call timeout UX). Routing
both endpoints through `pipeline_runner.py` would fix the audit-trail gap and give both issues a
shared foundation to build on.

---

## 3. Complexity / size hotspots (ranked by radon, not raw line count)

Line count alone is a weak signal — e.g. `app/models.py` is long but simple (mostly Pydantic
field declarations). Radon's maintainability index (MI) and per-function cyclomatic complexity
give a much better signal of where bugs are likely to hide and where changes are slow/risky.

**Worst maintainability index in `app/`:**

| File | MI grade | Notes |
|---|---|---|
| [app/feeds.py](../../app/feeds.py) | **C (0.00)** | Worst in the codebase, tied |
| [app/stories.py](../../app/stories.py) | **C (0.00)** | Worst in the codebase, tied |
| [app/llm_output.py](../../app/llm_output.py) | B (10.69) | |
| [app/pipeline_runner.py](../../app/pipeline_runner.py) | B (14.40) | |
| [app/routers/items.py](../../app/routers/items.py) | B (16.84) | |

**Highest-complexity individual functions** (radon cyclomatic complexity, rank D and worse):

| Function | File:line | Rank (score) |
|---|---|---|
| `generate_stories_simple` | [app/stories.py:2846](../../app/stories.py) | **F (50)** — most complex function in the app |
| `fetch_and_store` | [app/feeds.py:1374](../../app/feeds.py) | **F (49)** |
| `import_opml_content` | [app/feeds.py:597](../../app/feeds.py) | F (44) |
| `get_stories` | [app/stories.py:487](../../app/stories.py) | E (31) |
| `_calculate_clustering_metadata` | [app/stories.py:1359](../../app/stories.py) | D (30) |
| `_prepare_articles_for_synthesis` | [app/stories.py:2216](../../app/stories.py) | D (28) |
| `ensure_feed` | [app/feeds.py:356](../../app/feeds.py) | D (27) |
| `generate_summaries` | [app/routers/items.py:228](../../app/routers/items.py) | D (25) |
| `extract_entities` | [app/entities.py:385](../../app/entities.py) | D (23) |
| `get_scheduler_status` | [app/scheduler.py:741](../../app/scheduler.py) | D (22) |
| `extract_partial` | [app/llm_output.py:948](../../app/llm_output.py) | D (22) |
| `get_story_by_id` | [app/stories.py:387](../../app/stories.py) | D (21) |
| `classify_topic_with_keywords` | [app/topics.py:750](../../app/topics.py) | D (21) |
| `_calculate_ranking_score_legacy` | [app/feeds.py:1754](../../app/feeds.py) | C (20) — dead, see §1 |

**Recommendation**: `generate_stories_simple` (F/50) and `fetch_and_store` (F/49) are the two
highest-value split candidates — they're also the exact two functions implicated in this
morning's feed-refresh investigation and the earlier singleton-clustering fix. Breaking each
into named sub-steps would make the next bug in either much faster to isolate.

> **Resolved, `fetch_and_store` half (#347):** extract-method only, no behavior change. Split
> into 8 named helpers (`_fetch_feed_response`, `_store_feed_cache_headers`,
> `_lookup_existing_item`, `_extract_article_content`, `_classify_and_score_item`,
> `_upsert_item_row`, `_process_feed_entries`, `_finalize_refresh_stats`), one extraction per
> commit with the full non-Ollama test suite green after each. `fetch_and_store` itself dropped
> from **F (49)** to **B (8)**; the remaining per-entry orchestrator, `_process_feed_entries`, is
> **D (24)** — a big drop from the original monolith, though still the most complex piece since
> it coordinates the global/per-feed/time-limit early exits plus all 6 other helpers. All other
> new helpers are A/B rank.
>
> **Resolved, `generate_stories_simple` half (#347):** extract-method only, no behavior change.
> Split into 8 named helpers/promoted closures (`_fetch_window_articles`,
> `_group_articles_by_topic`, `_cluster_topic_group`, `_build_cluster_data`, `_synthesize_cluster`,
> `_persist_synthesized_story`, `_run_parallel_synthesis_and_persist`, `_build_generation_result`),
> one extraction per commit with the full non-Ollama test suite green after each, plus live
> synthesis smoke tests (fresh-cluster, dedup-skip, and overlap-update paths) after every step
> touching the threaded synthesis/persistence code to confirm identical clustering, scores, and
> outcomes vs. baseline. `generate_stories_simple` itself dropped from **F (50)** to **B (7)**; the
> two most complex new helpers, `_cluster_topic_group` and `_build_cluster_data`, are **C (16)**
> each — still the busiest pieces (per-topic keyword/entity clustering, and per-cluster
> scoring/metadata respectively) but a large drop from the original monolith. All other new
> helpers are A/B/C rank, with `_run_parallel_synthesis_and_persist` at **B (9)**. #347 is now
> fully resolved.

---

## 4. Docs / script bloat

No stale documentation was found — the tekton-removal doc pass done earlier in v0.8.7 already
cleaned this up, and remaining "tekton" mentions are correctly-labelled `Superseded` ADR
history, not live guidance.

One minor observation: `scripts/embedding_benchmark.py`, `scripts/model_fitness.py`, and
`scripts/rag_evaluation.py` started as one-off decision-point scripts but have since become
de-facto recurring tools (each tied to an ADR re-evaluation trigger or planned future milestone
work). None currently has a short header comment explaining when/why to rerun it. Worth a small
docstring addition next time one of them is touched — not worth a dedicated issue on its own.

---

## Issues filed from this audit

- [#345](https://github.com/Deim0s13/newsbrief/issues/345) — Safe removals (dead code + 2 unused dependencies)
- [#346](https://github.com/Deim0s13/newsbrief/issues/346) — Story CRUD API duplication (needs design decision)
- [#347](https://github.com/Deim0s13/newsbrief/issues/347) — Complexity hotspots (`generate_stories_simple` / `fetch_and_store`)
- [#348](https://github.com/Deim0s13/newsbrief/issues/348) — Legacy endpoints bypass pipeline tracking (ADR-0029)

All four are in the `v0.8.9 - Code Health & Tech Debt` milestone.

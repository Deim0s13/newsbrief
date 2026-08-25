# Code Health Audit — August 2026 (v0.8.9)

**Status**: Audit complete, findings-only. No code was deleted or refactored as part of this
pass — see the individual GitHub issues linked below for follow-up execution work.

**Scope (initial pass)**: `app/` (27,526 LOC / 62 files), `tests/` (14,481 LOC / 46 files),
`scripts/`, `requirements*.txt`. Docs were spot-checked but no new issues found (the
tekton-removal doc pass earlier in v0.8.7 already cleaned up stale references; remaining "tekton"
mentions are correctly-labelled historical ADRs).

**Scope (second pass, same audit period)**: infrastructure-as-code (`k8s/`, `ansible/`,
`.github/workflows/`, all Compose files, `Makefile`) and test-suite health as its own subject
(structure/duplication/correctness, not just "does app code have dead callers in tests") — see
§5 and §6. This closes a gap in the first pass, whose scope line above never actually covered
infra, and only used `tests/` to check for dead app-code callers rather than reviewing the test
suite itself.

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

## 5. Infrastructure health audit

**Scope**: `k8s/` (23 manifests, base + dev/prod overlays + `argocd/`), `ansible/` (5 roles, 2
playbooks), `.github/workflows/` (4 files), all 4 Compose files, the 704-line `Makefile`,
`scripts/` (26 files, `archive/` excluded as already-quarantined).

**Method**: manual read + cross-reference (`grep`/`Grep`/`diff`) of every file against its
consumers — Makefile targets, CI steps, launchd/Task Scheduler installers, and the docs that
describe each recovery/deploy path (`CLAUDE.md`, `docs/development/KUBERNETES.md`, ADRs). No
infra-specific static-analysis tool (e.g. `kube-linter`, `actionlint`, `checkov`) was run this
pass — only `ansible-lint` is currently installed locally; none are wired in yet. Worth adding for
a future pass if this area gets touched again.

### 5a. `make recover` is broken and diverges from the documented macOS recovery path

> This is the standout finding of the infra pass — a documented "break glass" recovery
> procedure that doesn't actually work, discoverable only during a real outage.

`ansible/roles/kind/tasks/main.yml` calls `scripts/setup-kind-registry.sh` to (re)create the kind
cluster's local registry. That script was archived months ago during the redundant-infra cleanup
and only exists at `scripts/archive/setup-kind-registry.sh` now — a fresh `make recover` on a
machine with no kind cluster fails at the Kind role.

Separately, `ansible/playbooks/recover.yml` starts the DB with
`podman-compose -f compose.yaml up -d db` (no `compose.prod.yaml` overlay), while
`scripts/infra-start.sh` — the actually-documented and actually-used macOS path — uses
`-f compose.yaml -f compose.prod.yaml`. A `make recover` run could bring up the DB with the wrong
secrets/config even if the kind step were fixed.

The Ansible `argocd` role also applies a narrower file set (`kubectl apply -f` on individual
files, skipping `argocd-cm.yaml`) than `infra-start.sh`'s `kubectl apply -f k8s/argocd/`
(whole-directory apply, which also happens to pick up the dormant `appset.yaml` — see 5d).

| Finding | Location | Notes |
|---|---|---|
| Kind role calls an archived script | [ansible/roles/kind/tasks/main.yml](../../ansible/roles/kind/tasks/main.yml) | Target `scripts/setup-kind-registry.sh` doesn't exist; only `scripts/archive/setup-kind-registry.sh` does |
| Recover's kind-registry sub-flow is entirely stale | same file, registry check/remove block | Registry was removed per ADR-0032 (GHCR instead); `infra-start.sh` never touches a registry |
| DB compose flags diverge | [ansible/playbooks/recover.yml](../../ansible/playbooks/recover.yml) vs [scripts/infra-start.sh](../../scripts/infra-start.sh) | `recover.yml` omits `-f compose.prod.yaml`; `infra-start.sh` includes it |
| ArgoCD apply scope diverges | [ansible/roles/argocd/tasks/main.yml](../../ansible/roles/argocd/tasks/main.yml) vs `infra-start.sh` | Role applies a named subset; script applies the whole `k8s/argocd/` directory |
| `force_recreate` var is dead | [ansible/playbooks/recover.yml](../../ansible/playbooks/recover.yml), documented in `ansible/README.md` | Defined/documented but never read by any role/task |

### 5b. Stale Tekton/kind-registry references across ADRs, `ARCHITECTURE.md`, and release docs

Same class of issue as the tekton-removal doc pass in v0.8.7 — that pass cleaned up the obvious
stuff, but several docs still read as if Tekton/the kind registry were live infrastructure:

| Finding | Location | Notes |
|---|---|---|
| ADR index lists Superseded ADRs as Accepted | [docs/ARCHITECTURE.md](../../docs/ARCHITECTURE.md) ADR table | ADR-0019 and ADR-0020 both have `Superseded` headers in their own files, but the index still shows `Accepted` |
| ADR bodies still describe Tekton as current | `docs/adr/0015-*.md`, `0017-*.md`, `0018-*.md`, `0021-*.md` | Only 0016/0019/0020 carry `Superseded` headers; these four don't, despite Tekton-centric context/examples |
| ADR-0007 same pattern | [docs/adr/0007-*.md](../../docs/adr/) | Marked `Superseded` in the file itself; `docs/ARCHITECTURE.md` still lists it `Accepted`. ADR-0022 has an open checklist item to fix this that was never actioned |
| Release history still advertises removed features | [docs/releases/README.md](../../docs/releases/README.md) | Still lists kind-registry and Tekton Dashboard/Triggers as shipped |
| Stale comments in live manifests | [k8s/overlays/dev/deployment-patch.yaml](../../k8s/overlays/dev/deployment-patch.yaml), [k8s/overlays/prod/deployment-patch.yaml](../../k8s/overlays/prod/deployment-patch.yaml), [k8s/kind/cluster-config.yaml](../../k8s/kind/cluster-config.yaml) | Comments reference the archived `push-kind-dev-image.sh` script and "mutable tags on Kind local registry"/"local registry" setup that no longer exists — functionally harmless (kustomize rewrites the image), but misleading to read |

### 5c. CI workflow duplication + dead workflow files

| Finding | Location | Notes |
|---|---|---|
| ~80 duplicated lines | [.github/workflows/ci-dev.yml](../../.github/workflows/ci-dev.yml) vs [ci-prod.yml](../../.github/workflows/ci-prod.yml) | `lint`/`test` jobs are near-identical (same Python/black/pgvector-service/pytest config); no reusable workflow extracted |
| Disabled workflow left in tree | [.github/workflows/project-automation.yml](../../.github/workflows/project-automation.yml) | Triggers commented out, `workflow_dispatch` only, header literally says "DISABLED" |
| `.disabled`-suffixed workflow file | [.github/workflows/dependencies.yml.disabled](../../.github/workflows/dependencies.yml.disabled) | Stale action version pins (v4/v5) vs the active workflows' v6 |
| `mypy` step is always non-blocking | both `ci-dev.yml` and `ci-prod.yml` | `continue-on-error: true` on every mypy step — intentional (matches the pre-existing mypy debt noted throughout this doc) but worth a comment saying so |
| Inconsistent SHA tag format | `ci-dev.yml` (`sha-<7-char>`) vs `ci-prod.yml` (`sha-<full 40-char>`) | Cosmetic; `scripts/k8s-version-check.sh` compares by suffix so it still works, but the two formats are easy to confuse when reading tags by eye |

### 5d. Orphaned/duplicate infra files

| Finding | Location | Notes |
|---|---|---|
| Dormant ApplicationSet | [k8s/argocd/appset.yaml](../../k8s/argocd/appset.yaml) | Commented out of `k8s/argocd/kustomization.yaml`; individual `app-dev.yaml`/`app-prod.yaml` used instead, but still gets applied if anyone runs `kubectl apply -f k8s/argocd/` directly (as `infra-start.sh` does — see 5a) |
| Duplicate cosign public key | [k8s/secrets/cosign.pub](../../k8s/secrets/cosign.pub) | Byte-identical to the repo-root `cosign.pub`; zero references to `k8s/secrets/` anywhere — CI signs against the root copy |
| Orphaned CLI wrapper | [scripts/import_mbfc.py](../../scripts/import_mbfc.py) | No references from Makefile/CI/docs; the app itself calls `app.credibility_import.import_mbfc_sources` directly from the scheduler/admin routes |

### 5e. Windows autostart path is ambiguous

Two different Windows Task Scheduler installers exist for two different purposes, and it's easy
to run the wrong one:

| Finding | Location | Notes |
|---|---|---|
| kind/ArgoCD-based installer | [scripts/infra-task-install.ps1](../../scripts/infra-task-install.ps1) + [scripts/infra-start.ps1](../../scripts/infra-start.ps1) | Only referenced from a `Makefile` hint string; not mentioned in `CLAUDE.md`'s Windows CD section |
| Compose-based installer (the documented canonical path) | [scripts/compose-task-install.ps1](../../scripts/compose-task-install.ps1) | This is what `CLAUDE.md`/ADR-0032 actually document as Windows prod CD |
| Legacy full-stack launchd installer (macOS) | [scripts/com.newsbrief.plist.template](../../scripts/com.newsbrief.plist.template), `make autostart-install` | Starts the **full** `compose.yaml` stack (api + caddy + db) on login — exactly the "duplicate standalone Compose app" pattern #325's writeup warned against on macOS, where K8s is the real prod. Not mentioned in `CLAUDE.md`/`KUBERNETES.md` at all |

### 5f. Needs a decision (lower urgency, grouped)

| Finding | Location | Notes |
|---|---|---|
| Prod DB password literal in Git | [k8s/overlays/prod/kustomization.yaml](../../k8s/overlays/prod/kustomization.yaml) `configMapGenerator` | Hardcoded alongside the dev overlay's copy; works because both point at the same shared Compose DB host, but a literal credential living in a versioned manifest is worth a second look |
| `replicas: 2` + PodDisruptionBudget on a single-node kind cluster | [k8s/overlays/prod/deployment-patch.yaml](../../k8s/overlays/prod/deployment-patch.yaml), [k8s/overlays/prod/pdb.yaml](../../k8s/overlays/prod/pdb.yaml) | HA semantics on a cluster that only has one node to schedule onto |
| Hardcoded `darwin` device type in the base configmap | [k8s/base/configmap.yaml](../../k8s/base/configmap.yaml) | Comment already flags "revisit if deployed elsewhere"; both overlays currently inherit the macOS assumption |
| Two Compose CLI entrypoints | `podman-compose` (macOS Makefile targets) vs `podman compose` (Windows `.ps1` scripts) | Deliberate per an existing comment in `infra-start.sh` (Podman secrets need the macOS variant) — just a two-tool-to-maintain fact worth having written down somewhere central |
| Harness scripts not promoted to `make` targets | [scripts/model_fitness.py](../../scripts/model_fitness.py), [scripts/embedding_benchmark.py](../../scripts/embedding_benchmark.py), [scripts/rag_evaluation.py](../../scripts/rag_evaluation.py) | Referenced from ADRs/docs as recurring re-evaluation tools, but have no `make` target — every run currently requires remembering the right `python3 scripts/...` invocation from memory or docs |

---

## 6. Test suite health audit

**Scope**: all 44 `test_*.py` files (~107 test functions), `tests/conftest.py` (70 lines),
`tests/pg_testutil.py` (135 lines). This is a review of the test suite's *own* health
(structure/duplication/correctness) — distinct from §1-3 above, which only used `tests/` to check
whether app-code findings had test callers.

**Method**: `grep`/`Grep` across all test files for shared patterns (explicit-ID inserts, helper
duplication, skip/xfail markers, marker usage), cross-referenced against `pyproject.toml`'s
pytest config and both CI workflows' test-invocation flags.

### 6a. Test DB sequence desync — confirmed root cause

> The standout finding of the test-suite pass. This is the exact failure mode we hit manually
> multiple times this session (`IntegrityError: duplicate key value violates unique constraint
> "items_pkey"`) while running smoke tests against the shared dev DB during the `#347` work —
> not a fluke, a structural gap with a concrete fix available.

`tests/pg_testutil.py`'s `pg_session_truncate_story_graph()` and
`pg_session_truncate_retrieval_traces()` both run `TRUNCATE ... RESTART IDENTITY CASCADE`, which
resets the `items`/`stories`/`feeds` serial sequences to 1. Roughly a dozen integration test files
then insert rows with **explicit** hardcoded primary keys (`id=1`, `id=999`, feed `id=1`, etc.)
after that truncate. Explicit-value inserts don't advance a Postgres serial sequence — so the
sequence stays parked at 1 (or wherever it last was) while low-numbered rows now exist in the
table. Any *subsequent* code that inserts via `DEFAULT`/omits the `id` column (a normal ORM
insert, or a manual script like the ones used for live smoke-testing) collides with those
existing low IDs.

Only two files correctly guard against this — `tests/test_entities.py` and
`tests/test_fetch_and_store_idempotency_integration.py`, both of which call `setval()` on the
relevant sequence after seeding. No other file does, and `pg_testutil.py`'s shared truncate
helpers don't do it centrally either, so every consumer has to remember to do it themselves (and
almost none do).

**Files inserting explicit/hardcoded feed `id=1`** (without a subsequent `setval`):
`test_pipeline_e2e.py`, `test_story_crud.py`, `test_incremental_updates.py`, `test_retention.py`,
`test_story_generation.py`, `test_story_generation_with_llm.py`, plus the RAG-integration cluster
(`test_retrieval.py`, `test_context_retrieval.py`, `test_light_rag.py`, `test_semantic_dedup.py`,
`test_retrieval_tracing.py`) via a duplicated `_seed_feed()` helper.

**Files inserting explicit/hardcoded item or story IDs** (same risk, same files as above plus
`test_historical_linking.py`).

**Fix path** (not implemented in this pass): add a `resync_sequences(session, tables=(...))`
helper to `tests/pg_testutil.py` and call it from `pg_session_truncate_story_graph()` /
`pg_session_truncate_retrieval_traces()` right after seeding, so every consumer gets the guard for
free instead of opting in per-file.

### 6b. Duplicated test setup helpers

| Helper | Duplicated in | Notes |
|---|---|---|
| `setup_test_db()` | 7 files (`test_story_crud.py`, `test_incremental_updates.py`, `test_retention.py`, `test_entities.py`, `test_story_generation.py`, `test_story_generation_with_llm.py`, `test_synthesis_cache.py`) | Near-identical bodies; candidate for a shared `pg_testutil.py` helper |
| `_seed_feed()` | 5 files (`test_retrieval.py`, `test_context_retrieval.py`, `test_light_rag.py`, `test_semantic_dedup.py`, `test_retrieval_tracing.py`) | Identical SQL in each — the RAG-integration test cluster shows the strongest copy-paste pattern in the suite |
| `_vec()` (test embedding vector builder) | 6 files (same RAG cluster + `test_historical_linking.py`) | Identical implementation copy-pasted rather than shared |

None of `pg_testutil.py`'s existing 5 exported helpers are unused — all are imported by at least
one test file.

### 6c. Dead/stale tests and config drift

| Finding | Location | Notes |
|---|---|---|
| No stale skip/xfail decorators | grep across `tests/` | Zero matches for `@pytest.mark.skip`/`xfail` — the runtime `pytest.skip()` calls that do exist are all conditional (no `DATABASE_URL`, DB unreachable, LLM unavailable), not stale decorators |
| Script-shaped test files | `test_story_generation.py`, `test_story_generation_with_llm.py`, `test_incremental_updates.py`, `test_synthesis_cache.py`, `test_credibility.py`, `test_credibility_import.py`, `test_models.py` | Each has an `if __name__ == "__main__":` block; `test_story_generation.py` additionally defines a `main()` that calls the pytest test function directly — a second, overlapping entry point |
| Coverage threshold doc drift | [pyproject.toml](../../pyproject.toml) (`fail_under = 34`, commented "lowered to current level") vs [docs/ARCHITECTURE.md](../../docs/ARCHITECTURE.md) (claims "41% met") | The threshold itself is a documented, intentional floor — not an accident — but the architecture doc's claimed number no longer matches it |
| `requires_ollama` marker name is slightly misleading | [tests/test_story_generation.py](../../tests/test_story_generation.py), [tests/test_story_generation_with_llm.py](../../tests/test_story_generation_with_llm.py) | Only 4 tests total carry this marker (correctly excluded in both CI workflows via `-m "not requires_ollama"`), but the tests themselves are backend-aware (Ollama or oMLX) since the #337/#339 fixes — the marker name predates that and now undersells what it's gating |

### 6d. Manual "test-like" scripts outside `tests/`

`scripts/model_fitness.py`, `scripts/embedding_benchmark.py`, and `scripts/rag_evaluation.py` are
intentionally-permanent evaluation harnesses (each tied to an ADR re-evaluation trigger), not
stray test files — no action needed here beyond the `make`-target promotion noted in §5f.
`scripts/seed_dev_feeds.py` wipes and reseeds feeds/items/stories, which is a destructive
operation on the same shared dev DB the integration tests also truncate — worth keeping in mind if
`#TBD` (§6a's fix) lands, since a manual seed run interleaved with a test run could still race.

---

## Issues filed from this audit

**App-code pass (§1-4):**

- [#345](https://github.com/Deim0s13/newsbrief/issues/345) — Safe removals (dead code + 2 unused dependencies)
- [#346](https://github.com/Deim0s13/newsbrief/issues/346) — Story CRUD API duplication (needs design decision)
- [#347](https://github.com/Deim0s13/newsbrief/issues/347) — Complexity hotspots (`generate_stories_simple` / `fetch_and_store`)
- [#348](https://github.com/Deim0s13/newsbrief/issues/348) — Legacy endpoints bypass pipeline tracking (ADR-0029)

**Infrastructure pass (§5):**

- [#352](https://github.com/Deim0s13/newsbrief/issues/352) — `make recover` is broken + diverges from `infra-start.sh`'s DB startup
- [#353](https://github.com/Deim0s13/newsbrief/issues/353) — Stale Tekton/kind-registry references across ADRs, `ARCHITECTURE.md`, and release docs
- [#354](https://github.com/Deim0s13/newsbrief/issues/354) — CI workflow duplication + 2 dead workflow files
- [#355](https://github.com/Deim0s13/newsbrief/issues/355) — Orphaned/duplicate infra files (`appset.yaml`, duplicate `cosign.pub`, `import_mbfc.py`)
- [#356](https://github.com/Deim0s13/newsbrief/issues/356) — Windows autostart path is ambiguous (2 different Task Scheduler installers)
- [#357](https://github.com/Deim0s13/newsbrief/issues/357) — Grab-bag: infra items needing a decision (prod DB password literal, prod HA on single-node kind, hardcoded `darwin` device type, harness scripts not `make` targets)

**Test-suite pass (§6):**

- [#358](https://github.com/Deim0s13/newsbrief/issues/358) — Test DB sequence desync — add `resync_sequences()` helper to `pg_testutil.py`
- [#359](https://github.com/Deim0s13/newsbrief/issues/359) — Consolidate duplicated test setup helpers (`setup_test_db` x7, `_seed_feed` x5, `_vec` x6)
- [#360](https://github.com/Deim0s13/newsbrief/issues/360) — Coverage-threshold doc drift + misc test hygiene

All thirteen are in the `v0.8.9 - Code Health & Tech Debt` milestone.

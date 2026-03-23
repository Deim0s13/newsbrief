# ADR 0030: Article and story processing states (canonical model)

## Status

Accepted

## Date

February 2026

## Context

[ADR-0029](0029-pipeline-oriented-orchestration.md) records the decision to adopt **pipeline-oriented orchestration** and an **explicit article/story state model**. It does not define the canonical state names, transition rules, or how they relate to existing database fields.

This ADR is the **specification** for that state model. It **does not restate** the strategic rationale, consequences, or non-goals of ADR-0029—read that ADR for “why pipeline orchestration.”

**Implementation tracking:** [GitHub #273](https://github.com/Deim0s13/newsbrief/issues/273).

## Decision

1. **Canonical processing states** for articles (`items`) and stories (`stories`)—including enums, allowed transitions, failure handling, and mapping to existing **`Story.status`** (`active` / `archived` for reader-facing lifecycle)—are **defined and maintained in this ADR** (sections below and future amendments), not in ADR-0029.

2. **[ADR-0029](0029-pipeline-oriented-orchestration.md)** remains the parent decision for orchestration, runner, retries, and observability; this ADR is **subordinate** and only covers the **processing state machine** specification.

3. **[ARCHITECTURE.md](../ARCHITECTURE.md)** may summarise or link here; the **normative** detail for states and transitions lives in **this ADR** to avoid drift between two full specifications.

4. **Storage and migration (agreed):**
   - **Separate columns** for pipeline position: `processing_state` on **`items`** and **`stories`** (exact SQL names may follow project naming conventions; semantics are as defined in this ADR).
   - **`stories.status`** remains **`active` / `archived`** for reader-facing lifecycle only; it is **not** overloaded with pipeline states.
   - **Backfill:** **Heuristic** defaults for existing rows at migration time (e.g. infer terminal pipeline states from current data; document assumptions). Nullable processing state is **not** the default approach.

## Scope

### In scope

- Article-level **processing** state (pipeline position; includes `failed` where applicable).
- Story-level **processing** state (pipeline position; includes `failed` where applicable).
- Relationship between processing state and **`stories.status`** (visibility lifecycle).
- Rules for invalid transitions (reject vs log-and-continue) at the specification level.

### Out of scope

- Pipeline runner design (see ADR-0029 and issue #274).
- Retry/backoff/dead-letter behaviour (ADR-0029; issue #275).
- Stage-aware metrics and dashboards (issues #276, #291).

## Specification

### Implementation reference (Phase 1)

Canonical string values and transition helpers live in **`app/processing_states.py`** (`ArticleProcessingState`, `StoryProcessingState`, `article_transition_allowed`, `story_transition_allowed`, `log_invalid_*`, `coerce_*`). **Normative enum values** match the tables below.

### Article processing states (`items.processing_state`)

| Value | Meaning |
|-------|--------|
| `discovered` | Known to the system before full ingest (optional; future use). |
| `fetched` | Row created from feed; raw metadata available. |
| `extracted` | Clean content extracted (tiered extraction path). |
| `enriched` | Summaries, topics, ranking, entities, etc. |
| `embedded` | Vector embedding stored (future RAG path; backfill may set when embeddings exist). |
| `clustered` | Assigned to at least one story cluster / generation batch. |
| `failed` | Terminal pipeline failure (retry may move back to `fetched`, `extracted`, or `enriched` per code). |

**Main path order:** `discovered` → `fetched` → `extracted` → `enriched` → `embedded` → `clustered`.

**Transition rules (summary):**

- Forward moves along the main path are allowed, **including skipping intermediate states** (e.g. combined ingest may jump `fetched` → `enriched`).
- Same-state updates are allowed (idempotent).
- Transition to `failed` is allowed from any state.
- From `failed`, only **retry** targets are allowed: `fetched`, `extracted`, `enriched` (see `app/processing_states.py`).
- Backward transitions (e.g. `enriched` → `fetched`) are **invalid**; callers should **log** (see `log_invalid_article_transition`) and may still write in recovery paths until enforcement is tightened.

### Story processing states (`stories.processing_state`)

| Value | Meaning |
|-------|--------|
| `candidate` | Cluster exists; not yet synthesized or incomplete. |
| `synthesizing` | LLM synthesis in progress or last run. |
| `context_enriched` | Post-synthesis context stage completed (future path). |
| `quality_checked` | Quality gate passed (future path). |
| `published` | Synthesis complete; story is eligible for default views (subject to `status`). |
| `archived` | Pipeline-level archived (aligned with reader archive / age rules). |
| `failed` | Terminal failure in synthesis or downstream stage. |

**Main path order:** `candidate` → `synthesizing` → `context_enriched` → `quality_checked` → `published` → `archived`.

**Transition rules (summary):**

- Forward moves on the main path are allowed, **including skipping** `context_enriched` / `quality_checked` until those stages exist (e.g. `synthesizing` → `published`).
- `published` → `archived` and `archived` → `archived` are allowed.
- `candidate` → `archived` is **invalid** (must go through `published` or use `failed` semantics as appropriate).
- Transition to `failed` is allowed from any state.
- From `failed`, retry targets: `candidate`, `synthesizing`.
- Invalid transitions: **log** via `log_invalid_story_transition`.

### `stories.status` vs `stories.processing_state`

| `status` | Typical `processing_state` | Notes |
|----------|----------------------------|--------|
| `active` | `published` (or earlier non-terminal while work runs) | Reader sees active stories; processing may still be mid-flight in future runner. |
| `archived` | `archived` | Scheduler “archive old stories” sets **`status`**; **`processing_state`** should be **`archived`** for backfill and when the pipeline archives. |

**Rules:**

- **`status`** controls default list filters for end users (`active` / `archived`).
- **`processing_state`** controls pipeline/ops views and “where in the flow” the row is.
- Do **not** encode pipeline position in `status`.

### Failure and error detail (Phase 2+)

- **Query by failure:** filter `processing_state = 'failed'` on `items` / `stories`.
- Optional later columns (not required for Phase 1 enums): e.g. nullable **`processing_error`** text on `items` / `stories`, or reuse existing fields where appropriate (`extraction_error` on items for extract failures). Tracked under #273 follow-up.

### Heuristic backfill (migration)

Applied once when adding `processing_state` columns. **Order matters** (first match wins).

**`stories`:**

1. If `status = 'archived'` → set `processing_state = 'archived'`.
2. Else if synthesis is present (non-empty `synthesis` or `article_count > 0` as appropriate) → `published`.
3. Else → `candidate`.

**`items`:**

1. If the item appears in **`story_articles`** → `clustered`.
2. Else if `entities_json` is non-null → `enriched`.
3. Else if `extracted_at` is non-null or extraction metadata indicates a completed extract → `extracted`.
4. Else if `content` or `summary` is present → `fetched`.
5. Else → `fetched`.

Adjustments during migration implementation are allowed if SQL requires tweaks; document any deviation in the migration file.

### Agreed implementation choices (recap)

| Topic | Decision |
|-------|----------|
| **Pipeline vs reader lifecycle** | **Separate `processing_state`** on `items` and `stories`; **`stories.status`** stays `active` / `archived` only. |
| **Backfill** | **Heuristic** defaults at migration; rules above. |

## Resolved implementation choices (reference)

### A. Separate `processing_state` vs reusing `Story.status`

**Chosen:** **Separate `processing_state`** on `items` and `stories`; **`stories.status`** unchanged for `active` / `archived`.

| Approach | Upside | Downside |
|----------|--------|----------|
| **New column(s)** (chosen) | Clear separation: pipeline position vs reader visibility; existing API semantics for `status` preserved. | Extra column(s), migration, and code paths to keep in sync. |
| **Overload `stories.status`** (rejected) | Fewer columns. | Collides with today’s meaning; breaks filters and semantics. |

### B. Backfill for existing rows

**Chosen:** **Heuristic** defaults at migration time; assumptions documented alongside the migration.

| Approach | Upside | Downside |
|----------|--------|----------|
| **Heuristic defaults** (chosen) | Fast rollout; non-null processing state for operational queries. | Imprecise for edge historical rows; must document rules. |
| **Nullable** (rejected as default) | Honest about unknowns. | More `NULL` handling everywhere. |

### C. Branching

**Chosen in practice:** Milestone work on branch **`milestone/v0.8.3`** (local/remote as used by the team). Feature work can still use smaller branches from it as needed.

## References

- Parent decision: [ADR-0029: Pipeline-oriented orchestration](0029-pipeline-oriented-orchestration.md)
- [ARCHITECTURE.md](../ARCHITECTURE.md) §7.5 Story Processing Pipeline (pipeline stages; high level)
- Issues: [#273](https://github.com/Deim0s13/newsbrief/issues/273) (state model), [#292](https://github.com/Deim0s13/newsbrief/issues/292) (tracker)

# ADR 0031: Pipeline idempotency and article re-ingest (content-hash upsert)

## Status

Accepted

## Date

April 2026

## Context

Feed refresh and downstream pipeline stages can run more than once (scheduler overlap, manual refresh, retries). Without a clear idempotency story, we risk duplicate rows, wasted work, or ambiguous “same URL, new text” behaviour.

The codebase already uses stable keys in several places, but **issue text and early designs sometimes assumed different keys than production** (for example URL + `published`, or URL scoped by `feed_id`). Documentation and tests were thin relative to the behaviour users and operators rely on.

This ADR records **canonical keys as implemented**, intentional tradeoffs, and a **phased plan**: a short documentation-and-test phase, then **bounded re-ingest with UPDATE only when `content_hash` changes**.

## Decision

### Canonical idempotency keys (articles and feed ingest)

| Concern | Key / rule | Notes |
|--------|------------|--------|
| **Article row identity** | `url_hash = SHA-256(normalized URL string)` | Stored on `items.url_hash` with a **global UNIQUE** constraint — **not** `(url, feed_id)`. The first ingest that wins for a URL owns the row; the same URL appearing in another feed still hits the unique key and does not create a second row (see tradeoffs). |
| **Content fingerprint** | `content_hash = create_content_hash(title, body_for_hash)` where `body_for_hash` is extracted `content` when present, else sanitized RSS `summary` | Used for cache keys, duplicate detection of “same body”, and **re-ingest upsert**: persist a full row update only when the new hash differs from the stored hash after a **gated** re-fetch. |
| **Feed entry times** | `items.published` is set from the entry’s first available of `published_parsed`, then `updated_parsed` (feedparser struct_time → UTC) | Matches historical behaviour; ranking and display use this single instant. **Re-ingest signalling** uses **`updated_parsed` only** when deciding if the feed claims a revision after what we stored (see below). |

### Stories and synthesis (unchanged summary)

| Concern | Key / rule | Notes |
|--------|------------|--------|
| **Story duplicate detection** | Stable hash over the **sorted list of article IDs** in the cluster (`story_hash`) | Regeneration / new synthesis versions are separate from “another row for the same cluster” (see ADR-0004 and story generation code paths). |
| **Synthesis caching** | `content_hash` + model (and related cache columns) | Updating an article’s body should invalidate or version downstream LLM artefacts; exact invalidation mechanics stay aligned with ADR-0003 and processing states (ADR-0030). |

### Phased scope

**Phase 1 (short):** Align documentation (this ADR, GitHub [#235](https://github.com/Deim0s13/newsbrief/issues/235)), cross-links from pipeline ADRs, and add **baseline tests** that lock current idempotency expectations: pure helpers in `tests/test_feeds_idempotency.py`, and **integration tests** in `tests/test_fetch_and_store_idempotency_integration.py` (mocked HTTP + optional PostgreSQL — skips when `DATABASE_URL` is unset or the server is unreachable).

**Phase 2 (ingest upsert):** In `fetch_and_store`, **do not** run full HTML fetch/extract for every existing URL on every poll. Re-run the expensive path only when:

1. **Retry body extraction:** stored `items.content` is null or whitespace-only (best-effort retry after failures or blocks), or
2. **Feed indicates revision:** `updated_parsed` is present and **strictly after** the stored `items.published` instant (both timezone-aware UTC).

After the gated re-run, compute a new `content_hash`. If it equals the stored hash, **skip the UPDATE** (log at debug). If it differs, **UPDATE** the ingest-related columns on the existing row (same `url_hash`), preserving columns not owned by ingest (e.g. AI summaries, entity JSON) unless separate ADRs require invalidation.

### Non-goals

- Changing the global uniqueness of `url_hash` to per-feed composite keys (would be a migration and product decision).
- Re-fetching every existing item on every feed poll.
- Full agentic orchestration (see ADR-0029).

## Consequences

### Positive

- Operators get **documented** behaviour for duplicates and URL collisions across feeds.
- **Bounded cost**: re-ingest work scales with **likely changes**, not with catalogue size each poll.
- **Clear logging** path: skip (unchanged hash), update (hash changed), skip (no re-ingest gate).

### Negative / tradeoffs

- **Same URL in two feeds** still maps to one row; the second feed does not get a distinct article record. This must stay visible in runbooks and support.
- Feeds without `updated_parsed` do not signal revisions via RSS alone; body retry still uses the null-content gate.

## References

- GitHub: [#235 — Implement idempotency for pipeline operations](https://github.com/Deim0s13/newsbrief/issues/235)
- Pipeline orchestration: [ADR-0029](0029-pipeline-oriented-orchestration.md), [#292](https://github.com/Deim0s13/newsbrief/issues/292)
- Processing states: [ADR-0030](0030-article-story-processing-states.md)
- Incremental story updates: [ADR-0004](0004-incremental-story-updates.md)
- Synthesis caching: [ADR-0003](0003-synthesis-caching.md)
